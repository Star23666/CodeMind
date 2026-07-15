from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.contracts import FeedbackCreate, FeedbackRead


class FeedbackConflictError(ValueError):
    pass


class FeedbackService:
    def submit(
        self,
        db: Session,
        *,
        qa_record_id: int,
        user_id: int,
        payload: FeedbackCreate,
    ) -> FeedbackRead:
        owned_record = db.execute(
            text(
                """
                SELECT id
                FROM qa_records
                WHERE id = :qa_record_id AND user_id = :user_id
                """
            ),
            {"qa_record_id": qa_record_id, "user_id": user_id},
        ).first()
        if owned_record is None:
            raise ValueError("QA record not found")

        try:
            result = db.execute(
                text(
                    """
                    INSERT INTO feedbacks (qa_record_id, user_id, rating, comment)
                    VALUES (:qa_record_id, :user_id, :rating, :comment)
                    """
                ),
                {
                    "qa_record_id": qa_record_id,
                    "user_id": user_id,
                    "rating": payload.rating,
                    "comment": payload.comment,
                },
            )
            feedback_id = int(result.lastrowid)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise FeedbackConflictError("该问答记录已经提交过反馈。") from exc

        return self.get(db, feedback_id=feedback_id)

    def get(self, db: Session, *, feedback_id: int) -> FeedbackRead:
        row = db.execute(
            text(
                """
                SELECT id, qa_record_id, user_id, rating, comment, created_at
                FROM feedbacks
                WHERE id = :feedback_id
                """
            ),
            {"feedback_id": feedback_id},
        ).mappings().first()
        if row is None:
            raise ValueError("Feedback not found")
        return self._to_read(row)

    def list_for_admin(
        self,
        db: Session,
        *,
        rating: int | None = None,
        user_id: int | None = None,
        knowledge_base_id: int | None = None,
    ) -> list[FeedbackRead]:
        conditions: list[str] = []
        params: dict[str, int] = {}
        if rating is not None:
            conditions.append("f.rating = :rating")
            params["rating"] = rating
        if user_id is not None:
            conditions.append("f.user_id = :user_id")
            params["user_id"] = user_id
        if knowledge_base_id is not None:
            conditions.append("q.knowledge_base_id = :knowledge_base_id")
            params["knowledge_base_id"] = knowledge_base_id

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = db.execute(
            text(
                f"""
                SELECT f.id, f.qa_record_id, f.user_id, f.rating, f.comment, f.created_at
                FROM feedbacks f
                JOIN qa_records q ON q.id = f.qa_record_id
                {where_clause}
                ORDER BY f.created_at DESC, f.id DESC
                """
            ),
            params,
        ).mappings()
        return [self._to_read(row) for row in rows]

    def _to_read(self, row) -> FeedbackRead:
        return FeedbackRead(
            id=int(row["id"]),
            qa_record_id=int(row["qa_record_id"]),
            user_id=int(row["user_id"]),
            rating=int(row["rating"]),
            comment=row["comment"],
            created_at=row["created_at"],
        )


feedback_service = FeedbackService()
