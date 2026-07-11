from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.contracts import (
    ChatRequest,
    HistoricalSourceReference,
    QaRecordRead,
    SourceReference,
)


class QaHistoryService:
    async def save_qa_record(
        self,
        *,
        db: Session,
        user_id: int,
        request: ChatRequest,
        rewritten_question: str | None,
        answer: str,
        sources: list[SourceReference],
    ) -> int:
        try:
            result = db.execute(
                text(
                    """
                    INSERT INTO qa_records (
                        user_id, knowledge_base_id, question,
                        rewritten_question, answer, source_count
                    )
                    VALUES (
                        :user_id, :knowledge_base_id, :question,
                        :rewritten_question, :answer, :source_count
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "knowledge_base_id": request.knowledge_base_id,
                    "question": request.question,
                    "rewritten_question": rewritten_question,
                    "answer": answer,
                    "source_count": len(sources),
                },
            )
            qa_record_id = int(result.lastrowid)

            for rank_no, source in enumerate(sources, start=1):
                db.execute(
                    text(
                        """
                        INSERT INTO qa_sources (
                            qa_record_id, document_id, chunk_id,
                            rank_no, score, source_text,
                            file_name, chunk_index, page_no
                        )
                        VALUES (
                            :qa_record_id, :document_id, :chunk_id,
                            :rank_no, :score, :source_text,
                            :file_name, :chunk_index, :page_no
                        )
                        """
                    ),
                    {
                        "qa_record_id": qa_record_id,
                        "document_id": source.document_id,
                        "chunk_id": source.chunk_id,
                        "rank_no": rank_no,
                        "score": source.score,
                        "source_text": source.source_text,
                        "file_name": source.file_name,
                        "chunk_index": source.chunk_index,
                        "page_no": source.page_no,
                    },
                )

            db.commit()
            return qa_record_id
        except Exception:
            db.rollback()
            raise

    def list_qa_records(
        self,
        db: Session,
        *,
        user_id: int,
        knowledge_base_id: int | None = None,
    ) -> list[QaRecordRead]:
        conditions = ["user_id = :user_id"]
        params: dict[str, object] = {"user_id": user_id}

        if knowledge_base_id is not None:
            conditions.append("knowledge_base_id = :knowledge_base_id")
            params["knowledge_base_id"] = knowledge_base_id

        rows = db.execute(
            text(
                f"""
                SELECT id, user_id, knowledge_base_id, question,
                       rewritten_question, answer, source_count, created_at
                FROM qa_records
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC, id DESC
                """
            ),
            params,
        ).mappings()
        return [self._to_record(row) for row in rows]

    def get_qa_record(
        self,
        db: Session,
        *,
        qa_record_id: int,
        user_id: int,
    ) -> QaRecordRead:
        row = db.execute(
            text(
                """
                SELECT id, user_id, knowledge_base_id, question,
                       rewritten_question, answer, source_count, created_at
                FROM qa_records
                WHERE id = :qa_record_id AND user_id = :user_id
                """
            ),
            {"qa_record_id": qa_record_id, "user_id": user_id},
        ).mappings().first()
        if row is None:
            raise ValueError("QA record not found")

        source_rows = db.execute(
            text(
                """
                SELECT s.document_id, s.chunk_id, s.file_name,
                       s.chunk_index, s.page_no, s.score, s.source_text,
                       d.id AS live_document_id, c.id AS live_chunk_id
                FROM qa_sources s
                LEFT JOIN documents d ON d.id = s.document_id
                LEFT JOIN document_chunks c
                  ON c.id = s.chunk_id AND c.document_id = d.id
                WHERE s.qa_record_id = :qa_record_id
                ORDER BY s.rank_no ASC, s.id ASC
                """
            ),
            {"qa_record_id": qa_record_id},
        ).mappings()

        sources = [self._to_source(source_row) for source_row in source_rows]
        return self._to_record(row, sources=sources)

    def _to_record(
        self,
        row,
        *,
        sources: list[HistoricalSourceReference] | None = None,
    ) -> QaRecordRead:
        return QaRecordRead(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            knowledge_base_id=int(row["knowledge_base_id"]),
            question=row["question"],
            rewritten_question=row["rewritten_question"],
            answer=row["answer"],
            source_count=int(row["source_count"] or 0),
            sources=sources or [],
            created_at=row["created_at"],
        )

    def _to_source(self, row) -> HistoricalSourceReference:
        source_is_available = (
            row["live_document_id"] is not None and row["live_chunk_id"] is not None
        )
        document_id = int(row["document_id"]) if source_is_available else None
        chunk_id = int(row["chunk_id"]) if source_is_available else None
        jump_url = f"/documents/{document_id}/chunks/{chunk_id}" if source_is_available else None
        return HistoricalSourceReference(
            document_id=document_id,
            chunk_id=chunk_id,
            file_name=row["file_name"],
            chunk_index=int(row["chunk_index"]),
            page_no=int(row["page_no"]) if row["page_no"] is not None else None,
            score=float(row["score"]) if row["score"] is not None else None,
            source_text=row["source_text"],
            jump_url=jump_url,
        )


qa_history_service = QaHistoryService()
