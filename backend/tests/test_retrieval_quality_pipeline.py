from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.schemas.contracts import ChatRequest
from app.services.reranker_client import (
    RerankResult,
    RerankerClient,
    RerankerServiceError,
)
from app.services.retrieval_scoring import (
    LexicalDocument,
    bm25_rank,
    reciprocal_rank_fusion,
)
from app.services.retrieval_service import RetrievalCandidate, RetrievalService
from app.services.vector_store import VectorSearchHit


def make_hit(vector_id: str, text: str, score: float = 0.8) -> VectorSearchHit:
    number = int("".join(char for char in vector_id if char.isdigit()) or 1)
    return VectorSearchHit(
        vector_id=vector_id,
        text=text,
        metadata={
            "document_id": number,
            "chunk_id": number,
            "chunk_index": 0,
            "file_name": f"doc-{number}.md",
            "section_title": "测试章节",
        },
        score=score,
    )


def test_bm25_prioritizes_exact_technical_identifier():
    ranked = bm25_rank(
        "innodb_lock_wait_timeout 精确配置",
        [
            LexicalDocument("generic", "MySQL 事务会持有锁并等待。"),
            LexicalDocument(
                "exact",
                "参数 innodb_lock_wait_timeout 控制锁等待超时秒数。",
            ),
        ],
        top_k=2,
    )

    assert ranked
    assert ranked[0][0] == "exact"


def test_reciprocal_rank_fusion_merges_dense_and_lexical_rankings():
    scores = reciprocal_rank_fusion(
        [["dense-only", "shared"], ["shared", "lexical-only"]],
        rank_constant=60,
    )

    assert scores["shared"] > scores["dense-only"]
    assert scores["shared"] > scores["lexical-only"]
    assert all(0.0 <= score <= 1.0 for score in scores.values())


def test_reranker_client_uses_qwen_direct_evidence_instruction():
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            captured.update({"url": url, "headers": headers, "json": json})
            return SimpleNamespace(
                status_code=200,
                request=SimpleNamespace(),
                json=lambda: {
                    "results": [
                        {"index": 1, "relevance_score": 0.92},
                        {"index": 0, "relevance_score": 0.12},
                    ]
                },
            )

    with (
        patch("app.services.reranker_client.httpx.Client", FakeClient),
        patch("app.services.reranker_client.settings.rerank_api_key", "test-key"),
        patch(
            "app.services.reranker_client.settings.rerank_base_url",
            "https://api.example.test/v1",
        ),
        patch(
            "app.services.reranker_client.settings.rerank_model",
            "Qwen/Qwen3-Reranker-8B",
        ),
    ):
        results = RerankerClient().rerank(
            query="线程和进程有什么区别？",
            documents=["资料一", "资料二"],
        )

    assert [result.index for result in results] == [1, 0]
    assert captured["url"] == "https://api.example.test/v1/rerank"
    assert captured["headers"] == {"Authorization": "Bearer test-key"}
    assert "仅主题相关" in captured["json"]["instruction"]
    assert captured["json"]["return_documents"] is False


def test_reranker_client_rejects_invalid_provider_indices():
    client = RerankerClient()
    with pytest.raises(ValueError):
        client._parse_results(
            {"results": [{"index": 3, "relevance_score": 0.9}]},
            document_count=2,
        )


def test_hybrid_candidates_include_lexical_only_result():
    service = RetrievalService()
    dense = [make_hit("v1", "向量候选")]
    lexical = [make_hit("v2", "关键词候选")]
    with (
        patch.object(service, "_lexical_hits", return_value=lexical),
        patch("app.services.retrieval_service.settings.retrieval_hybrid_enabled", True),
        patch("app.services.retrieval_service.settings.retrieval_fusion_candidate_k", 20),
    ):
        candidates = service._build_candidates(
            query="测试",
            dense_hits=dense,
            knowledge_base_id=1,
            owner_id=1,
        )

    assert {candidate.hit.vector_id for candidate in candidates} == {"v1", "v2"}


def test_online_rerank_applies_evidence_threshold_and_returns_model_score():
    service = RetrievalService()
    candidates = [
        RetrievalCandidate(make_hit("v1", "只在主题上相关"), 0.9),
        RetrievalCandidate(make_hit("v2", "包含直接答案"), 0.8),
    ]
    with (
        patch(
            "app.services.retrieval_service.reranker_client.rerank",
            return_value=[
                RerankResult(index=1, relevance_score=0.91),
                RerankResult(index=0, relevance_score=0.12),
            ],
        ),
    ):
        sources = service._online_rerank(
            query="问题",
            candidates=candidates,
            top_n=2,
            score_threshold=0.3,
        )

    assert [source.document_id for source in sources] == [2]
    assert sources[0].score == pytest.approx(0.91)


def test_retrieval_falls_back_to_legacy_vector_rerank_on_provider_failure():
    service = RetrievalService()
    dense = [make_hit("v1", "进程是资源分配单位。", 0.9)]
    request = ChatRequest(
        knowledge_base_id=1,
        question="进程是什么？",
        score_threshold=0.95,
        rerank_top_n=2,
        enable_rerank=True,
    )
    store = Mock()
    store.search.return_value = dense
    with (
        patch.object(service, "_scope_owner_id", return_value=1),
        patch.object(service, "_filter_current_hits", return_value=dense),
        patch.object(
            service,
            "_build_candidates",
            return_value=[RetrievalCandidate(dense[0], 1.0)],
        ),
        patch(
            "app.services.retrieval_service.embedding_client.embed_texts",
            return_value=[[0.1, 0.2]],
        ),
        patch("app.services.retrieval_service.get_vector_store", return_value=store),
        patch(
            "app.services.retrieval_service.reranker_client.rerank",
            side_effect=RerankerServiceError("provider unavailable"),
        ),
        patch("app.services.retrieval_service.settings.rerank_fail_open", True),
        patch("app.services.retrieval_service.settings.retrieval_score_threshold", 0.45),
    ):
        sources = service.retrieve_sources(request.question, request, user_id=1)

    assert [source.document_id for source in sources] == [1]
    assert sources[0].score == pytest.approx(0.9)


def test_query_rewrite_removes_polite_shell_without_changing_technical_content():
    assert (
        RetrievalService().rewrite_question(
            "请问，innodb_lock_wait_timeout 的作用是什么？谢谢"
        )
        == "innodb_lock_wait_timeout 的作用是什么"
    )
