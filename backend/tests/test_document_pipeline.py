import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.document_parser import DocumentParseError, DocumentParser
from app.services.document_service import DocumentService
from app.services.embedding_client import (
    EmbeddingAuthenticationError,
    EmbeddingClient,
    EmbeddingServiceError,
)
from app.services.text_splitter import TextBlock, TextSplitter


class FailingApiEmbeddingClient(EmbeddingClient):
    def _embed_with_api(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding api unavailable")


class InvalidKeyEmbeddingClient(EmbeddingClient):
    def _embed_with_api(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingAuthenticationError("Embedding API Key 无效，请检查服务端配置。")


class EmptyResponseEmbeddingClient(EmbeddingClient):
    def _embed_with_api(self, texts: list[str]) -> list[list[float]]:
        return []


class FakeVectorStore:
    def delete_ids(self, ids: list[str]) -> None:
        return None


class DocumentPipelineTest(unittest.TestCase):
    def test_text_splitter_preserves_order_and_offsets(self):
        splitter = TextSplitter(chunk_size=30, overlap=5)
        chunks = splitter.split_blocks(
            [
                TextBlock(
                    text=(
                        "第一段介绍进程拥有独立地址空间。"
                        "第二段介绍线程共享进程资源。"
                        "第三段介绍同步互斥和并发安全。"
                    ),
                    page_no=2,
                )
            ]
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].page_no, 2)
        self.assertLess(chunks[0].start_offset, chunks[0].end_offset)
        self.assertEqual(chunks[1].chunk_index, 1)

    def test_local_embedding_is_deterministic_and_normalized(self):
        client = EmbeddingClient()
        first = client._embed_locally("进程和线程共享资源")
        second = client._embed_locally("进程和线程共享资源")

        self.assertEqual(first, second)
        self.assertEqual(len(first), client.local_dimension)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0, places=6)

    def test_embedding_api_failure_returns_controlled_error(self):
        import app.services.embedding_client as embedding_module

        client = FailingApiEmbeddingClient()

        with (
            patch.object(embedding_module.settings, "embedding_api_key", "test-key"),
            patch.object(embedding_module.settings, "embedding_model", "test-model"),
        ):
            with self.assertRaises(EmbeddingServiceError) as context:
                client.embed_texts(["进程和线程共享资源"])

        self.assertIn("Embedding 服务调用失败", str(context.exception))

    def test_invalid_embedding_api_key_returns_specific_error(self):
        import app.services.embedding_client as embedding_module

        client = InvalidKeyEmbeddingClient()
        with (
            patch.object(embedding_module.settings, "embedding_api_key", "invalid-key"),
            patch.object(embedding_module.settings, "embedding_model", "test-model"),
        ):
            with self.assertRaises(EmbeddingAuthenticationError) as context:
                client.embed_texts(["进程和线程共享资源"])

        self.assertIn("API Key 无效", str(context.exception))

    def test_incomplete_embedding_config_returns_clear_error(self):
        import app.services.embedding_client as embedding_module

        with (
            patch.object(embedding_module.settings, "embedding_api_key", "test-key"),
            patch.object(embedding_module.settings, "embedding_model", ""),
        ):
            with self.assertRaises(EmbeddingServiceError) as context:
                EmbeddingClient().embed_texts(["测试文本"])

        self.assertIn("配置不完整", str(context.exception))

    def test_empty_embedding_response_returns_clear_error(self):
        import app.services.embedding_client as embedding_module

        with (
            patch.object(embedding_module.settings, "embedding_api_key", "test-key"),
            patch.object(embedding_module.settings, "embedding_model", "test-model"),
        ):
            with self.assertRaises(EmbeddingServiceError) as context:
                EmptyResponseEmbeddingClient().embed_texts(["测试文本"])

        self.assertIn("未返回有效向量", str(context.exception))

    def test_empty_document_returns_parse_error(self):
        parser = DocumentParser()
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "empty.txt"
            file_path.write_text("   ", encoding="utf-8")

            with self.assertRaises(DocumentParseError) as context:
                parser.parse(str(file_path), "txt")

        self.assertIn("未提取到可用文字", str(context.exception))

    def test_background_processing_persists_parse_and_embedding_errors(self):
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        session_factory = sessionmaker(bind=engine)
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
                    CREATE TABLE document_chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_id INTEGER NOT NULL,
                        knowledge_base_id INTEGER NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        chunk_text TEXT NOT NULL,
                        page_no INTEGER,
                        start_offset INTEGER,
                        end_offset INTEGER,
                        vector_id TEXT NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO documents VALUES (
                        1, 1, 1, 'test.txt', 'txt', 10, 'test.txt',
                        'pending', NULL, 0
                    )
                    """
                )
            )

        scenarios = [
            (
                patch(
                    "app.services.document_service.document_parser.parse",
                    side_effect=DocumentParseError("文档解析失败：测试文件损坏。"),
                ),
                patch("app.services.document_service.embedding_client.embed_texts"),
                "文档解析失败",
            ),
            (
                patch(
                    "app.services.document_service.document_parser.parse",
                    return_value=[TextBlock(text="可解析的测试内容")],
                ),
                patch(
                    "app.services.document_service.embedding_client.embed_texts",
                    side_effect=EmbeddingServiceError("Embedding 服务调用失败，请稍后重试。"),
                ),
                "Embedding 服务调用失败",
            ),
        ]

        for parser_patch, embedding_patch, expected_message in scenarios:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE documents SET parse_status = 'pending', error_message = NULL WHERE id = 1"
                    )
                )

            with (
                patch("app.services.document_service.SessionLocal", session_factory),
                patch("app.services.document_service.get_vector_store", return_value=FakeVectorStore()),
                parser_patch,
                embedding_patch,
            ):
                DocumentService().process_document(1)

            with session_factory() as db:
                row = db.execute(
                    text("SELECT parse_status, error_message FROM documents WHERE id = 1")
                ).mappings().one()

            self.assertEqual(row["parse_status"], "failed")
            self.assertIn(expected_message, row["error_message"])


if __name__ == "__main__":
    unittest.main()
