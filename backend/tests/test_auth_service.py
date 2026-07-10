import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.contracts import LoginRequest, UserCreate
from app.services.auth_service import (
    AuthenticationError,
    AuthService,
    RegistrationConflictError,
)
from app.services.knowledge_base_service import knowledge_base_service


class AuthServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
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
                        status VARCHAR(20) NOT NULL DEFAULT 'active'
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
        self.service = AuthService()

    def test_register_hashes_password_and_authenticates_by_username_or_email(self) -> None:
        db = self.SessionLocal()
        try:
            payload = UserCreate(username="alice", email="Alice@Example.com", password="password123")
            user = self.service.register(db, payload)

            stored = db.execute(
                text("SELECT password_hash FROM users WHERE id = :id"),
                {"id": user.id},
            ).scalar_one()
            self.assertNotEqual(stored, payload.password)
            self.assertEqual(user.email, "alice@example.com")
            default_base = db.execute(
                text("SELECT name, visibility FROM knowledge_bases WHERE owner_id = :owner_id"),
                {"owner_id": user.id},
            ).mappings().one()
            self.assertEqual(default_base["name"], "默认知识库")
            self.assertEqual(default_base["visibility"], "private")

            by_username = self.service.authenticate(
                db,
                LoginRequest(username="alice", password="password123"),
            )
            by_email = self.service.authenticate(
                db,
                LoginRequest(username="alice@example.com", password="password123"),
            )
            self.assertEqual(by_username.id, user.id)
            self.assertEqual(by_email.id, user.id)
        finally:
            db.close()

    def test_duplicate_username_or_email_is_rejected(self) -> None:
        db = self.SessionLocal()
        try:
            self.service.register(
                db,
                UserCreate(username="alice", email="alice@example.com", password="password123"),
            )

            with self.assertRaises(RegistrationConflictError):
                self.service.register(
                    db,
                    UserCreate(username="alice", email="another@example.com", password="password123"),
                )
            with self.assertRaises(RegistrationConflictError):
                self.service.register(
                    db,
                    UserCreate(username="another", email="alice@example.com", password="password123"),
                )
        finally:
            db.close()

    def test_wrong_password_and_tampered_token_are_rejected(self) -> None:
        db = self.SessionLocal()
        try:
            user = self.service.register(
                db,
                UserCreate(username="alice", email="alice@example.com", password="password123"),
            )
            with self.assertRaises(AuthenticationError):
                self.service.authenticate(
                    db,
                    LoginRequest(username="alice", password="wrong-password"),
                )

            token = self.service.create_access_token(user)
            self.assertEqual(self.service.decode_access_token(token), user.id)
            with self.assertRaises(AuthenticationError):
                self.service.decode_access_token(f"{token}tampered")
        finally:
            db.close()

    def test_deleted_last_knowledge_base_is_not_recreated_by_listing(self) -> None:
        db = self.SessionLocal()
        try:
            user = self.service.register(
                db,
                UserCreate(username="alice", email="alice@example.com", password="password123"),
            )
            db.execute(text("DELETE FROM knowledge_bases WHERE owner_id = :owner_id"), {"owner_id": user.id})
            db.commit()

            self.assertEqual(knowledge_base_service.list_for_owner(db, user.id), [])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
