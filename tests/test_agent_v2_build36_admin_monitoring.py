"""BUILD-36: unit tests for backend/services/agent_monitoring_metrics.py --
aggregate correctness, denominator correctness, N/A semantics, filter
effectiveness, error-code breakdown, Judge/Golden metrics, baseline
comparison deltas. SQLite in-memory (no Postgres-specific SQL used
anywhere in this module -- plain SQLAlchemy Select/func.count()), same
pattern BUILD-33/34's own unit test files already use. Real HTTP/auth-level
tests live in tests/test_api/test_admin_monitoring_routes.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import (
    AgentFeedbackTicket,
    AgentGoldenRun,
    AgentGoldenRunCase,
    AgentRun,
    AgentRunEvaluation,
    AgentRunJudge,
    AgentRunSpan,
    AgentSafetyEvent,
)
from backend.services.agent_monitoring_metrics import (
    MonitoringFilters,
    _average,
    _percentiles,
    _rate,
    compare_metrics,
    cost_metrics,
    errors_metrics,
    golden_metrics,
    golden_run_detail,
    judge_metrics,
    list_traces,
    overview_metrics,
    paginate,
    performance_metrics,
    quality_metrics,
    retrieval_metrics,
    trace_detail,
    version_filter_options,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (AgentRun, AgentRunSpan, AgentRunEvaluation, AgentRunJudge, AgentSafetyEvent, AgentFeedbackTicket, AgentGoldenRun, AgentGoldenRunCase):
        table.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def _run(db: Session, run_id: str, **overrides) -> AgentRun:
    base = dict(
        id=run_id, status="COMPLETED", started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
        model="gpt-5.4-mini", model_calls=1, input_tokens=10, output_tokens=20, total_tokens=30,
        total_cost_usd=0.001, cost_status="AVAILABLE", duration_ms=100.0, timeout=False, empty_reply=False,
        error_code=None, prompt_version="v1", retrieval_version="hybrid-v1",
    )
    base.update(overrides)
    run = AgentRun(**base)
    db.add(run)
    db.commit()
    return run


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


def test_rate_zero_denominator_is_not_applicable_not_fabricated_zero():
    r = _rate(0, 0)
    assert r["value"] is None
    assert r["status"] == "NOT_APPLICABLE"


def test_rate_real_zero_numerator_is_a_real_zero_not_na():
    r = _rate(0, 10)
    assert r["value"] == 0.0
    assert r["status"] == "AVAILABLE"


def test_average_empty_list_is_not_applicable():
    assert _average([])["status"] == "NOT_APPLICABLE"
    assert _average([])["value"] is None


def test_percentiles_empty_list_all_not_applicable():
    p = _percentiles([], points=(50, 95))
    assert p[50]["status"] == "NOT_APPLICABLE"
    assert p[95]["status"] == "NOT_APPLICABLE"


def test_percentiles_real_values_are_sorted_correctly():
    p = _percentiles([10.0, 20.0, 30.0, 40.0, 50.0], points=(50,))
    assert p[50]["value"] == 30.0
    assert p[50]["sample_count"] == 5


# ---------------------------------------------------------------------------
# overview_metrics
# ---------------------------------------------------------------------------


def test_overview_metrics_total_requests_and_denominators_correct(db):
    for i in range(7):
        _run(db, f"run-{i}", status="COMPLETED" if i < 5 else "FAILED", error_code=None if i < 5 else "MODEL_ERROR")
    result = overview_metrics(db, MonitoringFilters())
    assert result["available"] is True
    assert result["total_requests"] == 7
    assert result["success_rate"]["numerator"] == 5
    assert result["success_rate"]["denominator"] == 7
    assert result["error_rate"]["numerator"] == 2


def test_overview_metrics_empty_db_is_not_applicable_not_fabricated(db):
    result = overview_metrics(db, MonitoringFilters())
    assert result["available"] is True
    assert result["total_requests"] == 0
    assert result["success_rate"]["status"] == "NOT_APPLICABLE"
    assert result["success_rate"]["value"] is None


def test_overview_metrics_model_filter_actually_filters(db):
    _run(db, "run-a", model="gpt-5.4-mini")
    _run(db, "run-b", model="gpt-5.4")
    all_result = overview_metrics(db, MonitoringFilters())
    filtered = overview_metrics(db, MonitoringFilters(model="gpt-5.4-mini"))
    assert all_result["total_requests"] == 2
    assert filtered["total_requests"] == 1


def test_overview_metrics_date_filter_actually_filters(db):
    old = datetime.now(UTC) - timedelta(days=10)
    _run(db, "run-old", started_at=old)
    _run(db, "run-new", started_at=datetime.now(UTC))
    recent_only = overview_metrics(db, MonitoringFilters(date_from=datetime.now(UTC) - timedelta(days=1)))
    assert recent_only["total_requests"] == 1


def test_overview_metrics_ticket_and_judge_counted_correctly(db):
    _run(db, "run-1")
    _run(db, "run-2")
    db.add(AgentFeedbackTicket(
        id="t1", actor_id="a", patient_id="p", conversation_id="c", agent_run_id="run-1",
        user_message="q", assistant_message="a", reason="WRONG_ANSWER", priority="P2",
    ))
    db.add(AgentRunJudge(
        id="j1", agent_run_id="run-1", trace_id="tr1", judge_status="JUDGE_COMPLETED",
        eligibility_reason="RANDOM_SAMPLE", priority=4, judge_provider="openai", judge_model="gpt-4o",
        rubric_name="judge-generic", rubric_version="rubric-v1", judge_prompt_version="judge-v1", overall_score=0.9,
    ))
    db.commit()
    result = overview_metrics(db, MonitoringFilters())
    assert result["ticket_rate"]["numerator"] == 1
    assert result["judged_rate"]["numerator"] == 1


# ---------------------------------------------------------------------------
# quality_metrics
# ---------------------------------------------------------------------------


def test_quality_metrics_golden_ir_always_not_applicable(db):
    result = quality_metrics(db, MonitoringFilters())
    for key in ("golden_hit_rate_at_10", "golden_mrr_at_10", "golden_ndcg_at_10"):
        assert result[key]["status"] == "NOT_APPLICABLE"
        assert result[key]["value"] is None
        assert "no_stable_retrieval_id_contract" in result[key]["reason"]


def test_quality_metrics_judge_overall_score_averages_completed_only(db):
    _run(db, "run-1")
    db.add(AgentRunJudge(
        id="j1", agent_run_id="run-1", trace_id="t1", judge_status="JUDGE_COMPLETED",
        eligibility_reason="RANDOM_SAMPLE", priority=4, judge_provider="openai", judge_model="gpt-4o",
        rubric_name="judge-generic", rubric_version="rubric-v1", judge_prompt_version="judge-v1", overall_score=0.8,
    ))
    db.add(AgentRunJudge(
        id="j2", agent_run_id="run-1", trace_id="t1", judge_status="JUDGE_PENDING",
        eligibility_reason="RANDOM_SAMPLE", priority=4, judge_provider="openai", judge_model="gpt-4o",
        rubric_name="judge-generic", rubric_version="rubric-v2", judge_prompt_version="judge-v1", overall_score=None,
    ))
    db.commit()
    result = quality_metrics(db, MonitoringFilters())
    assert result["judge_overall_score"]["value"] == 0.8
    assert result["judge_overall_score"]["sample_count"] == 1


def test_quality_metrics_no_golden_run_is_not_applicable(db):
    result = quality_metrics(db, MonitoringFilters())
    assert result["golden_pass_rate"]["status"] == "NOT_APPLICABLE"
    assert result["regression_gate_status"]["status"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# retrieval_metrics -- the real correctness bug found+fixed during this build
# ---------------------------------------------------------------------------


def test_retrieval_metrics_empty_retrieval_rate_never_mixes_populations(db):
    """Regression test for a real bug found via manual smoke-testing during
    this build: RAG execution_path and GROUNDING_FAILURE error_code are
    mutually exclusive by construction (evaluation_v2.dispatch_evaluation
    requires real citations for RAG classification) -- an earlier version
    of retrieval_metrics paired them as if they were the same population
    and produced a nonsensical inflated rate. Must stay NOT_APPLICABLE with
    an honest reason, not a fabricated ratio."""

    _run(db, "run-rag")
    db.add(AgentRunEvaluation(agent_run_id="run-rag", trace_id="t1", evaluation_version="evaluation-v2", execution_path="RAG", metrics_json={}))
    _run(db, "run-fail", error_code="GROUNDING_FAILURE")
    db.commit()
    result = retrieval_metrics(db, MonitoringFilters())
    assert result["empty_retrieval_rate"]["status"] == "NOT_APPLICABLE"
    assert result["rag_query_volume"] == 1
    assert result["grounding_failure_rate"]["numerator"] == 1
    assert result["grounding_failure_rate"]["denominator"] == 2


def test_retrieval_metrics_golden_ir_always_not_applicable(db):
    result = retrieval_metrics(db, MonitoringFilters())
    for key in ("golden_hit_rate_at_10", "golden_mrr_at_10", "golden_ndcg_at_10", "golden_precision_at_10"):
        assert result[key]["status"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# performance_metrics -- real spans only
# ---------------------------------------------------------------------------


def test_performance_metrics_per_step_uses_real_spans(db):
    run = _run(db, "run-1")
    db.add(AgentRunSpan(
        id="s1", agent_run_id=run.id, trace_id="t1", span_name="router", span_type="ROUTER",
        status="OK", started_at=datetime.now(UTC), completed_at=datetime.now(UTC), duration_ms=5.0,
    ))
    db.add(AgentRunSpan(
        id="s2", agent_run_id=run.id, trace_id="t1", span_name="model", span_type="MODEL",
        status="OK", started_at=datetime.now(UTC), completed_at=datetime.now(UTC), duration_ms=250.0,
    ))
    db.commit()
    result = performance_metrics(db, MonitoringFilters())
    assert result["per_step"]["ROUTER"][50]["value"] == 5.0
    assert result["per_step"]["MODEL"][50]["value"] == 250.0
    assert result["per_step"]["TOOL"][50]["status"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# cost_metrics -- agent vs judge cost kept separate
# ---------------------------------------------------------------------------


def test_cost_metrics_agent_and_judge_cost_are_separate_axes(db):
    _run(db, "run-1", total_cost_usd=0.01, cost_status="AVAILABLE")
    db.add(AgentRunJudge(
        id="j1", agent_run_id="run-1", trace_id="t1", judge_status="JUDGE_COMPLETED",
        eligibility_reason="RANDOM_SAMPLE", priority=4, judge_provider="openai", judge_model="gpt-4o",
        rubric_name="judge-generic", rubric_version="rubric-v1", judge_prompt_version="judge-v1",
        cost_usd=0.002, cost_status="AVAILABLE",
    ))
    db.commit()
    result = cost_metrics(db, MonitoringFilters())
    assert result["agent_cost_usd"]["value"] == 0.01
    assert result["judge_cost_usd"]["value"] == 0.002
    assert result["total_cost_usd"]["value"] == pytest.approx(0.012)


def test_cost_metrics_unavailable_pricing_is_not_available_not_zero(db):
    _run(db, "run-1", total_cost_usd=None, cost_status="NOT_AVAILABLE")
    db.commit()
    result = cost_metrics(db, MonitoringFilters())
    assert result["agent_cost_usd"]["status"] == "NOT_AVAILABLE"
    assert result["agent_cost_usd"]["value"] is None


# ---------------------------------------------------------------------------
# errors_metrics -- canonical taxonomy incl. never-emitted codes
# ---------------------------------------------------------------------------


def test_errors_metrics_breakdown_and_never_emitted_codes(db):
    _run(db, "run-1", error_code="MODEL_TIMEOUT")
    _run(db, "run-2", error_code=None)
    db.commit()
    result = errors_metrics(db, MonitoringFilters())
    assert result["breakdown"]["MODEL_TIMEOUT"]["numerator"] == 1
    assert result["breakdown"]["MODEL_ERROR"]["numerator"] == 0
    assert result["breakdown"]["TOOL_TIMEOUT"]["value"] == 0.0
    assert result["breakdown"]["TOOL_TIMEOUT"]["status"] == "AVAILABLE"
    assert "never_emitted" in result["breakdown"]["TOOL_TIMEOUT"]["note"]
    assert "never_emitted" in result["breakdown"]["RETRIEVAL_TIMEOUT"]["note"]


def test_errors_metrics_unrecognized_code_surfaced_not_dropped(db):
    _run(db, "run-1", error_code="SOME_NEW_CODE_NOT_IN_TAXONOMY")
    db.commit()
    result = errors_metrics(db, MonitoringFilters())
    assert "SOME_NEW_CODE_NOT_IN_TAXONOMY" in result["unrecognized_error_codes"]


# ---------------------------------------------------------------------------
# judge_metrics
# ---------------------------------------------------------------------------


def test_judge_metrics_status_counts_and_low_score_cases(db):
    _run(db, "run-1")
    db.add(AgentRunJudge(
        id="j1", agent_run_id="run-1", trace_id="t1", judge_status="JUDGE_COMPLETED",
        eligibility_reason="RANDOM_SAMPLE", priority=4, judge_provider="openai", judge_model="gpt-4o",
        rubric_name="judge-generic", rubric_version="rubric-v1", judge_prompt_version="judge-v1", overall_score=0.2,
    ))
    db.add(AgentRunJudge(
        id="j2", agent_run_id="run-1", trace_id="t1", judge_status="JUDGE_FAILED",
        eligibility_reason="RANDOM_SAMPLE", priority=4, judge_provider="openai", judge_model="gpt-4o",
        rubric_name="judge-generic", rubric_version="rubric-v2", judge_prompt_version="judge-v1",
    ))
    db.commit()
    result = judge_metrics(db, MonitoringFilters())
    assert result["judged_completed"] == 1
    assert result["judged_failed"] == 1
    assert len(result["low_score_cases"]) == 1
    assert result["low_score_cases"][0]["score"] == 0.2


# ---------------------------------------------------------------------------
# golden_metrics / golden_run_detail
# ---------------------------------------------------------------------------


def test_golden_metrics_no_run_persisted_yet(db):
    result = golden_metrics(db)
    assert result["available"] is True
    assert result["has_run"] is False


def test_golden_metrics_real_persisted_run(db):
    db.add(AgentGoldenRun(
        id="run-1", golden_set_version="v1", git_commit="abc123", started_at="2026-08-25T00:00:00Z",
        completed_at="2026-08-25T00:01:00Z", total_cases=10, passed_cases=9, failed_cases=1, pass_rate=0.9,
        regression_gate_passed=True, provenance_json={}, aggregate_json={}, regression_gate_json={}, comparisons_json=[],
    ))
    db.add(AgentGoldenRunCase(id="c1", run_id="run-1", case_id="GOLD-A", category="RAG_GENERAL_MEDICAL", passed=True, checks_json=[]))
    db.add(AgentGoldenRunCase(id="c2", run_id="run-1", case_id="GOLD-B", category="RAG_GENERAL_MEDICAL", passed=False, checks_json=[]))
    db.commit()
    result = golden_metrics(db)
    assert result["has_run"] is True
    assert result["latest_run"]["pass_rate"] == 0.9
    assert result["latest_run"]["by_category"]["RAG_GENERAL_MEDICAL"] == {"total": 2, "passed": 1}
    assert result["latest_run"]["failed_case_ids"] == ["GOLD-B"]

    detail = golden_run_detail(db, "run-1")
    assert detail is not None
    assert len(detail["cases"]) == 2
    assert golden_run_detail(db, "does-not-exist") is None


# ---------------------------------------------------------------------------
# version_filter_options -- real distinct values, not hardcoded
# ---------------------------------------------------------------------------


def test_version_filter_options_reflects_real_distinct_values(db):
    _run(db, "run-1", model="gpt-5.4-mini")
    _run(db, "run-2", model="gpt-5.4")
    db.commit()
    result = version_filter_options(db)
    assert set(result["model"]) == {"gpt-5.4-mini", "gpt-5.4"}


# ---------------------------------------------------------------------------
# compare_metrics
# ---------------------------------------------------------------------------


def test_compare_metrics_identical_filters_zero_delta(db):
    _run(db, "run-1")
    db.commit()
    result = compare_metrics(db, "overview", MonitoringFilters(), MonitoringFilters())
    assert result["available"] is True
    assert result["comparison"]["total_requests"]["delta"] == 0


def test_compare_metrics_unknown_section_is_unavailable(db):
    result = compare_metrics(db, "not-a-real-section", MonitoringFilters(), MonitoringFilters())
    assert result["available"] is False


def test_compare_metrics_real_difference_produces_real_delta(db):
    _run(db, "run-a", model="gpt-5.4-mini")
    _run(db, "run-b", model="gpt-5.4-mini")
    _run(db, "run-c", model="gpt-5.4")
    db.commit()
    result = compare_metrics(db, "overview", MonitoringFilters(model="gpt-5.4-mini"), MonitoringFilters(model="gpt-5.4"))
    assert result["comparison"]["total_requests"]["before"] == 2
    assert result["comparison"]["total_requests"]["after"] == 1
    assert result["comparison"]["total_requests"]["delta"] == -1


# ---------------------------------------------------------------------------
# pagination
# ---------------------------------------------------------------------------


def test_paginate_returns_real_total_and_page(db):
    from sqlalchemy import select

    for i in range(5):
        _run(db, f"run-{i}")
    rows, total = paginate(db, select(AgentRun), limit=2, offset=2)
    assert total == 5
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# list_traces / trace_detail
# ---------------------------------------------------------------------------


def test_list_traces_markers_reflect_real_related_rows(db):
    _run(db, "run-1")
    db.add(AgentFeedbackTicket(id="t1", actor_id="a", patient_id="p", conversation_id="c", agent_run_id="run-1", user_message="q", assistant_message="a", reason="WRONG_ANSWER", priority="P2"))
    db.add(AgentSafetyEvent(agent_run_id="run-1", trace_id="tr1", outcome="HANDOFF_REQUIRED", reason_code="ACUTE_DANGER_DETECTED", severity="CRITICAL", severity_source="reason_code_mapped"))
    db.commit()
    result = list_traces(db, MonitoringFilters(), limit=10, offset=0)
    assert result["total"] == 1
    assert result["items"][0]["has_ticket"] is True
    assert result["items"][0]["has_safety_event"] is True
    assert result["items"][0]["has_judge_result"] is False


def test_trace_detail_not_found_returns_none(db):
    assert trace_detail(db, "no-such-trace") is None


def test_trace_detail_real_correlation(db):
    run = _run(db, "run-1")
    run.trace_id = "trace-xyz"
    db.add(AgentRunEvaluation(agent_run_id="run-1", trace_id="trace-xyz", evaluation_version="evaluation-v2", execution_path="RAG", metrics_json={"x": 1}))
    db.commit()
    detail = trace_detail(db, "trace-xyz")
    assert detail is not None
    assert detail["agent_run_id"] == "run-1"
    assert detail["execution_path"] == "RAG"
    assert detail["evaluation"] == {"x": 1}
