from datetime import datetime

from fastapi import APIRouter, File, Form, Header, UploadFile, status

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
from app.services.rag_service import rag_service

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
async def list_knowledge_bases() -> list[KnowledgeBaseRead]:
    return []


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    owner_id: int = Header(default=1, alias="X-User-Id"),
) -> KnowledgeBaseRead:
    return KnowledgeBaseRead(
        id=1,
        owner_id=owner_id,
        name=payload.name,
        description=payload.description,
        visibility=payload.visibility,
    )


@router.patch("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    owner_id: int = Header(default=1, alias="X-User-Id"),
) -> KnowledgeBaseRead:
    return KnowledgeBaseRead(
        id=knowledge_base_id,
        owner_id=owner_id,
        name=payload.name or "reference knowledge base",
        description=payload.description,
        visibility=payload.visibility or "private",
    )


@router.delete("/knowledge-bases/{knowledge_base_id}", response_model=ActionResponse)
async def delete_knowledge_base(knowledge_base_id: int) -> ActionResponse:
    return ActionResponse(status="accepted", message=f"Knowledge base {knowledge_base_id} will be deleted.")


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(
    knowledge_base_id: int | None = None,
    parse_status: str | None = None,
) -> list[DocumentRead]:
    return []


@router.post(
    "/documents/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    knowledge_base_id: int = Form(...),
    file: UploadFile = File(...),
    owner_id: int = Header(default=1, alias="X-User-Id"),
) -> DocumentRead:
    return DocumentRead(
        id=1,
        knowledge_base_id=knowledge_base_id,
        owner_id=owner_id,
        file_name=file.filename or "unknown",
        file_type=(file.filename or "unknown").split(".")[-1].lower(),
        file_size=getattr(file, "size", 0) or 0,
        parse_status="pending",
        chunk_count=0,
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: int) -> DocumentRead:
    return DocumentRead(
        id=document_id,
        knowledge_base_id=1,
        owner_id=1,
        file_name="reference.pdf",
        file_type="pdf",
        parse_status="completed",
        chunk_count=0,
    )


@router.delete("/documents/{document_id}", response_model=ActionResponse)
async def delete_document(document_id: int) -> ActionResponse:
    return ActionResponse(status="accepted", message=f"Document {document_id} and vectors will be deleted.")


@router.post("/documents/{document_id}/reindex", response_model=ActionResponse)
async def reindex_document(document_id: int) -> ActionResponse:
    return ActionResponse(status="processing", message=f"Document {document_id} entered the ingest pipeline.")


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunkRead])
async def list_document_chunks(document_id: int) -> list[DocumentChunkRead]:
    return []


@router.get("/documents/{document_id}/chunks/{chunk_id}", response_model=DocumentChunkRead)
async def get_document_chunk(document_id: int, chunk_id: int) -> DocumentChunkRead:
    return DocumentChunkRead(
        id=chunk_id,
        document_id=document_id,
        knowledge_base_id=1,
        chunk_index=0,
        chunk_text="Reference chunk text for document-position citation preview.",
        vector_id=f"chunk-{chunk_id}",
    )


@router.get("/chunks/{chunk_id}", response_model=DocumentChunkRead)
async def get_chunk(chunk_id: int) -> DocumentChunkRead:
    return DocumentChunkRead(
        id=chunk_id,
        document_id=1,
        knowledge_base_id=1,
        chunk_index=0,
        chunk_text="Reference chunk text for citation jump preview.",
        vector_id=f"chunk-{chunk_id}",
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents(payload: SearchRequest) -> SearchResponse:
    return SearchResponse(
        knowledge_base_id=payload.knowledge_base_id,
        query=payload.query,
        rewritten_query=payload.query if payload.enable_rewrite else None,
        results=[],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await rag_service.answer_question(request)


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
