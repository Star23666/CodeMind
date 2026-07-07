from app.schemas.chat import ChatRequest, ChatResponse


class RagService:
    async def answer_question(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            answer=(
                "RAG question answering is not connected yet. "
                "Next steps: retrieve chunks from Chroma, build a prompt, call the LLM API, "
                "and store the chat history in MySQL."
            ),
            sources=[],
        )


rag_service = RagService()

