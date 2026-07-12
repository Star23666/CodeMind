import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.contracts import MindMapHistoryRead, MindMapHistoryUpdate, MindMapResponse


class MindMapHistoryService:
    def save_generated(self, db: Session, *, owner_id: int, result: MindMapResponse) -> MindMapHistoryRead:
        self._ensure_table(db)
        title = result.root.title[:120]
        cursor = db.execute(text("""
            INSERT INTO mind_map_histories
                (user_id, knowledge_base_id, document_id, title, node_count, result_json, view_state_json)
            VALUES (:user_id, :knowledge_base_id, :document_id, :title, :node_count, :result_json, '{}')
        """), {
            "user_id": owner_id, "knowledge_base_id": result.knowledge_base_id,
            "document_id": result.document_id, "title": title, "node_count": result.node_count,
            "result_json": result.model_dump_json(),
        })
        db.commit()
        history_id = int(cursor.lastrowid)
        result.history_id = history_id
        db.execute(text("UPDATE mind_map_histories SET result_json=:result WHERE id=:id"), {
            "id": history_id, "result": result.model_dump_json(),
        })
        db.commit()
        return self.get(db, history_id=history_id, owner_id=owner_id)

    def list(self, db: Session, *, owner_id: int, knowledge_base_id: int | None = None):
        self._ensure_table(db)
        clause = "AND knowledge_base_id=:knowledge_base_id" if knowledge_base_id else ""
        rows = db.execute(text(f"""
            SELECT * FROM mind_map_histories WHERE user_id=:owner_id {clause}
            ORDER BY updated_at DESC, id DESC LIMIT 100
        """), {"owner_id": owner_id, "knowledge_base_id": knowledge_base_id}).mappings().all()
        return [self._read(row, include_result=False) for row in rows]

    def get(self, db: Session, *, history_id: int, owner_id: int) -> MindMapHistoryRead:
        self._ensure_table(db)
        row = db.execute(text("SELECT * FROM mind_map_histories WHERE id=:id AND user_id=:owner_id"), {
            "id": history_id, "owner_id": owner_id,
        }).mappings().first()
        if row is None:
            raise ValueError("Mind map history not found")
        return self._read(row, include_result=True)

    def update(self, db: Session, *, history_id: int, owner_id: int, payload: MindMapHistoryUpdate):
        current = self.get(db, history_id=history_id, owner_id=owner_id)
        result = current.result
        if payload.root is not None:
            result.root = payload.root
            result.node_count = self._count(payload.root)
        title = (payload.title or current.title).strip()[:120]
        db.execute(text("""
            UPDATE mind_map_histories SET title=:title, node_count=:node_count,
                result_json=:result, view_state_json=:view_state, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND user_id=:owner_id
        """), {"title": title, "node_count": result.node_count, "result": result.model_dump_json(),
                 "view_state": json.dumps(payload.view_state, ensure_ascii=False),
                 "id": history_id, "owner_id": owner_id})
        db.commit()
        return self.get(db, history_id=history_id, owner_id=owner_id)

    def delete(self, db: Session, *, history_id: int, owner_id: int) -> None:
        result = db.execute(text("DELETE FROM mind_map_histories WHERE id=:id AND user_id=:owner_id"), {
            "id": history_id, "owner_id": owner_id,
        })
        db.commit()
        if result.rowcount == 0:
            raise ValueError("Mind map history not found")

    def _read(self, row, *, include_result: bool):
        return MindMapHistoryRead(
            id=row["id"], knowledge_base_id=row["knowledge_base_id"], document_id=row["document_id"],
            title=row["title"], node_count=row["node_count"],
            result=MindMapResponse.model_validate_json(row["result_json"]) if include_result else None,
            view_state=json.loads(row["view_state_json"] or "{}"),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def _count(self, node):
        return 1 + sum(self._count(child) for child in node.children)

    def _ensure_table(self, db: Session):
        id_column = "INTEGER PRIMARY KEY AUTOINCREMENT" if db.bind.dialect.name == "sqlite" else "BIGINT PRIMARY KEY AUTO_INCREMENT"
        db.execute(text(f"""
            CREATE TABLE IF NOT EXISTS mind_map_histories (
                id {id_column}, user_id BIGINT NOT NULL,
                knowledge_base_id BIGINT NOT NULL, document_id BIGINT NULL,
                title VARCHAR(120) NOT NULL, node_count INTEGER NOT NULL,
                result_json LONGTEXT NOT NULL, view_state_json LONGTEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()


mind_map_history_service = MindMapHistoryService()
