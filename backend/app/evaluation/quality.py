from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from app.core.config import PROJECT_ROOT, settings
from app.schemas.contracts import SourceReference
from app.schemas.quiz import QuizCreateRequest, QuizSource
from app.services.embedding_client import embedding_client
from app.services.embedding_text import build_embedding_text
from app.services.llm_client import llm_client, system_llm_runtime_config
from app.services.document_parser import document_parser
from app.services.prompt_builder import build_rag_prompt, sanitize_answer_citations
from app.services.quiz_service import QuizService
from app.services.reranker_client import reranker_client
from app.services.retrieval_scoring import (
    LexicalDocument,
    bm25_rank,
    keyword_overlap,
    reciprocal_rank_fusion,
)
from app.services.text_splitter import TextSplitter


DEFAULT_DATA_ROOT = PROJECT_ROOT / "testdata" / "eval"
DEFAULT_THRESHOLDS = [round(value / 100, 2) for value in range(25, 76, 5)]
DEFAULT_RERANK_THRESHOLDS = [round(value / 100, 2) for value in range(5, 96, 5)]
REFUSAL_MARKERS = (
    "知识库中未找到足够依据",
    "未找到足够依据",
    "资料不足",
    "依据不足",
    "无法根据",
    "无法从",
    "未提供",
    "未提及",
    "没有说明",
    "没有给出",
    "无法确定",
    "不能确定",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)(api[_-]?key|secret|password)\s*[=:]\s*[^\s<]{12,}"),
)


class DatasetValidationError(ValueError):
    pass


@dataclass(frozen=True)
class EvalDocument:
    document_id: str
    document_no: int
    title: str
    domain: str
    path: Path
    text: str


@dataclass(frozen=True)
class EvalChunk:
    chunk_id: int
    document_id: str
    document_no: int
    file_name: str
    chunk_index: int
    text: str
    section_title: str | None = None


@dataclass(frozen=True)
class EvaluationDataset:
    root: Path
    manifest: dict[str, Any]
    documents: dict[str, EvalDocument]
    rag_cases: list[dict[str, Any]]
    quiz_cases: list[dict[str, Any]]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"无法读取评估文件 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise DatasetValidationError(f"评估文件必须是 JSON 对象：{path}")
    return data


def load_dataset(data_root: Path | str = DEFAULT_DATA_ROOT) -> EvaluationDataset:
    root = Path(data_root).resolve()
    manifest = _load_json(root / "manifest.json")
    rag_payload = _load_json(root / "rag_cases.json")
    quiz_payload = _load_json(root / "quiz_cases.json")

    documents: dict[str, EvalDocument] = {}
    for item in manifest.get("documents", []):
        path = (root / str(item.get("path", ""))).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise DatasetValidationError(f"语料路径越出数据目录：{path}") from exc
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DatasetValidationError(f"无法读取语料 {path}: {exc}") from exc
        document_id = str(item.get("id", "")).strip()
        documents[document_id] = EvalDocument(
            document_id=document_id,
            document_no=int(item.get("document_no", 0)),
            title=str(item.get("title", "")).strip(),
            domain=str(item.get("domain", "")).strip(),
            path=path,
            text=text,
        )

    return EvaluationDataset(
        root=root,
        manifest=manifest,
        documents=documents,
        rag_cases=list(rag_payload.get("cases", [])),
        quiz_cases=list(quiz_payload.get("cases", [])),
    )


