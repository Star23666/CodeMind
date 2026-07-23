import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.schemas.contracts import (
    ActionResponse,
    AdminDocumentRead,
    AdminFeedbackRead,
    AdminOverviewRead,
    AdminUserRead,
    AdminUserStatusUpdate,
    ChatRequest,
    ChatResponse,
    DocumentChunkRead,
    DocumentMoveRequest,
    DocumentRead,
    FeedbackCreate,
    FeedbackRead,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    LlmConfigCreate,
    LlmConfigOverview,
    LlmConfigRead,
    LlmConfigTestResult,
    LlmConfigUpdate,
    LoginRequest,
    MindMapGenerateRequest,
    MindMapExpandRequest,
    MindMapNode,
    MindMapHistoryCreate,
    MindMapHistoryRead,
    MindMapHistoryUpdate,
    MindMapJobRead,
    MindMapQuestionRequest,
    MindMapQuestionResponse,
    MindMapResponse,
    QaRecordBatchDeleteRequest,
    QaRecordRead,
    SearchRequest,
    SearchResponse,
    TokenResponse,
    UserCreate,
    UserRead,
)
from app.schemas.quiz import (
    QuizCreateRequest,
    QuizSessionRead,
    QuizSubmissionResult,
    QuizSubmitRequest,
)
from app.services.auth_service import (
    AuthenticationError,
    DisabledUserError,
    RegistrationConflictError,
    auth_service,
)
from app.services.admin_service import AdminOperationError, admin_service
from app.services.document_job_service import document_job_service
from app.services.document_service import (
    DocumentBusyError,
    DocumentMoveConsistencyError,
    DocumentMoveError,
    DocumentNotProcessingError,
    DocumentPermissionError,
    document_service,
)
from app.services.feedback_service import FeedbackConflictError, feedback_service
from app.services.health_service import health_service
from app.services.knowledge_base_service import (
    KnowledgeBasePermissionError,
    knowledge_base_service,
)
from app.services.llm_client import LlmServiceError
from app.services.llm_config_service import (
    LlmConfigError,
    LlmConfigRateLimitError,
    llm_config_service,
)
from app.services.mind_map_service import MindMapGenerationError, mind_map_service
from app.services.mind_map_job_service import MindMapJobStateError, mind_map_job_service
from app.services.mind_map_history_service import (
    MindMapHistoryValidationError,
    mind_map_history_service,
)
from app.services.qa_history_service import qa_history_service
from app.services.quiz_job_service import quiz_job_service
from app.services.quiz_service import QuizServiceError, quiz_service
from app.services.rag_service import rag_service
from app.services.retrieval_service import RetrievalServiceError, retrieval_service

router = APIRouter()


def _sse_event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _readiness_response():
    report = health_service.check_readiness()
    if report["status"] != "ok":
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=report)
    return report


@router.get("/health/live")
def liveness_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", response_model=None)
def readiness_check():
    return _readiness_response()


@router.get("/health", response_model=None)
def health_check():
    return _readiness_response()


