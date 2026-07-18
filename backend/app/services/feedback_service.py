from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.contracts import AdminFeedbackRead, FeedbackCreate, FeedbackRead


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

    def get_for_record(
        self,
        db: Session,
        *,
        qa_record_id: int,
        user_id: int,
    ) -> FeedbackRead | None:
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

        row = db.execute(
            text(
                """
                SELECT id, qa_record_id, user_id, rating, comment, created_at
                FROM feedbacks
                WHERE qa_record_id = :qa_record_id AND user_id = :user_id
                """
            ),
            {"qa_record_id": qa_record_id, "user_id": user_id},
        ).mappings().first()
        return self._to_read(row) if row is not None else None

    def list_for_admin(
        self,
        db: Session,
        *,
        rating: int | None = None,
        user_id: int | None = None,
        knowledge_base_id: int | None = None,
    ) -> list[AdminFeedbackRead]:
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
                SELECT f.id, f.qa_record_id, f.user_id, f.rating, f.comment, f.created_at,
                       u.username, q.knowledge_base_id,
                       CASE WHEN kb.visibility = 'public' THEN kb.name ELSE NULL END
                         AS knowledge_base_name,
                       kb.visibility AS knowledge_base_visibility,
                       CASE WHEN kb.visibility = 'public' THEN q.question ELSE NULL END
                         AS question,
                       CASE WHEN kb.visibility = 'public' THEN q.answer ELSE NULL END
                         AS answer,
                       q.source_count, q.created_at AS qa_created_at
                FROM feedbacks f
                JOIN qa_records q ON q.id = f.qa_record_id
                JOIN users u ON u.id = f.user_id
                JOIN knowledge_bases kb ON kb.id = q.knowledge_base_id
                {where_clause}
                ORDER BY f.created_at DESC, f.id DESC
                """
            ),
            params,
        ).mappings()
        return [self._to_admin_read(row) for row in rows]

    def _to_read(self, row) -> FeedbackRead:
        return FeedbackRead(
            id=int(row["id"]),
            qa_record_id=int(row["qa_record_id"]),
            user_id=int(row["user_id"]),
            rating=int(row["rating"]),
            comment=row["comment"],
            created_at=row["created_at"],
        )

    def _to_admin_read(self, row) -> AdminFeedbackRead:
        return AdminFeedbackRead(
            **self._to_read(row).model_dump(),
            username=row["username"],
            knowledge_base_id=int(row["knowledge_base_id"]),
            knowledge_base_name=row["knowledge_base_name"],
            knowledge_base_visibility=row["knowledge_base_visibility"],
            question=row["question"],
            answer=row["answer"],
            content_redacted=row["knowledge_base_visibility"] != "public",
            source_count=int(row["source_count"] or 0),
            qa_created_at=row["qa_created_at"],
        )


feedback_service = FeedbackService()