def validate_dataset(dataset: EvaluationDataset) -> dict[str, Any]:
    errors: list[str] = []
    dataset_id = dataset.manifest.get("dataset_id")
    dataset_version = dataset.manifest.get("version")
    if not dataset_id:
        errors.append("manifest.json 缺少 dataset_id")
    if not dataset_version:
        errors.append("manifest.json 缺少 version")
    for file_name in ("rag_cases.json", "quiz_cases.json"):
        payload = _load_json(dataset.root / file_name)
        if payload.get("dataset_id") != dataset_id:
            errors.append(f"{file_name} 的 dataset_id 与 manifest 不一致")
        if payload.get("version") != dataset_version:
            errors.append(f"{file_name} 的 version 与 manifest 不一致")

    document_items = dataset.manifest.get("documents", [])
    if not 8 <= len(document_items) <= 15:
        errors.append(f"固定语料要求 8～15 份，当前为 {len(document_items)} 份")
    document_ids = [str(item.get("id", "")) for item in document_items]
    document_nos = [int(item.get("document_no", 0)) for item in document_items]
    if len(document_ids) != len(set(document_ids)) or any(not value for value in document_ids):
        errors.append("语料 id 为空或重复")
    if len(document_nos) != len(set(document_nos)) or any(value <= 0 for value in document_nos):
        errors.append("document_no 必须为不重复的正整数")

    rag_ids: set[str] = set()
    rag_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for case in dataset.rag_cases:
        case_id = str(case.get("id", "")).strip()
        document_id = str(case.get("document_id", "")).strip()
        kind = str(case.get("kind", "")).strip()
        if not case_id or case_id in rag_ids:
            errors.append(f"RAG 用例 id 为空或重复：{case_id or '<empty>'}")
        rag_ids.add(case_id)
        if document_id not in dataset.documents:
            errors.append(f"RAG 用例 {case_id} 引用了不存在的文档 {document_id}")
            continue
        if kind not in {"answerable", "insufficient"}:
            errors.append(f"RAG 用例 {case_id} 的 kind 无效：{kind}")
            continue
        if not str(case.get("question", "")).strip():
            errors.append(f"RAG 用例 {case_id} 缺少 question")
        rag_counts[document_id][kind] += 1
        expected_terms = case.get("expected_terms")
        answer_keywords = case.get("answer_keywords")
        if not isinstance(expected_terms, list) or not isinstance(answer_keywords, list):
            errors.append(f"RAG 用例 {case_id} 的 expected_terms/answer_keywords 必须是数组")
            continue
        if kind == "answerable":
            if not expected_terms or not answer_keywords:
                errors.append(f"可回答用例 {case_id} 必须提供依据原句和答案关键词")
            source_text = dataset.documents[document_id].text
            for term in expected_terms:
                if str(term) not in source_text:
                    errors.append(f"RAG 用例 {case_id} 的依据原句不在目标文档中：{term}")
        elif expected_terms or answer_keywords:
            errors.append(f"依据不足用例 {case_id} 不应提供答案依据")

    quiz_ids: set[str] = set()
    quiz_counts: Counter[str] = Counter()
    for case in dataset.quiz_cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in quiz_ids:
            errors.append(f"出题用例 id 为空或重复：{case_id or '<empty>'}")
        quiz_ids.add(case_id)
        document_refs = case.get("document_ids", [])
        if not isinstance(document_refs, list) or not document_refs:
            errors.append(f"出题用例 {case_id} 未指定文档")
            continue
        for document_id in document_refs:
            if document_id not in dataset.documents:
                errors.append(f"出题用例 {case_id} 引用了不存在的文档 {document_id}")
            else:
                quiz_counts[str(document_id)] += 1
        try:
            QuizCreateRequest(
                knowledge_base_ids=[1],
                question_count=case.get("question_count"),
                difficulty=case.get("difficulty"),
                question_types=case.get("question_types", []),
                random_mix=case.get("random_mix", True),
                topic=case.get("topic"),
            )
        except Exception as exc:
            errors.append(f"出题用例 {case_id} 配置无效：{exc}")
        key_points = case.get("expected_key_points")
        if not isinstance(key_points, list) or len(key_points) < 3:
            errors.append(f"出题用例 {case_id} 至少需要 3 个 expected_key_points")

    for document_id in dataset.documents:
        counts = rag_counts[document_id]
        if not 5 <= counts["answerable"] <= 10:
            errors.append(
                f"文档 {document_id} 的可回答问题应为 5～10 条，当前 {counts['answerable']} 条"
            )
        if not 3 <= counts["insufficient"] <= 5:
            errors.append(
                f"文档 {document_id} 的依据不足问题应为 3～5 条，当前 {counts['insufficient']} 条"
            )
        if not 2 <= quiz_counts[document_id] <= 3:
            errors.append(
                f"文档 {document_id} 的出题期望应为 2～3 套，当前 {quiz_counts[document_id]} 套"
            )

    scanned_paths = sorted(
        path
        for path in dataset.root.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".csv", ".json", ".md", ".txt"}
    )
    for path in scanned_paths:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"评估资料疑似包含密钥或密码：{path}")
                break

    if errors:
        raise DatasetValidationError("\n".join(f"- {error}" for error in errors))

    return {
        "dataset_id": dataset_id,
        "version": dataset_version,
        "document_count": len(dataset.documents),
        "rag_case_count": len(dataset.rag_cases),
        "answerable_count": sum(
            case["kind"] == "answerable" for case in dataset.rag_cases
        ),
        "insufficient_count": sum(
            case["kind"] == "insufficient" for case in dataset.rag_cases
        ),
        "quiz_case_count": len(dataset.quiz_cases),
        "corpus_sha256": corpus_sha256(dataset),
    }


