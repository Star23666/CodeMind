import asyncio
import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.contracts import ChatRequest, SearchRequest, SourceReference
from app.services.embedding_client import EmbeddingServiceError, embedding_client
from app.services.embedding_text import build_embedding_text
from app.services.knowledge_base_service import knowledge_base_service
from app.services.reranker_client import RerankerServiceError, reranker_client
from app.services.retrieval_scoring import (
    LexicalDocument,
    bm25_rank,
    keyword_overlap,
    reciprocal_rank_fusion,
    rough_tokens,
)
from app.services.vector_store import VectorSearchHit, get_vector_store


logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_EMPTY_MESSAGE = (
    "当前知识库暂无可检索资料，请先上传文档并等待处理完成。"
)
NO_RELEVANT_RESULTS_MESSAGE = (
    "知识库中未检索到相关内容，请换一个更具体的问题，或适当降低相关度阈值。"
)


class RetrievalServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class RetrievalResult(BaseModel):
    rewritten_question: str | None = None
    sources: list[SourceReference] = Field(default_factory=list)
    empty_message: str | None = None


@dataclass(frozen=True)
class RetrievalCandidate:
    hit: VectorSearchHit
    fusion_score: float


class RetrievalService:
    """Retrieval side backed by Chroma vectors."""

    async def retrieve_for_chat(self, request: ChatRequest, user_id: int = 1) -> RetrievalResult:
        rewritten_question = self.rewrite_question(request.question) if request.enable_rewrite else None
        if not await asyncio.to_thread(
            self._has_searchable_content,
            request.knowledge_base_id,
            user_id,
        ):
            return RetrievalResult(
                rewritten_question=rewritten_question,
                empty_message=KNOWLEDGE_BASE_EMPTY_MESSAGE,
            )
        query = rewritten_question or request.question
        sources = await asyncio.to_thread(
            self.retrieve_sources,
            query,
            request,
            user_id=user_id,
        )
        return RetrievalResult(
            rewritten_question=rewritten_question,
            sources=sources,
            empty_message=None if sources else NO_RELEVANT_RESULTS_MESSAGE,
        )

    async def retrieve_for_search(self, request: SearchRequest, user_id: int = 1) -> RetrievalResult:
        rewritten_query = self.rewrite_question(request.query) if request.enable_rewrite else None
        if not await asyncio.to_thread(
            self._has_searchable_content,
            request.knowledge_base_id,
            user_id,
        ):
            return RetrievalResult(
                rewritten_question=rewritten_query,
                empty_message=KNOWLEDGE_BASE_EMPTY_MESSAGE,
            )
        query = rewritten_query or request.query
        sources = await asyncio.to_thread(
            self.retrieve_sources,
            query,
            request,
            user_id=user_id,
        )
        return RetrievalResult(
            rewritten_question=rewritten_query,
            sources=sources,
            empty_message=None if sources else NO_RELEVANT_RESULTS_MESSAGE,
        )

    def rewrite_question(self, question: str) -> str:
        normalized = " ".join(question.split()).strip()
        normalized = re.sub(
            r"^(?:请问|请帮我|麻烦(?:你)?|我想(?:知道|了解)|能否|可以(?:帮我)?)(?:一下|解释)?[，,：:\s]*",
            "",
            normalized,
        )
        normalized = re.sub(r"(?:可以吗|行吗|好吗|谢谢)[？?。.!！\s]*$", "", normalized)
        normalized = normalized.rstrip("？?。.!！ ")
        return normalized.strip() or question.strip()

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

        candidate_k = request.top_k
        if request.enable_rerank:
            candidate_k = max(candidate_k, settings.retrieval_dense_candidate_k)
        try:
            dense_hits = get_vector_store().search(
                embedding=query_embedding,
                knowledge_base_id=request.knowledge_base_id,
                owner_id=scope_owner_id,
                top_k=candidate_k,
            )
        except Exception as exc:
            logger.exception("Vector store search failed")
            raise RetrievalServiceError(
                "知识库检索服务暂时不可用，请稍后重试。"
            ) from exc

        dense_hits = self._filter_current_hits(
            dense_hits,
            knowledge_base_id=request.knowledge_base_id,
            owner_id=scope_owner_id,
        )
        if not request.enable_rerank:
            return [
                self._hit_to_source(hit)
                for hit in dense_hits
                if hit.score >= request.score_threshold
            ][: request.top_k]

        candidates = self._build_candidates(
            query=query,
            dense_hits=dense_hits,
            knowledge_base_id=request.knowledge_base_id,
            owner_id=scope_owner_id,
        )
        if candidates:
            try:
                return self._online_rerank(
                    query=query,
                    candidates=candidates,
                    top_n=request.rerank_top_n,
                    score_threshold=request.score_threshold,
                )
            except RerankerServiceError as exc:
                if not settings.rerank_fail_open:
                    raise RetrievalServiceError(str(exc), status_code=502) from exc
                logger.warning(
                    "Reranker unavailable; using vector fallback (model=%s)",
                    settings.rerank_model,
                )
        return self._legacy_vector_rerank(
            query,
            dense_hits,
            request,
            score_threshold=settings.retrieval_score_threshold,
        )

    def _build_candidates(
        self,
        *,
        query: str,
        dense_hits: list[VectorSearchHit],
        knowledge_base_id: int,
        owner_id: int | None,
    ) -> list[RetrievalCandidate]:
        hit_by_id = {hit.vector_id: hit for hit in dense_hits}
        rankings: list[list[str]] = [[hit.vector_id for hit in dense_hits]]
        if settings.retrieval_hybrid_enabled:
            lexical_hits = self._lexical_hits(
                query=query,
                knowledge_base_id=knowledge_base_id,
                owner_id=owner_id,
            )
            if lexical_hits:
                rankings.append([hit.vector_id for hit in lexical_hits])
                for hit in lexical_hits:
                    hit_by_id.setdefault(hit.vector_id, hit)

        fused = reciprocal_rank_fusion(
            rankings,
            rank_constant=max(1, settings.retrieval_rrf_k),
        )
        ordered_ids = sorted(fused, key=fused.get, reverse=True)
        limit = max(1, settings.retrieval_fusion_candidate_k)
        return [
            RetrievalCandidate(hit=hit_by_id[vector_id], fusion_score=fused[vector_id])
            for vector_id in ordered_ids[:limit]
        ]

    def _lexical_hits(
        self,
        *,
        query: str,
        knowledge_base_id: int,
        owner_id: int | None,
    ) -> list[VectorSearchHit]:
        owner_condition = "" if owner_id is None else "AND d.owner_id = :owner_id"
        limit = max(1, settings.retrieval_lexical_max_chunks)
        db = SessionLocal()
        try:
            rows = list(
                db.execute(
                    text(
                        f"""
                        SELECT c.id AS chunk_id, c.vector_id, c.chunk_text,
                               c.chunk_index, c.page_no, d.id AS document_id,
                               d.file_name
                        FROM document_chunks c
                        JOIN documents d ON d.id = c.document_id
                        WHERE d.knowledge_base_id = :knowledge_base_id
                          {owner_condition}
                        ORDER BY c.id
                        LIMIT :limit
                        """
                    ),
                    {
                        "knowledge_base_id": knowledge_base_id,
                        "owner_id": owner_id,
                        "limit": limit,
                    },
                ).mappings()
            )
        except Exception:
            logger.exception("Lexical candidate loading failed")
            return []
        finally:
            db.close()
        if len(rows) == limit:
            logger.warning(
                "Lexical retrieval reached configured chunk cap (knowledge_base_id=%s, cap=%s)",
                knowledge_base_id,
                limit,
            )
        rows_by_id = {str(row["vector_id"]): row for row in rows}
        try:
            vector_metadatas = get_vector_store().get_metadatas(list(rows_by_id))
        except Exception as exc:
            logger.warning(
                "Section metadata loading failed; lexical retrieval will use file names only "
                "(error=%s)",
                type(exc).__name__,
            )
            vector_metadatas = {}
        ranked = bm25_rank(
            query,
            [
                LexicalDocument(
                    key=vector_id,
                    text=build_embedding_text(
                        file_name=str(row["file_name"]),
                        section_title=str(
                            vector_metadatas.get(vector_id, {}).get("section_title")
                            or ""
                        ),
                        text=str(row["chunk_text"]),
                    ),
                )
                for vector_id, row in rows_by_id.items()
            ],
            top_k=max(1, settings.retrieval_lexical_candidate_k),
        )
        hits: list[VectorSearchHit] = []
        max_score = max((score for _, score in ranked), default=1.0)
        for vector_id, score in ranked:
            row = rows_by_id[vector_id]
            hits.append(
                VectorSearchHit(
                    vector_id=vector_id,
                    text=str(row["chunk_text"]),
                    metadata={
                        "document_id": int(row["document_id"]),
                        "chunk_id": int(row["chunk_id"]),
                        "chunk_index": int(row["chunk_index"]),
                        "file_name": str(row["file_name"]),
                        "page_no": int(row["page_no"] or 0),
                        "section_title": str(
                            vector_metadatas.get(vector_id, {}).get("section_title")
                            or ""
                        ),
                    },
                    score=max(-1.0, min(1.0, score / max_score)),
                )
            )
        return hits

    def _online_rerank(
        self,
        *,
        query: str,
        candidates: list[RetrievalCandidate],
        top_n: int,
        score_threshold: float,
    ) -> list[SourceReference]:
        documents = [self._rerank_document(candidate.hit) for candidate in candidates]
        results = reranker_client.rerank(
            query=query,
            documents=documents,
            top_n=len(documents),
        )
        sources: list[SourceReference] = []
        for result in results:
            if result.relevance_score < score_threshold:
                continue
            sources.append(
                self._hit_to_source(
                    candidates[result.index].hit,
                    score=result.relevance_score,
                )
            )
            if len(sources) >= top_n:
                break
        return sources

    def _rerank_document(self, hit: VectorSearchHit) -> str:
        section_title = str(hit.metadata.get("section_title") or "").strip()
        return build_embedding_text(
            file_name=str(hit.metadata.get("file_name") or "未命名文档"),
            section_title=section_title,
            text=hit.text,
        )

    def _legacy_vector_rerank(
        self,
        query: str,
        dense_hits: list[VectorSearchHit],
        request: ChatRequest | SearchRequest,
        *,
        score_threshold: float | None = None,
    ) -> list[SourceReference]:
        threshold = request.score_threshold if score_threshold is None else score_threshold
        sources = [
            self._hit_to_source(hit)
            for hit in dense_hits
            if hit.score >= threshold
        ]
        sources.sort(
            key=lambda source: self._rerank_score(query, source),
            reverse=True,
        )
        return sources[: request.rerank_top_n]

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

    def _hit_to_source(
        self,
        hit: VectorSearchHit,
        *,
        score: float | None = None,
    ) -> SourceReference:
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
            score=hit.score if score is None else score,
            source_text=hit.text,
            jump_url=f"/documents/{document_id}/chunks/{chunk_id}",
        )

    def _rerank_score(self, query: str, source: SourceReference) -> float:
        vector_score = source.score or 0.0
        overlap_score = self._keyword_overlap(query, source.source_text)
        return vector_score * 0.8 + overlap_score * 0.2

    def _keyword_overlap(self, query: str, text: str) -> float:
        return keyword_overlap(query, text)

    def _rough_tokens(self, text: str) -> list[str]:
        return rough_tokens(text)


retrieval_service = RetrievalService()

