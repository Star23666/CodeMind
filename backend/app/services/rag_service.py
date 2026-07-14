from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from app.schemas.contracts import ChatRequest, ChatResponse
from app.services.llm_client import LlmClient, LlmServiceError, llm_client
from app.services.prompt_builder import build_rag_prompt, sanitize_answer_citations
from app.services.qa_history_service import QaHistoryService, qa_history_service
from app.services.retrieval_service import RetrievalService, retrieval_service


class RagService:
    def __init__(
        self,
        *,
        retrieval_service: RetrievalService = retrieval_service,
        llm_client: LlmClient = llm_client,
        history_service: QaHistoryService = qa_history_service,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.llm_client = llm_client
        self.history_service = history_service

    async def answer_question(
        self,
        request: ChatRequest,
        *,
        user_id: int,
        db: Session,
    ) -> ChatResponse:
        retrieval_result, sources, rewritten_question, prompt = await self._prepare_answer(
            request,
            user_id=user_id,
        )

        if prompt:
            answer = await self.llm_client.generate_answer(prompt)
            answer = sanitize_answer_citations(answer, source_count=len(sources))
        else:
            answer = retrieval_result.empty_message or (
                "知识库中未找到足够依据，请先上传相关资料或换一个更具体的问题。"
            )

        qa_record_id = await self.history_service.save_qa_record(
            db=db,
            user_id=user_id,
            request=request,
            rewritten_question=rewritten_question,
            answer=answer,
            sources=sources,
        )

        return ChatResponse(
            qa_record_id=qa_record_id,
            knowledge_base_id=request.knowledge_base_id,
            question=request.question,
            rewritten_question=rewritten_question,
            answer=answer,
            sources=sources,
        )

    async def stream_answer(
        self,
        request: ChatRequest,
        *,
        user_id: int,
        db: Session,
    ) -> AsyncIterator[dict[str, object]]:
        retrieval_result, sources, rewritten_question, prompt = await self._prepare_answer(
            request,
            user_id=user_id,
        )

        serialized_sources = [source.model_dump(mode="json") for source in sources]
        yield {
            "event": "meta",
            "data": {
                "knowledge_base_id": request.knowledge_base_id,
                "question": request.question,
                "rewritten_question": rewritten_question,
                "sources": serialized_sources,
            },
        }

        if prompt:
            answer_parts: list[str] = []
            async for token in self.llm_client.stream_answer(prompt):
                answer_parts.append(token)
                yield {"event": "token", "data": {"delta": token}}

            raw_answer = "".join(answer_parts).strip()
            if not raw_answer:
                raise LlmServiceError("大模型服务未返回有效回答。", status_code=502)
            answer = sanitize_answer_citations(raw_answer, source_count=len(sources))
        else:
            answer = retrieval_result.empty_message or (
                "知识库中未找到足够依据，请先上传相关资料或换一个更具体的问题。"
            )

        qa_record_id = await self.history_service.save_qa_record(
            db=db,
            user_id=user_id,
            request=request,
            rewritten_question=rewritten_question,
            answer=answer,
            sources=sources,
        )
        yield {
            "event": "done",
            "data": {
                "qa_record_id": qa_record_id,
                "knowledge_base_id": request.knowledge_base_id,
                "question": request.question,
                "rewritten_question": rewritten_question,
                "answer": answer,
                "sources": serialized_sources,
            },
        }

    async def _prepare_answer(
        self,
        request: ChatRequest,
        *,
        user_id: int,
    ):
        retrieval_result = await self.retrieval_service.retrieve_for_chat(request, user_id=user_id)
        sources = retrieval_result.sources
        rewritten_question = retrieval_result.rewritten_question
        prompt = (
            build_rag_prompt(
                question=request.question,
                rewritten_question=rewritten_question,
                sources=sources,
            )
            if sources
            else None
        )
        return retrieval_result, sources, rewritten_question, prompt


rag_service = RagService()
