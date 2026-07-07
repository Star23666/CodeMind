from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question")
    session_id: int | None = Field(default=None, description="Optional chat session ID")
    top_k: int = Field(default=5, ge=1, le=10, description="Number of retrieved chunks")


class SourceReference(BaseModel):
    document_id: int | None = None
    document_name: str
    chunk_index: int | None = None
    page_number: int | None = None
    content: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceReference] = []

