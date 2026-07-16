from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.contracts import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    UserRole,
)


class KnowledgeBasePermissionError(ValueError):
    pass


class KnowledgeBaseService:
    def ensure_user_exists(self, db: Session, user_id: int) -> None:
        existing = db.execute(
            text("SELECT id FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
        if existing is None:
            raise ValueError("User not found")

    def list_accessible(self, db: Session, user_id: int) -> list[KnowledgeBaseRead]:
        self.ensure_user_exists(db, user_id)
        rows = db.execute(
            text(
                """
                SELECT id, owner_id, name, description, visibility
                FROM knowledge_bases
                WHERE owner_id = :user_id OR visibility = 'public'
                ORDER BY CASE WHEN visibility = 'public' THEN 0 ELSE 1 END,
                         created_at DESC, id DESC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()
        role = self._user_role(db, user_id) if any(
            row["visibility"] == "public" for row in rows
        ) else UserRole.USER
        return [self._to_read(row, user_id=user_id, role=role) for row in rows]

    def list_for_owner(self, db: Session, owner_id: int) -> list[KnowledgeBaseRead]:
        return self.list_accessible(db, owner_id)

    def create(
        self,
        db: Session,
        owner_id: int,
        payload: KnowledgeBaseCreate,
    ) -> KnowledgeBaseRead:
        self.ensure_user_exists(db, owner_id)
        result = db.execute(
            text(
                """
                INSERT INTO knowledge_bases (owner_id, name, description, visibility)
                VALUES (:owner_id, :name, :description, 'private')
                """
            ),
            {
                "owner_id": owner_id,
                "name": payload.name,
                "description": payload.description,
            },
        )
        db.commit()
        return self.get_readable(db, int(result.lastrowid), owner_id)

    def get_readable(
        self,
        db: Session,
        knowledge_base_id: int,
        user_id: int,
    ) -> KnowledgeBaseRead:
        self.ensure_user_exists(db, user_id)
        row = self._get_row(db, knowledge_base_id)
        if row is None or not self._can_read(row, user_id):
            raise ValueError("Knowledge base not found")
        role = (
            self._user_role(db, user_id)
            if row["visibility"] == "public"
            else UserRole.USER
        )
        return self._to_read(row, user_id=user_id, role=role)

    def get_owned(
        self,
        db: Session,
        knowledge_base_id: int,
        owner_id: int,
    ) -> KnowledgeBaseRead:
        return self.get_readable(db, knowledge_base_id, owner_id)

    def get_uploadable(
        self,
        db: Session,
        knowledge_base_id: int,
        user_id: int,
    ) -> KnowledgeBaseRead:
        knowledge_base = self.get_readable(db, knowledge_base_id, user_id)
        if not knowledge_base.can_upload:
            raise KnowledgeBasePermissionError("无权向该知识库上传文档。")
        return knowledge_base

    def update(
        self,
        db: Session,
        knowledge_base_id: int,
        owner_id: int,
        payload: KnowledgeBaseUpdate,
    ) -> KnowledgeBaseRead:
        current = self.get_readable(db, knowledge_base_id, owner_id)
        if not current.can_edit:
            raise KnowledgeBasePermissionError("只有管理员可以编辑公共知识库。")

        db.execute(
            text(
                """
                UPDATE knowledge_bases
                SET name = :name,
                    description = :description
                WHERE id = :id
                """
            ),
            {
                "id": knowledge_base_id,
                "name": payload.name or current.name,
                "description": (
                    payload.description
                    if payload.description is not None
                    else current.description
                ),
            },
        )
        db.commit()
        return self.get_readable(db, knowledge_base_id, owner_id)

    def delete(self, db: Session, knowledge_base_id: int, owner_id: int) -> None:
        current = self.get_readable(db, knowledge_base_id, owner_id)
        if current.visibility.value == "public":
            raise KnowledgeBasePermissionError("全局公共知识库不能删除。")
        if not current.can_delete:
            raise KnowledgeBasePermissionError("无权删除该知识库。")
        db.execute(
            text("DELETE FROM knowledge_bases WHERE id = :id AND owner_id = :owner_id"),
            {"id": knowledge_base_id, "owner_id": owner_id},
        )
        db.commit()

    def _get_row(self, db: Session, knowledge_base_id: int):
        return db.execute(
            text(
                """
                SELECT id, owner_id, name, description, visibility
                FROM knowledge_bases
                WHERE id = :id
                """
            ),
            {"id": knowledge_base_id},
        ).mappings().first()

    def _can_read(self, row, user_id: int) -> bool:
        return row["visibility"] == "public" or int(row["owner_id"]) == user_id

    def _user_role(self, db: Session, user_id: int) -> UserRole:
        role = db.execute(
            text("SELECT role FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar_one_or_none()
        if role is None:
            raise ValueError("User not found")
        return UserRole(role)

    def _to_read(
        self,
        row,
        *,
        user_id: int,
        role: UserRole,
    ) -> KnowledgeBaseRead:
        is_public = row["visibility"] == "public"
        is_owner = row["owner_id"] is not None and int(row["owner_id"]) == user_id
        can_manage = (is_public and role == UserRole.ADMIN) or is_owner
        return KnowledgeBaseRead(
            id=int(row["id"]),
            owner_id=int(row["owner_id"]) if row["owner_id"] is not None else None,
            name=row["name"],
            description=row["description"],
            visibility=row["visibility"],
            can_read=True,
            can_upload=is_public or is_owner,
            can_manage=can_manage,
            can_edit=can_manage,
            can_delete=is_owner and not is_public,
        )


knowledge_base_service = KnowledgeBaseService()
