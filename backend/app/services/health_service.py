import logging

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.vector_store import get_vector_store


logger = logging.getLogger(__name__)


class HealthService:
    def check_readiness(self) -> dict[str, object]:
        checks: dict[str, str] = {"mysql": "ok", "chroma": "ok"}

        db = None
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
        except Exception:
            logger.warning("MySQL readiness check failed", exc_info=True)
            checks["mysql"] = "unavailable"
        finally:
            if db is not None:
                db.close()

        try:
            vector_store = get_vector_store()
            heartbeat = getattr(vector_store.client, "heartbeat", None)
            if heartbeat is None:
                raise RuntimeError("Chroma client does not expose heartbeat")
            heartbeat()
        except Exception:
            logger.warning("Chroma readiness check failed", exc_info=True)
            checks["chroma"] = "unavailable"

        ready = all(value == "ok" for value in checks.values())
        return {
            "status": "ok" if ready else "unavailable",
            "checks": checks,
        }


health_service = HealthService()
