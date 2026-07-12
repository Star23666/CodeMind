import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.main import create_app
from app.schemas.contracts import UserRead


class DocumentContentApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_root = Path(self.temp_dir.name)
        owned_file = self.upload_root / "1" / "1" / "example.md"
        owned_file.parent.mkdir(parents=True)
        owned_file.write_text("# 原文件标题\n\n正文内容", encoding="utf-8")

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
                    CREATE TABLE documents (
                        id INTEGER PRIMARY KEY,
                        knowledge_base_id INTEGER NOT NULL,
                        owner_id INTEGER NOT NULL,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_path TEXT NOT NULL,
                        parse_status TEXT NOT NULL,
                        error_message TEXT,
                        chunk_count INTEGER NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO documents VALUES (
                        1, 1, 1, 'example.md', 'md', :file_size, :file_path,
                        'completed', NULL, 1
                    )
                    """
                ),
                {"file_size": owned_file.stat().st_size, "file_path": str(owned_file)},
            )

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app = create_app()
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: UserRead(
            id=1,
            username="alice",
            email="alice@example.com",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_owner_can_read_original_file_inline(self) -> None:
        with patch.object(settings, "upload_dir", str(self.upload_root)):
            response = self.client.get("/api/documents/1/content")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8").replace("\r\n", "\n")
        self.assertEqual(content, "# 原文件标题\n\n正文内容")
        self.assertIn("text/markdown", response.headers["content-type"])
        self.assertTrue(response.headers["content-disposition"].startswith("inline"))

    def test_other_user_cannot_read_file(self) -> None:
        app = self.client.app
        app.dependency_overrides[get_current_user] = lambda: UserRead(
            id=2,
            username="bob",
            email="bob@example.com",
        )
        with patch.object(settings, "upload_dir", str(self.upload_root)):
            response = self.client.get("/api/documents/1/content")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
