import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.contracts import (
    MindMapHistoryCreate,
    MindMapHistoryRead,
    MindMapHistoryUpdate,
    MindMapResponse,
)


class MindMapHistoryService:
    def save_generated(self, db: Session, *, owner_id: int, result: MindMapResponse) -> MindMapHistoryRead:
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

    def create(self, db: Session, *, owner_id: int, payload: MindMapHistoryCreate) -> MindMapHistoryRead:
        node_count = self._count(payload.root)
        title = (payload.title or payload.root.title).strip()[:120] or "未命名知识地图"
        result = MindMapResponse(
            history_id=None,
            knowledge_base_id=payload.knowledge_base_id,
            document_id=payload.document_id,
            generation_mode=payload.generation_mode,
            node_count=node_count,
            message="用户保存的知识地图版本。",
            root=payload.root,
        )
        cursor = db.execute(text("""
            INSERT INTO mind_map_histories
                (user_id, knowledge_base_id, document_id, title, node_count, result_json, view_state_json)
            VALUES (:user_id, :knowledge_base_id, :document_id, :title, :node_count, :result_json, :view_state)
        """), {
            "user_id": owner_id, "knowledge_base_id": payload.knowledge_base_id,
            "document_id": payload.document_id, "title": title, "node_count": node_count,
            "result_json": result.model_dump_json(),
            "view_state": json.dumps(payload.view_state, ensure_ascii=False),
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
        clause = "AND knowledge_base_id=:knowledge_base_id" if knowledge_base_id else ""
        rows = db.execute(text(f"""
            SELECT * FROM mind_map_histories WHERE user_id=:owner_id {clause}
            ORDER BY updated_at DESC, id DESC LIMIT 100
        """), {"owner_id": owner_id, "knowledge_base_id": knowledge_base_id}).mappings().all()
        return [self._read(row, include_result=False) for row in rows]

    def get(self, db: Session, *, history_id: int, owner_id: int) -> MindMapHistoryRead:
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

mind_map_history_service = MindMapHistoryService()
