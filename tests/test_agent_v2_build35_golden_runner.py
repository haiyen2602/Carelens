"""BUILD-35: unit tests for scripts/agent_v2/run_golden_evaluation.py's
pure/non-DB helper functions -- dataset path resolution, provenance
construction, baseline artifact loading, output JSON/Markdown writing, and
the dataset-validation-rejection CLI path (which itself never touches the
DB, since it exits before any case runs). No DB, no HTTP, no model call --
the real DB/model/Judge-backed scenarios are covered by
scripts/agent_v2/build35_golden_evaluation_local_e2e.py, run manually
against real local Postgres (see BUILD-35 report).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.agent_v2.run_golden_evaluation as runner  # noqa: E402
from backend.agents.v2.golden_evaluation import (  # noqa: E402
    GROUND_TRUTH_CONTRACT_VERSION,
    CaseOutcome,
    CaseResult,
    ComparisonStatus,
    RegressionGateResult,
    RunProvenance,
)

# ---------------------------------------------------------------------------
# _resolve_dataset_path
# ---------------------------------------------------------------------------


def test_resolve_dataset_path_bare_version_resolves_under_golden_dir():
    resolved = runner._resolve_dataset_path("v1")
    assert resolved == runner.DEFAULT_DATASET_DIR / "golden_set_v1.json"


def test_resolve_dataset_path_literal_path_passed_through():
    resolved = runner._resolve_dataset_path("some/dir/custom.json")
    assert resolved == Path("some/dir/custom.json")


def test_resolve_dataset_path_bare_filename_ending_json_passed_through():
    resolved = runner._resolve_dataset_path("custom.json")
    assert resolved == Path("custom.json")


# ---------------------------------------------------------------------------
# _git_commit
# ---------------------------------------------------------------------------


def test_git_commit_returns_a_real_non_empty_value_in_this_repo():
    commit = runner._git_commit()
    assert commit != ""
    # Either a real 40-char hex sha (this repo IS a git repo) or the
    # documented honest fallback -- never silently empty/fabricated.
    assert commit == "UNKNOWN" or (len(commit) == 40 and all(c in "0123456789abcdef" for c in commit))


# ---------------------------------------------------------------------------
# _build_provenance
# ---------------------------------------------------------------------------


def test_build_provenance_reads_real_settings_fields_never_fabricates():
    settings = SimpleNamespace(
        rag_prompt_version="medication-chat-v1.0",
        agent_router_model="gpt-5.4-nano",
        agent_main_model="gpt-5.4-mini",
        agent_fallback_model="gpt-5.4",
        agent_embedding_model="text-embedding-3-small",
        rag_retriever_version="hybrid-rrf-v2",
        agent_judge_model="gemini-3.7-flash",
        agent_judge_rubric_version="rubric-v1",
    )
    from datetime import UTC, datetime

    started = datetime(2026, 8, 25, tzinfo=UTC)
    provenance = runner._build_provenance(settings=settings, golden_set_version="v1", started_at=started)
    assert provenance.golden_set_version == "v1"
    assert provenance.prompt_version == "medication-chat-v1.0"
    assert provenance.main_model == "gpt-5.4-mini"
    assert provenance.judge_model == "gemini-3.7-flash"
    assert provenance.evaluation_version == "evaluation-v2"
    assert provenance.completed_at is None  # not yet finished -- never fabricated


def test_build_provenance_missing_settings_field_is_honest_not_available():
    settings = SimpleNamespace()  # no fields at all
    from datetime import UTC, datetime

    provenance = runner._build_provenance(settings=settings, golden_set_version="v1", started_at=datetime.now(UTC))
    assert provenance.main_model == "NOT_AVAILABLE"
    assert provenance.judge_model is None  # judge is genuinely optional, not "NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# _load_baseline_results
# ---------------------------------------------------------------------------


def test_load_baseline_results_none_path_returns_none():
    assert runner._load_baseline_results(None) is None


def test_load_baseline_results_loads_from_wrapped_results_shape(tmp_path):
    payload = {"results": [{"case_id": "GOLD-X-001", "category": "OUT_OF_SCOPE", "tags": ["x"], "passed": True}]}
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    results = runner._load_baseline_results(str(path))
    assert len(results) == 1
    assert results[0].case_id == "GOLD-X-001"
    assert results[0].passed is True
    assert results[0].checks == ()
    assert results[0].turn_outcomes == ()


def test_load_baseline_results_loads_from_bare_list_shape(tmp_path):
    payload = [{"case_id": "GOLD-Y-001", "category": "OUT_OF_SCOPE", "tags": [], "passed": False}]
    path = tmp_path / "baseline_list.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    results = runner._load_baseline_results(str(path))
    assert len(results) == 1
    assert results[0].passed is False


# ---------------------------------------------------------------------------
# _write_outputs -- JSON + Markdown validity, no raw patient secret leakage
# ---------------------------------------------------------------------------


def _fake_case_result(case_id: str, *, passed: bool) -> CaseResult:
    outcome = CaseOutcome(
        execution_path="RAG", intent="GENERAL_MEDICAL_INFORMATION", status="COMPLETED",
        response_text="mot cau tra loi", citation_titles=("Bai viet A",), tool_names=("search_drug",),
        trace_id="trace-1", agent_run_id="run-1",
    )
    from backend.agents.v2.golden_evaluation import CheckResult, CheckStatus

    check = CheckResult("execution_path", CheckStatus.PASS if passed else CheckStatus.FAIL, "detail")
    return CaseResult(case_id=case_id, category="RAG_GENERAL_MEDICAL", tags=("rag",), passed=passed, checks=(check,), turn_outcomes=(outcome,))


def _fake_provenance() -> RunProvenance:
    return RunProvenance(
        git_commit="abc123", agent_version="agent-v2", chatbot_version="agent-v2", prompt_version="v1",
        router_model="r", main_model="m", fallback_model="f", embedding_model="e", retrieval_version="rv",
        judge_model=None, rubric_version=None, evaluation_version="evaluation-v2", golden_set_version="v1",
        started_at="2026-08-25T00:00:00+00:00", completed_at="2026-08-25T00:01:00+00:00",
    )


def test_write_outputs_produces_valid_round_trippable_json(tmp_path):
    results = [_fake_case_result("GOLD-RAG-001", passed=True), _fake_case_result("GOLD-RAG-002", passed=False)]
    from backend.agents.v2.golden_evaluation import aggregate_results, compare_to_baseline

    aggregate = aggregate_results(results)
    comparisons = compare_to_baseline(results, None)
    gate = RegressionGateResult(passed=False, critical_failures=(), regressed_non_critical=(), non_critical_pass_rate=0.5, non_critical_threshold=0.8)

    json_path, md_path = runner._write_outputs(
        out_dir=tmp_path, run_id="20260825T000000Z", provenance=_fake_provenance(), results=results,
        aggregate=aggregate, comparisons=comparisons, gate=gate, dataset_errors=[],
    )
    assert json_path.exists() and md_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "20260825T000000Z"
    assert payload["aggregate"]["total_cases"] == 2
    assert payload["regression_gate"]["passed"] is False
    assert len(payload["results"]) == 2
    assert all(c["status"] in {s.value for s in ComparisonStatus} for c in payload["comparisons"])

    md_text = md_path.read_text(encoding="utf-8")
    assert "GOLD-RAG-002" in md_text  # the failed case is named in the Markdown summary
    assert "FAIL" in md_text


def test_write_outputs_never_leaks_patient_or_actor_identifiers(tmp_path):
    """CaseOutcome/CaseResult structurally carry no patient_id/actor_id/JWT
    field at all (see backend.agents.v2.golden_evaluation's own dataclasses)
    -- this proves the WRITTEN artifact reflects that, not just the dataclass
    shape in isolation."""

    results = [_fake_case_result("GOLD-RAG-001", passed=True)]
    from backend.agents.v2.golden_evaluation import aggregate_results, compare_to_baseline

    gate = RegressionGateResult(passed=True, critical_failures=(), regressed_non_critical=(), non_critical_pass_rate=1.0, non_critical_threshold=0.8)
    json_path, _ = runner._write_outputs(
        out_dir=tmp_path, run_id="20260825T000001Z", provenance=_fake_provenance(), results=results,
        aggregate=aggregate_results(results), comparisons=compare_to_baseline(results, None), gate=gate, dataset_errors=[],
    )
    raw_text = json_path.read_text(encoding="utf-8")
    for forbidden in ("patient_id", "actor_id", "agent-v2-staging-patient-1", "Bearer "):
        assert forbidden not in raw_text


# ---------------------------------------------------------------------------
# main() -- dataset-validation-rejection path (no DB touched before this)
# ---------------------------------------------------------------------------


def test_main_rejects_malformed_dataset_before_running_anything(tmp_path):
    broken = [
        {
            "case_id": "GOLD-DUP-001", "golden_set_version": "v1", "category": "OUT_OF_SCOPE", "tags": [],
            "turns": [{"query": "q", "expected": {"execution_path": "OUT_OF_SCOPE"}}], "created_at": "2026-08-25",
            "expected_contract_version": GROUND_TRUTH_CONTRACT_VERSION,
        },
        {
            "case_id": "GOLD-DUP-001", "golden_set_version": "v1", "category": "OUT_OF_SCOPE", "tags": [],
            "turns": [{"query": "q2", "expected": {}}], "created_at": "2026-08-25",
            "expected_contract_version": GROUND_TRUTH_CONTRACT_VERSION,
        },
    ]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")

    rc = runner.main(["--dataset", str(path), "--out-dir", str(tmp_path)])
    assert rc == 2
    # No run artifact should have been written -- validation failure exits
    # before any case executes or any output is produced.
    assert list(tmp_path.glob("*.json")) == [path]  # only the input file we wrote ourselves


def test_main_empty_case_selection_exits_without_touching_db(tmp_path):
    rc = runner.main(["--dataset", str(runner.DEFAULT_DATASET_DIR / "golden_set_v1.json"), "--case-id", "DOES-NOT-EXIST", "--out-dir", str(tmp_path)])
    assert rc == 2
    assert list(tmp_path.glob("*.json")) == []


# ---------------------------------------------------------------------------
# _DETERMINISTIC_CATEGORIES -- the CI-safety contract itself
# ---------------------------------------------------------------------------


def test_deterministic_categories_excludes_every_model_calling_category():
    from backend.agents.v2.golden_evaluation import GoldenCategory

    model_calling = {
        GoldenCategory.RAG_GENERAL_MEDICAL, GoldenCategory.RAG_PARAPHRASE, GoldenCategory.MULTI_TURN_CONTEXT,
        GoldenCategory.DRUG_INFORMATION, GoldenCategory.DRUG_FOLLOWUP, GoldenCategory.FALLBACK,
    }
    assert runner._DETERMINISTIC_CATEGORIES.isdisjoint(model_calling)
    # every category is accounted for one way or the other (no silent gap)
    assert runner._DETERMINISTIC_CATEGORIES | model_calling == set(GoldenCategory)