@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    try:
        return auth_service.register(db, payload)
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = auth_service.authenticate(db, payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except DisabledUserError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return TokenResponse(
        access_token=auth_service.create_access_token(
            user,
            token_version=auth_service.get_token_version(db, user.id),
        )
    )


@router.post("/auth/logout", response_model=ActionResponse)
async def logout(
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    auth_service.revoke_tokens(db, current_user.id)
    return ActionResponse(status="ok", message=f"用户 {current_user.username} 已退出登录。")


@router.get("/auth/me", response_model=UserRead)
async def current_user(current_user: UserRead = Depends(get_current_user)) -> UserRead:
    return current_user


@router.get("/me/llm-configs", response_model=LlmConfigOverview)
async def list_my_llm_configs(
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmConfigOverview:
    return llm_config_service.list_overview(db, user_id=current_user.id)


@router.post(
    "/me/llm-configs",
    response_model=LlmConfigRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_llm_config(
    payload: LlmConfigCreate,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmConfigRead:
    try:
        return llm_config_service.create(db, user_id=current_user.id, payload=payload)
    except LlmConfigError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="模型配置名称已存在。") from exc


@router.put("/me/llm-configs/{config_id}", response_model=LlmConfigRead)
async def update_my_llm_config(
    config_id: int,
    payload: LlmConfigUpdate,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmConfigRead:
    try:
        return llm_config_service.update(
            db,
            user_id=current_user.id,
            config_id=config_id,
            payload=payload,
        )
    except LlmConfigError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="模型配置名称已存在。") from exc


@router.delete("/me/llm-configs/{config_id}", response_model=ActionResponse)
async def delete_my_llm_config(
    config_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        llm_config_service.delete(
            db,
            user_id=current_user.id,
            config_id=config_id,
        )
    except LlmConfigError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ActionResponse(status="ok", message="模型配置已删除。")


@router.post("/me/llm-configs/{config_id}/test", response_model=LlmConfigTestResult)
async def test_my_llm_config(
    config_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmConfigTestResult:
    try:
        return await llm_config_service.test_config(
            db,
            user_id=current_user.id,
            config_id=config_id,
        )
    except LlmConfigRateLimitError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except LlmConfigError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except LlmServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/me/llm-configs/{config_id}/activate", response_model=LlmConfigOverview)
async def activate_my_llm_config(
    config_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmConfigOverview:
    try:
        return llm_config_service.activate(
            db,
            user_id=current_user.id,
            config_id=config_id,
        )
    except LlmConfigError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/me/llm-configs/use-system-default", response_model=LlmConfigOverview)
async def use_system_default_llm_config(
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmConfigOverview:
    return llm_config_service.use_system_default(db, user_id=current_user.id)


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseRead])
async def list_knowledge_bases(
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeBaseRead]:
    return knowledge_base_service.list_accessible(db, current_user.id)


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeBaseRead:
    try:
        return knowledge_base_service.create(db, current_user.id, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同名知识库已存在。") from exc


@router.patch("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeBaseRead:
    try:
        return knowledge_base_service.update(db, knowledge_base_id, current_user.id, payload)
    except KnowledgeBasePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在。") from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同名知识库已存在。") from exc


@router.delete("/knowledge-bases/{knowledge_base_id}", response_model=ActionResponse)
async def delete_knowledge_base(
    knowledge_base_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        document_service.delete_knowledge_base(
            db,
            knowledge_base_id=knowledge_base_id,
            owner_id=current_user.id,
        )
    except KnowledgeBasePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在。") from exc

    return ActionResponse(status="accepted", message=f"Knowledge base {knowledge_base_id} has been deleted.")


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(
    knowledge_base_id: int | None = None,
    parse_status: str | None = None,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    try:
        return document_service.list_documents(
            db,
            owner_id=current_user.id,
            knowledge_base_id=knowledge_base_id,
            parse_status=parse_status,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在。",
        ) from exc


@router.post(
    "/documents/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    knowledge_base_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    try:
        document = await document_service.save_upload(
            db=db,
            owner_id=current_user.id,
            knowledge_base_id=knowledge_base_id,
            file=file,
        )
    except KnowledgeBasePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在。") from exc

    document_job_service.enqueue(document.id)
    return document


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    try:
        return document_service.get_owned_document(db, document_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc


@router.get("/documents/{document_id}/content", response_class=FileResponse)
async def get_document_content(
    document_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    try:
        file_info = document_service.get_owned_file(
            db,
            document_id=document_id,
            owner_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在或原文件已丢失。") from exc

    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "md": "text/markdown; charset=utf-8",
        "markdown": "text/markdown; charset=utf-8",
        "txt": "text/plain; charset=utf-8",
    }
    return FileResponse(
        path=file_info["path"],
        filename=file_info["file_name"],
        media_type=media_types.get(str(file_info["file_type"]), "application/octet-stream"),
        content_disposition_type="inline",
    )


@router.delete("/documents/{document_id}", response_model=ActionResponse)
async def delete_document(
    document_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        document_service.delete_document(db, document_id=document_id, owner_id=current_user.id)
    except DocumentPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc

    return ActionResponse(status="accepted", message=f"Document {document_id} and vectors have been deleted.")


@router.post("/documents/{document_id}/reindex", response_model=ActionResponse)
async def reindex_document(
    document_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        document_service.queue_reindex(db, document_id=document_id, owner_id=current_user.id)
    except DocumentBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="文档已经在等待处理或正在处理中。",
        ) from exc
    except DocumentPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc

    document_job_service.enqueue(document_id)
    return ActionResponse(status="processing", message=f"Document {document_id} entered the ingest pipeline.")


@router.post("/documents/{document_id}/cancel", response_model=ActionResponse)
async def cancel_document_processing(
    document_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        document_service.cancel_processing(db, document_id=document_id, owner_id=current_user.id)
    except DocumentNotProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="文档当前不在等待处理或处理中。",
        ) from exc
    except DocumentPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc
    return ActionResponse(status="cancelled", message=f"Document {document_id} processing was cancelled.")


@router.patch("/documents/{document_id}/knowledge-base", response_model=DocumentRead)
async def move_document(
    document_id: int,
    payload: DocumentMoveRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    try:
        return document_service.move_document(
            db,
            document_id=document_id,
            target_knowledge_base_id=payload.target_knowledge_base_id,
            owner_id=current_user.id,
        )
    except DocumentMoveError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DocumentMoveConsistencyError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档或目标知识库不存在。") from exc


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunkRead])
async def list_document_chunks(
    document_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentChunkRead]:
    try:
        return document_service.list_chunks(db, document_id=document_id, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在。") from exc


@router.get("/documents/{document_id}/chunks/{chunk_id}", response_model=DocumentChunkRead)
async def get_document_chunk(
    document_id: int,
    chunk_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentChunkRead:
    try:
        return document_service.get_owned_chunk(
            db,
            chunk_id=chunk_id,
            document_id=document_id,
            owner_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="片段不存在。") from exc


@router.get("/chunks/{chunk_id}", response_model=DocumentChunkRead)
async def get_chunk(
    chunk_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentChunkRead:
    try:
        return document_service.get_owned_chunk(db, chunk_id=chunk_id, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="片段不存在。") from exc


@router.post("/mind-maps/generate", response_model=MindMapResponse)
async def generate_mind_map(
    payload: MindMapGenerateRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MindMapResponse:
    try:
        return await mind_map_service.generate(
            db,
            owner_id=current_user.id,
            request=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库或文档不存在。") from exc
    except MindMapGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/mind-maps/jobs", response_model=MindMapJobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_mind_map_job(
    payload: MindMapGenerateRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MindMapJobRead:
    try:
        job = mind_map_job_service.create_job(db, owner_id=current_user.id, request=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库或文档不存在。") from exc
    mind_map_job_service.enqueue(job.job_id)
    return job


@router.get("/mind-maps/jobs/{job_id}", response_model=MindMapJobRead)
async def get_mind_map_job(
    job_id: str,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MindMapJobRead:
    try:
        return mind_map_job_service.get_job(db, job_id=job_id, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="思维导图任务不存在。") from exc


@router.post("/mind-maps/jobs/{job_id}/cancel", response_model=MindMapJobRead)
async def cancel_mind_map_job(
    job_id: str,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MindMapJobRead:
    try:
        return await mind_map_job_service.cancel_job(
            db,
            job_id=job_id,
            owner_id=current_user.id,
        )
    except MindMapJobStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="思维导图任务不存在。") from exc


@router.post("/mind-maps/ask", response_model=MindMapQuestionResponse)
async def ask_mind_map_node(
    payload: MindMapQuestionRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MindMapQuestionResponse:
    try:
        return await mind_map_service.answer_node_question(
            db,
            owner_id=current_user.id,
            request=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点来源不存在或不属于当前用户。") from exc
    except MindMapGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/mind-maps/expand", response_model=MindMapNode)
async def expand_mind_map_node(
    payload: MindMapExpandRequest, current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return await mind_map_service.expand_node(db, owner_id=current_user.id, request=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="节点来源不存在或无权访问。") from exc
    except MindMapGenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/mind-maps/histories", response_model=MindMapHistoryRead, status_code=status.HTTP_201_CREATED)
async def create_mind_map_history(
    payload: MindMapHistoryCreate,
    current_user: UserRead = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        knowledge_base_service.get_readable(db, payload.knowledge_base_id, current_user.id)
        if payload.document_id is not None:
            document = document_service.get_owned_document(db, payload.document_id, current_user.id)
            if document.knowledge_base_id != payload.knowledge_base_id:
                raise ValueError("Document not found")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="知识库或文档不存在。") from exc
    try:
        return mind_map_history_service.create(db, owner_id=current_user.id, payload=payload)
    except MindMapHistoryValidationError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc


@router.get("/mind-maps/histories", response_model=list[MindMapHistoryRead])
async def list_mind_map_histories(
    knowledge_base_id: int | None = None,
    current_user: UserRead = Depends(get_current_user), db: Session = Depends(get_db),
):
    return mind_map_history_service.list(db, owner_id=current_user.id, knowledge_base_id=knowledge_base_id)


@router.get("/mind-maps/histories/{history_id}", response_model=MindMapHistoryRead)
async def get_mind_map_history(
    history_id: int, current_user: UserRead = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return mind_map_history_service.get(db, history_id=history_id, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="思维导图历史记录不存在。") from exc


@router.put("/mind-maps/histories/{history_id}", response_model=MindMapHistoryRead)
async def update_mind_map_history(
    history_id: int, payload: MindMapHistoryUpdate,
    current_user: UserRead = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return mind_map_history_service.update(db, history_id=history_id, owner_id=current_user.id, payload=payload)
    except MindMapHistoryValidationError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="思维导图历史记录不存在。") from exc


@router.delete("/mind-maps/histories/{history_id}", response_model=ActionResponse)
async def delete_mind_map_history(
    history_id: int, current_user: UserRead = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        mind_map_history_service.delete(db, history_id=history_id, owner_id=current_user.id)
        return ActionResponse(status="accepted", message="思维导图历史记录已删除。")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="思维导图历史记录不存在。") from exc


@router.post(
    "/quizzes/sessions",
    response_model=QuizSessionRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_quiz_session(
    payload: QuizCreateRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizSessionRead:
    try:
        session = quiz_service.create_session(
            db,
            owner_id=current_user.id,
            request=payload,
        )
    except QuizServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    quiz_job_service.enqueue(session.session_id)
    return session


@router.get("/quizzes/sessions/{session_id}", response_model=QuizSessionRead)
async def get_quiz_session(
    session_id: str,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizSessionRead:
    try:
        return quiz_service.get_session(
            db,
            session_id=session_id,
            owner_id=current_user.id,
        )
    except QuizServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/quizzes/sessions/{session_id}/submit",
    response_model=QuizSubmissionResult,
)
async def submit_quiz_session(
    session_id: str,
    payload: QuizSubmitRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizSubmissionResult:
    try:
        return quiz_service.submit(
            db,
            session_id=session_id,
            owner_id=current_user.id,
            request=payload,
        )
    except QuizServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.delete("/quizzes/sessions/{session_id}", response_model=ActionResponse)
async def abandon_quiz_session(
    session_id: str,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        quiz_service.abandon(db, session_id=session_id, owner_id=current_user.id)
    except QuizServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ActionResponse(status="accepted", message="临时练习已清理。")


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    payload: SearchRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    try:
        knowledge_base_service.get_readable(db, payload.knowledge_base_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在。") from exc

    try:
        retrieval_result = await retrieval_service.retrieve_for_search(payload, user_id=current_user.id)
    except RetrievalServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SearchResponse(
        knowledge_base_id=payload.knowledge_base_id,
        query=payload.query,
        rewritten_query=retrieval_result.rewritten_question,
        results=retrieval_result.sources,
        message=retrieval_result.empty_message,
    )



@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        knowledge_base_service.get_readable(
            db,
            request.knowledge_base_id,
            current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在。",
        ) from exc

    try:
        return await rag_service.answer_question(
            request,
            user_id=current_user.id,
            db=db,
        )
    except LlmServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc
    except RetrievalServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        knowledge_base_service.get_readable(
            db,
            request.knowledge_base_id,
            current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在。",
        ) from exc

    async def event_stream():
        try:
            async for event in rag_service.stream_answer(
                request,
                user_id=current_user.id,
                db=db,
            ):
                yield _sse_event(
                    str(event["event"]),
                    event["data"],
                )
        except (LlmServiceError, RetrievalServiceError) as exc:
            yield _sse_event(
                "error",
                {"status_code": exc.status_code, "detail": str(exc)},
            )
        except Exception:
            yield _sse_event(
                "error",
                {"status_code": 500, "detail": "流式回答处理失败，请稍后重试。"},
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/qa-records", response_model=list[QaRecordRead])
async def list_qa_records(
    knowledge_base_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=50),
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[QaRecordRead]:
    return qa_history_service.list_qa_records(
        db,
        user_id=current_user.id,
        knowledge_base_id=knowledge_base_id,
        limit=limit,
    )


@router.delete("/qa-records", response_model=ActionResponse)
async def delete_qa_records(
    payload: QaRecordBatchDeleteRequest,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    deleted_count = qa_history_service.delete_qa_records(
        db,
        qa_record_ids=payload.qa_record_ids,
        user_id=current_user.id,
    )
    return ActionResponse(
        status="accepted",
        message=f"已删除 {deleted_count} 条问答记录。",
    )


@router.get("/qa-records/{qa_record_id}", response_model=QaRecordRead)
async def get_qa_record(
    qa_record_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QaRecordRead:
    try:
        return qa_history_service.get_qa_record(
            db,
            qa_record_id=qa_record_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="问答记录不存在。",
        ) from exc


@router.delete("/qa-records/{qa_record_id}", response_model=ActionResponse)
async def delete_qa_record(
    qa_record_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    try:
        qa_history_service.delete_qa_record(
            db,
            qa_record_id=qa_record_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="问答记录不存在。",
        ) from exc
    return ActionResponse(status="accepted", message="问答记录已删除。")


@router.post(
    "/qa-records/{qa_record_id}/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    qa_record_id: int,
    payload: FeedbackCreate,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackRead:
    try:
        return feedback_service.submit(
            db,
            qa_record_id=qa_record_id,
            user_id=current_user.id,
            payload=payload,
        )
    except FeedbackConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问答记录不存在。") from exc


@router.get("/qa-records/{qa_record_id}/feedback", response_model=FeedbackRead | None)
async def get_feedback(
    qa_record_id: int,
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackRead | None:
    try:
        return feedback_service.get_for_record(
            db,
            qa_record_id=qa_record_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问答记录不存在。") from exc


@router.get("/admin/overview", response_model=AdminOverviewRead)
async def admin_overview(
    admin_user: UserRead = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminOverviewRead:
    return admin_service.overview(db)


@router.get("/admin/users", response_model=list[AdminUserRead])
async def list_admin_users(
    query: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None, pattern="^(user|admin)$"),
    user_status: str | None = Query(default=None, alias="status", pattern="^(active|disabled)$"),
    admin_user: UserRead = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminUserRead]:
    return admin_service.list_users(db, query=query, role=role, status=user_status)


@router.patch("/admin/users/{user_id}/status", response_model=AdminUserRead)
async def update_admin_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    admin_user: UserRead = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserRead:
    try:
        return admin_service.update_user_status(
            db,
            target_user_id=user_id,
            status=payload.status,
            admin_user_id=admin_user.id,
        )
    except AdminOperationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。") from exc


@router.get("/admin/documents", response_model=list[AdminDocumentRead])
async def list_admin_documents(
    query: str | None = Query(default=None, max_length=120),
    owner_id: int | None = Query(default=None, ge=1),
    knowledge_base_id: int | None = Query(default=None, ge=1),
    parse_status: str | None = Query(
        default=None,
        pattern="^(pending|processing|completed|failed|cancelled)$",
    ),
    visibility: str | None = Query(default=None, pattern="^(private|public)$"),
    admin_user: UserRead = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminDocumentRead]:
    return admin_service.list_documents(
        db,
        query=query,
        owner_id=owner_id,
        knowledge_base_id=knowledge_base_id,
        parse_status=parse_status,
        visibility=visibility,
    )


@router.get("/admin/feedbacks", response_model=list[AdminFeedbackRead])
async def list_feedbacks(
    rating: int | None = Query(default=None, ge=1, le=5),
    user_id: int | None = Query(default=None, ge=1),
    knowledge_base_id: int | None = Query(default=None, ge=1),
    admin_user: UserRead = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminFeedbackRead]:
    return feedback_service.list_for_admin(
        db,
        rating=rating,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
    )
