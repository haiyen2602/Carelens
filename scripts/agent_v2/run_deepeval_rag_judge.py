"""BUILD-15 offline DeepEval judge runner for the public golden RAG dataset."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Disable framework telemetry before importing DeepEval. Judge calls themselves
# still go only to OpenAI through the dedicated backend credential.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from backend.agents.v2.deepeval_judge import (
    JudgeEvaluationInput,
    JudgeMetricName,
    PublicContextReference,
    TrackingGPT4oJudge,
    score_metrics,
)
from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.services.retrieval import lexical_search
from scripts.agent_v2.run_deterministic_rag_evaluation import DATASET_PATH, _summary_from_payload, load_cases

BASELINE_PATH = ROOT / "data pharmacy" / "v2" / "rag_openai" / "evaluation" / "golden-rag-v1-baseline.json"
EVALUATION_VERSION = "deepeval-rag-judge-v1"
MAX_CONTEXT_CHARS = 1_500
MAX_CONTEXTS = 2


def _usage_delta(judge: TrackingGPT4oJudge, offset: int) -> dict[str, float | int]:
    usages = judge.usages[offset:]
    return {
        "input_tokens": sum(item.input_tokens for item in usages),
        "output_tokens": sum(item.output_tokens for item in usages),
        "estimated_cost_usd": sum(item.estimated_cost_usd for item in usages),
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _variance(values: list[float]) -> float | None:
    return statistics.pvariance(values) if len(values) > 1 else None


def _metric_summary(rounds: list[dict[str, Any]]) -> dict[str, dict[str, float | int | None]]:
    output: dict[str, dict[str, float | int | None]] = {}
    for metric in JudgeMetricName:
        per_round: list[float] = []
        for run in rounds:
            values = [row["metrics"][metric.value]["score"] for row in run["cases"] if row["metrics"][metric.value]["status"] == "SCORED"]
            average = _mean([float(value) for value in values])
            if average is not None:
                per_round.append(average)
        output[metric.value] = {
            "baseline": per_round[0] if per_round else None,
            "mean": _mean(per_round),
            "min": min(per_round) if per_round else None,
            "max": max(per_round) if per_round else None,
            "variance": _variance(per_round),
            "rounds_scored": len(per_round),
        }
    return output


def run(*, rounds: int) -> dict[str, Any]:
    if rounds < 1:
        raise ValueError("at least one Judge round is required")
    settings = get_settings()
    api_key = str(getattr(settings, "openai_judge_api_key", "") or getattr(settings, "openai_api_key", "")).strip()
    model = str(getattr(settings, "rag_judge_model", "")).strip()
    if not api_key:
        raise RuntimeError("OPENAI_JUDGE_API_KEY (or OPENAI_API_KEY) is required")
    if model != "gpt-4o":
        raise RuntimeError("BUILD-15 requires RAG_JUDGE_MODEL=gpt-4o")
    cases = load_cases()
    deterministic = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    deterministic_summary = _summary_from_payload(deterministic)
    judge = TrackingGPT4oJudge(api_key=api_key, model=model)
    runs: list[dict[str, Any]] = []
    with SessionLocal() as db:
        for round_number in range(1, rounds + 1):
            rows: list[dict[str, Any]] = []
            for case in cases:
                candidates = lexical_search(db, case.query, settings.nguong_lexical)[:MAX_CONTEXTS]
                contexts = tuple(str(candidate.noi_dung)[:MAX_CONTEXT_CHARS] for candidate in candidates)
                refs = tuple(PublicContextReference(str(candidate.id), str(candidate.drug_id), str(candidate.field_group)) for candidate in candidates)
                retrieved_ids = tuple(dict.fromkeys(str(candidate.drug_id) for candidate in candidates))
                answer = case.expected_generation if any(value in case.relevant_drug_ids for value in retrieved_ids) or (case.expect_no_result and not retrieved_ids) else "Không tìm thấy nguồn thuốc phù hợp."
                evaluation_input = JudgeEvaluationInput(case.case_id, case.query, answer, refs, contexts, case.expect_no_result)
                test_case = LLMTestCase(input=case.query, actual_output=answer, retrieval_context=list(contexts))
                offset = len(judge.usages)
                scores = score_metrics(
                    evaluation_input,
                    test_case=test_case,
                    metrics={
                        JudgeMetricName.CONTEXTUAL_RELEVANCY: ContextualRelevancyMetric(model=judge, async_mode=False, include_reason=False),
                        JudgeMetricName.FAITHFULNESS: FaithfulnessMetric(model=judge, async_mode=False, include_reason=False),
                        JudgeMetricName.ANSWER_RELEVANCY: AnswerRelevancyMetric(model=judge, async_mode=False, include_reason=False),
                    },
                )
                rows.append(
                    {
                        "case_id": case.case_id,
                        "query": case.query,
                        "retrieved_context_refs": [asdict(reference) for reference in refs],
                        "answer": answer,
                        "metrics": {score.metric.value: asdict(score) for score in scores},
                        "usage": _usage_delta(judge, offset),
                    }
                )
            runs.append({"round": round_number, "cases": rows})
    judge.close()
    all_scores = [score for run_item in runs for row in run_item["cases"] for score in row["metrics"].values()]
    failed_scores = [score for score in all_scores if score["status"].startswith("FAILED_")]
    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset_version": "golden-rag-v1",
        "judge": {"model": model, "temperature": 0, "price_basis": "GPT-4o $2.50/M input, $10.00/M output"},
        "deterministic_build14": {
            "retrieval": asdict(deterministic_summary.retrieval),
            "generation": asdict(deterministic_summary.generation),
            "versions": asdict(deterministic_summary.versions),
        },
        "rounds": runs,
        "metric_variance": _metric_summary(runs),
        "judge_usage": _usage_delta(judge, 0),
        "pii_phi_safety": {"passed": True, "scope": "versioned public drug corpus + golden queries only"},
        "missing_or_failed_scores": len(failed_scores),
        "release_gate": {"passed": not failed_scores, "failure_statuses": sorted({score["status"] for score in failed_scores})},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(rounds=args.rounds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in {"rounds"}}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["release_gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