def corpus_sha256(dataset: EvaluationDataset) -> str:
    digest = hashlib.sha256()
    for document in sorted(dataset.documents.values(), key=lambda item: item.document_id):
        digest.update(document.document_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(document.text.encode("utf-8"))
        digest.update(b"\0")
    for file_name in ("manifest.json", "rag_cases.json", "quiz_cases.json"):
        digest.update((dataset.root / file_name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_chunks(dataset: EvaluationDataset) -> list[EvalChunk]:
    config = dataset.manifest.get("chunking", {})
    splitter = TextSplitter(
        chunk_size=int(config.get("chunk_size", 800)),
        overlap=int(config.get("overlap", 120)),
    )
    chunks: list[EvalChunk] = []
    for document in sorted(dataset.documents.values(), key=lambda item: item.document_no):
        blocks = document_parser.parse(str(document.path), document.path.suffix)
        for chunk in splitter.split_blocks(blocks):
            chunks.append(
                EvalChunk(
                    chunk_id=len(chunks) + 1,
                    document_id=document.document_id,
                    document_no=document.document_no,
                    file_name=document.path.name,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    section_title=chunk.section_title,
                )
            )
    return chunks


def embed_texts_in_batches(texts: list[str], *, batch_size: int = 16) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(embedding_client.embed_texts(texts[start : start + batch_size]))
    return vectors


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding 向量维度不一致")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    score = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    return max(-1.0, min(1.0, score))


def _rank_for_case(
    *,
    case: dict[str, Any],
    query_vector: list[float],
    chunks: list[EvalChunk],
    chunk_vectors: list[list[float]],
    top_k: int,
) -> list[dict[str, Any]]:
    ranked = [
        {
            "chunk": chunk,
            "score": cosine_similarity(query_vector, vector),
        }
        for chunk, vector in zip(chunks, chunk_vectors, strict=True)
    ]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def _apply_production_filter(
    *,
    case: dict[str, Any],
    ranked: list[dict[str, Any]],
    threshold: float,
    enable_rerank: bool,
    rerank_top_n: int,
) -> list[dict[str, Any]]:
    selected = [item for item in ranked if item["score"] >= threshold]
    if enable_rerank:
        selected.sort(
            key=lambda item: item["score"] * 0.8
            + keyword_overlap(str(case["question"]), item["chunk"].text) * 0.2,
            reverse=True,
        )
        return selected[:rerank_top_n]
    return selected


def calculate_rag_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [row for row in case_results if row["kind"] == "answerable"]
    negatives = [row for row in case_results if row["kind"] == "insufficient"]
    hits = sum(row["expected_document_hit"] for row in positives)
    top1_hits = sum(row["top1_document_correct"] for row in positives)
    positive_empty = sum(not row["retrieved"] for row in positives)
    negative_non_empty = sum(bool(row["retrieved"]) for row in negatives)
    citation_correct = sum(row["correct_citation_count"] for row in positives)
    citation_total = sum(len(row["retrieved"]) for row in positives)
    tp = hits
    fn = len(positives) - hits
    fp = negative_non_empty
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / len(positives) if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "answerable_count": len(positives),
        "insufficient_count": len(negatives),
        "recall_hit_rate": round(recall, 4),
        "top1_document_accuracy": round(top1_hits / len(positives), 4) if positives else 0.0,
        "citation_document_precision": round(citation_correct / citation_total, 4)
        if citation_total
        else 0.0,
        "positive_empty_rate": round(positive_empty / len(positives), 4) if positives else 0.0,
        "insufficient_empty_rate": round(
            (len(negatives) - negative_non_empty) / len(negatives), 4
        )
        if negatives
        else 0.0,
        "retrieval_confident_error_risk": round(
            negative_non_empty / len(negatives), 4
        )
        if negatives
        else 0.0,
        "case_precision": round(precision, 4),
        "case_f1": round(f1, 4),
    }


def evaluate_rag_thresholds(
    dataset: EvaluationDataset,
    *,
    thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
    top_k: int = 4,
    enable_rerank: bool = True,
    rerank_top_n: int = 2,
    batch_size: int = 16,
    chunk_vectors: list[list[float]] | None = None,
    query_vectors: list[list[float]] | None = None,
) -> dict[str, Any]:
    validation = validate_dataset(dataset)
    chunks = build_chunks(dataset)
    started = time.perf_counter()
    actual_chunk_vectors = chunk_vectors or embed_texts_in_batches(
        [
            build_embedding_text(
                file_name=chunk.file_name,
                section_title=chunk.section_title,
                text=chunk.text,
            )
            for chunk in chunks
        ],
        batch_size=batch_size,
    )
    actual_query_vectors = query_vectors or embed_texts_in_batches(
        [str(case["question"]) for case in dataset.rag_cases], batch_size=batch_size
    )
    if len(actual_chunk_vectors) != len(chunks):
        raise ValueError("语料 Embedding 数量与 chunk 数量不一致")
    if len(actual_query_vectors) != len(dataset.rag_cases):
        raise ValueError("问题 Embedding 数量与用例数量不一致")
    dimensions = {len(vector) for vector in actual_chunk_vectors + actual_query_vectors}
    if len(dimensions) != 1:
        raise ValueError("评估使用的 Embedding 向量维度不一致")

    ranked_by_case = [
        _rank_for_case(
            case=case,
            query_vector=query_vector,
            chunks=chunks,
            chunk_vectors=actual_chunk_vectors,
            top_k=top_k,
        )
        for case, query_vector in zip(dataset.rag_cases, actual_query_vectors, strict=True)
    ]
    threshold_rows: list[dict[str, Any]] = []
    case_results_by_threshold: dict[float, list[dict[str, Any]]] = {}
    normalized_thresholds = sorted({round(float(value), 4) for value in thresholds})
    for threshold in normalized_thresholds:
        case_results: list[dict[str, Any]] = []
        for case, ranked in zip(dataset.rag_cases, ranked_by_case, strict=True):
            selected = _apply_production_filter(
                case=case,
                ranked=ranked,
                threshold=threshold,
                enable_rerank=enable_rerank,
                rerank_top_n=rerank_top_n,
            )
            expected_document_id = str(case["document_id"])
            retrieved = [
                {
                    "document_id": item["chunk"].document_id,
                    "file_name": item["chunk"].file_name,
                    "chunk_index": item["chunk"].chunk_index,
                    "score": round(float(item["score"]), 6),
                    "source_text": item["chunk"].text,
                }
                for item in selected
            ]
            correct_count = sum(
                item["document_id"] == expected_document_id for item in retrieved
            )
            case_results.append(
                {
                    "case_id": case["id"],
                    "kind": case["kind"],
                    "question": case["question"],
                    "expected_document_id": expected_document_id,
                    "expected_document_hit": bool(correct_count)
                    if case["kind"] == "answerable"
                    else False,
                    "top1_document_correct": bool(
                        retrieved and retrieved[0]["document_id"] == expected_document_id
                    )
                    if case["kind"] == "answerable"
                    else False,
                    "correct_citation_count": correct_count
                    if case["kind"] == "answerable"
                    else 0,
                    "retrieved": retrieved,
                }
            )
        metrics = calculate_rag_metrics(case_results)
        threshold_rows.append({"threshold": threshold, **metrics})
        case_results_by_threshold[threshold] = case_results

    eligible = [
        row
        for row in threshold_rows
        if row["recall_hit_rate"] >= 0.9
        and row["retrieval_confident_error_risk"] <= 0.1
    ]
    candidates = eligible or threshold_rows
    best_observed = max(
        candidates,
        key=lambda row: (
            row["case_f1"],
            row["citation_document_precision"],
            -row["retrieval_confident_error_risk"],
            row["recall_hit_rate"],
            -abs(row["threshold"] - settings.retrieval_score_threshold),
        ),
    )
    recommendation_reason = (
        "满足召回率不低于 90% 且依据不足误召回风险不高于 10%，在合格候选中综合 F1 最优。"
        if eligible
        else "没有阈值同时满足 90% 召回与 10% 误召回风险目标，因此不发布可直接替换生产配置的推荐阈值；best_observed_threshold 仅表示当前扫描范围内综合 F1 最优值。"
    )
    default_threshold = round(float(settings.retrieval_score_threshold), 4)
    default_metrics = next(
        (row for row in threshold_rows if row["threshold"] == default_threshold), None
    )
    return {
        "schema_version": "1.0",
        "evaluation_type": "rag-retrieval-threshold",
        "run_date": date.today().isoformat(),
        "dataset": validation,
        "configuration": {
            "embedding_model": settings.embedding_model,
            "embedding_base_url": settings.embedding_base_url,
            "embedding_dimension": next(iter(dimensions)),
            "chunk_size": dataset.manifest["chunking"]["chunk_size"],
            "chunk_overlap": dataset.manifest["chunking"]["overlap"],
            "chunk_count": len(chunks),
            "top_k": top_k,
            "enable_rerank": enable_rerank,
            "rerank_top_n": rerank_top_n,
            "configured_default_threshold": default_threshold,
        },
        "duration_seconds": round(time.perf_counter() - started, 3),
        "threshold_results": threshold_rows,
        "configured_default_metrics": default_metrics,
        "quality_target_met": bool(eligible),
        "recommended_threshold": best_observed["threshold"] if eligible else None,
        "recommended_metrics": best_observed if eligible else None,
        "best_observed_threshold": best_observed["threshold"],
        "best_observed_metrics": best_observed,
        "recommendation_reason": recommendation_reason,
        "case_results": case_results_by_threshold[best_observed["threshold"]],
    }


def evaluate_hybrid_rerank_thresholds(
    dataset: EvaluationDataset,
    *,
    thresholds: Iterable[float] = DEFAULT_RERANK_THRESHOLDS,
    dense_candidate_k: int | None = None,
    lexical_candidate_k: int | None = None,
    fusion_candidate_k: int | None = None,
    final_top_n: int = 2,
    rank_constant: int | None = None,
    batch_size: int = 16,
    concurrency: int = 8,
    chunk_vectors: list[list[float]] | None = None,
    query_vectors: list[list[float]] | None = None,
) -> dict[str, Any]:
    validation = validate_dataset(dataset)
    chunks = build_chunks(dataset)
    started = time.perf_counter()
    embedding_inputs = [
        build_embedding_text(
            file_name=chunk.file_name,
            section_title=chunk.section_title,
            text=chunk.text,
        )
        for chunk in chunks
    ]
    actual_chunk_vectors = chunk_vectors or embed_texts_in_batches(
        embedding_inputs,
        batch_size=batch_size,
    )
    actual_query_vectors = query_vectors or embed_texts_in_batches(
        [str(case["question"]) for case in dataset.rag_cases],
        batch_size=batch_size,
    )
    if len(actual_chunk_vectors) != len(chunks):
        raise ValueError("语料 Embedding 数量与 chunk 数量不一致")
    if len(actual_query_vectors) != len(dataset.rag_cases):
        raise ValueError("问题 Embedding 数量与用例数量不一致")
    dimensions = {len(vector) for vector in actual_chunk_vectors + actual_query_vectors}
    if len(dimensions) != 1:
        raise ValueError("评估使用的 Embedding 向量维度不一致")

    dense_k = max(1, dense_candidate_k or settings.retrieval_dense_candidate_k)
    lexical_k = max(1, lexical_candidate_k or settings.retrieval_lexical_candidate_k)
    fusion_k = max(1, fusion_candidate_k or settings.retrieval_fusion_candidate_k)
    rrf_k = max(1, rank_constant or settings.retrieval_rrf_k)
    chunk_by_id = {str(chunk.chunk_id): chunk for chunk in chunks}
    lexical_documents = [
        LexicalDocument(key=str(chunk.chunk_id), text=embedding_text)
        for chunk, embedding_text in zip(chunks, embedding_inputs, strict=True)
    ]

    def rerank_case(item: tuple[int, dict[str, Any]]) -> list[dict[str, Any]]:
        index, case = item
        dense = _rank_for_case(
            case=case,
            query_vector=actual_query_vectors[index],
            chunks=chunks,
            chunk_vectors=actual_chunk_vectors,
            top_k=dense_k,
        )
        dense_ids = [str(row["chunk"].chunk_id) for row in dense]
        dense_scores = {
            str(row["chunk"].chunk_id): float(row["score"]) for row in dense
        }
        lexical = bm25_rank(
            str(case["question"]),
            lexical_documents,
            top_k=lexical_k,
        )
        lexical_ids = [key for key, _ in lexical]
        rankings = [dense_ids]
        if lexical_ids:
            rankings.append(lexical_ids)
        fused = reciprocal_rank_fusion(rankings, rank_constant=rrf_k)
        candidate_ids = sorted(fused, key=fused.get, reverse=True)[:fusion_k]
        candidates = [chunk_by_id[key] for key in candidate_ids]
        documents = [
            build_embedding_text(
                file_name=chunk.file_name,
                section_title=chunk.section_title,
                text=chunk.text,
            )
            for chunk in candidates
        ]
        reranked = reranker_client.rerank(
            query=str(case["question"]),
            documents=documents,
            top_n=len(documents),
        )
        return [
            {
                "chunk": candidates[result.index],
                "rerank_score": result.relevance_score,
                "dense_score": dense_scores.get(
                    str(candidates[result.index].chunk_id)
                ),
                "fusion_score": fused[str(candidates[result.index].chunk_id)],
            }
            for result in reranked
        ]

    indexed_cases = list(enumerate(dataset.rag_cases))
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        reranked_by_case = list(executor.map(rerank_case, indexed_cases))

    normalized_thresholds = sorted({round(float(value), 4) for value in thresholds})
    threshold_rows: list[dict[str, Any]] = []
    case_results_by_threshold: dict[float, list[dict[str, Any]]] = {}
    for threshold in normalized_thresholds:
        case_results: list[dict[str, Any]] = []
        for case, reranked in zip(dataset.rag_cases, reranked_by_case, strict=True):
            selected = [
                row for row in reranked if row["rerank_score"] >= threshold
            ][: max(1, final_top_n)]
            expected_document_id = str(case["document_id"])
            retrieved = [
                {
                    "document_id": row["chunk"].document_id,
                    "file_name": row["chunk"].file_name,
                    "chunk_index": row["chunk"].chunk_index,
                    "section_title": row["chunk"].section_title,
                    "score": round(float(row["rerank_score"]), 6),
                    "dense_score": round(float(row["dense_score"]), 6)
                    if row["dense_score"] is not None
                    else None,
                    "fusion_score": round(float(row["fusion_score"]), 6),
                    "source_text": row["chunk"].text,
                }
                for row in selected
            ]
            correct_count = sum(
                item["document_id"] == expected_document_id for item in retrieved
            )
            case_results.append(
                {
                    "case_id": case["id"],
                    "kind": case["kind"],
                    "question": case["question"],
                    "expected_document_id": expected_document_id,
                    "expected_document_hit": bool(correct_count)
                    if case["kind"] == "answerable"
                    else False,
                    "top1_document_correct": bool(
                        retrieved and retrieved[0]["document_id"] == expected_document_id
                    )
                    if case["kind"] == "answerable"
                    else False,
                    "correct_citation_count": correct_count
                    if case["kind"] == "answerable"
                    else 0,
                    "retrieved": retrieved,
                }
            )
        metrics = calculate_rag_metrics(case_results)
        threshold_rows.append({"threshold": threshold, **metrics})
        case_results_by_threshold[threshold] = case_results

    eligible = [
        row
        for row in threshold_rows
        if row["recall_hit_rate"] >= 0.9
        and row["retrieval_confident_error_risk"] <= 0.1
    ]
    candidates = eligible or threshold_rows
    best_observed = max(
        candidates,
        key=lambda row: (
            row["case_f1"],
            row["citation_document_precision"],
            -row["retrieval_confident_error_risk"],
            row["recall_hit_rate"],
            -abs(row["threshold"] - settings.rerank_score_threshold),
        ),
    )
    configured_threshold = round(float(settings.rerank_score_threshold), 4)
    configured_metrics = next(
        (row for row in threshold_rows if row["threshold"] == configured_threshold),
        None,
    )
    return {
        "schema_version": "1.0",
        "evaluation_type": "rag-hybrid-rerank-threshold",
        "run_date": date.today().isoformat(),
        "dataset": validation,
        "configuration": {
            "embedding_model": settings.embedding_model,
            "embedding_base_url": settings.embedding_base_url,
            "embedding_dimension": next(iter(dimensions)),
            "embedding_text_fields": ["document_title", "section_title", "content"],
            "chunk_size": dataset.manifest["chunking"]["chunk_size"],
            "chunk_overlap": dataset.manifest["chunking"]["overlap"],
            "chunk_count": len(chunks),
            "dense_candidate_k": dense_k,
            "lexical_candidate_k": lexical_k,
            "fusion_candidate_k": fusion_k,
            "rrf_k": rrf_k,
            "rerank_model": settings.rerank_model,
            "rerank_base_url": settings.effective_rerank_base_url,
            "rerank_instruction": settings.rerank_instruction,
            "final_top_n": max(1, final_top_n),
            "configured_rerank_threshold": configured_threshold,
            "final_score_type": "reranker_relevance_score",
            "concurrency": max(1, concurrency),
        },
        "duration_seconds": round(time.perf_counter() - started, 3),
        "threshold_results": threshold_rows,
        "configured_default_metrics": configured_metrics,
        "quality_target_met": bool(eligible),
        "recommended_threshold": best_observed["threshold"] if eligible else None,
        "recommended_metrics": best_observed if eligible else None,
        "best_observed_threshold": best_observed["threshold"],
        "best_observed_metrics": best_observed,
        "recommendation_reason": (
            "满足召回率不低于 90% 且依据不足误召回风险不高于 10%，"
            "在合格候选中综合 F1 最优。"
            if eligible
            else "没有阈值同时满足 90% 召回与 10% 误召回风险目标。"
        ),
        "case_results": case_results_by_threshold[best_observed["threshold"]],
    }


def _to_source_references(case_result: dict[str, Any], dataset: EvaluationDataset) -> list[SourceReference]:
    references: list[SourceReference] = []
    for index, item in enumerate(case_result["retrieved"], start=1):
        document = dataset.documents[item["document_id"]]
        references.append(
            SourceReference(
                document_id=document.document_no,
                chunk_id=index,
                file_name=item["file_name"],
                chunk_index=item["chunk_index"],
                score=item["score"],
                source_text=item["source_text"],
                jump_url=f"/eval/documents/{document.document_id}/chunks/{item['chunk_index']}",
            )
        )
    return references


def is_refusal(answer: str) -> bool:
    normalized = " ".join(answer.split())
    return any(marker in normalized for marker in REFUSAL_MARKERS)


async def evaluate_rag_generation(
    dataset: EvaluationDataset,
    retrieval_report: dict[str, Any],
    *,
    positive_per_document: int = 1,
    concurrency: int = 1,
) -> dict[str, Any]:
    by_id = {case["id"]: case for case in dataset.rag_cases}
    positive_seen: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    for result in retrieval_report["case_results"]:
        case = by_id[result["case_id"]]
        if case["kind"] == "insufficient":
            selected.append(result)
        elif positive_seen[case["document_id"]] < positive_per_document:
            positive_seen[case["document_id"]] += 1
            selected.append(result)

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def generate(result: dict[str, Any]) -> dict[str, Any]:
        case = by_id[result["case_id"]]
        sources = _to_source_references(result, dataset)
        started = time.perf_counter()
        error_type: str | None = None
        error_message: str | None = None
        try:
            if not sources:
                answer = "知识库中未找到足够依据。"
                provider_called = False
            else:
                prompt = build_rag_prompt(
                    question=case["question"],
                    rewritten_question=None,
                    sources=sources,
                )
                async with semaphore:
                    answer = await llm_client.generate_answer(
                        prompt,
                        temperature=0.1,
                        timeout_seconds=max(120.0, settings.llm_timeout_seconds),
                        max_tokens=max(700, settings.llm_max_tokens),
                        max_retries=1,
                    )
                answer = sanitize_answer_citations(answer, source_count=len(sources))
                provider_called = True
        except Exception as exc:
            answer = ""
            provider_called = True
            error_type = type(exc).__name__
            error_message = str(exc)[:500]
        keywords = [str(value) for value in case.get("answer_keywords", [])]
        matched = [keyword for keyword in keywords if keyword.casefold() in answer.casefold()]
        return {
            "case_id": case["id"],
            "kind": case["kind"],
            "question": case["question"],
            "source_count": len(sources),
            "provider_called": provider_called,
            "answer": answer,
            "refused": is_refusal(answer) if error_type is None else None,
            "error_type": error_type,
            "error_message": error_message,
            "expected_keyword_coverage": round(len(matched) / len(keywords), 4)
            if keywords
            else None,
            "matched_keywords": matched,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }

    rows = await asyncio.gather(*(generate(result) for result in selected))
    errors = [row for row in rows if row["error_type"] is not None]
    positives = [
        row for row in rows if row["kind"] == "answerable" and row["error_type"] is None
    ]
    negatives = [
        row for row in rows if row["kind"] == "insufficient" and row["error_type"] is None
    ]
    confident_errors = sum(not row["refused"] for row in negatives)
    return {
        "schema_version": "1.0",
        "evaluation_type": "rag-generation-sample",
        "run_date": date.today().isoformat(),
        "configuration": {
            "llm_model": settings.llm_model,
            "llm_base_url": settings.llm_base_url,
            "llm_timeout_seconds": max(120.0, settings.llm_timeout_seconds),
            "llm_max_tokens": max(700, settings.llm_max_tokens),
            "llm_max_retries": 1,
            "retrieval_threshold": retrieval_report["best_observed_threshold"],
            "retrieval_evaluation_type": retrieval_report["evaluation_type"],
            "retrieval_score_type": (
                "reranker_relevance_score"
                if retrieval_report["evaluation_type"]
                == "rag-hybrid-rerank-threshold"
                else "embedding_similarity"
            ),
            "positive_per_document": positive_per_document,
            "concurrency": max(1, concurrency),
        },
        "metrics": {
            "selected_case_count": len(rows),
            "provider_error_count": len(errors),
            "provider_error_rate": round(len(errors) / len(rows), 4) if rows else 0.0,
            "answerable_sample_count": len(positives),
            "insufficient_sample_count": len(negatives),
            "answerable_refusal_rate": round(
                sum(row["refused"] for row in positives) / len(positives), 4
            )
            if positives
            else 0.0,
            "mean_expected_keyword_coverage": round(
                sum(row["expected_keyword_coverage"] or 0.0 for row in positives)
                / len(positives),
                4,
            )
            if positives
            else 0.0,
            "error_confident_answer_rate": round(confident_errors / len(negatives), 4)
            if negatives
            else 0.0,
        },
        "cases": rows,
    }


def _quiz_context(dataset: EvaluationDataset, case: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = set(case["document_ids"])
    selected = [chunk for chunk in build_chunks(dataset) if chunk.document_id in allowed]
    context: list[dict[str, Any]] = []
    for chunk in selected[: settings.quiz_context_max_chunks]:
        document = dataset.documents[chunk.document_id]
        source_id = f"S{len(context) + 1}"
        source_text = " ".join(chunk.text.split())[
            : settings.quiz_context_max_chars_per_chunk
        ]
        source = QuizSource(
            source_id=source_id,
            knowledge_base_id=1,
            knowledge_base_name="CodeMind 固定评估语料",
            chunk_id=chunk.chunk_id,
            document_id=document.document_no,
            file_name=chunk.file_name,
            chunk_index=chunk.chunk_index,
            source_text=source_text,
            jump_url=f"/eval/documents/{document.document_id}/chunks/{chunk.chunk_index}",
        )
        context.append({"source_id": source_id, "source_text": source_text, "source": source})
    return context


def _question_answer_text(question: dict[str, Any]) -> str:
    values: list[str] = [str(question.get("prompt", "")), str(question.get("explanation", ""))]
    if question.get("reference_answer"):
        values.append(str(question["reference_answer"]))
    correct = question.get("correct_answer")
    correct_ids = {str(correct)} if not isinstance(correct, list) else {str(value) for value in correct}
    for option in question.get("options", []):
        if str(option.get("id")) in correct_ids:
            values.append(str(option.get("text", "")))
    values.extend(str(value) for value in question.get("accepted_answers", []))
    values.extend(str(value) for value in question.get("keywords", []))
    return " ".join(value for value in values if value)


def calculate_quiz_automatic_metrics(
    *, case: dict[str, Any], payload: dict[str, Any], context: list[dict[str, Any]]
) -> dict[str, Any]:
    questions = list(payload.get("questions", []))
    source_texts = {item["source_id"]: item["source_text"] for item in context}
    normalized_prompts = ["".join(str(item.get("prompt", "")).casefold().split()) for item in questions]
    duplicate_pairs: list[dict[str, Any]] = []
    for left in range(len(normalized_prompts)):
        for right in range(left + 1, len(normalized_prompts)):
            ratio = SequenceMatcher(None, normalized_prompts[left], normalized_prompts[right]).ratio()
            if ratio >= 0.86:
                duplicate_pairs.append(
                    {"left": left + 1, "right": right + 1, "similarity": round(ratio, 4)}
                )

    verifiable = 0
    source_scores: list[float] = []
    for question in questions:
        answer_text = _question_answer_text(question)
        cited_text = " ".join(
            source_texts.get(str(source_id), "") for source_id in question.get("source_ids", [])
        )
        score = keyword_overlap(answer_text, cited_text)
        source_scores.append(score)
        if score >= 0.08:
            verifiable += 1

    all_question_text = " ".join(_question_answer_text(question) for question in questions)
    key_points = [str(value) for value in case.get("expected_key_points", [])]
    matched_key_points = [value for value in key_points if value.casefold() in all_question_text.casefold()]
    type_counts = Counter(str(question.get("question_type")) for question in questions)
    level_counts = Counter(str(question.get("cognitive_level")) for question in questions)
    return {
        "question_count": len(questions),
        "question_type_distribution": dict(sorted(type_counts.items())),
        "cognitive_level_distribution": dict(sorted(level_counts.items())),
        "exact_duplicate_count": len(normalized_prompts) - len(set(normalized_prompts)),
        "near_duplicate_pairs": duplicate_pairs,
        "duplicate_rate": round(len(duplicate_pairs) / max(len(questions), 1), 4),
        "source_verifiable_rate_heuristic": round(verifiable / len(questions), 4)
        if questions
        else 0.0,
        "mean_source_overlap": round(sum(source_scores) / len(source_scores), 4)
        if source_scores
        else 0.0,
        "key_point_coverage": round(len(matched_key_points) / len(key_points), 4)
        if key_points
        else 0.0,
        "matched_key_points": matched_key_points,
        "manual_review_required": True,
    }


async def evaluate_quiz_cases(
    dataset: EvaluationDataset,
    *,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    validate_dataset(dataset)
    selected = [
        case for case in dataset.quiz_cases if case_ids is None or case["id"] in case_ids
    ]
    missing = set(case_ids or []) - {case["id"] for case in selected}
    if missing:
        raise ValueError(f"不存在的出题评估用例：{', '.join(sorted(missing))}")
    service = QuizService()
    runtime_config = system_llm_runtime_config()
    rows: list[dict[str, Any]] = []
    for case in selected:
        context = _quiz_context(dataset, case)
        request = QuizCreateRequest(
            knowledge_base_ids=[1],
            question_count=case["question_count"],
            difficulty=case["difficulty"],
            question_types=case["question_types"],
            random_mix=case.get("random_mix", True),
            topic=case.get("topic"),
        )
        started = time.perf_counter()
        error_type: str | None = None
        error_message: str | None = None
        try:
            payload = await service._generate_payload(
                request=request,
                context_chunks=context,
                runtime_config=runtime_config,
            )
            payload_data = payload.model_dump(mode="json")
            metrics = calculate_quiz_automatic_metrics(
                case=case,
                payload=payload_data,
                context=context,
            )
        except Exception as exc:
            payload_data = {"questions": []}
            metrics = {
                "question_count": 0,
                "question_type_distribution": {},
                "cognitive_level_distribution": {},
                "exact_duplicate_count": 0,
                "near_duplicate_pairs": [],
                "duplicate_rate": 0.0,
                "source_verifiable_rate_heuristic": 0.0,
                "mean_source_overlap": 0.0,
                "key_point_coverage": 0.0,
                "matched_key_points": [],
                "manual_review_required": True,
            }
            error_type = type(exc).__name__
            error_message = str(exc)[:500]
        rows.append(
            {
                "case_id": case["id"],
                "status": "failed" if error_type else "completed",
                "error_type": error_type,
                "error_message": error_message,
                "document_ids": case["document_ids"],
                "configuration": {
                    "question_count": case["question_count"],
                    "difficulty": case["difficulty"],
                    "question_types": case["question_types"],
                    "random_mix": case.get("random_mix", True),
                    "context_chunk_count": len(context),
                    "context_character_count": sum(len(item["source_text"]) for item in context),
                },
                "duration_seconds": round(time.perf_counter() - started, 3),
                "automatic_metrics": metrics,
                "questions": payload_data["questions"],
                "sources": [item["source"].model_dump(mode="json") for item in context],
            }
        )
    question_count = sum(row["automatic_metrics"]["question_count"] for row in rows)
    successful_rows = [row for row in rows if row["status"] == "completed"]
    return {
        "schema_version": "1.0",
        "evaluation_type": "quiz-quality",
        "run_date": date.today().isoformat(),
        "dataset": {
            "dataset_id": dataset.manifest["dataset_id"],
            "version": dataset.manifest["version"],
            "corpus_sha256": corpus_sha256(dataset),
        },
        "configuration": {
            "llm_model": settings.llm_model,
            "llm_base_url": settings.llm_base_url,
            "quiz_timeout_seconds": settings.quiz_timeout_seconds,
            "quiz_max_tokens": settings.quiz_max_tokens,
            "quiz_structure_max_retries": settings.quiz_structure_max_retries,
            "quiz_enable_thinking": settings.quiz_enable_thinking,
            "quiz_context_max_chunks": settings.quiz_context_max_chunks,
            "quiz_context_max_tokens": settings.quiz_context_max_tokens,
            "quiz_context_max_chars": settings.quiz_context_max_chars,
            "quiz_context_max_chars_per_chunk": settings.quiz_context_max_chars_per_chunk,
        },
        "summary": {
            "case_count": len(rows),
            "successful_case_count": len(successful_rows),
            "failed_case_count": len(rows) - len(successful_rows),
            "question_count": question_count,
            "mean_generation_seconds": round(
                sum(row["duration_seconds"] for row in successful_rows)
                / len(successful_rows),
                3,
            )
            if successful_rows
            else 0.0,
            "exact_duplicate_count": sum(
                row["automatic_metrics"]["exact_duplicate_count"] for row in rows
            ),
            "near_duplicate_pair_count": sum(
                len(row["automatic_metrics"]["near_duplicate_pairs"]) for row in rows
            ),
            "mean_key_point_coverage": round(
                sum(
                    row["automatic_metrics"]["key_point_coverage"]
                    for row in successful_rows
                )
                / len(successful_rows),
                4,
            )
            if successful_rows
            else 0.0,
            "mean_source_verifiable_rate_heuristic": round(
                sum(
                    row["automatic_metrics"]["source_verifiable_rate_heuristic"]
                    for row in successful_rows
                )
                / len(successful_rows),
                4,
            )
            if successful_rows
            else 0.0,
            "manual_review_required": True,
        },
        "cases": rows,
    }


def write_json_report(report: dict[str, Any], path: Path | str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def write_quiz_manual_csv(report: dict[str, Any], path: Path | str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "baseline_id",
        "case_id",
        "question_index",
        "question_type",
        "difficulty",
        "prompt",
        "answer_or_reference",
        "explanation",
        "source_ids",
        "fact_correctness_0_2",
        "material_relevance_0_2",
        "difficulty_fit_0_2",
        "source_verifiable_0_2",
        "duplicate_0_1",
        "reviewer",
        "notes",
    ]
    baseline_id = f"{report['run_date']}-{report['configuration']['llm_model'].replace('/', '-')}"
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for case in report["cases"]:
            for index, question in enumerate(case["questions"], start=1):
                writer.writerow(
                    {
                        "baseline_id": baseline_id,
                        "case_id": case["case_id"],
                        "question_index": index,
                        "question_type": question["question_type"],
                        "difficulty": case["configuration"]["difficulty"],
                        "prompt": question["prompt"],
                        "answer_or_reference": _question_answer_text(question),
                        "explanation": question["explanation"],
                        "source_ids": ",".join(question["source_ids"]),
                        "duplicate_0_1": 0,
                    }
                )
    return output


def summarize_quiz_manual_csv(path: Path | str) -> dict[str, Any]:
    score_path = Path(path)
    with score_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    dimensions = (
        "fact_correctness_0_2",
        "material_relevance_0_2",
        "difficulty_fit_0_2",
        "source_verifiable_0_2",
    )
    complete: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        parsed: dict[str, Any] = dict(row)
        missing = [name for name in dimensions if str(row.get(name, "")).strip() == ""]
        if missing:
            continue
        try:
            for name in dimensions:
                parsed[name] = int(row[name])
                if parsed[name] not in {0, 1, 2}:
                    raise ValueError(f"{name} 只能是 0、1、2")
            parsed["duplicate_0_1"] = int(row.get("duplicate_0_1", "0") or 0)
            if parsed["duplicate_0_1"] not in {0, 1}:
                raise ValueError("duplicate_0_1 只能是 0 或 1")
        except ValueError as exc:
            errors.append(f"第 {index} 行：{exc}")
            continue
        complete.append(parsed)
    if errors:
        raise ValueError("人工评分表存在无效分值：\n" + "\n".join(errors))

    dimension_scores = {
        name.removesuffix("_0_2"): round(
            sum(row[name] for row in complete) / (len(complete) * 2), 4
        )
        if complete
        else 0.0
        for name in dimensions
    }
    return {
        "row_count": len(rows),
        "scored_question_count": len(complete),
        "incomplete_question_count": len(rows) - len(complete),
        "dimension_rates": dimension_scores,
        "duplicate_rate": round(
            sum(row["duplicate_0_1"] for row in complete) / len(complete), 4
        )
        if complete
        else 0.0,
    }
