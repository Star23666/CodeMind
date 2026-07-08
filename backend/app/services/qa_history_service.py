from itertools import count

from app.schemas.contracts import ChatRequest, SourceReference


class QaHistoryService:
    def __init__(self) -> None:
        self._ids = count(1001)
        self._records: dict[int, dict] = {}

    async def save_qa_record(
        self,
        *,
        user_id: int,
        request: ChatRequest,
        rewritten_question: str | None,
        answer: str,
        sources: list[SourceReference],
    ) -> int:
        qa_record_id = next(self._ids)
        self._records[qa_record_id] = {
            "id": qa_record_id,
            "user_id": user_id,
            "knowledge_base_id": request.knowledge_base_id,
            "question": request.question,
            "rewritten_question": rewritten_question,
            "answer": answer,
            "sources": sources,
            "source_count": len(sources),
        }
        return qa_record_id


qa_history_service = QaHistoryService()

