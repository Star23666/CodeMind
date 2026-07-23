import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.document_job_service import DocumentJobService
from app.services.document_service import DocumentBusyError, DocumentService
from app.services.embedding_client import EmbeddingServiceError
from app.services.retrieval_service import RetrievalService
from app.services.vector_store import VectorSearchHit
from app.schemas.contracts import ChatRequest


class RecordingVectorStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []
        self.deletes: list[list[str]] = []

    def upsert_chunks(self, **kwargs) -> None:
        self.upserts.append(kwargs)

    def delete_ids(self, ids: list[str]) -> None:
        self.deletes.append(list(ids))


class DocumentReliabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        role TEXT NOT NULL DEFAULT 'user'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE knowledge_bases (
                        id INTEGER PRIMARY KEY,
                        owner_id INTEGER,
                        name TEXT NOT NULL DEFAULT 'test',
                        description TEXT,
                        visibility TEXT NOT NULL
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
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_path TEXT NOT NULL,
                        parse_status TEXT NOT NULL,
                        error_message TEXT,
                        chunk_count INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(text("INSERT INTO users (id) VALUES (7)"))
            connection.execute(
                text(
                    """
                    INSERT INTO knowledge_bases (id, owner_id, visibility)
                    VALUES (10, 7, 'private')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE document_chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_id INTEGER NOT NULL,
                        knowledge_base_id INTEGER NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        chunk_text TEXT NOT NULL,
                        page_no INTEGER,
                        start_offset INTEGER,
                        end_offset INTEGER,
                        vector_id TEXT NOT NULL UNIQUE,
                        UNIQUE (document_id, chunk_index)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        id, knowledge_base_id, owner_id, file_name, file_type,
                        file_size, file_path, parse_status, chunk_count
                    ) VALUES (1, 10, 7, 'notes.txt', 'txt', 20, 'notes.txt', 'completed', 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO document_chunks (
                        document_id, knowledge_base_id, chunk_index, chunk_text,
                        page_no, start_offset, end_offset, vector_id
                    ) VALUES (1, 10, 0, '旧索引内容', 1, 0, 5, 'old-vector')
                    """
                )
            )

    def _status(self, document_id: int = 1):
        with self.SessionLocal() as db:
            return db.execute(
                text(
                    "SELECT parse_status, error_message, chunk_count "
                    "FROM documents WHERE id = :id"
                ),
                {"id": document_id},
            ).mappings().one()

    def _chunks(self) -> list[dict[str, object]]:
        with self.SessionLocal() as db:
            return [
                dict(row)
                for row in db.execute(
                    text(
                        "SELECT chunk_text, vector_id FROM document_chunks "
                        "WHERE document_id = 1 ORDER BY chunk_index"
                    )
                ).mappings()
            ]

    def _processing_patches(self, vector_store: RecordingVectorStore):
        chunks = [
            SimpleNamespace(
                chunk_index=0,
                text="新索引第一段",
                page_no=1,
                start_offset=0,
                end_offset=7,
            ),
            SimpleNamespace(
                chunk_index=1,
                text="新索引第二段",
                page_no=2,
                start_offset=8,
                end_offset=15,
            ),
        ]
        return (
            patch("app.services.document_service.SessionLocal", self.SessionLocal),
            patch("app.services.document_service.document_parser.parse", return_value=[object()]),
            patch("app.services.document_service.text_splitter.split_blocks", return_value=chunks),
            patch(
                "app.services.document_service.embedding_client.embed_texts",
                return_value=[[0.1, 0.2], [0.3, 0.4]],
            ),
            patch("app.services.document_service.get_vector_store", return_value=vector_store),
        )

    def test_reindex_is_atomic_and_rejects_a_second_queue_request(self) -> None:
        service = DocumentService()
        with self.SessionLocal() as db:
            service.queue_reindex(db, document_id=1, owner_id=7)
            with self.assertRaises(DocumentBusyError):
                service.queue_reindex(db, document_id=1, owner_id=7)

        self.assertEqual(self._status()["parse_status"], "pending")
        self.assertEqual(self._chunks()[0]["vector_id"], "old-vector")

    def test_successful_reindex_swaps_index_and_old_vectors_once(self) -> None:
        service = DocumentService()
        store = RecordingVectorStore()
        with self.SessionLocal() as db:
            service.queue_reindex(db, document_id=1, owner_id=7)

        patches = self._processing_patches(store)
        with patches[0], patches[1] as parser, patches[2], patches[3], patches[4]:
            service.process_document(1)
            service.process_document(1)

        status = self._status()
        chunks = self._chunks()
        self.assertEqual(status["parse_status"], "completed")
        self.assertEqual(status["chunk_count"], 2)
        self.assertEqual([row["chunk_text"] for row in chunks], ["新索引第一段", "新索引第二段"])
        self.assertEqual(len(store.upserts), 1)
        self.assertEqual(store.deletes, [["old-vector"]])
        parser.assert_called_once()

    def test_embedding_failure_preserves_previous_database_and_vector_index(self) -> None:
        service = DocumentService()
        store = RecordingVectorStore()
        with self.SessionLocal() as db:
            service.queue_reindex(db, document_id=1, owner_id=7)

        with (
            patch("app.services.document_service.SessionLocal", self.SessionLocal),
            patch("app.services.document_service.document_parser.parse", return_value=[object()]),
            patch(
                "app.services.document_service.text_splitter.split_blocks",
                return_value=[SimpleNamespace(text="new")],
            ),
            patch(
                "app.services.document_service.embedding_client.embed_texts",
                side_effect=EmbeddingServiceError("embedding unavailable"),
            ),
            patch("app.services.document_service.get_vector_store", return_value=store),
        ):
            service.process_document(1)

        status = self._status()
        self.assertEqual(status["parse_status"], "failed")
        self.assertEqual(status["chunk_count"], 1)
        self.assertIn("embedding unavailable", status["error_message"])
        self.assertEqual(self._chunks(), [{"chunk_text": "旧索引内容", "vector_id": "old-vector"}])
        self.assertEqual(store.upserts, [])
        self.assertEqual(store.deletes, [])

        with patch("app.services.retrieval_service.SessionLocal", self.SessionLocal):
            self.assertTrue(RetrievalService()._has_searchable_content(10, 7))

    def test_retrieval_drops_stale_chroma_hits_not_present_in_mysql(self) -> None:
        service = RetrievalService()
        request = ChatRequest(
            knowledge_base_id=10,
            question="旧索引内容是什么？",
            score_threshold=0.0,
            enable_rerank=False,
        )
        current_hit = VectorSearchHit(
            vector_id="old-vector",
            text="旧索引内容",
            metadata={
                "document_id": 1,
                "chunk_id": 1,
                "chunk_index": 0,
                "file_name": "notes.txt",
            },
            score=0.9,
        )
        stale_hit = VectorSearchHit(
            vector_id="stale-vector",
            text="已经失效的内容",
            metadata={
                "document_id": 1,
                "chunk_id": 99,
                "chunk_index": 0,
                "file_name": "notes.txt",
            },
            score=0.99,
        )
        store = Mock()
        store.search.return_value = [stale_hit, current_hit]

        with (
            patch("app.services.retrieval_service.SessionLocal", self.SessionLocal),
            patch(
                "app.services.retrieval_service.embedding_client.embed_texts",
                return_value=[[0.1, 0.2]],
            ),
            patch("app.services.retrieval_service.get_vector_store", return_value=store),
        ):
            sources = service.retrieve_sources(request.question, request, user_id=7)

        self.assertEqual([source.source_text for source in sources], ["旧索引内容"])

    def test_lexical_retrieval_respects_private_owner_and_public_scope(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id) VALUES (8)"))
            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        id, knowledge_base_id, owner_id, file_name, file_type,
                        file_size, file_path, parse_status, chunk_count
                    ) VALUES (
                        2, 10, 8, 'other.txt', 'txt', 20, 'other.txt',
                        'completed', 1
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO document_chunks (
                        document_id, knowledge_base_id, chunk_index, chunk_text,
                        page_no, start_offset, end_offset, vector_id
                    ) VALUES (
                        2, 10, 0, '其他用户的独有配置内容',
                        1, 0, 30, 'other-vector'
                    )
                    """
                )
            )

        service = RetrievalService()
        store = Mock()
        store.get_metadatas.return_value = {
            "old-vector": {"section_title": "普通章节"},
            "other-vector": {"section_title": "alpha_private_token"},
        }
        with (
            patch("app.services.retrieval_service.SessionLocal", self.SessionLocal),
            patch("app.services.retrieval_service.get_vector_store", return_value=store),
        ):
            private_hits = service._lexical_hits(
                query="alpha_private_token",
                knowledge_base_id=10,
                owner_id=7,
            )
            public_hits = service._lexical_hits(
                query="alpha_private_token",
                knowledge_base_id=10,
                owner_id=None,
            )

        self.assertEqual(private_hits, [])
        self.assertEqual([hit.vector_id for hit in public_hits], ["other-vector"])
        self.assertEqual(public_hits[0].metadata["document_id"], 2)
        self.assertEqual(
            public_hits[0].metadata["section_title"], "alpha_private_token"
        )

    def test_cancellation_during_embedding_preserves_previous_index(self) -> None:
        service = DocumentService()
        store = RecordingVectorStore()
        with self.SessionLocal() as db:
            service.queue_reindex(db, document_id=1, owner_id=7)

        def cancel_then_return(_texts):
            with self.SessionLocal() as cancel_db:
                service.cancel_processing(cancel_db, document_id=1, owner_id=7)
            return [[0.1, 0.2]]

        with (
            patch("app.services.document_service.SessionLocal", self.SessionLocal),
            patch("app.services.document_service.document_parser.parse", return_value=[object()]),
            patch(
                "app.services.document_service.text_splitter.split_blocks",
                return_value=[
                    SimpleNamespace(
                        chunk_index=0,
                        text="new",
                        page_no=1,
                        start_offset=0,
                        end_offset=3,
                    )
                ],
            ),
            patch(
                "app.services.document_service.embedding_client.embed_texts",
                side_effect=cancel_then_return,
            ),
            patch("app.services.document_service.get_vector_store", return_value=store),
        ):
            service.process_document(1)

        self.assertEqual(self._status()["parse_status"], "cancelled")
        self.assertEqual(self._chunks()[0]["vector_id"], "old-vector")
        self.assertEqual(store.upserts, [])

    def test_oversized_parsed_content_stops_before_embedding_and_preserves_index(self) -> None:
        service = DocumentService()
        with self.SessionLocal() as db:
            service.queue_reindex(db, document_id=1, owner_id=7)

        with (
            patch("app.services.document_service.SessionLocal", self.SessionLocal),
            patch(
                "app.services.document_service.document_parser.parse",
                return_value=[SimpleNamespace(text="内容过长")],
            ),
            patch("app.services.document_service.settings.document_max_parsed_chars", 2),
            patch("app.services.document_service.embedding_client.embed_texts") as embed,
        ):
            service.process_document(1)

        embed.assert_not_called()
        self.assertEqual(self._status()["parse_status"], "failed")
        self.assertIn("文字过多", self._status()["error_message"])
        self.assertEqual(self._chunks()[0]["vector_id"], "old-vector")

    def test_excessive_chunk_count_stops_before_embedding_and_preserves_index(self) -> None:
        service = DocumentService()
        with self.SessionLocal() as db:
            service.queue_reindex(db, document_id=1, owner_id=7)

        chunks = [
            SimpleNamespace(
                chunk_index=index,
                text=f"片段 {index}",
                page_no=1,
                start_offset=index,
                end_offset=index + 1,
            )
            for index in range(3)
        ]
        with (
            patch("app.services.document_service.SessionLocal", self.SessionLocal),
            patch(
                "app.services.document_service.document_parser.parse",
                return_value=[SimpleNamespace(text="可解析内容")],
            ),
            patch("app.services.document_service.text_splitter.split_blocks", return_value=chunks),
            patch("app.services.document_service.settings.document_max_chunks", 2),
            patch("app.services.document_service.embedding_client.embed_texts") as embed,
        ):
            service.process_document(1)

        embed.assert_not_called()
        self.assertEqual(self._status()["parse_status"], "failed")
        self.assertIn("片段过多", self._status()["error_message"])
        self.assertEqual(self._chunks()[0]["vector_id"], "old-vector")

    def test_startup_recovery_requeues_processing_and_pending_documents(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE documents SET parse_status = 'processing' WHERE id = 1"))
            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        id, knowledge_base_id, owner_id, file_name, file_type,
                        file_size, file_path, parse_status, chunk_count
                    ) VALUES (2, 10, 7, 'second.txt', 'txt', 10, 'second.txt', 'pending', 0)
                    """
                )
            )

        with self.SessionLocal() as db:
            recovered = DocumentService().recover_incomplete_documents(db)

        self.assertEqual(recovered, [1, 2])
        status = self._status()
        self.assertEqual(status["parse_status"], "pending")
        self.assertIn("服务重启", status["error_message"])


class DocumentJobServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_recovers_jobs_and_local_duplicate_enqueue_is_rejected(self) -> None:
        processed: list[int] = []
        fake_service = Mock()
        fake_service.process_document.side_effect = processed.append
        jobs = DocumentJobService(service=fake_service)

        with patch.object(jobs, "_recover_incomplete_documents", return_value=[4, 5]):
            await jobs.start()
            self.assertFalse(jobs.enqueue(4))
            await asyncio.gather(*list(jobs._tasks.values()))

        self.assertCountEqual(processed, [4, 5])
        await jobs.stop()


if __name__ == "__main__":
    unittest.main()
