from app.schemas.contracts import ChatRequest, ChatResponse
from app.services.llm_client import LlmClient, llm_client
from app.services.prompt_builder import build_rag_prompt
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

    async def answer_question(self, request: ChatRequest, user_id: int = 1) -> ChatResponse:
        retrieval_result = await self.retrieval_service.retrieve_for_chat(request, user_id=user_id)
        sources = retrieval_result.sources
        rewritten_question = retrieval_result.rewritten_question

        if sources:
            prompt = build_rag_prompt(
                question=request.question,
                rewritten_question=rewritten_question,
                sources=sources,
            )
            answer = await self.llm_client.generate_answer(prompt)
        else:
            answer = "知识库中未找到足够依据。请先上传相关资料，或换一个更具体的问题。"

        qa_record_id = await self.history_service.save_qa_record(
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


rag_service = RagService()
