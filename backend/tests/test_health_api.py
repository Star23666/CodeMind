import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.main import create_app
from app.services.health_service import HealthService


class HealthApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_liveness_does_not_depend_on_mysql_or_chroma(self) -> None:
        with patch(
            "app.api.routes.health_service.check_readiness",
            side_effect=AssertionError("liveness must not run dependency checks"),
        ):
            response = self.client.get("/api/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_and_legacy_health_return_503_for_dependency_failure(self) -> None:
        report = {
            "status": "unavailable",
            "checks": {"mysql": "unavailable", "chroma": "ok"},
        }
        with patch("app.api.routes.health_service.check_readiness", return_value=report):
            readiness = self.client.get("/api/health/ready")
            legacy = self.client.get("/api/health")
        self.assertEqual(readiness.status_code, 503)
        self.assertEqual(legacy.status_code, 503)
        self.assertEqual(readiness.json(), report)

    def test_readiness_checks_mysql_and_chroma_without_online_model_calls(self) -> None:
        db = Mock()
        vector_store = SimpleNamespace(client=Mock())
        with (
            patch("app.services.health_service.SessionLocal", return_value=db),
            patch("app.services.health_service.get_vector_store", return_value=vector_store),
        ):
            report = HealthService().check_readiness()

        self.assertEqual(report["status"], "ok")
        db.execute.assert_called_once()
        db.close.assert_called_once()
        vector_store.client.heartbeat.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
