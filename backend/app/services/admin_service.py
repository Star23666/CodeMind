from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.contracts import (
    AdminAnomalyRead,
    AdminDocumentRead,
    AdminOverviewRead,
    AdminUserRead,
    UserStatus,
)
from app.services.health_service import health_service


class AdminOperationError(ValueError):
    pass


class AdminService:
    def list_users(
        self,
        db: Session,
        *,
        query: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> list[AdminUserRead]:
        conditions: list[str] = []
        params: dict[str, object] = {}
        if query:
            conditions.append(
                "(LOWER(username) LIKE LOWER(:query) OR LOWER(email) LIKE LOWER(:query))"
            )
            params["query"] = f"%{query.strip()}%"
        if role:
            conditions.append("role = :role")
            params["role"] = role
        if status:
            conditions.append("status = :status")
            params["status"] = status

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = db.execute(
            text(
                f"""
                SELECT id, username, email, role, status, created_at
                FROM users
                {where_clause}
                ORDER BY created_at DESC, id DESC
                """
            ),
            params,
        ).mappings()
        return [self._to_user_read(row) for row in rows]

    def update_user_status(
        self,
        db: Session,
        *,
        target_user_id: int,
        status: UserStatus,
        admin_user_id: int,
    ) -> AdminUserRead:
        row = db.execute(
            text(
                """
                SELECT id, username, email, role, status, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": target_user_id},
        ).mappings().first()
        if row is None:
            raise ValueError("User not found")

        current_status = UserStatus(row["status"])
        if current_status == status:
            return self._to_user_read(row)
        if target_user_id == admin_user_id and status == UserStatus.DISABLED:
            raise AdminOperationError("不能停用当前登录的管理员账号。")
        if row["role"] == "admin" and status == UserStatus.DISABLED:
            lock_clause = (
                ""
                if db.bind is not None and db.bind.dialect.name == "sqlite"
                else " FOR UPDATE"
            )
            active_admin_ids = db.execute(
                text(
                    "SELECT id FROM users "
                    "WHERE role = 'admin' AND status = 'active' "
                    f"ORDER BY id{lock_clause}"
                )
            ).scalars().all()
            if len(active_admin_ids) <= 1:
                raise AdminOperationError("系统必须至少保留一个启用状态的管理员。")

        db.execute(
            text(
                """
                UPDATE users
                SET status = :status,
                    token_version = token_version + CASE WHEN :status = 'disabled' THEN 1 ELSE 0 END
                WHERE id = :user_id
                """
            ),
            {"user_id": target_user_id, "status": status.value},
        )
        db.commit()
        updated = db.execute(
            text(
                """
                SELECT id, username, email, role, status, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": target_user_id},
        ).mappings().one()
        return self._to_user_read(updated)

    def list_documents(
        self,
        db: Session,
        *,
        query: str | None = None,
        owner_id: int | None = None,
        knowledge_base_id: int | None = None,
        parse_status: str | None = None,
        visibility: str | None = None,
    ) -> list[AdminDocumentRead]:
        conditions: list[str] = []
        params: dict[str, object] = {}
        if query:
            conditions.append(
                "(LOWER(u.username) LIKE LOWER(:query) "
                "OR (kb.visibility = 'public' AND LOWER(d.file_name) LIKE LOWER(:query)))"
            )
            params["query"] = f"%{query.strip()}%"
        if owner_id is not None:
            conditions.append("d.owner_id = :owner_id")
            params["owner_id"] = owner_id
        if knowledge_base_id is not None:
            conditions.append("d.knowledge_base_id = :knowledge_base_id")
            params["knowledge_base_id"] = knowledge_base_id
        if parse_status:
            conditions.append("d.parse_status = :parse_status")
            params["parse_status"] = parse_status
        if visibility:
            conditions.append("kb.visibility = :visibility")
            params["visibility"] = visibility

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = db.execute(
            text(
                f"""
                SELECT d.id, d.knowledge_base_id, d.owner_id,
                       CASE WHEN kb.visibility = 'public' THEN kb.name ELSE NULL END AS knowledge_base_name,
                       u.username AS uploader_username,
                       CASE WHEN kb.visibility = 'public' THEN d.file_name ELSE NULL END AS file_name,
                       d.file_type, d.file_size, d.parse_status,
                       CASE WHEN kb.visibility = 'public' THEN d.error_message ELSE NULL END
                         AS error_message,
                       d.chunk_count, kb.visibility AS knowledge_base_visibility,
                       d.created_at
                FROM documents d
                JOIN users u ON u.id = d.owner_id
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                {where_clause}
                ORDER BY d.created_at DESC, d.id DESC
                """
            ),
            params,
        ).mappings()
        return [
            AdminDocumentRead(
                id=int(row["id"]),
                knowledge_base_id=int(row["knowledge_base_id"]),
                knowledge_base_name=row["knowledge_base_name"],
                owner_id=int(row["owner_id"]),
                uploader_username=row["uploader_username"],
                file_name=row["file_name"],
                file_type=row["file_type"],
                file_size=int(row["file_size"] or 0),
                parse_status=row["parse_status"],
                error_message=(
                    self._safe_message(row["error_message"])
                    if row["knowledge_base_visibility"] == "public"
                    else (
                        "私人文档处理失败，错误详情已隐藏。"
                        if row["parse_status"] == "failed"
                        else None
                    )
                ),
                chunk_count=int(row["chunk_count"] or 0),
                knowledge_base_visibility=row["knowledge_base_visibility"],
                can_manage=row["knowledge_base_visibility"] == "public",
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def overview(self, db: Session) -> AdminOverviewRead:
        counts = db.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM users) AS users_total,
                  (SELECT COUNT(*) FROM users WHERE status = 'active') AS users_active,
                  (SELECT COUNT(*) FROM documents) AS documents_total,
                  (SELECT COUNT(*) FROM documents WHERE parse_status = 'failed') AS documents_failed,
                  (SELECT COUNT(*) FROM feedbacks) AS feedbacks_total
                """
            )
        ).mappings().one()
        anomalies = self._recent_anomalies(db)
        return AdminOverviewRead(
            users_total=int(counts["users_total"] or 0),
            users_active=int(counts["users_active"] or 0),
            documents_total=int(counts["documents_total"] or 0),
            documents_failed=int(counts["documents_failed"] or 0),
            feedbacks_total=int(counts["feedbacks_total"] or 0),
            readiness=health_service.check_readiness(),
            recent_anomalies=anomalies,
        )

    def _recent_anomalies(self, db: Session) -> list[AdminAnomalyRead]:
        rows: list[dict[str, object]] = []
        document_rows = db.execute(
            text(
                """
                SELECT CAST(d.id AS CHAR) AS resource_id, d.owner_id AS user_id,
                       d.knowledge_base_id, d.parse_status AS status,
                       CASE WHEN kb.visibility = 'public' THEN d.error_message ELSE NULL END
                         AS message,
                       kb.visibility, d.updated_at AS created_at
                FROM documents d
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                WHERE d.parse_status = 'failed'
                ORDER BY d.updated_at DESC, d.id DESC
                LIMIT 5
                """
            )
        ).mappings()
        rows.extend(
            {
                "resource_type": "document",
                **dict(row),
                "message": (
                    row["message"]
                    if row["visibility"] == "public"
                    else "私人文档处理失败，错误详情已隐藏。"
                ),
            }
            for row in document_rows
        )

        for table, resource_type in (
            ("mind_map_jobs", "mind_map_job"),
            ("quiz_sessions", "quiz_session"),
        ):
            job_rows = db.execute(
                text(
                    f"""
                    SELECT CAST(job.id AS CHAR) AS resource_id, job.user_id,
                           {"job.knowledge_base_id" if table == "mind_map_jobs" else "NULL AS knowledge_base_id"},
                           job.status,
                           {"CASE WHEN kb.visibility = 'public' THEN job.error_message ELSE NULL END" if table == "mind_map_jobs" else "NULL"} AS message,
                           {"kb.visibility" if table == "mind_map_jobs" else "NULL"} AS visibility,
                           job.updated_at AS created_at
                    FROM {table} job
                    {"JOIN knowledge_bases kb ON kb.id = job.knowledge_base_id" if table == "mind_map_jobs" else ""}
                    WHERE job.status = 'failed'
                    ORDER BY job.updated_at DESC
                    LIMIT 5
                    """
                )
            ).mappings()
            rows.extend(
                {
                    "resource_type": resource_type,
                    **dict(row),
                    "message": (
                        row["message"]
                        if row["message"] is not None
                        else f"{('私人知识地图' if resource_type == 'mind_map_job' else 'AI 出题')}任务失败，错误详情已隐藏。"
                    ),
                }
                for row in job_rows
            )

        def sort_key(row: dict[str, object]) -> datetime:
            value = row.get("created_at")
            return value if isinstance(value, datetime) else datetime.min

        rows.sort(key=sort_key, reverse=True)
        return [
            AdminAnomalyRead(
                resource_type=str(row["resource_type"]),
                resource_id=str(row["resource_id"]),
                status=str(row["status"]),
                message=self._safe_message(row.get("message")) or "未记录错误详情。",
                user_id=int(row["user_id"]) if row.get("user_id") is not None else None,
                knowledge_base_id=(
                    int(row["knowledge_base_id"])
                    if row.get("knowledge_base_id") is not None
                    else None
                ),
                created_at=row.get("created_at"),
            )
            for row in rows[:8]
        ]

    def _safe_message(self, value: object) -> str | None:
        if value is None:
            return None
        message = " ".join(str(value).split())
        return message[:240]

    def _to_user_read(self, row) -> AdminUserRead:
        return AdminUserRead(
            id=int(row["id"]),
            username=row["username"],
            email=row["email"],
            role=row["role"],
            status=row["status"],
            created_at=row["created_at"],
        )


admin_service = AdminService()
