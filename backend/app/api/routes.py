from fastapi import APIRouter, File, UploadFile, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.contracts import (
    ActionResponse,
    ChatRequest,
    ChatResponse,
    DocumentChunkRead,
    DocumentRead,
    FeedbackCreate,
    FeedbackRead,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    LoginRequest,
    QaRecordRead,
    SearchRequest,
    SearchResponse,
    TokenResponse,
    UserCreate,
    UserRead,
)
from app.services.document_service import document_service
from app.services.knowledge_base_service import knowledge_base_service
from app.services.rag_service import rag_service
from app.api.dependencies import get_current_user
from app.models.user import User
from app.db.session import get_db

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate) -> UserRead:
    return UserRead(id=1, username=payload.username, email=payload.email)


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    return TokenResponse(access_token=f"reference-token-for-{payload.username}")


@router.post("/auth/logout", response_model=ActionResponse)
async def logout() -> ActionResponse:
    return ActionResponse(status="ok", message="Token invalidation is implemented by the auth service.")


@router.get("/auth/me", response_model=UserRead)
async def current_user(user_id: int = Header(default=1, alias="X-User-Id")) -> UserRead:
    return UserRead(id=user_id, username="reference_user", email="user@example.com")


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseRead])
async def list_knowledge_bases(
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> list[KnowledgeBaseRead]:
    return knowledge_base_service.list_for_owner(db, owner_id)


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> KnowledgeBaseRead:
    try:
        return knowledge_base_service.create(db, owner_id, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同名知识库已存在。") from exc


@router.patch("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> KnowledgeBaseRead:
    try:
        return knowledge_base_service.update(db, knowledge_base_id, owner_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在。") from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同名知识库已存在。") from exc


@router.delete("/knowledge-bases/{knowledge_base_id}", response_model=ActionResponse)
async def delete_knowledge_base(
    knowledge_base_id: int,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        document_service.delete_vectors_for_knowledge_base(db, knowledge_base_id=knowledge_base_id, owner_id=owner_id)
        knowledge_base_service.delete(db, knowledge_base_id, owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在。") from exc

    return ActionResponse(status="accepted", message=f"Knowledge base {knowledge_base_id} has been deleted.")


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(
    knowledge_base_id: int | None = None,
    parse_status: str | None = None,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    return document_service.list_documents(
        db,
        owner_id=owner_id,
        knowledge_base_id=knowledge_base_id,
        parse_status=parse_status,
    )


@router.post(
    "/documents/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    knowledge_base_id: int = Form(...),
    file: UploadFile = File(...),
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> DocumentRead:
    try:
        document = await document_service.save_upload(
            db=db,
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            file=file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在。") from exc

    background_tasks.add_task(document_service.process_document, document.id)
    return document


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: int,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> DocumentRead:
    try:
        return document_service.get_owned_document(db, document_id, owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc


@router.delete("/documents/{document_id}", response_model=ActionResponse)
async def delete_document(
    document_id: int,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        document_service.delete_document(db, document_id=document_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc

    return ActionResponse(status="accepted", message=f"Document {document_id} and vectors have been deleted.")


@router.post("/documents/{document_id}/reindex", response_model=ActionResponse)
async def reindex_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        document_service.queue_reindex(db, document_id=document_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc

    background_tasks.add_task(document_service.process_document, document_id)
    return ActionResponse(status="processing", message=f"Document {document_id} entered the ingest pipeline.")


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunkRead])
async def list_document_chunks(
    document_id: int,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> list[DocumentChunkRead]:
    try:
        return document_service.list_chunks(db, document_id=document_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc


@router.get("/documents/{document_id}/chunks/{chunk_id}", response_model=DocumentChunkRead)
async def get_document_chunk(
    document_id: int,
    chunk_id: int,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> DocumentChunkRead:
    try:
        return document_service.get_owned_chunk(db, chunk_id=chunk_id, document_id=document_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="片段不存在。") from exc


@router.get("/chunks/{chunk_id}", response_model=DocumentChunkRead)
async def get_chunk(
    chunk_id: int,
    owner_id: int = Header(default=1, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> DocumentChunkRead:
    try:
        return document_service.get_owned_chunk(db, chunk_id=chunk_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="片段不存在。") from exc


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    payload: SearchRequest,
    user_id: int = Header(default=1, alias="X-User-Id"),
) -> SearchResponse:
    retrieval_result = await retrieval_service.retrieve_for_search(payload, user_id=user_id)
    return SearchResponse(
        knowledge_base_id=payload.knowledge_base_id,
        query=payload.query,
        rewritten_query=retrieval_result.rewritten_question,
        results=retrieval_result.sources,
    )



@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: int = Header(default=1, alias="X-User-Id"),
) -> ChatResponse:
    return await rag_service.answer_question(request, user_id=user_id)


@router.get("/qa-records", response_model=list[QaRecordRead])
async def list_qa_records(knowledge_base_id: int | None = None) -> list[QaRecordRead]:
    return []


@router.get("/qa-records/{qa_record_id}", response_model=QaRecordRead)
async def get_qa_record(qa_record_id: int) -> QaRecordRead:
    return QaRecordRead(
        id=qa_record_id,
        user_id=1,
        knowledge_base_id=1,
        question="Reference question",
        answer="Reference answer generated from retrieved chunks.",
        source_count=0,
        created_at=datetime.utcnow(),
    )


@router.post(
    "/qa-records/{qa_record_id}/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    qa_record_id: int,
    payload: FeedbackCreate,
    user_id: int = Header(default=1, alias="X-User-Id"),
) -> FeedbackRead:
    return FeedbackRead(
        id=1,
        qa_record_id=qa_record_id,
        user_id=user_id,
        rating=payload.rating,
        comment=payload.comment,
        created_at=datetime.utcnow(),
    )


@router.get("/admin/feedbacks", response_model=list[FeedbackRead])
async def list_feedbacks() -> list[FeedbackRead]:
    return []
