import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.llm_client import LlmServiceError
from app.services.quiz_service import QuizServiceError, quiz_service


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class QuizJobService:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cleanup_task: asyncio.Task[None] | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def start(self) -> None:
        self._semaphore = asyncio.Semaphore(max(1, settings.quiz_worker_concurrency))
        job_ids: list[str] = []
        db = SessionLocal()
        try:
            quiz_service.cleanup_expired(db)
            db.execute(
                text(
                    """
                    UPDATE quiz_sessions
                    SET status = 'queued', stage = 'queued', progress = 0,
                        message = '服务恢复后重新排队。', updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'processing' AND expires_at > :now
                    """
                ),
                {"now": _utc_now()},
            )
            db.commit()
            rows = db.execute(
                text(
                    """
                    SELECT id FROM quiz_sessions
                    WHERE status = 'queued' AND expires_at > :now
                    ORDER BY created_at ASC
                    """
                ),
                {"now": _utc_now()},
            ).all()
            job_ids = [str(row[0]) for row in rows]
        except Exception:
            db.rollback()
            logger.info(
                "Quiz tables are unavailable or recovery failed; skipping quiz recovery",
                exc_info=True,
            )
        finally:
            db.close()

        for job_id in job_ids:
            self.enqueue(job_id)
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="quiz-session-cleanup",
        )

    async def stop(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
            self._cleanup_task = None
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def enqueue(self, session_id: str) -> None:
        current = self._tasks.get(session_id)
        if current is not None and not current.done():
            return
        task = asyncio.create_task(
            self.process_job(session_id),
            name=f"quiz-{session_id}",
        )
        self._tasks[session_id] = task
        task.add_done_callback(lambda finished: self._task_finished(session_id, finished))

    async def process_job(self, session_id: str) -> None:
        semaphore = self._semaphore or asyncio.Semaphore(
            max(1, settings.quiz_worker_concurrency)
        )
        async with semaphore:
            db = SessionLocal()
            try:
                if not self._claim_job(db, session_id):
                    return
                await quiz_service.generate_session(
                    db,
                    session_id=session_id,
                    progress_callback=lambda stage, progress, message: self._update_progress(
                        db,
                        session_id=session_id,
                        stage=stage,
                        progress=progress,
                        message=message,
                    ),
                )
            except asyncio.CancelledError:
                self._requeue(db, session_id)
                raise
            except (QuizServiceError, LlmServiceError) as exc:
                self._mark_failed(db, session_id, str(exc))
            except Exception:
                logger.exception("Quiz background job failed: %s", session_id)
                self._mark_failed(db, session_id, "出题失败，请稍后重试。")
            finally:
                db.close()

    def _claim_job(self, db, session_id: str) -> bool:
        result = db.execute(
            text(
                """
                UPDATE quiz_sessions
                SET status = 'processing', stage = 'starting', progress = 5,
                    message = '正在准备出题资料。', error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :session_id AND status = 'queued'
                  AND expires_at > :now
                """
            ),
            {"session_id": session_id, "now": _utc_now()},
        )
        db.commit()
        return bool(result.rowcount)

    def _update_progress(
        self,
        db,
        *,
        session_id: str,
        stage: str,
        progress: int,
        message: str,
    ) -> None:
        db.execute(
            text(
                """
                UPDATE quiz_sessions
                SET stage = :stage, progress = :progress, message = :message,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :session_id AND status = 'processing'
                """
            ),
            {
                "session_id": session_id,
                "stage": stage,
                "progress": max(0, min(99, progress)),
                "message": message[:255],
            },
        )
        db.commit()

    def _mark_failed(self, db, session_id: str, message: str) -> None:
        try:
            db.execute(
                text(
                    """
                    UPDATE quiz_sessions
                    SET status = 'failed', stage = 'failed',
                        message = '出题失败。', error_message = :error_message,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :session_id
                    """
                ),
                {"session_id": session_id, "error_message": message[:1000]},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Unable to persist quiz job failure: %s", session_id)

    def _requeue(self, db, session_id: str) -> None:
        try:
            db.execute(
                text(
                    """
                    UPDATE quiz_sessions
                    SET status = 'queued', stage = 'queued', progress = 0,
                        message = '任务已重新排队。', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :session_id AND status = 'processing'
                    """
                ),
                {"session_id": session_id},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Unable to requeue quiz job: %s", session_id)

    async def _cleanup_loop(self) -> None:
        interval = max(10, settings.quiz_cleanup_interval_seconds)
        while True:
            await asyncio.sleep(interval)
            db = SessionLocal()
            try:
                removed = quiz_service.cleanup_expired(db)
                if removed:
                    logger.info("Removed %s expired quiz sessions", removed)
            except Exception:
                db.rollback()
                logger.exception("Failed to clean expired quiz sessions")
            finally:
                db.close()

    def _task_finished(self, session_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(session_id) is task:
            self._tasks.pop(session_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("Unhandled quiz task error %s: %s", session_id, error)


quiz_job_service = QuizJobService()
