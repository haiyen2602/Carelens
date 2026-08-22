"""BUILD-14C repeated, no-cost latency benchmark for the golden RAG runner."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.agents.v2.rag_evaluation import (
    describe_latency,
    empirical_performance_gate,
    evaluate_embedding_drift,
    evaluate_release_gate,
)
from scripts.agent_v2.run_deterministic_rag_evaluation import _summary_from_payload, evaluate

DEFAULT_BASELINE = ROOT / "data pharmacy" / "v2" / "rag_openai" / "evaluation" / "golden-rag-v1-baseline.json"


def _run_once() -> dict[str, Any]:
    return evaluate()


def benchmark(*, baseline_path: Path, warmup_runs: int, cohort_runs: int) -> dict[str, Any]:
    if warmup_runs < 1 or cohort_runs < 2:
        raise ValueError("use at least one warm-up and two runs per cohort")
    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    stored_baseline = _summary_from_payload(baseline_payload)
    for _ in range(warmup_runs):
        _run_once()

    baseline_cohort = tuple(_run_once() for _ in range(cohort_runs))
    candidate_cohort = tuple(_run_once() for _ in range(cohort_runs))
    all_payloads = (*baseline_cohort, *candidate_cohort)
    all_summaries = tuple(_summary_from_payload(payload) for payload in all_payloads)
    quality_failures: list[str] = []
    identity_failures: list[str] = []
    for index, summary in enumerate(all_summaries, start=1):
        quality = evaluate_release_gate(stored_baseline, summary)
        quality_failures.extend(f"run-{index}:{failure}" for failure in quality.failures if failure != "P95_LATENCY_REGRESSION")
        identity = evaluate_embedding_drift(stored_baseline.versions, summary.versions)
        identity_failures.extend(f"run-{index}:{failure}" for failure in identity.reason_codes)

    baseline_p95 = tuple(summary.p95_latency_ms for summary in all_summaries[:cohort_runs])
    candidate_p95 = tuple(summary.p95_latency_ms for summary in all_summaries[cohort_runs:])
    performance = empirical_performance_gate(
        stored_baseline_p95_ms=stored_baseline.p95_latency_ms,
        baseline_run_p95_ms=baseline_p95,
        candidate_run_p95_ms=candidate_p95,
    )
    raw_latencies = tuple(result.latency_ms for summary in all_summaries for result in summary.results)
    passed = not quality_failures and not identity_failures and performance.passed
    return {
        "warmup_runs": warmup_runs,
        "cohort_runs": cohort_runs,
        "stored_baseline_p95_ms": stored_baseline.p95_latency_ms,
        "baseline_p95_distribution": asdict(describe_latency(baseline_p95)),
        "candidate_p95_distribution": asdict(describe_latency(candidate_p95)),
        "all_request_latency_distribution": asdict(describe_latency(raw_latencies)),
        "performance_tolerance_ms": {
            "method": "pooled empirical P95 envelope",
            "minimum": min(*baseline_p95, *candidate_p95),
            "maximum": max(*baseline_p95, *candidate_p95),
        },
        "quality_regression": {"passed": not quality_failures, "failures": quality_failures},
        "corpus_identity": {"passed": not identity_failures, "failures": identity_failures},
        "performance_gate": asdict(performance),
        "release_gate": {"passed": passed},
        "provider_requests": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--cohort-runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = benchmark(baseline_path=args.baseline, warmup_runs=args.warmup_runs, cohort_runs=args.cohort_runs)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(rendered)
    return 0 if result["release_gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
