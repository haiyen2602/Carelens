"""BUILD-35 section 15: real local E2E for the Golden Set & Continuous
Evaluation runner -- 11 required scenarios (A-K), against real local
Postgres and (for the RAG/DRUG/MULTI_TURN/K scenarios) the real configured
model + Judge providers. Every scenario below was first proven manually
against this exact environment during the build (see the BUILD-35 report's
own E2E section for the transcript); this script formalizes them into one
reproducible artifact, same pattern as
scripts/agent_v2/build34_safety_monitoring_local_e2e.py.

Usage:

    python scripts/agent_v2/build35_golden_evaluation_local_e2e.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Set here, before importing the runner module -- this script (unlike
# tests/test_agent_v2_build35_golden_runner.py) genuinely needs real Agent
# V2 calls for every scenario, and is only ever run standalone (never
# imported by pytest), so this is safe here in a way it is NOT at
# run_golden_evaluation.py's own module level -- see that module's
# `if __name__ == "__main__":` guard for why.
os.environ.setdefault("AGENT_RUNTIME_ENABLED", "true")

import scripts.agent_v2.run_golden_evaluation as runner  # noqa: E402

DATASET = runner.DEFAULT_DATASET_DIR / "golden_set_v1.json"


def _latest_run_json(out_dir: Path) -> dict:
    files = sorted(out_dir.glob("*.json"))
    assert files, f"no run artifact written in {out_dir}"
    return json.loads(files[-1].read_text(encoding="utf-8"))


def scenario_a_dataset_loads_and_validates_clean() -> bool:
    cases = runner.load_golden_set(DATASET)
    errors = runner.validate_golden_set(cases)
    categories = {c.category.value for c in cases}
    ok = len(cases) >= 20 and not errors and len(categories) >= 14
    print(f"  A: {len(cases)} cases, {len(errors)} validation errors, {len(categories)} categories -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_b_malformed_dataset_rejected_before_any_run() -> bool:
    raw = json.loads(DATASET.read_text(encoding="utf-8"))
    broken = [dict(raw[0]), dict(raw[0])]  # exact duplicate case_id (both copies of raw[0])
    # ACUTE_DANGER requires execution_path + expected_severity +
    # expected_handoff_required -- present-but-incomplete (not empty -- an
    # empty turn is a deliberate, valid skip; this specifically tests
    # MISSING_EXPECTED_KEYS on a turn that DOES assert something but leaves
    # out required keys) on the SECOND entry only, so this dataset carries
    # two distinct real validation errors at once (DUPLICATE_CASE_ID +
    # MISSING_EXPECTED_KEYS), same as the scenario's own name claims.
    broken[1]["category"] = "ACUTE_DANGER"
    broken[1]["turns"] = [{"query": "x", "expected": {"execution_path": "SAFETY"}}]
    with tempfile.TemporaryDirectory() as tmp:
        broken_path = Path(tmp) / "broken.json"
        broken_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        rc = runner.main(["--dataset", str(broken_path), "--out-dir", tmp])
    ok = rc == 2
    print(f"  B: malformed dataset exit_code={rc} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_c_deterministic_only_full_run() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main(["--dataset", str(DATASET), "--deterministic-only", "--out-dir", tmp])
        payload = _latest_run_json(Path(tmp))
    all_zero_calls = all(
        o.get("model_calls", 0) == 0
        for r in payload["results"]
        for o in r["turn_outcomes"]
    )
    ok = rc == 0 and payload["aggregate"]["pass_rate"] == 1.0 and all_zero_calls
    print(f"  C: deterministic-only rc={rc} pass_rate={payload['aggregate']['pass_rate']} all_zero_model_calls={all_zero_calls} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_d_rag_real_grounding_with_citations() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main([
            "--dataset", str(DATASET), "--out-dir", tmp,
            "--case-id", "GOLD-RAG-001", "--case-id", "GOLD-RAG-002",
            "--case-id", "GOLD-RAG-003", "--case-id", "GOLD-RAG-004",
        ])
        payload = _latest_run_json(Path(tmp))
    has_citations = all(
        any(o["citation_titles"] for o in r["turn_outcomes"]) for r in payload["results"]
    )
    ok = rc == 0 and payload["aggregate"]["pass_rate"] == 1.0 and has_citations
    print(f"  D: RAG rc={rc} pass_rate={payload['aggregate']['pass_rate']} real_citations_present={has_citations} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_e_multi_turn_topic_preserved() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main(["--dataset", str(DATASET), "--out-dir", tmp, "--case-id", "GOLD-MULTI-001"])
        payload = _latest_run_json(Path(tmp))
    result = payload["results"][0]
    topics = [o["active_topic"] for o in result["turn_outcomes"]]
    ok = rc == 0 and result["passed"] and all(t == "gan nhiễm mỡ" for t in topics)
    print(f"  E: multi-turn rc={rc} passed={result['passed']} topics={topics} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_f_drug_lookup_and_honest_decline() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main([
            "--dataset", str(DATASET), "--out-dir", tmp,
            "--case-id", "GOLD-DRUG-001", "--case-id", "GOLD-DRUG-002", "--case-id", "GOLD-DRUG-003",
        ])
        payload = _latest_run_json(Path(tmp))
    ok = rc == 0 and payload["aggregate"]["pass_rate"] == 1.0
    print(f"  F: drug lookup/follow-up/honest-decline rc={rc} pass_rate={payload['aggregate']['pass_rate']} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_g_safety_escalation_severity_and_handoff() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main([
            "--dataset", str(DATASET), "--out-dir", tmp,
            "--case-id", "GOLD-OVERDOSE-001", "--case-id", "GOLD-ACUTE-001", "--case-id", "GOLD-ACUTE-002",
        ])
        payload = _latest_run_json(Path(tmp))
    severities = {r["case_id"]: r["turn_outcomes"][0]["safety_severity"] for r in payload["results"]}
    handoffs = {r["case_id"]: r["turn_outcomes"][0]["handoff_created"] for r in payload["results"]}
    ok = (
        rc == 0
        and payload["aggregate"]["pass_rate"] == 1.0
        and severities.get("GOLD-OVERDOSE-001") == "HIGH"
        and severities.get("GOLD-ACUTE-001") == "CRITICAL"
        and all(handoffs.values())
    )
    print(f"  G: safety escalation rc={rc} severities={severities} handoffs={handoffs} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_h_negation_guard_regression_case() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main(["--dataset", str(DATASET), "--out-dir", tmp, "--case-id", "GOLD-ACUTE-003"])
        payload = _latest_run_json(Path(tmp))
    result = payload["results"][0]
    outcome = result["turn_outcomes"][0]
    ok = rc == 0 and result["passed"] and outcome["execution_path"] == "TRIAGE" and outcome["safety_outcome"] is None
    print(f"  H: negation-guard rc={rc} passed={result['passed']} execution_path={outcome['execution_path']} safety_outcome={outcome['safety_outcome']} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_i_auth_isolation_real_cross_patient_403() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main(["--dataset", str(DATASET), "--out-dir", tmp, "--case-id", "GOLD-AUTH-001"])
        payload = _latest_run_json(Path(tmp))
    result = payload["results"][0]
    http_status = result["turn_outcomes"][0]["http_status"]
    ok = rc == 0 and result["passed"] and http_status == 403
    print(f"  I: auth isolation rc={rc} passed={result['passed']} http_status={http_status} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_j_baseline_comparison_unchanged_and_new() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rc1 = runner.main(["--dataset", str(DATASET), "--out-dir", tmp, "--case-id", "GOLD-DOSE-001", "--case-id", "GOLD-OOS-001"])
        baseline_file = sorted(tmp_path.glob("*.json"))[-1]

        rc2 = runner.main([
            "--dataset", str(DATASET), "--out-dir", tmp, "--baseline", str(baseline_file),
            "--case-id", "GOLD-DOSE-001", "--case-id", "GOLD-OOS-001", "--case-id", "GOLD-OOS-002",
        ])
        candidate_payload = _latest_run_json(tmp_path)

    statuses = {c["case_id"]: c["status"] for c in candidate_payload["comparisons"]}
    ok = (
        rc1 == 0 and rc2 == 0
        and statuses.get("GOLD-DOSE-001") == "UNCHANGED"
        and statuses.get("GOLD-OOS-001") == "UNCHANGED"
        and statuses.get("GOLD-OOS-002") == "NEW"
    )
    print(f"  J: baseline comparison statuses={statuses} -> {'OK' if ok else 'FAIL'}")
    return ok


def scenario_k_judge_scores_without_altering_deterministic_grade() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        rc = runner.main(["--dataset", str(DATASET), "--out-dir", tmp, "--case-id", "GOLD-DOSE-001", "--with-judge"])
        payload = _latest_run_json(Path(tmp))
    result = payload["results"][0]
    outcome = result["turn_outcomes"][0]
    ok = (
        rc == 0
        and result["passed"]  # deterministic grade unaffected by Judge involvement
        and outcome["judge_status"] == "JUDGE_COMPLETED"
        and outcome["judge_overall_score"] is not None
    )
    print(f"  K: Judge integration rc={rc} passed={result['passed']} judge_status={outcome['judge_status']} judge_score={outcome['judge_overall_score']} -> {'OK' if ok else 'FAIL'}")
    return ok


def main() -> int:
    print("BUILD-35 local E2E -- real Postgres, real model, real Judge provider\n")
    scenarios = [
        ("A", scenario_a_dataset_loads_and_validates_clean),
        ("B", scenario_b_malformed_dataset_rejected_before_any_run),
        ("C", scenario_c_deterministic_only_full_run),
        ("D", scenario_d_rag_real_grounding_with_citations),
        ("E", scenario_e_multi_turn_topic_preserved),
        ("F", scenario_f_drug_lookup_and_honest_decline),
        ("G", scenario_g_safety_escalation_severity_and_handoff),
        ("H", scenario_h_negation_guard_regression_case),
        ("I", scenario_i_auth_isolation_real_cross_patient_403),
        ("J", scenario_j_baseline_comparison_unchanged_and_new),
        ("K", scenario_k_judge_scores_without_altering_deterministic_grade),
    ]
    results = {}
    for label, fn in scenarios:
        try:
            results[label] = fn()
        except Exception as exc:  # noqa: BLE001 -- one scenario's crash must not stop the rest
            print(f"  {label}: EXCEPTION {exc}")
            results[label] = False

    all_ok = all(results.values())
    print(f"\n{'ALL SCENARIOS OK' if all_ok else 'SOME SCENARIOS FAILED'} ({sum(results.values())}/{len(results)})")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
