from pydantic import BaseModel, Field

from app.schemas.contracts import ChatRequest, SourceReference


class RetrievalResult(BaseModel):
    rewritten_question: str | None = None
    sources: list[SourceReference] = Field(default_factory=list)


class RetrievalService:
    """Temporary retrieval-side contract.

    Li Zhuhuan can replace this implementation with Chroma retrieval while
    keeping the return type stable for the generation side.
    """

    async def retrieve_for_chat(self, request: ChatRequest) -> RetrievalResult:
        rewritten_question = self.rewrite_question(request.question) if request.enable_rewrite else None
        query = rewritten_question or request.question
        sources = self.retrieve_mock_sources(query, request)
        return RetrievalResult(rewritten_question=rewritten_question, sources=sources)

    def rewrite_question(self, question: str) -> str:
        return question.strip()

    def retrieve_mock_sources(self, query: str, request: ChatRequest) -> list[SourceReference]:
        query_text = query.lower()
        candidates = [
            SourceReference(
                document_id=1,
                chunk_id=10,
                file_name="操作系统笔记.pdf",
                chunk_index=3,
                page_no=12,
                score=0.89,
                source_text="进程是资源分配的基本单位，拥有独立地址空间；线程是 CPU 调度的基本单位，同一进程内的线程共享进程资源。",
                jump_url="/documents/1/chunks/10",
            ),
            SourceReference(
                document_id=1,
                chunk_id=11,
                file_name="操作系统笔记.pdf",
                chunk_index=4,
                page_no=13,
                score=0.83,
                source_text="进程切换开销通常大于线程切换；线程共享数据时需要关注同步、互斥和并发安全问题。",
                jump_url="/documents/1/chunks/11",
            ),
            SourceReference(
                document_id=2,
                chunk_id=21,
                file_name="RAG 技术导论.md",
                chunk_index=1,
                page_no=2,
                score=0.88,
                source_text="RAG 是检索增强生成技术，先从知识库检索相关资料，再将资料作为上下文交给大模型生成回答。",
                jump_url="/documents/2/chunks/21",
            ),
        ]

        if "rag" in query_text or "检索" in query_text or "知识库" in query_text:
            filtered = [source for source in candidates if source.document_id == 2]
        elif "进程" in query_text or "线程" in query_text:
            filtered = [source for source in candidates if source.document_id == 1]
        else:
            filtered = []

        filtered = [
            source
            for source in filtered
            if source.score is None or source.score >= request.score_threshold
        ]
        return filtered[: request.rerank_top_n if request.enable_rerank else request.top_k]


retrieval_service = RetrievalService()

