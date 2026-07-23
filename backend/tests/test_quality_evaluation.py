import json
from pathlib import Path

import pytest

from app.evaluation.quality import (
    build_chunks,
    calculate_quiz_automatic_metrics,
    calculate_rag_metrics,
    cosine_similarity,
    corpus_sha256,
    evaluate_rag_thresholds,
    is_refusal,
    load_dataset,
    summarize_quiz_manual_csv,
    validate_dataset,
)


DATA_ROOT = Path(__file__).resolve().parents[2] / "testdata" / "eval"


def test_fixed_quality_dataset_satisfies_issue_32_contract():
    summary = validate_dataset(load_dataset(DATA_ROOT))

    assert summary["document_count"] == 8
    assert summary["rag_case_count"] == 64
    assert summary["answerable_count"] == 40
    assert summary["insufficient_count"] == 24
    assert summary["quiz_case_count"] == 16
    assert len(summary["corpus_sha256"]) == 64


def test_fixed_quality_dataset_hash_is_independent_of_checkout_newlines(tmp_path: Path):
    dataset = load_dataset(DATA_ROOT)
    for file_name in ("manifest.json", "rag_cases.json", "quiz_cases.json"):
        raw = (DATA_ROOT / file_name).read_bytes()
        lf_only = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        (tmp_path / file_name).write_bytes(lf_only.replace(b"\n", b"\r\n"))
    crlf_dataset = type(dataset)(
        root=tmp_path,
        manifest=dataset.manifest,
        documents=dataset.documents,
        rag_cases=dataset.rag_cases,
        quiz_cases=dataset.quiz_cases,
    )

    assert corpus_sha256(crlf_dataset) == corpus_sha256(dataset)


def test_cosine_similarity_matches_chroma_cosine_score_semantics():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_rag_metrics_separate_recall_citation_and_insufficient_risk():
    rows = [
        {
            "kind": "answerable",
            "expected_document_hit": True,
            "top1_document_correct": True,
            "correct_citation_count": 1,
            "retrieved": [{"document_id": "doc-a"}],
        },
        {
            "kind": "answerable",
            "expected_document_hit": False,
            "top1_document_correct": False,
            "correct_citation_count": 0,
            "retrieved": [],
        },
        {
            "kind": "insufficient",
            "expected_document_hit": False,
            "top1_document_correct": False,
            "correct_citation_count": 0,
            "retrieved": [{"document_id": "doc-a"}],
        },
        {
            "kind": "insufficient",
            "expected_document_hit": False,
            "top1_document_correct": False,
            "correct_citation_count": 0,
            "retrieved": [],
        },
    ]

    metrics = calculate_rag_metrics(rows)

    assert metrics["recall_hit_rate"] == 0.5
    assert metrics["citation_document_precision"] == 1.0
    assert metrics["positive_empty_rate"] == 0.5
    assert metrics["insufficient_empty_rate"] == 0.5
    assert metrics["retrieval_confident_error_risk"] == 0.5


def test_threshold_recommendation_requires_recall_and_insufficient_risk_gate():
    dataset = load_dataset(DATA_ROOT)
    chunks = build_chunks(dataset)
    document_axes = {
        document_id: index for index, document_id in enumerate(dataset.documents)
    }

    def vector_for(document_id: str) -> list[float]:
        vector = [0.0] * len(document_axes)
        vector[document_axes[document_id]] = 1.0
        return vector

    chunk_vectors = [vector_for(chunk.document_id) for chunk in chunks]
    safe_queries = [
        vector_for(case["document_id"])
        if case["kind"] == "answerable"
        else [0.0] * len(document_axes)
        for case in dataset.rag_cases
    ]
    safe_report = evaluate_rag_thresholds(
        dataset,
        thresholds=[0.5],
        chunk_vectors=chunk_vectors,
        query_vectors=safe_queries,
    )

    assert safe_report["quality_target_met"] is True
    assert safe_report["recommended_threshold"] == 0.5
    assert safe_report["recommended_metrics"]["recall_hit_rate"] == 1.0
    assert safe_report["recommended_metrics"]["retrieval_confident_error_risk"] == 0.0

    risky_queries = [vector_for(case["document_id"]) for case in dataset.rag_cases]
    risky_report = evaluate_rag_thresholds(
        dataset,
        thresholds=[0.5],
        chunk_vectors=chunk_vectors,
        query_vectors=risky_queries,
    )

    assert risky_report["quality_target_met"] is False
    assert risky_report["recommended_threshold"] is None
    assert risky_report["best_observed_threshold"] == 0.5
    assert risky_report["best_observed_metrics"]["retrieval_confident_error_risk"] == 1.0


