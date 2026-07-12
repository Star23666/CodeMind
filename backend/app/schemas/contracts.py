from datetime import datetime
from enum import Enum
import re

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Visibility(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if normalized and not re.fullmatch(r"[\w\u4e00-\u9fff.-]+", normalized):
            raise ValueError("用户名只能包含中文、字母、数字、下划线、点或短横线")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if normalized and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("邮箱格式不正确")
        return normalized


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized.lower() if "@" in normalized else normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.ACTIVE


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE

    @field_validator("visibility")
    @classmethod
    def private_only(cls, value: Visibility) -> Visibility:
        if value != Visibility.PRIVATE:
            raise ValueError("目前仅支持私人知识库")
        return value


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    visibility: Visibility | None = None

    @field_validator("visibility")
    @classmethod
    def private_only(cls, value: Visibility | None) -> Visibility | None:
        if value not in {None, Visibility.PRIVATE}:
            raise ValueError("目前仅支持私人知识库")
        return value


class KnowledgeBaseRead(BaseModel):
    id: int
    owner_id: int
    name: str
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE


class DocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    owner_id: int
    file_name: str
    file_type: str
    file_size: int = 0
    parse_status: ParseStatus = ParseStatus.PENDING
    error_message: str | None = None
    chunk_count: int = 0


class DocumentChunkRead(BaseModel):
    id: int
    document_id: int
    knowledge_base_id: int
    chunk_index: int
    chunk_text: str
    page_no: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    vector_id: str


class MindMapGenerateRequest(BaseModel):
    knowledge_base_id: int = Field(..., ge=1)
    document_id: int | None = Field(default=None, ge=1)
    max_depth: int = Field(default=3, ge=2, le=4)
    max_nodes: int = Field(default=36, ge=8, le=60)


class MindMapSource(BaseModel):
    chunk_id: int
    document_id: int
    file_name: str
    chunk_index: int
    page_no: int | None = None
    source_text: str
    jump_url: str


class MindMapNode(BaseModel):
    id: str
    title: str
    summary: str = ""
    depth: int = 0
    sources: list[MindMapSource] = Field(default_factory=list)
    children: list["MindMapNode"] = Field(default_factory=list)


class MindMapResponse(BaseModel):
    history_id: int | None = None
    knowledge_base_id: int
    document_id: int | None = None
    generation_mode: str
    node_count: int
    message: str
    root: MindMapNode


class MindMapHistoryCreate(BaseModel):
    knowledge_base_id: int = Field(..., ge=1)
    document_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    generation_mode: str = "ai"
    root: MindMapNode
    view_state: dict = Field(default_factory=dict)


class MindMapHistoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    root: MindMapNode | None = None
    view_state: dict = Field(default_factory=dict)


class MindMapHistoryRead(BaseModel):
    id: int
    knowledge_base_id: int
    document_id: int | None = None
    title: str
    node_count: int
    result: MindMapResponse | None = None
    view_state: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MindMapExpandRequest(BaseModel):
    knowledge_base_id: int = Field(..., ge=1)
    node_title: str = Field(..., min_length=1, max_length=100)
    node_summary: str = Field(default="", max_length=500)
    source_chunk_ids: list[int] = Field(..., min_length=1, max_length=8)
    child_count: int = Field(default=4, ge=2, le=8)


class MindMapJobRead(BaseModel):
    job_id: str
    status: str
    stage: str
    progress: int = Field(..., ge=0, le=100)
    message: str
    result: MindMapResponse | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RetrievalOptions(BaseModel):
    top_k: int = Field(default=4, ge=1, le=10)
    score_threshold: float = Field(default=0.77, ge=-1, le=1)
    rerank_top_n: int = Field(default=2, ge=1, le=10)
    enable_rewrite: bool = True
    enable_rerank: bool = True


class SearchRequest(RetrievalOptions):
    knowledge_base_id: int
    query: str = Field(..., min_length=1)


class SourceReference(BaseModel):
    document_id: int
    chunk_id: int
    file_name: str
    chunk_index: int
    page_no: int | None = None
    score: float | None = Field(default=None, ge=-1, le=1)
    source_text: str
    jump_url: str


class MindMapQuestionRequest(BaseModel):
    knowledge_base_id: int = Field(..., ge=1)
    node_title: str = Field(..., min_length=1, max_length=100)
    question: str = Field(..., min_length=1, max_length=500)
    source_chunk_ids: list[int] = Field(..., min_length=1, max_length=8)


class MindMapQuestionResponse(BaseModel):
    knowledge_base_id: int
    node_title: str
    question: str
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)


class HistoricalSourceReference(BaseModel):
    document_id: int | None = None
    chunk_id: int | None = None
    file_name: str
    chunk_index: int
    page_no: int | None = None
    score: float | None = Field(default=None, ge=-1, le=1)
    source_text: str
    jump_url: str | None = None


class SearchResponse(BaseModel):
    knowledge_base_id: int
    query: str
    rewritten_query: str | None = None
    results: list[SourceReference] = Field(default_factory=list)
    message: str | None = None


class ChatRequest(RetrievalOptions):
    knowledge_base_id: int
    question: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    qa_record_id: int | None = None
    knowledge_base_id: int
    question: str
    rewritten_question: str | None = None
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)


class QaRecordRead(BaseModel):
    id: int
    user_id: int
    knowledge_base_id: int
    question: str
    rewritten_question: str | None = None
    answer: str
    source_count: int = 0
    sources: list[HistoricalSourceReference] = Field(default_factory=list)
    created_at: datetime | None = None


class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class FeedbackRead(BaseModel):
    id: int
    qa_record_id: int
    user_id: int
    rating: int
    comment: str | None = None
    created_at: datetime | None = None


class ActionResponse(BaseModel):
    status: str
    message: str
