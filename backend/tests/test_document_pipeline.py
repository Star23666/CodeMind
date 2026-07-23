import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
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
from app.services.embedding_text import build_embedding_text
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


class BatchRecordingEmbeddingClient(EmbeddingClient):
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def _embed_with_api(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[float(len(text)), 1.0] for text in texts]


class RecordingEmbeddings:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.3, 0.4]),
                SimpleNamespace(index=0, embedding=[0.1, 0.2]),
            ]
        )


class RecordingEmbeddingClient:
    def __init__(self) -> None:
        self.embeddings = RecordingEmbeddings()


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

    def test_text_splitter_preserves_section_title(self):
        chunks = TextSplitter(chunk_size=30, overlap=5).split_blocks(
            [TextBlock(text="进程和线程。" * 10, section_title="操作系统 > 并发")]
        )

        self.assertTrue(chunks)
        self.assertTrue(all(chunk.section_title == "操作系统 > 并发" for chunk in chunks))

    def test_markdown_parser_preserves_heading_hierarchy(self):
        parser = DocumentParser()
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "os.md"
            file_path.write_text(
                "# 操作系统\n总览。\n## 进程与线程\n线程共享资源。\n"
                "```python\n# 这里不是标题\n```\n",
                encoding="utf-8",
            )
            blocks = parser.parse(str(file_path), "md")

        assert [block.section_title for block in blocks] == [
            "操作系统",
            "操作系统 > 进程与线程",
        ]
        assert "这里不是标题" in blocks[1].text

    def test_embedding_text_adds_document_and_section_without_changing_source(self):
        source = "线程共享进程资源。"
        value = build_embedding_text(
            file_name="操作系统笔记.md",
            section_title="进程与线程",
            text=source,
        )

        self.assertEqual(
            value,
            "文档：操作系统笔记\n章节：进程与线程\n内容：线程共享进程资源。",
        )
        self.assertEqual(source, "线程共享进程资源。")

    def test_missing_online_config_never_falls_back_locally(self):
        import app.services.embedding_client as embedding_module

        client = EmbeddingClient()
        with (
            patch.object(embedding_module.settings, "embedding_api_key", ""),
            patch.object(embedding_module.settings, "embedding_model", ""),
            patch.object(client, "_embed_with_api") as api_call,
        ):
            with self.assertRaises(EmbeddingServiceError) as context:
                client.embed_texts(["进程和线程共享资源"])

        api_call.assert_not_called()
        self.assertIn("在线服务未配置", str(context.exception))

    def test_online_provider_uses_timeout_retries_and_preserves_response_order(self):
        import app.services.embedding_client as embedding_module

        recording_client = RecordingEmbeddingClient()
        constructor_kwargs = {}

        def make_client(**kwargs):
            constructor_kwargs.update(kwargs)
            return recording_client

        with (
            patch.object(embedding_module.settings, "embedding_api_key", "test-key"),
            patch.object(embedding_module.settings, "embedding_model", "test-model"),
            patch.object(embedding_module.settings, "embedding_base_url", "https://example.test/v1"),
            patch.object(embedding_module.settings, "embedding_timeout_seconds", 12.0),
            patch.object(embedding_module.settings, "embedding_max_retries", 2),
            patch("openai.OpenAI", side_effect=make_client),
        ):
            vectors = EmbeddingClient().embed_texts(["第一段", "第二段"])

        self.assertEqual(vectors, [[0.1, 0.2], [0.3, 0.4]])
        self.assertEqual(constructor_kwargs["timeout"], 12.0)
        self.assertEqual(constructor_kwargs["max_retries"], 2)
        self.assertEqual(recording_client.embeddings.kwargs["model"], "test-model")
        self.assertEqual(recording_client.embeddings.kwargs["input"], ["第一段", "第二段"])

    def test_embedding_requests_are_batched_without_changing_order(self):
        import app.services.embedding_client as embedding_module

        client = BatchRecordingEmbeddingClient()
        texts = ["一", "二二", "三三三", "四四四四", "五五五五五"]
        with (
            patch.object(embedding_module.settings, "embedding_api_key", "test-key"),
            patch.object(embedding_module.settings, "embedding_model", "test-model"),
            patch.object(embedding_module.settings, "embedding_batch_size", 2),
        ):
            vectors = client.embed_texts(texts)

        self.assertEqual(client.batches, [["一", "二二"], ["三三三", "四四四四"], ["五五五五五"]])
        self.assertEqual([vector[0] for vector in vectors], [1.0, 2.0, 3.0, 4.0, 5.0])

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

        self.assertIn("在线服务未配置", str(context.exception))

    def test_empty_embedding_response_returns_clear_error(self):
        import app.services.embedding_client as embedding_module

        with (
            patch.object(embedding_module.settings, "embedding_api_key", "test-key"),
            patch.object(embedding_module.settings, "embedding_model", "test-model"),
        ):
            with self.assertRaises(EmbeddingServiceError) as context:
                EmptyResponseEmbeddingClient().embed_texts(["测试文本"])

        self.assertIn("向量数量不正确", str(context.exception))

    def test_blank_text_is_rejected_before_online_request(self):
        import app.services.embedding_client as embedding_module

        client = EmbeddingClient()
        with (
            patch.object(embedding_module.settings, "embedding_api_key", "test-key"),
            patch.object(embedding_module.settings, "embedding_model", "test-model"),
            patch.object(client, "_embed_with_api") as api_call,
        ):
            with self.assertRaises(EmbeddingServiceError) as context:
                client.embed_texts(["   "])

        api_call.assert_not_called()
        self.assertIn("待向量化文本为空", str(context.exception))

    def test_empty_document_returns_parse_error(self):
        parser = DocumentParser()
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "empty.txt"
            file_path.write_text("   ", encoding="utf-8")

            with self.assertRaises(DocumentParseError) as context:
                parser.parse(str(file_path), "txt")

        self.assertIn("未提取到可用文字", str(context.exception))

    def test_markdown_parser_preserves_section_boundaries(self):
        parser = DocumentParser()
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "notes.md"
            file_path.write_text("# 第一章\n\n第一段内容。\n\n## 第二章\n\n第二段内容。", encoding="utf-8")
            text_value = parser.parse(str(file_path), "md")[0].text

        self.assertIn("第一章\n第一段内容。", text_value)
        self.assertIn("第二章\n第二段内容。", text_value)

    def test_upload_name_and_file_signatures_are_validated(self):
        service = DocumentService()
        self.assertEqual(service._normalize_upload_name(r"C:\fakepath\课堂笔记?.txt"), "课堂笔记_.txt")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_pdf = temp_path / "fake.pdf"
            fake_pdf.write_bytes(b"not-a-pdf")
            with self.assertRaises(HTTPException):
                service._validate_saved_file(fake_pdf, "pdf")

            binary_text = temp_path / "binary.txt"
            binary_text.write_bytes(b"plain\x00binary")
            with self.assertRaises(HTTPException):
                service._validate_saved_file(binary_text, "txt")

            valid_docx = temp_path / "valid.docx"
            with zipfile.ZipFile(valid_docx, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types />")
                archive.writestr("word/document.xml", "<document />")
            service._validate_saved_file(valid_docx, "docx")

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