def test_quiz_automatic_metrics_report_duplicates_sources_and_key_points():
    case = {"expected_key_points": ["互斥锁", "死锁", "线程"]}
    context = [
        {
            "source_id": "S1",
            "source_text": "线程使用互斥锁保护共享状态，统一加锁顺序可以降低死锁风险。",
        }
    ]
    question = {
        "question_type": "short_answer",
        "cognitive_level": "understand",
        "prompt": "线程为什么需要互斥锁？",
        "options": [],
        "correct_answer": None,
        "accepted_answers": [],
        "keywords": ["互斥锁"],
        "reference_answer": "互斥锁保护线程共享状态。",
        "explanation": "统一加锁顺序还可以降低死锁风险。",
        "source_ids": ["S1"],
    }

    metrics = calculate_quiz_automatic_metrics(
        case=case,
        payload={"questions": [question, dict(question)]},
        context=context,
    )

    assert metrics["exact_duplicate_count"] == 1
    assert metrics["near_duplicate_pairs"]
    assert metrics["source_verifiable_rate_heuristic"] == 1.0
    assert metrics["key_point_coverage"] == 1.0
    assert metrics["manual_review_required"] is True


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("知识库中未找到足够依据。", True),
        ("资料没有给出该参数的精确值。", True),
        ("默认值是 30 秒。", False),
    ],
)
def test_refusal_detection(answer: str, expected: bool):
    assert is_refusal(answer) is expected


def test_manual_quiz_score_summary_tracks_incomplete_rows(tmp_path: Path):
    score_file = tmp_path / "scores.csv"
    score_file.write_text(
        "fact_correctness_0_2,material_relevance_0_2,difficulty_fit_0_2,"
        "source_verifiable_0_2,duplicate_0_1\n"
        "2,2,1,2,0\n"
        ",2,2,2,0\n",
        encoding="utf-8",
    )

    summary = summarize_quiz_manual_csv(score_file)

    assert summary["row_count"] == 2
    assert summary["scored_question_count"] == 1
    assert summary["incomplete_question_count"] == 1
    assert summary["dimension_rates"]["fact_correctness"] == 1.0
    assert summary["dimension_rates"]["difficulty_fit"] == 0.5


