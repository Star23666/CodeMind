import asyncio
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import UploadFile
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.schemas.contracts import KnowledgeBaseUpdate, SearchRequest
from app.services.document_service import (
    DocumentPermissionError,
    DocumentService,
)
from app.services.knowledge_base_service import (
    KnowledgeBasePermissionError,
    KnowledgeBaseService,
)
from app.services.retrieval_service import RetrievalService
from app.services.vector_store import VectorSearchHit
from scripts.promote_admin import promote_user


def run_async(coro):
    return asyncio.run(coro)


class FakeVectorStore:
    def __init__(self, hits=None) -> None:
        self.hits = list(hits or [])
        self.deleted_ids: list[str] = []
        self.search_owner_ids: list[int | None] = []

    def delete_ids(self, vector_ids: list[str]) -> None:
        self.deleted_ids.extend(vector_ids)

    def search(self, **kwargs):
        self.search_owner_ids.append(kwargs["owner_id"])
        return self.hits


class PublicKnowledgeBaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.execute(text("PRAGMA foreign_keys = ON"))
        self._create_schema()
        self._seed_data()
        self.kb_service = KnowledgeBaseService()
        self.document_service = DocumentService()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_all_users_receive_the_same_public_base_with_permissions(self) -> None:
        alice = self.kb_service.list_accessible(self.db, 1)
        bob = self.kb_service.list_accessible(self.db, 2)
        admin = self.kb_service.list_accessible(self.db, 3)

        self.assertEqual([base.id for base in alice], [100, 11])
        self.assertEqual([base.id for base in bob], [100, 12])
        self.assertEqual([base.id for base in admin], [100, 13])
        self.assertEqual(alice[0].owner_id, None)
        self.assertTrue(alice[0].can_read)
        self.assertTrue(alice[0].can_upload)
        self.assertFalse(alice[0].can_manage)
        self.assertFalse(alice[0].can_edit)
        self.assertFalse(alice[0].can_delete)
        self.assertTrue(admin[0].can_edit)
        self.assertTrue(admin[0].can_manage)
        self.assertFalse(admin[0].can_delete)

    def test_only_admin_edits_public_base_and_nobody_deletes_it(self) -> None:
        payload = KnowledgeBaseUpdate(name="全站公共知识库", description="管理员维护说明")
        with self.assertRaises(KnowledgeBasePermissionError):
            self.kb_service.update(self.db, 100, 1, payload)

        updated = self.kb_service.update(self.db, 100, 3, payload)
        self.assertEqual(updated.name, "全站公共知识库")
        self.assertEqual(updated.description, "管理员维护说明")

        for user_id in (1, 3):
            with self.subTest(user_id=user_id):
                with self.assertRaises(KnowledgeBasePermissionError):
                    self.kb_service.delete(self.db, 100, user_id)

    def test_public_document_list_is_shared_but_private_documents_are_isolated(self) -> None:
        alice_public = self.document_service.list_documents(
            self.db,
            owner_id=1,
            knowledge_base_id=100,
        )
        admin_public = self.document_service.list_documents(
            self.db,
            owner_id=3,
            knowledge_base_id=100,
        )

        self.assertEqual([doc.owner_id for doc in alice_public], [2, 1])
        self.assertEqual(
            [doc.uploader_username for doc in alice_public],
            ["bob", "alice"],
        )
        self.assertEqual([doc.can_manage for doc in alice_public], [False, True])
        self.assertEqual([doc.can_manage for doc in admin_public], [True, True])
        self.assertTrue(all(doc.knowledge_base_visibility.value == "public" for doc in alice_public))

        alice_private = self.document_service.list_documents(
            self.db,
            owner_id=1,
            knowledge_base_id=11,
        )
        self.assertEqual([doc.id for doc in alice_private], [111])
        with self.assertRaises(ValueError):
            self.document_service.list_documents(
                self.db,
                owner_id=1,
                knowledge_base_id=12,
            )
        with self.assertRaises(ValueError):
            self.document_service.get_owned_document(self.db, 121, 1)

    def test_public_document_detail_chunks_and_file_are_readable_cross_user(self) -> None:
        document = self.document_service.get_owned_document(self.db, 201, 2)
        self.assertEqual(document.uploader_username, "alice")
        self.assertEqual(document.knowledge_base_visibility.value, "public")
        self.assertFalse(document.can_manage)

        chunks = self.document_service.list_chunks(
            self.db,
            document_id=201,
            owner_id=2,
        )
        self.assertEqual([chunk.id for chunk in chunks], [301])
        with patch.object(settings, "upload_dir", str(self.root)):
            file_info = self.document_service.get_owned_file(
                self.db,
                document_id=201,
                owner_id=2,
            )
        self.assertEqual(
            Path(file_info["path"]),
            (self.root / "alice-public.txt").resolve(),
        )

    def test_upload_to_public_base_records_uploader_and_public_metadata(self) -> None:
        upload = UploadFile(
            filename="bob-upload.txt",
            file=io.BytesIO("Bob 上传的公共内容".encode("utf-8")),
        )
        with patch.object(settings, "upload_dir", str(self.root / "uploads")):
            created = run_async(
                self.document_service.save_upload(
                    db=self.db,
                    owner_id=2,
                    knowledge_base_id=100,
                    file=upload,
                )
            )

        self.assertEqual(created.owner_id, 2)
        self.assertEqual(created.uploader_username, "bob")
        self.assertEqual(created.knowledge_base_visibility.value, "public")
        self.assertTrue(created.can_manage)
        visible_to_alice = self.document_service.get_owned_document(
            self.db,
            created.id,
            1,
        )
        self.assertFalse(visible_to_alice.can_manage)

    def test_document_management_is_owner_or_public_admin_only(self) -> None:
        with self.assertRaises(DocumentPermissionError):
            self.document_service.queue_reindex(self.db, document_id=201, owner_id=2)

        self.document_service.queue_reindex(self.db, document_id=201, owner_id=3)
        status_value = self.db.execute(
            text("SELECT parse_status FROM documents WHERE id = 201")
        ).scalar_one()
        self.assertEqual(status_value, "pending")

        with self.assertRaises(DocumentPermissionError):
            self.document_service.delete_document(self.db, document_id=202, owner_id=1)

    def test_deleting_own_public_document_cleans_database_file_and_vectors(self) -> None:
        vector_store = FakeVectorStore()
        file_path = self.root / "alice-public.txt"
        with patch(
            "app.services.document_service.get_vector_store",
            return_value=vector_store,
        ):
            self.document_service.delete_document(
                self.db,
                document_id=201,
                owner_id=1,
            )

        self.assertEqual(vector_store.deleted_ids, ["public-alice-vector"])
        self.assertFalse(file_path.exists())
        self.assertEqual(
            self.db.execute(text("SELECT COUNT(*) FROM documents WHERE id = 201")).scalar_one(),
            0,
        )
        self.assertEqual(
            self.db.execute(text("SELECT COUNT(*) FROM document_chunks WHERE document_id = 201")).scalar_one(),
            0,
        )

    def test_public_retrieval_searches_all_uploaders_while_private_stays_scoped(self) -> None:
        hits = [
            VectorSearchHit(
                vector_id="public-alice-vector",
                text="Alice 公共资料",
                metadata={
                    "document_id": 201,
                    "chunk_id": 301,
                    "chunk_index": 0,
                    "file_name": "alice-public.txt",
                },
                score=0.95,
            ),
            VectorSearchHit(
                vector_id="public-bob-vector",
                text="Bob 公共资料",
                metadata={
                    "document_id": 202,
                    "chunk_id": 302,
                    "chunk_index": 0,
                    "file_name": "bob-public.txt",
                },
                score=0.93,
            ),
        ]
        vector_store = FakeVectorStore(hits)
        retrieval = RetrievalService()
        with (
            patch("app.services.retrieval_service.SessionLocal", self.Session),
            patch(
                "app.services.retrieval_service.embedding_client.embed_texts",
                return_value=[[0.1, 0.2]],
            ),
            patch(
                "app.services.retrieval_service.get_vector_store",
                return_value=vector_store,
            ),
        ):
            public_sources = retrieval.retrieve_sources(
                "公共资料",
                SearchRequest(
                    knowledge_base_id=100,
                    query="公共资料",
                    score_threshold=0.1,
                    enable_rewrite=False,
                    enable_rerank=False,
                ),
                user_id=2,
            )
            retrieval.retrieve_sources(
                "私人资料",
                SearchRequest(
                    knowledge_base_id=12,
                    query="私人资料",
                    score_threshold=0.1,
                    enable_rewrite=False,
                    enable_rerank=False,
                ),
                user_id=2,
            )

        self.assertEqual([source.document_id for source in public_sources], [201, 202])
        self.assertEqual(vector_store.search_owner_ids, [None, 2])

    def test_admin_promotion_uses_existing_account_without_credentials(self) -> None:
        promoted = promote_user(self.db, email="ADMIN@EXAMPLE.COM")
        self.assertEqual(promoted, "admin")
        role = self.db.execute(
            text("SELECT role FROM users WHERE id = 3")
        ).scalar_one()
        self.assertEqual(role, "admin")
        with self.assertRaises(LookupError):
            promote_user(self.db, username="missing")

    def _create_schema(self) -> None:
        self.db.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'user'
                )
                """
            )
        )
        self.db.execute(
            text(
                """
                CREATE TABLE knowledge_bases (
                    id INTEGER PRIMARY KEY,
                    owner_id INTEGER,
                    name TEXT NOT NULL,
                    description TEXT,
                    visibility TEXT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
        )
        self.db.execute(
            text(
                """
                CREATE TABLE documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    knowledge_base_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL DEFAULT 'txt',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    file_path TEXT NOT NULL,
                    parse_status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
        )
        self.db.execute(
            text(
                """
                CREATE TABLE document_chunks (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    knowledge_base_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    page_no INTEGER,
                    start_offset INTEGER,
                    end_offset INTEGER,
                    vector_id TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                )
                """
            )
        )
        self.db.commit()

    def _seed_data(self) -> None:
        for file_name, content in (
            ("alice-public.txt", "Alice 公共资料"),
            ("bob-public.txt", "Bob 公共资料"),
            ("alice-private.txt", "Alice 私人资料"),
            ("bob-private.txt", "Bob 私人资料"),
        ):
            (self.root / file_name).write_text(content, encoding="utf-8")

        self.db.execute(
            text(
                """
                INSERT INTO users (id, username, email, role) VALUES
                (1, 'alice', 'alice@example.com', 'user'),
                (2, 'bob', 'bob@example.com', 'user'),
                (3, 'admin', 'admin@example.com', 'admin')
                """
            )
        )
        self.db.execute(
            text(
                """
                INSERT INTO knowledge_bases (id, owner_id, name, description, visibility) VALUES
                (100, NULL, '公共知识库', '全局公共资料', 'public'),
                (11, 1, 'Alice 私人库', NULL, 'private'),
                (12, 2, 'Bob 私人库', NULL, 'private'),
                (13, 3, 'Admin 私人库', NULL, 'private')
                """
            )
        )
        documents = (
            (201, 100, 1, "alice-public.txt", "public completed", 1),
            (202, 100, 2, "bob-public.txt", "public completed", 1),
            (111, 11, 1, "alice-private.txt", "private completed", 1),
            (121, 12, 2, "bob-private.txt", "private completed", 1),
        )
        for document_id, kb_id, owner_id, file_name, _, chunk_count in documents:
            self.db.execute(
                text(
                    """
                    INSERT INTO documents (
                        id, knowledge_base_id, owner_id, file_name, file_type,
                        file_size, file_path, parse_status, chunk_count
                    ) VALUES (
                        :id, :kb_id, :owner_id, :file_name, 'txt', 32,
                        :file_path, 'completed', :chunk_count
                    )
                    """
                ),
                {
                    "id": document_id,
                    "kb_id": kb_id,
                    "owner_id": owner_id,
                    "file_name": file_name,
                    "file_path": str(self.root / file_name),
                    "chunk_count": chunk_count,
                },
            )
        chunks = (
            (301, 201, 100, "Alice 公共资料", "public-alice-vector"),
            (302, 202, 100, "Bob 公共资料", "public-bob-vector"),
            (311, 111, 11, "Alice 私人资料", "private-alice-vector"),
            (312, 121, 12, "Bob 私人资料", "private-bob-vector"),
        )
        for chunk_id, document_id, kb_id, content, vector_id in chunks:
            self.db.execute(
                text(
                    """
                    INSERT INTO document_chunks (
                        id, document_id, knowledge_base_id, chunk_index,
                        chunk_text, start_offset, end_offset, vector_id
                    ) VALUES (
                        :id, :document_id, :kb_id, 0, :content, 0,
                        :end_offset, :vector_id
                    )
                    """
                ),
                {
                    "id": chunk_id,
                    "document_id": document_id,
                    "kb_id": kb_id,
                    "content": content,
                    "end_offset": len(content),
                    "vector_id": vector_id,
                },
            )
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
