import logging
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.schemas.contracts import MindMapGenerateRequest, MindMapJobRead, MindMapResponse
from app.services.document_service import document_service
from app.services.knowledge_base_service import knowledge_base_service
from app.services.mind_map_service import MindMapGenerationError, mind_map_service
from app.services.mind_map_history_service import mind_map_history_service


logger = logging.getLogger(__name__)


class MindMapJobService:
    def create_job(
        self,
        db: Session,
        *,
        owner_id: int,
        request: MindMapGenerateRequest,
    ) -> MindMapJobRead:
        knowledge_base_service.get_owned(db, request.knowledge_base_id, owner_id)
        if request.document_id is not None:
            document = document_service.get_owned_document(db, request.document_id, owner_id)
            if document.knowledge_base_id != request.knowledge_base_id:
                raise ValueError("Document not found")

        job_id = uuid4().hex
        db.execute(
            text(
                """
                INSERT INTO mind_map_jobs (
                    id, user_id, knowledge_base_id, document_id, max_depth, max_nodes,
                    status, stage, progress, message
                ) VALUES (
                    :id, :user_id, :knowledge_base_id, :document_id, :max_depth, :max_nodes,
                    'queued', 'queued', 0, '任务已创建，正在等待处理'
                )
                """
            ),
            {
                "id": job_id,
                "user_id": owner_id,
                "knowledge_base_id": request.knowledge_base_id,
                "document_id": request.document_id,
                "max_depth": request.max_depth,
                "max_nodes": request.max_nodes,
            },
        )
        db.commit()
        return self.get_job(db, job_id=job_id, owner_id=owner_id)

    async def process_job(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            row = self._get_row(db, job_id=job_id)
            if row is None:
                return

            request = MindMapGenerateRequest(
                knowledge_base_id=int(row["knowledge_base_id"]),
                document_id=int(row["document_id"]) if row["document_id"] is not None else None,
                max_depth=int(row["max_depth"]),
                max_nodes=int(row["max_nodes"]),
            )
            self._update(db, job_id, status="processing", stage="collecting", progress=5, message="开始读取资料")

            def report(stage: str, progress: int, message: str) -> None:
                self._update(
                    db,
                    job_id,
                    status="processing",
                    stage=stage,
                    progress=progress,
                    message=message,
                )

            result = await mind_map_service.generate(
                db,
                owner_id=int(row["user_id"]),
                request=request,
                progress_callback=report,
            )
            mind_map_history_service.save_generated(db, owner_id=int(row["user_id"]), result=result)
            self._update(
                db,
                job_id,
                status="completed",
                stage="completed",
                progress=100,
                message="知识地图生成完成",
                result_json=result.model_dump_json(),
                error_message=None,
            )
        except MindMapGenerationError as exc:
            self._mark_failed(db, job_id, str(exc))
        except Exception:
            logger.exception("Mind map background job failed: %s", job_id)
            self._mark_failed(db, job_id, "思维导图生成失败，请稍后重试。")
        finally:
            db.close()

    def get_job(self, db: Session, *, job_id: str, owner_id: int) -> MindMapJobRead:
        row = self._get_row(db, job_id=job_id, owner_id=owner_id)
        if row is None:
            raise ValueError("Mind map job not found")
        result = MindMapResponse.model_validate_json(row["result_json"]) if row["result_json"] else None
        return MindMapJobRead(
            job_id=row["id"],
            status=row["status"],
            stage=row["stage"],
            progress=int(row["progress"]),
            message=row["message"],
            result=result,
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _get_row(self, db: Session, *, job_id: str, owner_id: int | None = None):
        condition = "id = :job_id"
        params = {"job_id": job_id}
        if owner_id is not None:
            condition += " AND user_id = :owner_id"
            params["owner_id"] = owner_id
        return db.execute(
            text(f"SELECT * FROM mind_map_jobs WHERE {condition}"),
            params,
        ).mappings().first()

    def _update(
        self,
        db: Session,
        job_id: str,
        *,
        status: str,
        stage: str,
        progress: int,
        message: str,
        result_json: str | None = None,
        error_message: str | None = None,
    ) -> None:
        db.execute(
            text(
                """
                UPDATE mind_map_jobs
                SET status = :status,
                    stage = :stage,
                    progress = :progress,
                    message = :message,
                    result_json = COALESCE(:result_json, result_json),
                    error_message = :error_message,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :job_id
                """
            ),
            {
                "job_id": job_id,
                "status": status,
                "stage": stage,
                "progress": progress,
                "message": message,
                "result_json": result_json,
                "error_message": error_message,
            },
        )
        db.commit()

    def _mark_failed(self, db: Session, job_id: str, message: str) -> None:
        try:
            self._update(
                db,
                job_id,
                status="failed",
                stage="failed",
                progress=100,
                message="知识地图生成失败",
                error_message=message,
            )
        except Exception:
            db.rollback()
            logger.exception("Unable to persist mind map job failure: %s", job_id)

mind_map_job_service = MindMapJobService()
