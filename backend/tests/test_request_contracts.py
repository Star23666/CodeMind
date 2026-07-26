import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.contracts import ChatRequest, MindMapQuestionRequest, SearchRequest
from app.schemas.quiz import QuizCreateRequest, QuizQuestionType


class RequestContractsTest(unittest.TestCase):
    def test_search_and_chat_trim_input_and_enforce_server_side_limits(self) -> None:
        search = SearchRequest(knowledge_base_id=1, query="  TCP 拥塞控制  ")
        chat = ChatRequest(knowledge_base_id=1, question="  线程和进程的区别  ")

        self.assertEqual(search.query, "TCP 拥塞控制")
        self.assertEqual(chat.question, "线程和进程的区别")

        with self.assertRaises(ValidationError):
            SearchRequest(knowledge_base_id=1, query="   ")
        with self.assertRaises(ValidationError):
            ChatRequest(knowledge_base_id=1, question="x" * 501)
        with self.assertRaises(ValidationError):
            SearchRequest(knowledge_base_id=0, query="有效问题")

    def test_mind_map_question_rejects_blank_text(self) -> None:
        with self.assertRaises(ValidationError):
            MindMapQuestionRequest(
                knowledge_base_id=1,
                node_title="  ",
                question="  ",
                source_chunk_ids=[1],
            )

    def test_specified_type_count_cannot_exceed_question_count(self) -> None:
        with self.assertRaises(ValidationError):
            QuizCreateRequest(
                knowledge_base_ids=[1],
                question_count=5,
                question_types=list(QuizQuestionType),
                random_mix=False,
            )


if __name__ == "__main__":
    unittest.main()
