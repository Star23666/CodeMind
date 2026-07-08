import asyncio
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.contracts import ChatRequest, SourceReference
from app.services.prompt_builder import build_rag_prompt
from app.services.rag_service import RagService
from app.services.retrieval_service import RetrievalResult


def run_async(coro):
    return asyncio.run(coro)


def make_source(chunk_id: int = 10, score: float = 0.86) -> SourceReference:
    return SourceReference(
        document_id=1,
        chunk_id=chunk_id,
        file_name="操作系统笔记.pdf",
        chunk_index=3,
        page_no=12,
        score=score,
        source_text="进程是资源分配的基本单位，线程是 CPU 调度的基本单位。",
        jump_url=f"/documents/1/chunks/{chunk_id}",
    )


class FakeRetrievalService:
    def __init__(self, sources: list[SourceReference]):
        self.sources = sources
        self.last_request = None

    async def retrieve_for_chat(self, request: ChatRequest) -> RetrievalResult:
        self.last_request = request
        rewritten = "操作系统中进程与线程的区别是什么？" if request.enable_rewrite else None
        return RetrievalResult(rewritten_question=rewritten, sources=self.sources)


class FakeLlmClient:
    def __init__(self):
        self.last_prompt = None
        self.called = False

    async def generate_answer(self, prompt: str) -> str:
        self.called = True
        self.last_prompt = prompt
        return "进程负责资源分配，线程负责 CPU 调度。 [来源1]"


class FakeHistoryService:
    def __init__(self):
        self.saved = None

    async def save_qa_record(
        self,
        *,
        user_id: int,
        request: ChatRequest,
        rewritten_question: str | None,
        answer: str,
        sources: list[SourceReference],
    ) -> int:
        self.saved = {
            "user_id": user_id,
            "request": request,
            "rewritten_question": rewritten_question,
            "answer": answer,
            "sources": sources,
        }
        return 1001


class RagGenerationTest(unittest.TestCase):
    def test_build_prompt_numbers_sources_and_includes_guardrails(self):
        prompt = build_rag_prompt(
            question="进程和线程有什么区别？",
            rewritten_question="操作系统中进程与线程的区别是什么？",
            sources=[make_source()],
        )

        self.assertIn("请只根据给定资料回答", prompt)
        self.assertIn("进程和线程有什么区别？", prompt)
        self.assertIn("操作系统中进程与线程的区别是什么？", prompt)
        self.assertIn("[来源1]", prompt)
        self.assertIn("操作系统笔记.pdf", prompt)

    def test_answer_question_uses_retrieval_prompt_llm_history_and_returns_sources(self):
        retrieval = FakeRetrievalService([make_source()])
        llm = FakeLlmClient()
        history = FakeHistoryService()
        service = RagService(
            retrieval_service=retrieval,
            llm_client=llm,
            history_service=history,
        )
        request = ChatRequest(knowledge_base_id=1, question="进程和线程有什么区别？")

        response = run_async(service.answer_question(request, user_id=7))

        self.assertEqual(response.qa_record_id, 1001)
        self.assertEqual(response.knowledge_base_id, 1)
        self.assertEqual(response.rewritten_question, "操作系统中进程与线程的区别是什么？")
        self.assertEqual(response.sources[0].chunk_id, 10)
        self.assertTrue(llm.called)
        self.assertIn("[来源1]", llm.last_prompt)
        self.assertEqual(history.saved["user_id"], 7)
        self.assertEqual(history.saved["sources"][0].file_name, "操作系统笔记.pdf")

    def test_answer_question_returns_insufficient_evidence_without_calling_llm(self):
        retrieval = FakeRetrievalService([])
        llm = FakeLlmClient()
        history = FakeHistoryService()
        service = RagService(
            retrieval_service=retrieval,
            llm_client=llm,
            history_service=history,
        )
        request = ChatRequest(knowledge_base_id=1, question="量子计算是什么？")

        response = run_async(service.answer_question(request, user_id=7))

        self.assertFalse(llm.called)
        self.assertIn("知识库中未找到足够依据", response.answer)
        self.assertEqual(response.sources, [])
        self.assertEqual(response.qa_record_id, 1001)
        self.assertEqual(history.saved["sources"], [])


if __name__ == "__main__":
    unittest.main()
