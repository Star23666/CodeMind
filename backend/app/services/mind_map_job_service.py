import asyncio
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


class MindMapJobStateError(ValueError):
    pass


class _MindMapJobNoLongerProcessing(RuntimeError):
    """The durable job state changed while a worker was still running."""


class MindMapJobService:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        """Requeue jobs that were interrupted by a backend restart."""
        db = SessionLocal()
        try:
            job_ids = list(
                db.execute(
                    text(
                        """
                        SELECT id
                        FROM mind_map_jobs
                        WHERE status IN ('queued', 'processing')
                        ORDER BY created_at ASC
                        """
                    )
                ).scalars()
            )
            if job_ids:
                db.execute(
                    text(
                        """
                        UPDATE mind_map_jobs
                        SET status = 'queued',
                            stage = 'queued',
                            progress = 0,
                            message = '服务已恢复，任务重新排队',
                            error_message = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE status IN ('queued', 'processing')
                        """
                    )
                )
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Unable to recover interrupted mind map jobs")
            return
        finally:
            db.close()

        for job_id in job_ids:
            self.enqueue(str(job_id))

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def enqueue(self, job_id: str) -> None:
        current = self._tasks.get(job_id)
        if current is not None and not current.done():
            return

        task = asyncio.create_task(self.process_job(job_id), name=f"mind-map-{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda finished: self._task_finished(job_id, finished))

    def _task_finished(self, job_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(job_id) is task:
            self._tasks.pop(job_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("Unhandled mind map task error %s: %s", job_id, error)

    def create_job(
        self,
        db: Session,
        *,
        owner_id: int,
        request: MindMapGenerateRequest,
    ) -> MindMapJobRead:
        knowledge_base_service.get_readable(db, request.knowledge_base_id, owner_id)
        if request.document_id is not None:
            document = document_service.get_owned_document(db, request.document_id, owner_id)
            if document.knowledge_base_id != request.knowledge_base_id:
                raise ValueError("Document not found")

        active_job_id = db.execute(
            text(
                """
                SELECT id
                FROM mind_map_jobs
                WHERE user_id = :user_id
                  AND knowledge_base_id = :knowledge_base_id
                  AND (
                    (document_id IS NULL AND :document_id IS NULL)
                    OR document_id = :document_id
                  )
                  AND status IN ('queued', 'processing')
                ORDER BY created_at ASC
                LIMIT 1
                """
            ),
            {
                "user_id": owner_id,
                "knowledge_base_id": request.knowledge_base_id,
                "document_id": request.document_id,
            },
        ).scalar_one_or_none()
        if active_job_id is not None:
            return self.get_job(db, job_id=str(active_job_id), owner_id=owner_id)

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

    async def cancel_job(
        self,
        db: Session,
        *,
        job_id: str,
        owner_id: int,
    ) -> MindMapJobRead:
        row = self._get_row(db, job_id=job_id, owner_id=owner_id)
        if row is None:
            raise ValueError("Mind map job not found")
        if row["status"] not in {"queued", "processing"}:
            raise MindMapJobStateError("只有等待中或生成中的任务可以取消。")

        result = db.execute(
            text(
                """
                UPDATE mind_map_jobs
                SET status = 'cancelled',
                    stage = 'cancelled',
                    progress = 100,
                    message = '知识地图生成已取消',
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :job_id
                  AND user_id = :owner_id
                  AND status IN ('queued', 'processing')
                """
            ),
            {"job_id": job_id, "owner_id": owner_id},
        )
        if result.rowcount != 1:
            db.rollback()
            raise MindMapJobStateError("任务状态已经变化，请刷新后重试。")
        db.commit()

        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.get_job(db, job_id=job_id, owner_id=owner_id)

    async def process_job(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            row = self._claim_job(db, job_id=job_id)
            if row is None:
                return

            request = MindMapGenerateRequest(
                knowledge_base_id=int(row["knowledge_base_id"]),
                document_id=int(row["document_id"]) if row["document_id"] is not None else None,
                max_depth=int(row["max_depth"]),
                max_nodes=int(row["max_nodes"]),
            )
            def report(stage: str, progress: int, message: str) -> None:
                if not self._update(
                    db,
                    job_id,
                    status="processing",
                    stage=stage,
                    progress=progress,
                    message=message,
                ):
                    raise _MindMapJobNoLongerProcessing

            result = await mind_map_service.generate(
                db,
                owner_id=int(row["user_id"]),
                request=request,
                progress_callback=report,
            )
            mind_map_history_service.save_generated(
                db,
                owner_id=int(row["user_id"]),
                result=result,
                commit=False,
            )
            if not self._update(
                db,
                job_id,
                status="completed",
                stage="completed",
                progress=100,
                message="知识地图生成完成",
                result_json=result.model_dump_json(),
                error_message=None,
            ):
                raise _MindMapJobNoLongerProcessing
        except asyncio.CancelledError:
            self._requeue(db, job_id)
            raise
        except _MindMapJobNoLongerProcessing:
            db.rollback()
            logger.info(
                "Mind map job %s stopped because its durable state changed",
                job_id,
            )
        except MindMapGenerationError as exc:
            db.rollback()
            self._mark_failed(db, job_id, str(exc))
        except Exception:
            logger.exception("Mind map background job failed: %s", job_id)
            db.rollback()
            self._mark_failed(db, job_id, "思维导图生成失败，请稍后重试。")
        finally:
            db.close()

    def _claim_job(self, db: Session, *, job_id: str):
        result = db.execute(
            text(
                """
                UPDATE mind_map_jobs
                SET status = 'processing',
                    stage = 'collecting',
                    progress = 5,
                    message = '开始读取资料',
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :job_id
                  AND status = 'queued'
                """
            ),
            {"job_id": job_id},
        )
        if result.rowcount != 1:
            db.rollback()
            return None
        db.commit()
        return self._get_row(db, job_id=job_id)

    def _requeue(self, db: Session, job_id: str) -> None:
        try:
            db.execute(
                text(
                    """
                    UPDATE mind_map_jobs
                    SET status = 'queued',
                        stage = 'queued',
                        progress = 0,
                        message = '服务停止，任务将在下次启动时继续',
                        error_message = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :job_id
                      AND status = 'processing'
                    """
                ),
                {"job_id": job_id},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Unable to requeue cancelled mind map job: %s", job_id)

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
    ) -> bool:
        result = db.execute(
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
                  AND status = 'processing'
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
        if result.rowcount != 1:
            # The same transaction may already contain a generated history row.
            # Rolling back here prevents a cancelled job from leaving that row behind.
            db.rollback()
            return False
        db.commit()
        return True

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
