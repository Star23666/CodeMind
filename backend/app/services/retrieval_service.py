import logging

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db.session import SessionLocal
from app.schemas.contracts import ChatRequest, SearchRequest, SourceReference
from app.services.embedding_client import EmbeddingServiceError, embedding_client
from app.services.knowledge_base_service import knowledge_base_service
from app.services.vector_store import VectorSearchHit, get_vector_store


logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_EMPTY_MESSAGE = (
    "当前知识库暂无可检索资料，请先上传文档并等待处理完成。"
)
NO_RELEVANT_RESULTS_MESSAGE = (
    "知识库中未检索到相关内容，请换一个更具体的问题，或适当降低相似度阈值。"
)


class RetrievalServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class RetrievalResult(BaseModel):
    rewritten_question: str | None = None
    sources: list[SourceReference] = Field(default_factory=list)
    empty_message: str | None = None


class RetrievalService:
    """Retrieval side backed by Chroma vectors."""

    async def retrieve_for_chat(self, request: ChatRequest, user_id: int = 1) -> RetrievalResult:
        rewritten_question = self.rewrite_question(request.question) if request.enable_rewrite else None
        if not self._has_searchable_content(request.knowledge_base_id, user_id):
            return RetrievalResult(
                rewritten_question=rewritten_question,
                empty_message=KNOWLEDGE_BASE_EMPTY_MESSAGE,
            )
        query = rewritten_question or request.question
        sources = self.retrieve_sources(query, request, user_id=user_id)
        return RetrievalResult(
            rewritten_question=rewritten_question,
            sources=sources,
            empty_message=None if sources else NO_RELEVANT_RESULTS_MESSAGE,
        )

    async def retrieve_for_search(self, request: SearchRequest, user_id: int = 1) -> RetrievalResult:
        rewritten_query = self.rewrite_question(request.query) if request.enable_rewrite else None
        if not self._has_searchable_content(request.knowledge_base_id, user_id):
            return RetrievalResult(
                rewritten_question=rewritten_query,
                empty_message=KNOWLEDGE_BASE_EMPTY_MESSAGE,
            )
        query = rewritten_query or request.query
        sources = self.retrieve_sources(query, request, user_id=user_id)
        return RetrievalResult(
            rewritten_question=rewritten_query,
            sources=sources,
            empty_message=None if sources else NO_RELEVANT_RESULTS_MESSAGE,
        )

    def rewrite_question(self, question: str) -> str:
        return question.strip()

    def retrieve_sources(
        self,
        query: str,
        request: ChatRequest | SearchRequest,
        *,
        user_id: int,
    ) -> list[SourceReference]:
        scope_owner_id = self._scope_owner_id(request.knowledge_base_id, user_id)
        try:
            query_embedding = embedding_client.embed_texts([query])[0]
        except EmbeddingServiceError as exc:
            raise RetrievalServiceError(str(exc), status_code=502) from exc

        try:
            hits = get_vector_store().search(
                embedding=query_embedding,
                knowledge_base_id=request.knowledge_base_id,
                owner_id=scope_owner_id,
                top_k=request.top_k,
            )
        except Exception as exc:
            logger.exception("Vector store search failed")
            raise RetrievalServiceError(
                "知识库检索服务暂时不可用，请稍后重试。"
            ) from exc

        hits = self._filter_current_hits(
            hits,
            knowledge_base_id=request.knowledge_base_id,
            owner_id=scope_owner_id,
        )
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

    def _has_searchable_content(self, knowledge_base_id: int, user_id: int) -> bool:
        db = SessionLocal()
        try:
            knowledge_base = knowledge_base_service.get_readable(
                db,
                knowledge_base_id,
                user_id,
            )
            owner_condition = (
                "" if knowledge_base.visibility.value == "public" else "AND d.owner_id = :owner_id"
            )
            count = db.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.knowledge_base_id = :knowledge_base_id
                      {owner_condition}
                    """
                ),
                {"knowledge_base_id": knowledge_base_id, "owner_id": user_id},
            ).scalar_one()
            return int(count) > 0
        except Exception as exc:
            logger.exception("Failed to inspect searchable knowledge base content")
            raise RetrievalServiceError(
                "暂时无法检查知识库资料状态，请稍后重试。"
            ) from exc
        finally:
            db.close()

    def _filter_current_hits(
        self,
        hits: list[VectorSearchHit],
        *,
        knowledge_base_id: int,
        owner_id: int | None,
    ) -> list[VectorSearchHit]:
        if not hits:
            return []

        db = SessionLocal()
        try:
            owner_condition = "" if owner_id is None else "AND d.owner_id = :owner_id"
            rows = db.execute(
                text(
                    f"""
                    SELECT c.vector_id
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.knowledge_base_id = :knowledge_base_id
                      {owner_condition}
                    """
                ),
                {"knowledge_base_id": knowledge_base_id, "owner_id": owner_id},
            ).mappings()
            current_vector_ids = {str(row["vector_id"]) for row in rows}
            return [hit for hit in hits if hit.vector_id in current_vector_ids]
        except Exception as exc:
            logger.exception("Failed to validate vector search hits against MySQL")
            raise RetrievalServiceError(
                "暂时无法校验知识库检索结果，请稍后重试。"
            ) from exc
        finally:
            db.close()

    def _scope_owner_id(self, knowledge_base_id: int, user_id: int) -> int | None:
        db = SessionLocal()
        try:
            knowledge_base = knowledge_base_service.get_readable(
                db,
                knowledge_base_id,
                user_id,
            )
            return None if knowledge_base.visibility.value == "public" else user_id
        except ValueError as exc:
            raise RetrievalServiceError("知识库不存在或无权访问。", status_code=404) from exc
        finally:
            db.close()

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