def test_committed_quality_baseline_artifacts_match_fixed_dataset():
    dataset = load_dataset(DATA_ROOT)
    expected_hash = validate_dataset(dataset)["corpus_sha256"]
    baseline_root = DATA_ROOT / "baselines" / "2026-07-22"
    json_paths = sorted(baseline_root.glob("*.json"))
    reports = {}

    assert len(json_paths) == 5
    for path in json_paths:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        reports[path.name] = payload
        assert payload["dataset"]["corpus_sha256"] == expected_hash
        assert "api_key" not in path.read_text(encoding="utf-8-sig").casefold()

    threshold = reports["rag_threshold_qwen3-vl-embedding-8b.json"]
    assert threshold["configuration"]["embedding_model"] == "Qwen/Qwen3-VL-Embedding-8B"
    assert threshold["configuration"]["embedding_dimension"] == 4096
    assert threshold["configuration"]["configured_default_threshold"] == 0.45
    assert threshold["quality_target_met"] is False
    assert threshold["recommended_threshold"] is None
    assert threshold["best_observed_threshold"] == 0.3
    assert [row["threshold"] for row in threshold["threshold_results"]] == [
        0.25,
        0.3,
        0.35,
        0.4,
        0.45,
        0.5,
        0.55,
        0.6,
        0.65,
        0.7,
        0.75,
    ]
    assert threshold["generation_evaluation"]["configuration"] == {
        "llm_model": "Qwen/Qwen3.6-35B-A3B",
        "llm_base_url": "https://api.siliconflow.cn/v1",
        "llm_timeout_seconds": 120.0,
        "llm_max_tokens": 1200,
        "llm_max_retries": 1,
        "retrieval_threshold": 0.3,
        "positive_per_document": 1,
        "concurrency": 1,
    }
    assert threshold["generation_evaluation"]["metrics"]["error_confident_answer_rate"] == 0.0

    hybrid = reports["rag_hybrid_qwen3-reranker-8b.json"]
    assert hybrid["evaluation_type"] == "rag-hybrid-rerank-threshold"
    assert hybrid["configuration"]["embedding_text_fields"] == [
        "document_title",
        "section_title",
        "content",
    ]
    assert hybrid["configuration"]["chunk_count"] == 33
    assert hybrid["configuration"]["rerank_model"] == "Qwen/Qwen3-Reranker-8B"
    assert hybrid["configuration"]["configured_rerank_threshold"] == 0.55
    assert hybrid["configuration"]["final_score_type"] == "reranker_relevance_score"
    assert hybrid["quality_target_met"] is True
    assert hybrid["recommended_threshold"] == 0.55
    assert hybrid["recommended_metrics"]["recall_hit_rate"] == 1.0
    assert hybrid["recommended_metrics"]["top1_document_accuracy"] == 1.0
    assert hybrid["recommended_metrics"]["citation_document_precision"] == 1.0
    assert (
        hybrid["recommended_metrics"]["retrieval_confident_error_risk"] == 0.0
    )
    hybrid_generation = hybrid["generation_evaluation"]
    assert hybrid_generation["configuration"]["retrieval_score_type"] == (
        "reranker_relevance_score"
    )
    assert hybrid_generation["metrics"]["provider_error_count"] == 0
    assert hybrid_generation["metrics"]["answerable_refusal_rate"] == 0.0
    assert hybrid_generation["metrics"]["mean_expected_keyword_coverage"] == 1.0
    assert hybrid_generation["metrics"]["error_confident_answer_rate"] == 0.0

    default_generation = reports["rag_default_045_generation.json"]
    assert default_generation["best_observed_threshold"] == 0.45
    assert default_generation["generation_evaluation"]["metrics"]["answerable_refusal_rate"] == 0.5

    quiz_initial = reports["quiz_initial_qwen3.6-35b-a3b.json"]
    assert quiz_initial["configuration"]["llm_model"] == "Qwen/Qwen3.6-35B-A3B"
    assert quiz_initial["configuration"]["quiz_structure_max_retries"] == 1
    assert quiz_initial["configuration"]["quiz_context_max_tokens"] == 8000
    assert quiz_initial["configuration"]["quiz_context_max_chars"] == 30000
    assert quiz_initial["summary"]["successful_case_count"] == 4
    assert quiz_initial["summary"]["failed_case_count"] == 4
    assert quiz_initial["summary"]["question_count"] == 20

    quiz_recovery = reports["quiz_recovery_qwen3.6-35b-a3b.json"]
    assert quiz_recovery["summary"]["successful_case_count"] == 4
    assert quiz_recovery["summary"]["failed_case_count"] == 0
    assert quiz_recovery["summary"]["question_count"] == 20

    manual = summarize_quiz_manual_csv(baseline_root / "quiz_manual_scores.csv")
    assert manual["scored_question_count"] == 40
    assert manual["incomplete_question_count"] == 0
    assert manual["dimension_rates"] == {
        "fact_correctness": 0.9875,
        "material_relevance": 1.0,
        "difficulty_fit": 0.975,
        "source_verifiable": 1.0,
    }
    assert manual["duplicate_rate"] == 0.0
