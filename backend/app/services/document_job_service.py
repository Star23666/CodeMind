import asyncio
import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.document_service import DocumentService, document_service


logger = logging.getLogger(__name__)


class DocumentJobService:
    def __init__(self, service: DocumentService = document_service) -> None:
        self.service = service
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._semaphore: asyncio.Semaphore | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._semaphore = asyncio.Semaphore(max(1, settings.document_worker_concurrency))
        try:
            document_ids = await asyncio.to_thread(self._recover_incomplete_documents)
        except Exception:
            logger.exception("Failed to recover interrupted document jobs")
            return
        for document_id in document_ids:
            self.enqueue(document_id)

    async def stop(self) -> None:
        self._running = False
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def enqueue(self, document_id: int) -> bool:
        current = self._tasks.get(document_id)
        if current is not None and not current.done():
            return False
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(max(1, settings.document_worker_concurrency))
        task = asyncio.create_task(self._run(document_id))
        self._tasks[document_id] = task
        task.add_done_callback(lambda completed, doc_id=document_id: self._forget(doc_id, completed))
        return True

    async def _run(self, document_id: int) -> None:
        if self._semaphore is None:
            return
        async with self._semaphore:
            await asyncio.to_thread(self.service.process_document, document_id)

    def _recover_incomplete_documents(self) -> list[int]:
        db = SessionLocal()
        try:
            return self.service.recover_incomplete_documents(db)
        finally:
            db.close()

    def _forget(self, document_id: int, task: asyncio.Task[None]) -> None:
        if self._tasks.get(document_id) is task:
            self._tasks.pop(document_id, None)
        exception = None if task.cancelled() else task.exception()
        if exception is not None:
            logger.error(
                "Document worker task failed (document_id=%s)",
                document_id,
                exc_info=(type(exception), exception, exception.__traceback__),
            )


document_job_service = DocumentJobService()
