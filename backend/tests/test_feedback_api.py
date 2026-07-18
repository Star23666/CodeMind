import sys
import unittest
from pathlib import Path

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


class FeedbackApiTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        username TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        email TEXT NOT NULL,
                        role TEXT NOT NULL,
                        status TEXT NOT NULL,
                        token_version INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE knowledge_bases (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        visibility TEXT NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE qa_records (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        knowledge_base_id INTEGER NOT NULL,
                        question TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        source_count INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE feedbacks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        qa_record_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        rating INTEGER NOT NULL,
                        comment TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (qa_record_id, user_id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO users VALUES
                      (1, 'alice', 'unused', 'alice@example.com', 'user', 'active', 0),
                      (2, 'bob', 'unused', 'bob@example.com', 'user', 'active', 0),
                      (3, 'admin', 'unused', 'admin@example.com', 'admin', 'active', 0)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO knowledge_bases (id, name, visibility)
                    VALUES (100, '测试知识库', 'public')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO qa_records (id, user_id, knowledge_base_id, question, answer)
                    VALUES (10, 1, 100, '什么是进程？', '进程是资源分配单位。')
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

    def _headers(self, user_id: int, role: str = "user") -> dict[str, str]:
        user = UserRead(
            id=user_id,
            username={1: "alice", 2: "bob", 3: "admin"}[user_id],
            email=f"user{user_id}@example.com",
            role=role,
            status="active",
        )
        token = auth_service.create_access_token(user, token_version=0)
        return {"Authorization": f"Bearer {token}"}

    def test_feedback_persists_and_duplicate_returns_conflict(self) -> None:
        response = self.client.post(
            "/api/qa-records/10/feedback",
            headers=self._headers(1),
            json={"rating": 5, "comment": "回答准确"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["qa_record_id"], 10)

        stored = self.client.get(
            "/api/qa-records/10/feedback",
            headers=self._headers(1),
        )
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["rating"], 5)

        duplicate = self.client.post(
            "/api/qa-records/10/feedback",
            headers=self._headers(1),
            json={"rating": 4},
        )
        self.assertEqual(duplicate.status_code, 409)

        with self.SessionLocal() as db:
            persisted = db.execute(text("SELECT rating, comment FROM feedbacks")).mappings().one()
        self.assertEqual(persisted["rating"], 5)
        self.assertEqual(persisted["comment"], "回答准确")

    def test_feedback_rejects_other_users_record(self) -> None:
        response = self.client.post(
            "/api/qa-records/10/feedback",
            headers=self._headers(2),
            json={"rating": 1},
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_list_is_real_filterable_and_protected(self) -> None:
        self.client.post(
            "/api/qa-records/10/feedback",
            headers=self._headers(1),
            json={"rating": 5, "comment": "good"},
        )

        forbidden = self.client.get("/api/admin/feedbacks", headers=self._headers(1))
        self.assertEqual(forbidden.status_code, 403)

        admin_headers = self._headers(3, role="admin")
        all_feedback = self.client.get("/api/admin/feedbacks", headers=admin_headers)
        self.assertEqual(all_feedback.status_code, 200)
        self.assertEqual(len(all_feedback.json()), 1)
        self.assertEqual(all_feedback.json()[0]["username"], "alice")
        self.assertEqual(all_feedback.json()[0]["knowledge_base_name"], "测试知识库")
        self.assertEqual(all_feedback.json()[0]["question"], "什么是进程？")
        self.assertFalse(all_feedback.json()[0]["content_redacted"])

        matching = self.client.get(
            "/api/admin/feedbacks?rating=5&user_id=1&knowledge_base_id=100",
            headers=admin_headers,
        )
        self.assertEqual(len(matching.json()), 1)
        not_matching = self.client.get(
            "/api/admin/feedbacks?rating=2",
            headers=admin_headers,
        )
        self.assertEqual(not_matching.json(), [])


if __name__ == "__main__":
    unittest.main()
