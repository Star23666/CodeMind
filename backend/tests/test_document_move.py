import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.document_service import (
    DocumentMoveConsistencyError,
    DocumentMoveError,
    DocumentService,
)
from app.services.vector_store import VectorStore


class FakeVectorStore:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls: list[tuple[list[str], list[dict[str, object]]]] = []

    def update_metadatas(self, *, ids, metadatas) -> None:
        self.calls.append((list(ids), [dict(item) for item in metadatas]))
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("simulated Chroma failure")


class DocumentMoveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        for statement in self._schema_statements():
            self.db.execute(text(statement))
        self._seed()
        self.service = DocumentService()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_move_updates_mysql_chroma_and_document_history_scope(self) -> None:
        vector_store = FakeVectorStore()
        with patch(
            "app.services.document_service.get_vector_store",
            return_value=vector_store,
        ):
            moved = self.service.move_document(
                self.db,
                document_id=21,
                target_knowledge_base_id=12,
                owner_id=1,
            )

        self.assertEqual(moved.knowledge_base_id, 12)
        self.assertEqual(
            self.db.execute(text("SELECT knowledge_base_id FROM document_chunks WHERE id = 31")).scalar_one(),
            12,
        )
        self.assertEqual(
            self.db.execute(text("SELECT knowledge_base_id FROM mind_map_histories WHERE id = 51")).scalar_one(),
            12,
        )
        self.assertEqual(len(vector_store.calls), 1)
        self.assertEqual(vector_store.calls[0][0], ["vector-31"])
        self.assertEqual(vector_store.calls[0][1][0]["knowledge_base_id"], 12)

        snapshot = self.db.execute(
            text("SELECT file_name, source_text FROM qa_sources WHERE id = 61")
        ).mappings().one()
        self.assertEqual(snapshot["file_name"], "source.txt")
        self.assertEqual(snapshot["source_text"], "历史来源快照")

    def test_vector_failure_rolls_back_mysql_and_restores_old_metadata(self) -> None:
        vector_store = FakeVectorStore(fail_first=True)
        with (
            patch(
                "app.services.document_service.get_vector_store",
                return_value=vector_store,
            ),
            self.assertRaises(DocumentMoveConsistencyError),
        ):
            self.service.move_document(
                self.db,
                document_id=21,
                target_knowledge_base_id=12,
                owner_id=1,
            )

        self.assertEqual(
            self.db.execute(text("SELECT knowledge_base_id FROM documents WHERE id = 21")).scalar_one(),
            11,
        )
        self.assertEqual(
            self.db.execute(text("SELECT knowledge_base_id FROM document_chunks WHERE id = 31")).scalar_one(),
            11,
        )
        self.assertEqual(len(vector_store.calls), 2)
        self.assertEqual(vector_store.calls[0][1][0]["knowledge_base_id"], 12)
        self.assertEqual(vector_store.calls[1][1][0]["knowledge_base_id"], 11)

    def test_move_rejects_public_busy_and_foreign_targets(self) -> None:
        cases = (
            (22, 12, "公共资料不能直接移动"),
            (23, 12, "仅已完成处理的文档"),
        )
        with patch(
            "app.services.document_service.get_vector_store",
            return_value=FakeVectorStore(),
        ):
            for document_id, target_id, message in cases:
                with self.subTest(document_id=document_id, target_id=target_id):
                    with self.assertRaisesRegex(DocumentMoveError, message):
                        self.service.move_document(
                            self.db,
                            document_id=document_id,
                            target_knowledge_base_id=target_id,
                            owner_id=1,
                        )
                    self.db.rollback()

        with self.assertRaises(ValueError):
            self.service.move_document(
                self.db,
                document_id=21,
                target_knowledge_base_id=13,
                owner_id=1,
            )
        self.db.rollback()

        with self.assertRaises(ValueError):
            self.service.move_document(
                self.db,
                document_id=24,
                target_knowledge_base_id=12,
                owner_id=1,
            )

    def _seed(self) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO users (id, username, role) VALUES
                  (1, 'alice', 'user'), (2, 'bob', 'user')
                """
            )
        )
        self.db.execute(
            text(
                """
                INSERT INTO knowledge_bases (id, owner_id, name, visibility) VALUES
                  (11, 1, '源私人库', 'private'),
                  (12, 1, '目标私人库', 'private'),
                  (13, 2, 'Bob 私人库', 'private'),
                  (100, NULL, '公共知识库', 'public')
                """
            )
        )
        for values in (
            (21, 11, 1, "source.txt", "completed"),
            (22, 100, 1, "public.txt", "completed"),
            (23, 11, 1, "busy.txt", "processing"),
            (24, 13, 2, "foreign.txt", "completed"),
        ):
            self.db.execute(
                text(
                    """
                    INSERT INTO documents
                      (id, knowledge_base_id, owner_id, file_name, file_type, file_size,
                       file_path, parse_status, chunk_count)
                    VALUES (:id, :kb, :owner, :name, 'txt', 20, '/tmp/file', :status, 1)
                    """
                ),
                {"id": values[0], "kb": values[1], "owner": values[2], "name": values[3], "status": values[4]},
            )
        self.db.execute(
            text(
                """
                INSERT INTO document_chunks
                  (id, document_id, knowledge_base_id, chunk_index, chunk_text,
                   page_no, start_offset, end_offset, vector_id)
                VALUES (31, 21, 11, 0, '测试片段', 1, 0, 4, 'vector-31')
                """
            )
        )
        self.db.execute(
            text(
                """
                INSERT INTO mind_map_histories (id, user_id, knowledge_base_id, document_id)
                VALUES (51, 1, 11, 21)
                """
            )
        )
        self.db.execute(
            text(
                """
                INSERT INTO qa_sources (id, document_id, chunk_id, file_name, source_text)
                VALUES (61, 21, 31, 'source.txt', '历史来源快照')
                """
            )
        )
        self.db.commit()

    @staticmethod
    def _schema_statements() -> list[str]:
        return [
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT)",
            """
            CREATE TABLE knowledge_bases (
              id INTEGER PRIMARY KEY, owner_id INTEGER, name TEXT, description TEXT,
              visibility TEXT,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE documents (
              id INTEGER PRIMARY KEY, knowledge_base_id INTEGER, owner_id INTEGER,
              file_name TEXT, file_type TEXT, file_size INTEGER, file_path TEXT,
              parse_status TEXT, error_message TEXT, chunk_count INTEGER,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE document_chunks (
              id INTEGER PRIMARY KEY, document_id INTEGER, knowledge_base_id INTEGER,
              chunk_index INTEGER, chunk_text TEXT, page_no INTEGER,
              start_offset INTEGER, end_offset INTEGER, vector_id TEXT
            )
            """,
            """
            CREATE TABLE mind_map_histories (
              id INTEGER PRIMARY KEY, user_id INTEGER, knowledge_base_id INTEGER,
              document_id INTEGER
            )
            """,
            """
            CREATE TABLE qa_sources (
              id INTEGER PRIMARY KEY, document_id INTEGER, chunk_id INTEGER,
              file_name TEXT, source_text TEXT
            )
            """,
        ]


class VectorMetadataVerificationTest(unittest.TestCase):
    def test_update_metadatas_rejects_missing_or_stale_records(self) -> None:
        class FakeCollection:
            def __init__(self, stored):
                self.stored = stored

            def update(self, *, ids, metadatas) -> None:
                pass

            def get(self, *, ids, include):
                found_ids = [vector_id for vector_id in ids if vector_id in self.stored]
                return {
                    "ids": found_ids,
                    "metadatas": [self.stored[vector_id] for vector_id in found_ids],
                }

        store = VectorStore.__new__(VectorStore)
        store.collection = FakeCollection({"vector-1": {"knowledge_base_id": 12}})
        store.update_metadatas(
            ids=["vector-1"],
            metadatas=[{"knowledge_base_id": 12}],
        )

        store.collection = FakeCollection({})
        with self.assertRaisesRegex(RuntimeError, "vector-1"):
            store.update_metadatas(
                ids=["vector-1"],
                metadatas=[{"knowledge_base_id": 12}],
            )


if __name__ == "__main__":
    unittest.main()
