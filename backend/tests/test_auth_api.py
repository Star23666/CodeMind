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


class AuthApiTest(unittest.TestCase):
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
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username VARCHAR(50) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        email VARCHAR(120) NOT NULL UNIQUE,
                        role VARCHAR(20) NOT NULL DEFAULT 'user',
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        token_version INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE knowledge_bases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_id INTEGER NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        visibility VARCHAR(20) NOT NULL DEFAULT 'private',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (owner_id, name)
                    )
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

    def test_authentication_flow_and_protected_route(self) -> None:
        unauthorized = self.client.get("/api/knowledge-bases")
        self.assertEqual(unauthorized.status_code, 401)

        registration = self.client.post(
            "/api/auth/register",
            json={
                "username": "alice",
                "email": "Alice@Example.com",
                "password": "password123",
            },
        )
        self.assertEqual(registration.status_code, 201)
        self.assertEqual(registration.json()["email"], "alice@example.com")

        duplicate = self.client.post(
            "/api/auth/register",
            json={
                "username": "alice",
                "email": "another@example.com",
                "password": "password123",
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        invalid_login = self.client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )
        self.assertEqual(invalid_login.status_code, 401)

        login = self.client.post(
            "/api/auth/login",
            json={"username": "alice@example.com", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200)
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        current_user = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(current_user.status_code, 200)
        self.assertEqual(current_user.json()["username"], "alice")

        knowledge_bases = self.client.get("/api/knowledge-bases", headers=headers)
        self.assertEqual(knowledge_bases.status_code, 200)
        self.assertEqual([item["name"] for item in knowledge_bases.json()], ["默认知识库"])

        logout = self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(logout.status_code, 200)

        revoked = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(revoked.status_code, 401)

        relogin = self.client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "password123"},
        )
        self.assertEqual(relogin.status_code, 200)
        refreshed_headers = {
            "Authorization": f"Bearer {relogin.json()['access_token']}"
        }
        self.assertEqual(
            self.client.get("/api/auth/me", headers=refreshed_headers).status_code,
            200,
        )

        tampered = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}tampered"},
        )
        self.assertEqual(tampered.status_code, 401)


if __name__ == "__main__":
    unittest.main()
