#!/usr/bin/env python3
"""Tune nguong cosine cho audit match trieu chung - tac_dung_phu (Vong 4).

Bo eval co nhan thu cong chi chua cac thuoc active cua tung case. Script
dung chinh `search_active_side_effect_chunks()` nhu node production se dung,
nen khong co SQL/eval rieng co the lech hanh vi san pham.

Chi phi: 1 embedding/case, hien la 11 loi goi embedding va khong goi LLM sinh
cau tra loi. Chi chay sau khi da duoc phe duyet chi phi eval.

Usage:
    python eval/tune_side_effect_match.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import SessionLocal  # noqa: E402
from backend.services.classification import classify_side_effect_match  # noqa: E402
from backend.services.embeddings import embed_query  # noqa: E402
from backend.services.retrieval import search_active_side_effect_chunks  # noqa: E402

EVAL_PATH = Path(__file__).resolve().parent / "side_effect_match_ground_truth.json"
REPORT_PATH = Path(__file__).resolve().parent / "side_effect_match_tuning.json"
THRESHOLD_GRID = [round(value / 100, 2) for value in range(20, 81, 5)]


def _load_items() -> list[dict]:
    return json.loads(EVAL_PATH.read_text(encoding="utf-8"))


def _evaluate_at_threshold(runs: list[dict], threshold: float) -> dict:
    true_positive = false_positive = false_negative = 0
    exact_cases = 0
    redflag_exact_cases = 0
    redflag_case_count = 0

    for run in runs:
        expected = set(run["expected_match_drug_ids"])
        actual = {match["drug_id"] for match in run["matches"] if match["score"] >= threshold}
        true_positive += len(expected & actual)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
        if actual == expected:
            exact_cases += 1
            if run["redflag"]:
                redflag_exact_cases += 1
        if run["redflag"]:
            redflag_case_count += 1

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "false_positive_count": false_positive,
        "false_negative_count": false_negative,
        "exact_case_accuracy": exact_cases / len(runs),
        "redflag_exact_case_accuracy": redflag_exact_cases / redflag_case_count if redflag_case_count else 1.0,
    }


def _validate_llm(runs: list[dict], candidate_threshold: float) -> dict:
    """Live eval cua tang 2 tren candidate da qua cosine filter rong."""
    true_positive = false_positive = false_negative = 0
    per_case = []
    for run in runs:
        expected = set(run["expected_match_drug_ids"])
        candidate_matches = [match for match in run["matches"] if match["score"] >= candidate_threshold]
        actual: set[str] = set()
        decisions = []
        for match in candidate_matches:
            is_match = classify_side_effect_match(run["utterance"], match["side_effect_content"])
            decisions.append({"drug_id": match["drug_id"], "score": match["score"], "is_match": is_match})
            if is_match:
                actual.add(match["drug_id"])
        true_positive += len(expected & actual)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
        per_case.append({"id": run["id"], "expected": sorted(expected), "actual": sorted(actual), "decisions": decisions})

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    return {
        "candidate_threshold": candidate_threshold,
        "precision": precision,
        "recall": recall,
        "false_positive_count": false_positive,
        "false_negative_count": false_negative,
        "per_case": per_case,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-llm", action="store_true", help="goi LLM nhi phan tren candidate da qua cosine")
    parser.add_argument("--candidate-threshold", type=float, default=0.20)
    args = parser.parse_args()

    items = _load_items()
    db = SessionLocal()
    try:
        runs = []
        for item in items:
            matches = search_active_side_effect_chunks(
                db, embed_query(item["utterance"]), item["active_drug_ids"]
            )
            runs.append(
                {
                    **item,
                    "matches": [
                        {
                            "drug_id": match.drug_id,
                            "ten_thuoc": match.ten_thuoc,
                            "score": match.score,
                            "side_effect_content": match.noi_dung,
                        }
                        for match in matches
                    ],
                }
            )
    finally:
        db.close()

    sweep = [_evaluate_at_threshold(runs, threshold) for threshold in THRESHOLD_GRID]
    print("=== Sweep nguong cosine side-effect audit ===")
    print(f"{'nguong':>8} {'precision':>10} {'recall':>8} {'FP':>4} {'FN':>4} {'exact':>8} {'redflag':>9}")
    for row in sweep:
        print(
            f"{row['threshold']:>8.2f} {row['precision']:>9.0%} {row['recall']:>7.0%} "
            f"{row['false_positive_count']:>4} {row['false_negative_count']:>4} "
            f"{row['exact_case_accuracy']:>7.0%} {row['redflag_exact_case_accuracy']:>8.0%}"
        )

    report = {"runs": runs, "sweep": sweep}
    if args.validate_llm:
        llm_validation = _validate_llm(runs, args.candidate_threshold)
        report["llm_validation"] = llm_validation
        print(
            f"LLM @ {args.candidate_threshold:.2f}: precision={llm_validation['precision']:.0%}, "
            f"recall={llm_validation['recall']:.0%}, FP={llm_validation['false_positive_count']}, "
            f"FN={llm_validation['false_negative_count']}"
        )
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Da ghi {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
