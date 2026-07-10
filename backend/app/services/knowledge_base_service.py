from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.contracts import KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate


class KnowledgeBaseService:
    def ensure_user_exists(self, db: Session, user_id: int) -> None:
        existing = db.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id}).first()
        if existing is None:
            raise ValueError("User not found")

    def list_for_owner(self, db: Session, owner_id: int) -> list[KnowledgeBaseRead]:
        self.ensure_user_exists(db, owner_id)
        rows = db.execute(
            text(
                """
                SELECT id, owner_id, name, description, visibility
                FROM knowledge_bases
                WHERE owner_id = :owner_id
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"owner_id": owner_id},
        ).mappings()
        return [self._to_read(row) for row in rows]

    def create(self, db: Session, owner_id: int, payload: KnowledgeBaseCreate) -> KnowledgeBaseRead:
        self.ensure_user_exists(db, owner_id)
        result = db.execute(
            text(
                """
                INSERT INTO knowledge_bases (owner_id, name, description, visibility)
                VALUES (:owner_id, :name, :description, :visibility)
                """
            ),
            {
                "owner_id": owner_id,
                "name": payload.name,
                "description": payload.description,
                "visibility": payload.visibility.value,
            },
        )
        db.commit()
        return self.get_owned(db, int(result.lastrowid), owner_id)

    def get_owned(self, db: Session, knowledge_base_id: int, owner_id: int) -> KnowledgeBaseRead:
        row = db.execute(
            text(
                """
                SELECT id, owner_id, name, description, visibility
                FROM knowledge_bases
                WHERE id = :id AND owner_id = :owner_id
                """
            ),
            {"id": knowledge_base_id, "owner_id": owner_id},
        ).mappings().first()
        if row is None:
            raise ValueError("Knowledge base not found")
        return self._to_read(row)

    def update(
        self,
        db: Session,
        knowledge_base_id: int,
        owner_id: int,
        payload: KnowledgeBaseUpdate,
    ) -> KnowledgeBaseRead:
        current = self.get_owned(db, knowledge_base_id, owner_id)
        db.execute(
            text(
                """
                UPDATE knowledge_bases
                SET name = :name,
                    description = :description,
                    visibility = :visibility
                WHERE id = :id AND owner_id = :owner_id
                """
            ),
            {
                "id": knowledge_base_id,
                "owner_id": owner_id,
                "name": payload.name or current.name,
                "description": payload.description if payload.description is not None else current.description,
                "visibility": (payload.visibility or current.visibility).value,
            },
        )
        db.commit()
        return self.get_owned(db, knowledge_base_id, owner_id)

    def delete(self, db: Session, knowledge_base_id: int, owner_id: int) -> None:
        self.get_owned(db, knowledge_base_id, owner_id)
        db.execute(
            text("DELETE FROM knowledge_bases WHERE id = :id AND owner_id = :owner_id"),
            {"id": knowledge_base_id, "owner_id": owner_id},
        )
        db.commit()

    def _to_read(self, row) -> KnowledgeBaseRead:
        return KnowledgeBaseRead(
            id=int(row["id"]),
            owner_id=int(row["owner_id"]),
            name=row["name"],
            description=row["description"],
            visibility=row["visibility"],
        )


knowledge_base_service = KnowledgeBaseService()
