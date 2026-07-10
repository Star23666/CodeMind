import asyncio
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.contracts import ChatRequest, SourceReference
from app.services.qa_history_service import QaHistoryService


def run_async(coro):
    return asyncio.run(coro)


class QaHistoryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.db.execute(text("PRAGMA foreign_keys = ON"))
        for statement in self._schema_statements():
            self.db.execute(text(statement))
        self._seed_data()
        self.service = QaHistoryService()

    def tearDown(self) -> None:
        self.db.close()

    def test_save_list_and_get_record_with_source_snapshot(self):
        record_id = run_async(
            self.service.save_qa_record(
                db=self.db,
                user_id=1,
                request=ChatRequest(knowledge_base_id=1, question="进程和线程有什么区别？"),
                rewritten_question="进程与线程的区别",
                answer="进程负责资源分配，线程负责调度。[来源1]",
                sources=[self._source()],
            )
        )

        records = self.service.list_qa_records(self.db, user_id=1, knowledge_base_id=1)
        detail = self.service.get_qa_record(self.db, qa_record_id=record_id, user_id=1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_count, 1)
        self.assertEqual(records[0].sources, [])
        self.assertEqual(detail.id, record_id)
        self.assertEqual(detail.sources[0].file_name, "操作系统笔记.pdf")
        self.assertEqual(detail.sources[0].source_text, self._source().source_text)
        self.assertEqual(detail.sources[0].jump_url, "/documents/1/chunks/10")

    def test_records_are_isolated_by_user(self):
        record_id = run_async(
            self.service.save_qa_record(
                db=self.db,
                user_id=1,
                request=ChatRequest(knowledge_base_id=1, question="什么是进程？"),
                rewritten_question=None,
                answer="进程是资源分配单位。[来源1]",
                sources=[self._source()],
            )
        )

        self.assertEqual(self.service.list_qa_records(self.db, user_id=2), [])
        with self.assertRaises(ValueError):
            self.service.get_qa_record(self.db, qa_record_id=record_id, user_id=2)

    def test_source_insert_failure_rolls_back_record(self):
        invalid_source = self._source()
        invalid_source.document_id = 999
        invalid_source.chunk_id = 999

        with self.assertRaises(Exception):
            run_async(
                self.service.save_qa_record(
                    db=self.db,
                    user_id=1,
                    request=ChatRequest(knowledge_base_id=1, question="测试事务"),
                    rewritten_question=None,
                    answer="测试回答。[来源1]",
                    sources=[invalid_source],
                )
            )

        count = self.db.execute(text("SELECT COUNT(*) FROM qa_records")).scalar_one()
        self.assertEqual(count, 0)

    def _seed_data(self) -> None:
        self.db.execute(
            text("INSERT INTO users (id, username) VALUES (1, 'user1'), (2, 'user2')")
        )
        self.db.execute(text("INSERT INTO knowledge_bases (id, owner_id) VALUES (1, 1)"))
        self.db.execute(
            text(
                "INSERT INTO documents (id, knowledge_base_id, owner_id, file_name) "
                "VALUES (1, 1, 1, '操作系统笔记.pdf')"
            )
        )
        self.db.execute(
            text(
                "INSERT INTO document_chunks "
                "(id, document_id, knowledge_base_id, chunk_index, chunk_text, page_no) "
                "VALUES (10, 1, 1, 3, '进程是资源分配单位。', 12)"
            )
        )
        self.db.commit()

    def _source(self) -> SourceReference:
        return SourceReference(
            document_id=1,
            chunk_id=10,
            file_name="操作系统笔记.pdf",
            chunk_index=3,
            page_no=12,
            score=0.864321,
            source_text="进程是资源分配的基本单位，线程是 CPU 调度的基本单位。",
            jump_url="/documents/1/chunks/10",
        )

    def _schema_statements(self) -> list[str]:
        return [
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL)",
            """
            CREATE TABLE knowledge_bases (
                id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                knowledge_base_id INTEGER NOT NULL REFERENCES knowledge_bases(id),
                owner_id INTEGER NOT NULL REFERENCES users(id),
                file_name TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE document_chunks (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                knowledge_base_id INTEGER NOT NULL REFERENCES knowledge_bases(id),
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                page_no INTEGER
            )
            """,
            """
            CREATE TABLE qa_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                knowledge_base_id INTEGER NOT NULL REFERENCES knowledge_bases(id),
                question TEXT NOT NULL,
                rewritten_question TEXT,
                answer TEXT NOT NULL,
                source_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE qa_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qa_record_id INTEGER NOT NULL REFERENCES qa_records(id) ON DELETE CASCADE,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                chunk_id INTEGER NOT NULL REFERENCES document_chunks(id),
                rank_no INTEGER NOT NULL,
                score NUMERIC,
                source_text TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]
