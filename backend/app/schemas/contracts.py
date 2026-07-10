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


class SearchResponse(BaseModel):
    knowledge_base_id: int
    query: str
    rewritten_query: str | None = None
    results: list[SourceReference] = Field(default_factory=list)


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
    sources: list[SourceReference] = Field(default_factory=list)
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
