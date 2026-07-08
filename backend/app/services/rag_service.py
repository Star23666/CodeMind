from app.schemas.contracts import ChatRequest, ChatResponse


class RagService:
    async def answer_question(self, request: ChatRequest) -> ChatResponse:
        rewritten_question = request.question if request.enable_rewrite else None

        return ChatResponse(
            qa_record_id=None,
            knowledge_base_id=request.knowledge_base_id,
            question=request.question,
            rewritten_question=rewritten_question,
            answer=(
                "Reference RAG pipeline placeholder: rewrite the question when enabled, "
                "embed the query, retrieve top_k chunks from Chroma, filter by "
                "score_threshold, rerank to rerank_top_n chunks, build the prompt, "
                "call the LLM API, then persist qa_records and qa_sources in MySQL."
            ),
            sources=[],
        )


rag_service = RagService()
