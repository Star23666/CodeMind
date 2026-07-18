import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import get_db
from app.main import create_app
from app.schemas.contracts import UserRead
from app.services.auth_service import auth_service


class Issue28AdminApiTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=engine)
        with engine.begin() as connection:
            for statement in self._schema_statements():
                connection.execute(text(statement))
            connection.execute(
                text(
                    """
                    INSERT INTO users
                      (id, username, password_hash, email, role, status, token_version)
                    VALUES
                      (1, 'alice', 'unused', 'alice@example.com', 'user', 'active', 0),
                      (2, 'bob', 'unused', 'bob@example.com', 'user', 'disabled', 0),
                      (3, 'admin', 'unused', 'admin@example.com', 'admin', 'active', 0),
                      (4, 'backup-admin', 'unused', 'backup@example.com', 'admin', 'active', 0)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO knowledge_bases (id, owner_id, name, visibility) VALUES
                      (11, 1, 'Alice 私人库', 'private'),
                      (100, NULL, '公共知识库', 'public')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO documents
                      (id, knowledge_base_id, owner_id, file_name, file_type, file_size,
                       file_path, parse_status, error_message, chunk_count)
                    VALUES
                      (21, 11, 1, 'private-notes.txt', 'txt', 20, '/private', 'failed',
                       '解析失败', 0),
                      (22, 100, 1, 'public-notes.txt', 'txt', 30, '/public', 'completed',
                       NULL, 2)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO qa_records
                      (id, user_id, knowledge_base_id, question, answer, source_count)
                    VALUES (31, 1, 11, '测试问题', '测试回答', 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO feedbacks (id, qa_record_id, user_id, rating, comment)
                    VALUES (41, 31, 1, 2, '需要改进')
                    """
                )
            )

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app = create_app()
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def _headers(self, user_id: int, role: str) -> dict[str, str]:
        user = UserRead(
            id=user_id,
            username="admin" if role == "admin" else "alice",
            email=f"user{user_id}@example.com",
            role=role,
            status="active",
        )
        return {
            "Authorization": f"Bearer {auth_service.create_access_token(user, token_version=0)}"
        }

    def test_admin_routes_are_protected_and_overview_is_sanitized(self) -> None:
        user_headers = self._headers(1, "user")
        for path in ("/api/admin/overview", "/api/admin/users", "/api/admin/documents"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=user_headers).status_code, 403)

        with patch(
            "app.services.admin_service.health_service.check_readiness",
            return_value={"status": "ok", "checks": {"mysql": "ok", "chroma": "ok"}},
        ):
            response = self.client.get("/api/admin/overview", headers=self._headers(3, "admin"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["users_total"], 4)
        self.assertEqual(body["documents_failed"], 1)
        self.assertEqual(body["feedbacks_total"], 1)
        self.assertEqual(body["readiness"]["status"], "ok")

        documents = self.client.get(
            "/api/admin/documents",
            headers=self._headers(3, "admin"),
        ).json()
        private_document = next(item for item in documents if item["id"] == 21)
        public_document = next(item for item in documents if item["id"] == 22)
        self.assertIsNone(private_document["file_name"])
        self.assertIsNone(private_document["knowledge_base_name"])
        self.assertFalse(private_document["can_manage"])
        self.assertEqual(private_document["error_message"], "私人文档处理失败，错误详情已隐藏。")
        self.assertNotIn("解析失败", private_document["error_message"])
        self.assertEqual(public_document["file_name"], "public-notes.txt")
        self.assertTrue(public_document["can_manage"])

        private_anomaly = next(
            item for item in body["recent_anomalies"] if item["resource_type"] == "document"
        )
        self.assertEqual(private_anomaly["message"], "私人文档处理失败，错误详情已隐藏。")

        feedbacks = self.client.get(
            "/api/admin/feedbacks",
            headers=self._headers(3, "admin"),
        ).json()
        self.assertEqual(len(feedbacks), 1)
        self.assertTrue(feedbacks[0]["content_redacted"])
        self.assertIsNone(feedbacks[0]["knowledge_base_name"])
        self.assertIsNone(feedbacks[0]["question"])
        self.assertIsNone(feedbacks[0]["answer"])
        self.assertEqual(feedbacks[0]["comment"], "需要改进")

    def test_user_filters_and_status_changes_revoke_tokens(self) -> None:
        admin_headers = self._headers(3, "admin")
        users = self.client.get("/api/admin/users?query=alice", headers=admin_headers)
        self.assertEqual(users.status_code, 200)
        self.assertEqual([item["username"] for item in users.json()], ["alice"])

        disabled = self.client.patch(
            "/api/admin/users/1/status",
            headers=admin_headers,
            json={"status": "disabled"},
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["status"], "disabled")
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self._headers(1, "user")).status_code,
            403,
        )

        enabled = self.client.patch(
            "/api/admin/users/1/status",
            headers=admin_headers,
            json={"status": "active"},
        )
        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(enabled.json()["status"], "active")

        self_disable = self.client.patch(
            "/api/admin/users/3/status",
            headers=admin_headers,
            json={"status": "disabled"},
        )
        self.assertEqual(self_disable.status_code, 409)

        backup_disabled = self.client.patch(
            "/api/admin/users/4/status",
            headers=admin_headers,
            json={"status": "disabled"},
        )
        self.assertEqual(backup_disabled.status_code, 200)
        self.assertEqual(backup_disabled.json()["status"], "disabled")

    @staticmethod
    def _schema_statements() -> list[str]:
        return [
            """
            CREATE TABLE users (
              id INTEGER PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL,
              email TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL,
              token_version INTEGER NOT NULL DEFAULT 0,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE knowledge_bases (
              id INTEGER PRIMARY KEY, owner_id INTEGER, name TEXT NOT NULL,
              visibility TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE documents (
              id INTEGER PRIMARY KEY, knowledge_base_id INTEGER NOT NULL, owner_id INTEGER NOT NULL,
              file_name TEXT NOT NULL, file_type TEXT NOT NULL, file_size INTEGER NOT NULL,
              file_path TEXT NOT NULL, parse_status TEXT NOT NULL, error_message TEXT,
              chunk_count INTEGER NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE qa_records (
              id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, knowledge_base_id INTEGER NOT NULL,
              question TEXT NOT NULL, answer TEXT NOT NULL, source_count INTEGER NOT NULL DEFAULT 0,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE feedbacks (
              id INTEGER PRIMARY KEY, qa_record_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
              rating INTEGER NOT NULL, comment TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE mind_map_jobs (
              id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, knowledge_base_id INTEGER NOT NULL,
              status TEXT NOT NULL, error_message TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE quiz_sessions (
              id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, status TEXT NOT NULL,
              error_message TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]


if __name__ == "__main__":
    unittest.main()
