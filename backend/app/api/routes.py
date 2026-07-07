from fastapi import APIRouter, File, UploadFile

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import rag_service

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/documents")
async def list_documents() -> dict[str, list]:
    return {"items": []}


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)) -> dict[str, str]:
    return {
        "filename": file.filename or "unknown",
        "status": "received",
        "message": "Document parsing and indexing will be implemented next.",
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await rag_service.answer_question(request)

