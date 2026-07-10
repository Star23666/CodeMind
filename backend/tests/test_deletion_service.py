import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import app.services.document_service as document_module
from app.services.document_service import DocumentService


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted_ids: list[str] = []

    def delete_ids(self, ids: list[str]) -> None:
        self.deleted_ids.extend(ids)


class KnowledgeBaseDeletionTest(unittest.TestCase):
    def test_deleting_knowledge_base_removes_vectors_database_rows_and_files(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        SessionLocal = sessionmaker(bind=engine)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE knowledge_bases (
                        id INTEGER PRIMARY KEY,
                        owner_id INTEGER NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        visibility VARCHAR(20) NOT NULL DEFAULT 'private',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE documents (
                        id INTEGER PRIMARY KEY,
                        knowledge_base_id INTEGER NOT NULL,
                        owner_id INTEGER NOT NULL,
                        file_path VARCHAR(500) NOT NULL,
                        FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE document_chunks (
                        id INTEGER PRIMARY KEY,
                        document_id INTEGER NOT NULL,
                        vector_id VARCHAR(128) NOT NULL,
                        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                    )
                    """
                )
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir)
            knowledge_base_dir = upload_dir / "1" / "10"
            knowledge_base_dir.mkdir(parents=True)
            uploaded_file = knowledge_base_dir / "document.txt"
            uploaded_file.write_text("test document", encoding="utf-8")

            db = SessionLocal()
            try:
                db.execute(text("INSERT INTO users (id) VALUES (1)"))
                db.execute(
                    text(
                        """
                        INSERT INTO knowledge_bases (id, owner_id, name, description, visibility)
                        VALUES (10, 1, '测试知识库', NULL, 'private')
                        """
                    )
                )
                db.execute(
                    text(
                        """
                        INSERT INTO documents (id, knowledge_base_id, owner_id, file_path)
                        VALUES (20, 10, 1, :file_path)
                        """
                    ),
                    {"file_path": str(uploaded_file)},
                )
                db.execute(
                    text(
                        """
                        INSERT INTO document_chunks (id, document_id, vector_id)
                        VALUES (30, 20, 'vector-30')
                        """
                    )
                )
                db.commit()

                vector_store = FakeVectorStore()
                with (
                    patch.object(document_module.settings, "upload_dir", str(upload_dir)),
                    patch.object(document_module, "get_vector_store", return_value=vector_store),
                ):
                    DocumentService().delete_knowledge_base(db, knowledge_base_id=10, owner_id=1)

                self.assertEqual(vector_store.deleted_ids, ["vector-30"])
                self.assertEqual(db.execute(text("SELECT COUNT(*) FROM knowledge_bases")).scalar_one(), 0)
                self.assertEqual(db.execute(text("SELECT COUNT(*) FROM documents")).scalar_one(), 0)
                self.assertEqual(db.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar_one(), 0)
                self.assertFalse(uploaded_file.exists())
                self.assertFalse(knowledge_base_dir.exists())
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
