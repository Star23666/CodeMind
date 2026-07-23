import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.contracts import (
    MindMapHistoryCreate,
    MindMapHistoryRead,
    MindMapHistoryUpdate,
    MindMapResponse,
)


class MindMapHistoryValidationError(ValueError):
    pass


class MindMapHistoryService:
    max_nodes = 300
    max_depth = 8
    max_tree_json_bytes = 2 * 1024 * 1024
    max_view_state_json_bytes = 256 * 1024

    def save_generated(
        self,
        db: Session,
        *,
        owner_id: int,
        result: MindMapResponse,
        commit: bool = True,
    ) -> MindMapHistoryRead:
        title = result.root.title[:120]
        try:
            cursor = db.execute(text("""
                INSERT INTO mind_map_histories
                    (user_id, knowledge_base_id, document_id, title, node_count, result_json, view_state_json)
                VALUES (:user_id, :knowledge_base_id, :document_id, :title, :node_count, :result_json, '{}')
            """), {
                "user_id": owner_id, "knowledge_base_id": result.knowledge_base_id,
                "document_id": result.document_id, "title": title, "node_count": result.node_count,
                "result_json": result.model_dump_json(),
            })
            history_id = int(cursor.lastrowid)
            result.history_id = history_id
            db.execute(text("UPDATE mind_map_histories SET result_json=:result WHERE id=:id"), {
                "id": history_id, "result": result.model_dump_json(),
            })
            if commit:
                db.commit()
            else:
                db.flush()
        except Exception:
            db.rollback()
            raise
        return self.get(db, history_id=history_id, owner_id=owner_id)

    def create(self, db: Session, *, owner_id: int, payload: MindMapHistoryCreate) -> MindMapHistoryRead:
        node_count = self._validate_payload(payload.root, payload.view_state)
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
        try:
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
            history_id = int(cursor.lastrowid)
            result.history_id = history_id
            db.execute(text("UPDATE mind_map_histories SET result_json=:result WHERE id=:id"), {
                "id": history_id, "result": result.model_dump_json(),
            })
            db.commit()
        except Exception:
            db.rollback()
            raise
        return self.get(db, history_id=history_id, owner_id=owner_id)

    def list(self, db: Session, *, owner_id: int, knowledge_base_id: int | None = None):
        clause = "AND knowledge_base_id=:knowledge_base_id" if knowledge_base_id else ""
        rows = db.execute(text(f"""
            SELECT id, knowledge_base_id, document_id, title, node_count,
                   created_at, updated_at
            FROM mind_map_histories
            WHERE user_id=:owner_id {clause}
            ORDER BY updated_at DESC, id DESC
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
        title = (payload.title or current.title).strip()[:120]
        view_state = current.view_state if payload.view_state is None else payload.view_state
        result.node_count = self._validate_payload(result.root, view_state)
        params = {
            "title": title,
            "view_state": json.dumps(view_state, ensure_ascii=False),
            "id": history_id,
            "owner_id": owner_id,
        }
        if payload.root is None:
            db.execute(
                text(
                    """
                    UPDATE mind_map_histories
                    SET title=:title, view_state_json=:view_state,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id AND user_id=:owner_id
                    """
                ),
                params,
            )
        else:
            db.execute(
                text(
                    """
                    UPDATE mind_map_histories
                    SET title=:title, node_count=:node_count,
                        result_json=:result, view_state_json=:view_state,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id AND user_id=:owner_id
                    """
                ),
                {
                    **params,
                    "node_count": result.node_count,
                    "result": result.model_dump_json(),
                },
            )
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
            view_state=json.loads(row["view_state_json"] or "{}") if include_result else {},
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def _validate_payload(self, root, view_state: dict) -> int:
        node_count = 0
        stack = [(root, 0)]
        while stack:
            node, depth = stack.pop()
            node_count += 1
            if node_count > self.max_nodes:
                raise MindMapHistoryValidationError(
                    f"思维导图节点过多，最多允许保存 {self.max_nodes} 个节点。"
                )
            if depth > self.max_depth:
                raise MindMapHistoryValidationError(
                    f"思维导图层级过深，最多允许保存 {self.max_depth + 1} 层。"
                )
            stack.extend((child, depth + 1) for child in node.children)

        tree_size = len(root.model_dump_json().encode("utf-8"))
        if tree_size > self.max_tree_json_bytes:
            raise MindMapHistoryValidationError("思维导图内容过大，请精简节点内容后保存。")
        view_state_size = len(
            json.dumps(view_state, ensure_ascii=False).encode("utf-8")
        )
        if view_state_size > self.max_view_state_json_bytes:
            raise MindMapHistoryValidationError("思维导图画布状态过大，无法保存。")
        return node_count

mind_map_history_service = MindMapHistoryService()
