import logging

from pydantic import BaseModel, Field

from app.schemas.contracts import ChatRequest, SearchRequest, SourceReference
from app.services.embedding_client import embedding_client
from app.services.vector_store import VectorSearchHit, get_vector_store


logger = logging.getLogger(__name__)


class RetrievalResult(BaseModel):
    rewritten_question: str | None = None
    sources: list[SourceReference] = Field(default_factory=list)


class RetrievalService:
    """Retrieval side backed by Chroma vectors."""

    async def retrieve_for_chat(self, request: ChatRequest, user_id: int = 1) -> RetrievalResult:
        rewritten_question = self.rewrite_question(request.question) if request.enable_rewrite else None
        query = rewritten_question or request.question
        sources = self.retrieve_sources(query, request, user_id=user_id)
        return RetrievalResult(rewritten_question=rewritten_question, sources=sources)

    async def retrieve_for_search(self, request: SearchRequest, user_id: int = 1) -> RetrievalResult:
        rewritten_query = self.rewrite_question(request.query) if request.enable_rewrite else None
        query = rewritten_query or request.query
        sources = self.retrieve_sources(query, request, user_id=user_id)
        return RetrievalResult(rewritten_question=rewritten_query, sources=sources)

    def rewrite_question(self, question: str) -> str:
        return question.strip()

    def retrieve_sources(
        self,
        query: str,
        request: ChatRequest | SearchRequest,
        *,
        user_id: int,
    ) -> list[SourceReference]:
        query_embedding = embedding_client.embed_texts([query])[0]
        try:
            hits = get_vector_store().search(
                embedding=query_embedding,
                knowledge_base_id=request.knowledge_base_id,
                owner_id=user_id,
                top_k=request.top_k,
            )
        except Exception as exc:
            logger.warning("Vector store unavailable, returning empty retrieval result: %s", exc)
            return []

        sources = [
            self._hit_to_source(hit)
            for hit in hits
            if hit.score >= request.score_threshold
        ]

        if request.enable_rerank:
            sources = sorted(
                sources,
                key=lambda source: self._rerank_score(query, source),
                reverse=True,
            )
            return sources[: request.rerank_top_n]

        return sources[: request.top_k]

    def _hit_to_source(self, hit: VectorSearchHit) -> SourceReference:
        metadata = hit.metadata
        document_id = int(metadata["document_id"])
        chunk_id = int(metadata["chunk_id"])
        page_no = int(metadata.get("page_no") or 0) or None

        return SourceReference(
            document_id=document_id,
            chunk_id=chunk_id,
            file_name=str(metadata.get("file_name") or ""),
            chunk_index=int(metadata.get("chunk_index") or 0),
            page_no=page_no,
            score=hit.score,
            source_text=hit.text,
            jump_url=f"/documents/{document_id}/chunks/{chunk_id}",
        )

    def _rerank_score(self, query: str, source: SourceReference) -> float:
        vector_score = source.score or 0.0
        overlap_score = self._keyword_overlap(query, source.source_text)
        return vector_score * 0.8 + overlap_score * 0.2

    def _keyword_overlap(self, query: str, text: str) -> float:
        query_tokens = set(self._rough_tokens(query))
        text_tokens = set(self._rough_tokens(text))
        if not query_tokens or not text_tokens:
            return 0.0
        return len(query_tokens & text_tokens) / len(query_tokens)

    def _rough_tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        tokens: list[str] = []
        current: list[str] = []
        cjk_chars: list[str] = []

        for char in lowered:
            if char.isascii() and char.isalnum():
                current.append(char)
                continue

            if current:
                tokens.append("".join(current))
                current = []

            if "\u4e00" <= char <= "\u9fff":
                cjk_chars.append(char)

        if current:
            tokens.append("".join(current))

        tokens.extend("".join(cjk_chars[index : index + 2]) for index in range(max(len(cjk_chars) - 1, 0)))
        return tokens


retrieval_service = RetrievalService()

