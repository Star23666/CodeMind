import argparse
import asyncio
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.evaluation.quality import (
    DEFAULT_DATA_ROOT,
    DEFAULT_RERANK_THRESHOLDS,
    DEFAULT_THRESHOLDS,
    evaluate_hybrid_rerank_thresholds,
    evaluate_quiz_cases,
    evaluate_rag_generation,
    evaluate_rag_thresholds,
    load_dataset,
    summarize_quiz_manual_csv,
    validate_dataset,
    write_json_report,
    write_quiz_manual_csv,
)


def _thresholds(value: str | None) -> list[float]:
    values = list(DEFAULT_THRESHOLDS)
    if value:
        try:
            values = [float(item.strip()) for item in value.split(",") if item.strip()]
        except ValueError as exc:
            raise argparse.ArgumentTypeError("阈值必须是逗号分隔的数字") from exc
    values.append(float(settings.retrieval_score_threshold))
    if any(value < -1 or value > 1 for value in values):
        raise argparse.ArgumentTypeError("阈值必须位于 -1 到 1 之间")
    return sorted(set(round(value, 4) for value in values))


def _rerank_thresholds(value: str | None) -> list[float]:
    values = list(DEFAULT_RERANK_THRESHOLDS)
    if value:
        try:
            values = [float(item.strip()) for item in value.split(",") if item.strip()]
        except ValueError as exc:
            raise argparse.ArgumentTypeError("阈值必须是逗号分隔的数字") from exc
    values.append(float(settings.rerank_score_threshold))
    if any(value < -1 or value > 1 for value in values):
        raise argparse.ArgumentTypeError("阈值必须位于 -1 到 1 之间")
    return sorted(set(round(value, 4) for value in values))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CodeMind 固定 RAG 与 AI 出题质量评估工具"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="固定评估数据目录，默认使用仓库 testdata/eval",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="仅校验固定语料和标注完整性")

    rag = subparsers.add_parser("rag", help="调用在线 Embedding 并评估检索阈值")
    rag.add_argument("--output", type=Path, required=True, help="JSON 结果输出路径")
    rag.add_argument(
        "--thresholds",
        help="逗号分隔的阈值；无论是否指定都会包含当前配置默认值",
    )
    rag.add_argument("--top-k", type=int, default=4)
    rag.add_argument("--rerank-top-n", type=int, default=2)
    rag.add_argument("--disable-rerank", action="store_true")
    rag.add_argument("--batch-size", type=int, default=16)
    rag.add_argument(
        "--with-generation",
        action="store_true",
        help="在合格推荐值或当前扫描的相对最优阈值上调用在线 LLM，评估拒答与正例回答",
    )
    rag.add_argument("--generation-positive-per-document", type=int, default=1)
    rag.add_argument("--generation-concurrency", type=int, default=1)

    hybrid = subparsers.add_parser(
        "rag-hybrid",
        help="评估 Dense + BM25 + RRF + 在线 Reranker 完整检索链路",
    )
    hybrid.add_argument("--output", type=Path, required=True, help="JSON 结果输出路径")
    hybrid.add_argument("--thresholds", help="逗号分隔的 Rerank 阈值")
    hybrid.add_argument(
        "--dense-candidate-k",
        type=int,
        default=settings.retrieval_dense_candidate_k,
    )
    hybrid.add_argument(
        "--lexical-candidate-k",
        type=int,
        default=settings.retrieval_lexical_candidate_k,
    )
    hybrid.add_argument(
        "--fusion-candidate-k",
        type=int,
        default=settings.retrieval_fusion_candidate_k,
    )
    hybrid.add_argument("--final-top-n", type=int, default=2)
    hybrid.add_argument("--batch-size", type=int, default=16)
    hybrid.add_argument("--concurrency", type=int, default=8)
    hybrid.add_argument(
        "--with-generation",
        action="store_true",
        help="在推荐 Rerank 阈值上调用在线 LLM，评估拒答与正例回答",
    )
    hybrid.add_argument("--generation-positive-per-document", type=int, default=1)
    hybrid.add_argument("--generation-concurrency", type=int, default=1)

    quiz = subparsers.add_parser("quiz", help="调用生产出题 Prompt/结构校验生成基线")
    quiz.add_argument("--output", type=Path, required=True, help="JSON 结果输出路径")
    quiz.add_argument(
        "--manual-csv", type=Path, required=True, help="人工语义评分表输出路径"
    )
    quiz.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="只执行指定 case id，可重复；不传则运行全部用例并消耗较多额度",
    )
    manual = subparsers.add_parser(
        "manual-summary", help="汇总已填写的 AI 出题人工语义评分表"
    )
    manual.add_argument("--input", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset = load_dataset(args.data_root)
    if args.command == "validate":
        print(json.dumps(validate_dataset(dataset), ensure_ascii=False, indent=2))
        return 0

    if args.command == "rag":
        report = evaluate_rag_thresholds(
            dataset,
            thresholds=_thresholds(args.thresholds),
            top_k=args.top_k,
            enable_rerank=not args.disable_rerank,
            rerank_top_n=args.rerank_top_n,
            batch_size=max(1, args.batch_size),
        )
        if args.with_generation:
            report["generation_evaluation"] = asyncio.run(
                evaluate_rag_generation(
                    dataset,
                    report,
                    positive_per_document=max(
                        0, args.generation_positive_per_document
                    ),
                    concurrency=max(1, args.generation_concurrency),
                )
            )
        output = write_json_report(report, args.output)
        print(
            json.dumps(
                {
                    "output": str(output),
                    "recommended_threshold": report["recommended_threshold"],
                    "recommended_metrics": report["recommended_metrics"],
                    "best_observed_threshold": report["best_observed_threshold"],
                    "best_observed_metrics": report["best_observed_metrics"],
                    "generation_metrics": report.get("generation_evaluation", {}).get(
                        "metrics"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "rag-hybrid":
        report = evaluate_hybrid_rerank_thresholds(
            dataset,
            thresholds=_rerank_thresholds(args.thresholds),
            dense_candidate_k=max(1, args.dense_candidate_k),
            lexical_candidate_k=max(1, args.lexical_candidate_k),
            fusion_candidate_k=max(1, args.fusion_candidate_k),
            final_top_n=max(1, args.final_top_n),
            batch_size=max(1, args.batch_size),
            concurrency=max(1, args.concurrency),
        )
        if args.with_generation:
            report["generation_evaluation"] = asyncio.run(
                evaluate_rag_generation(
                    dataset,
                    report,
                    positive_per_document=max(
                        0, args.generation_positive_per_document
                    ),
                    concurrency=max(1, args.generation_concurrency),
                )
            )
        output = write_json_report(report, args.output)
        print(
            json.dumps(
                {
                    "output": str(output),
                    "quality_target_met": report["quality_target_met"],
                    "recommended_threshold": report["recommended_threshold"],
                    "recommended_metrics": report["recommended_metrics"],
                    "best_observed_threshold": report["best_observed_threshold"],
                    "best_observed_metrics": report["best_observed_metrics"],
                    "generation_metrics": report.get("generation_evaluation", {}).get(
                        "metrics"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "manual-summary":
        print(
            json.dumps(
                summarize_quiz_manual_csv(args.input),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    report = asyncio.run(evaluate_quiz_cases(dataset, case_ids=args.case_ids))
    output = write_json_report(report, args.output)
    manual_csv = write_quiz_manual_csv(report, args.manual_csv)
    print(
        json.dumps(
            {
                "output": str(output),
                "manual_csv": str(manual_csv),
                "summary": report["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
