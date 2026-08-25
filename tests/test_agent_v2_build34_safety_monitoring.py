"""BUILD-34: unit/integration tests for the Safety & Handoff monitoring
domain -- canonical AgentSafetyEvent persistence (pure builder + best-effort
write), metrics/denominators, drill-down queries, Judge secondary-signal
correlation, and structural guarantees (no chain-of-thought, Safety runtime
untouched, no legacy double-counting).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import (
    AgentFeedbackTicket,
    AgentRun,
    AgentRunJudge,
    AgentSafetyEvent,
    DoctorReviewRequest,
    Escalation,
)
from backend.services.agent_safety_monitoring import (
    build_safety_event,
    classify_severity,
    judge_suspected_missed_risk_signals,
    legacy_escalation_count,
    list_safety_events,
    persist_safety_event,
    safety_event_detail,
    safety_metrics_summary,
)

# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


def _fake_result(
    *,
    agent_run_id="run-1",
    trace_id="trace-1",
    intent="ACUTE_DANGER_ESCALATION",
    status="HANDOFF_CREATED",
    outcome="HANDOFF_REQUIRED",
    reason_code="ACUTE_DANGER_DETECTED",
    risk_level=None,
    provenance="agent-orchestrator:acute-danger",
    handoff_request_id=None,
    handoff_status=None,
    handoff_created=False,
    error_code=None,
    safety_decision_present=True,
):
    safety_decision = None
    if safety_decision_present:
        safety_decision = SimpleNamespace(
            outcome=SimpleNamespace(value=outcome),
            reason_code=reason_code,
            risk_level=risk_level,
            provenance=provenance,
        )
    handoff_result = None
    if handoff_request_id:
        handoff_result = SimpleNamespace(request_id=handoff_request_id, status=handoff_status, created=handoff_created)
    return SimpleNamespace(
        agent_run_id=agent_run_id,
        trace_id=trace_id,
        intent=SimpleNamespace(value=intent),
        status=SimpleNamespace(value=status),
        response="fixed reply",
        tool_results=(),
        citations=(),
        safety_decision=safety_decision,
        handoff_result=handoff_result,
        error_code=error_code,
    )


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AgentSafetyEvent.__table__.create(engine)
    AgentRun.__table__.create(engine)
    AgentRunJudge.__table__.create(engine)
    AgentFeedbackTicket.__table__.create(engine)
    DoctorReviewRequest.__table__.create(engine)
    Escalation.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# classify_severity (pure)
# ---------------------------------------------------------------------------


def test_classify_severity_prefers_real_risk_level_over_reason_code_map():
    severity, source = classify_severity(reason_code="ACUTE_DANGER_DETECTED", risk_level="high")
    assert severity == "HIGH" and source == "risk_level_field"


def test_classify_severity_uses_reason_code_map_when_no_risk_level():
    severity, source = classify_severity(reason_code="ACUTE_DANGER_DETECTED", risk_level=None)
    assert severity == "CRITICAL" and source == "reason_code_mapped"


def test_classify_severity_unmapped_reason_code_gets_safe_default_not_low():
    severity, source = classify_severity(reason_code="SOME_FUTURE_REASON_CODE", risk_level=None)
    assert severity == "MEDIUM" and source == "unmapped_default"
    assert severity != "LOW"  # never under-report an unrecognized reason code


# ---------------------------------------------------------------------------
# build_safety_event (pure)
# ---------------------------------------------------------------------------


def test_build_safety_event_returns_none_for_safe_outcome():
    result = _fake_result(outcome="SAFE", reason_code="SAFETY_NOT_REQUIRED", safety_decision_present=True)
    row = build_safety_event(result=result, conversation_id="c1", patient_id="p1", actor_id="a1")
    assert row is None


def test_build_safety_event_returns_none_when_no_safety_decision_at_all():
    result = _fake_result(safety_decision_present=False)
    row = build_safety_event(result=result, conversation_id="c1", patient_id="p1", actor_id="a1")
    assert row is None


def test_build_safety_event_captures_acute_danger_escalation():
    result = _fake_result(
        outcome="HANDOFF_REQUIRED",
        reason_code="ACUTE_DANGER_DETECTED",
        handoff_request_id="handoff-1",
        handoff_status="PENDING",
        handoff_created=True,
    )
    row = build_safety_event(result=result, conversation_id="conv-1", patient_id="patient-1", actor_id="actor-1")
    assert row is not None
    assert row.outcome == "HANDOFF_REQUIRED"
    assert row.reason_code == "ACUTE_DANGER_DETECTED"
    assert row.severity == "CRITICAL"
    assert row.handoff_required is True
    assert row.handoff_created is True
    assert row.handoff_id == "handoff-1"
    assert row.conversation_id == "conv-1" and row.patient_id == "patient-1" and row.actor_id == "actor-1"


def test_build_safety_event_captures_handoff_creation_failure():
    """The exact failure-semantics scenario BUILD-34 §8 asks to distinguish
    -- HANDOFF_REQUIRED without HANDOFF_CREATED, with the real error_code."""

    result = _fake_result(
        outcome="HANDOFF_REQUIRED", reason_code="ACUTE_DANGER_DETECTED", status="FAILED", error_code="HANDOFF_FAILURE"
    )
    row = build_safety_event(result=result, conversation_id="c1", patient_id="p1", actor_id="a1")
    assert row.handoff_required is True
    assert row.handoff_created is False
    assert row.handoff_id is None
    assert row.error_code == "HANDOFF_FAILURE"


def test_build_safety_event_captures_safety_blocked():
    result = _fake_result(outcome="SAFETY_BLOCKED", reason_code="DOSE_UNRESOLVED", intent="MISSED_DOSE", status="SAFETY_BLOCKED")
    row = build_safety_event(result=result, conversation_id="c1", patient_id="p1", actor_id="a1")
    assert row is not None
    assert row.outcome == "SAFETY_BLOCKED"
    assert row.handoff_required is False


def test_build_safety_event_never_stores_free_text_reasoning():
    """Structural no-chain-of-thought guarantee: the model has no column
    that could hold raw response/reasoning text at all."""

    columns = {c.name for c in AgentSafetyEvent.__table__.columns}
    assert "response" not in columns and "reasoning" not in columns and "raw_text" not in columns


# ---------------------------------------------------------------------------
# persist_safety_event (real sqlite db)
# ---------------------------------------------------------------------------


def test_persist_safety_event_writes_row_and_is_readable_from_fresh_session(db, tmp_path):
    """Restart-durability proxy: write via one session, then read back via
    a genuinely independent session/engine bound to the same on-disk file --
    the same technique BUILD-18B's own transaction-durability tests use."""

    db_path = str(tmp_path / "safety_restart.db")
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    AgentSafetyEvent.__table__.create(engine)
    session_a = Session(engine)
    result = _fake_result(agent_run_id="run-restart", trace_id="trace-restart", handoff_request_id="h-1", handoff_status="PENDING", handoff_created=True)
    row = persist_safety_event(session_a, result=result, conversation_id="c1", patient_id="p1", actor_id="a1")
    assert row is not None
    session_a.close()

    session_b = Session(create_engine(f"sqlite+pysqlite:///{db_path}"))
    found = session_b.execute(select(AgentSafetyEvent).where(AgentSafetyEvent.agent_run_id == "run-restart")).scalar_one_or_none()
    assert found is not None
    assert found.reason_code == "ACUTE_DANGER_DETECTED"
    session_b.close()


def test_persist_safety_event_never_raises_on_internal_failure(db, monkeypatch):
    import backend.services.agent_safety_monitoring as mod

    def _boom(*a, **k):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(mod, "build_safety_event", _boom)
    result = _fake_result()
    row = persist_safety_event(db, result=result, conversation_id="c1", patient_id="p1", actor_id="a1")  # must not raise
    assert row is None


def test_persist_safety_event_no_row_for_safe_outcome(db):
    result = _fake_result(outcome="SAFE", reason_code="SAFETY_NOT_REQUIRED")
    row = persist_safety_event(db, result=result, conversation_id="c1", patient_id="p1", actor_id="a1")
    assert row is None
    assert db.execute(select(AgentSafetyEvent)).scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Metrics / denominators
# ---------------------------------------------------------------------------


def _add_run(db, run_id, **overrides):
    import datetime

    base = dict(id=run_id, status="COMPLETED", started_at=datetime.datetime.now(datetime.UTC))
    base.update(overrides)
    db.add(AgentRun(**base))


def test_safety_metrics_summary_denominator_is_real_agent_run_count(db):
    for i in range(5):
        _add_run(db, f"run-{i}")
    db.commit()
    metrics = safety_metrics_summary(db)
    assert metrics["denominator_agent_v2_total_runs"] == 5
    assert metrics["safety_trigger_count"] == 0
    assert metrics["safety_trigger_rate"] == 0.0


def test_safety_metrics_summary_na_not_zero_when_no_runs_at_all(db):
    metrics = safety_metrics_summary(db)
    assert metrics["denominator_agent_v2_total_runs"] == 0
    assert metrics["safety_trigger_rate"] is None  # N/A, not a fabricated 0.0


def test_safety_metrics_summary_counts_severity_and_reason_distributions(db):
    for i in range(3):
        _add_run(db, f"run-{i}")
    db.commit()
    for i in range(3):
        result = _fake_result(agent_run_id=f"run-{i}", trace_id=f"trace-{i}")
        persist_safety_event(db, result=result, conversation_id="c", patient_id="p", actor_id="a")

    metrics = safety_metrics_summary(db)
    assert metrics["safety_trigger_count"] == 3
    assert metrics["safety_trigger_rate"] == 1.0
    assert metrics["severity_distribution"] == {"CRITICAL": 3}
    assert metrics["reason_code_distribution"] == {"ACUTE_DANGER_DETECTED": 3}


def test_safety_metrics_summary_handoff_failure_rate_has_handoff_required_denominator(db):
    _add_run(db, "run-a")
    _add_run(db, "run-b")
    db.commit()
    ok = _fake_result(agent_run_id="run-a", trace_id="trace-a", handoff_request_id="h-a", handoff_status="PENDING", handoff_created=True)
    failed = _fake_result(agent_run_id="run-b", trace_id="trace-b", status="FAILED", error_code="HANDOFF_FAILURE")
    persist_safety_event(db, result=ok, conversation_id="c", patient_id="p", actor_id="a")
    persist_safety_event(db, result=failed, conversation_id="c", patient_id="p", actor_id="a")

    metrics = safety_metrics_summary(db)
    assert metrics["handoff_required_count"] == 2
    assert metrics["handoff_created_count"] == 1
    assert metrics["handoff_failure_count"] == 1
    assert metrics["handoff_failure_rate"] == 0.5  # denominator is handoff_required, not total runs


def test_safety_metrics_summary_time_to_review_and_unresolved_from_live_doctor_review_request(db):
    import datetime

    _add_run(db, "run-a")
    db.commit()
    created = datetime.datetime(2026, 8, 25, 8, 0, tzinfo=datetime.UTC)
    resolved = datetime.datetime(2026, 8, 25, 8, 30, tzinfo=datetime.UTC)
    result = _fake_result(agent_run_id="run-a", trace_id="trace-a", handoff_request_id="doc-review-1", handoff_status="PENDING", handoff_created=True)
    row = persist_safety_event(db, result=result, conversation_id="c", patient_id="p", actor_id="a")
    row.created_at = created
    db.add(
        DoctorReviewRequest(
            id="doc-review-1", patient_id="p", created_by_actor_id="a", reason_code="ACUTE_DANGER_DETECTED",
            risk_disposition="HANDOFF_REQUIRED", patient_question="q", agent_summary="s", status="ANSWERED",
            idempotency_key="k1", created_at=created, answered_at=resolved,
        )
    )
    db.commit()

    metrics = safety_metrics_summary(db)
    assert metrics["unresolved_handoff_count"] == 0
    assert metrics["time_to_review_avg_seconds"] == pytest.approx(1800.0)
    assert metrics["handoff_status_distribution"] == {"ANSWERED": 1}


def test_safety_metrics_summary_unresolved_when_handoff_still_pending(db):
    _add_run(db, "run-a")
    db.commit()
    result = _fake_result(agent_run_id="run-a", trace_id="trace-a", handoff_request_id="doc-review-2", handoff_status="PENDING", handoff_created=True)
    persist_safety_event(db, result=result, conversation_id="c", patient_id="p", actor_id="a")
    import datetime

    db.add(
        DoctorReviewRequest(
            id="doc-review-2", patient_id="p", created_by_actor_id="a", reason_code="ACUTE_DANGER_DETECTED",
            risk_disposition="HANDOFF_REQUIRED", patient_question="q", agent_summary="s", status="PENDING",
            idempotency_key="k2", created_at=datetime.datetime.now(datetime.UTC),
        )
    )
    db.commit()
    metrics = safety_metrics_summary(db)
    assert metrics["unresolved_handoff_count"] == 1


# ---------------------------------------------------------------------------
# list/detail drill-down
# ---------------------------------------------------------------------------


def test_list_safety_events_filters_by_severity_and_reason_code(db):
    _add_run(db, "run-1")
    _add_run(db, "run-2")
    db.commit()
    persist_safety_event(db, result=_fake_result(agent_run_id="run-1", trace_id="t1"), conversation_id="c", patient_id="p", actor_id="a")
    persist_safety_event(
        db,
        result=_fake_result(agent_run_id="run-2", trace_id="t2", outcome="HANDOFF_REQUIRED", reason_code="POSSIBLE_OVERDOSE_REPORTED"),
        conversation_id="c", patient_id="p", actor_id="a",
    )
    items, total = list_safety_events(db, severity="CRITICAL")
    assert total == 1 and items[0]["reason_code"] == "ACUTE_DANGER_DETECTED"

    items, total = list_safety_events(db, reason_code="POSSIBLE_OVERDOSE_REPORTED")
    assert total == 1 and items[0]["severity"] == "HIGH"


def test_list_safety_events_batches_handoff_status_lookup_not_n_plus_1(db):
    """Regression for a real N+1 found in code review: fetching live
    handoff status for a page of events must be O(1) extra queries, not
    O(N events) -- counts real DB round-trips via SQLAlchemy's own
    before_cursor_execute event, not just asserting correctness."""

    from sqlalchemy import event

    for i in range(5):
        run_id = f"run-n1-{i}"
        _add_run(db, run_id)
        db.commit()
        persist_safety_event(
            db,
            result=_fake_result(
                agent_run_id=run_id, trace_id=f"t-n1-{i}", handoff_request_id=f"handoff-n1-{i}", handoff_status="PENDING", handoff_created=True
            ),
            conversation_id="c", patient_id="p", actor_id="a",
        )
        db.add(
            DoctorReviewRequest(
                id=f"handoff-n1-{i}", patient_id="p", created_by_actor_id="a", reason_code="ACUTE_DANGER_DETECTED",
                risk_disposition="HANDOFF_REQUIRED", patient_question="q", agent_summary="s", status="PENDING",
                idempotency_key=f"k-n1-{i}",
            )
        )
    db.commit()

    query_count = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        query_count["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _count)
    try:
        items, total = list_safety_events(db, limit=10)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert total == 5
    assert len(items) == 5
    # Old N+1 code: 1 count + 1 events + 5 (one _live_handoff_status per
    # event) = 7. New batched code: 1 count + 1 events + 1 batched handoff
    # lookup = 3. Bounding at 4 leaves slack without re-permitting O(N).
    assert query_count["n"] <= 4, f"expected O(1) queries regardless of event count, got {query_count['n']}"


def test_safety_event_detail_links_ticket_and_judge_when_present(db):
    _add_run(db, "run-1")
    db.commit()
    row = persist_safety_event(db, result=_fake_result(agent_run_id="run-1", trace_id="t1"), conversation_id="conv-1", patient_id="p", actor_id="a")
    db.add(
        AgentFeedbackTicket(
            id="ticket-1", actor_id="a", patient_id="p", conversation_id="conv-1", agent_run_id="run-1",
            user_message="q", assistant_message="a", reason="UNSAFE_OR_INAPPROPRIATE", chatbot_version="agent-v2",
            status="OPEN", priority="P0", p0_review_required=True,
        )
    )
    db.add(
        AgentRunJudge(
            agent_run_id="run-1", trace_id="t1", judge_status="JUDGE_COMPLETED", eligibility_reason="SAFETY_ANOMALY",
            priority=1, execution_path="SAFETY", judge_provider="openai", judge_model="gpt-4o",
            judge_config_json={}, rubric_name="judge-safety-handoff", rubric_version="v1", judge_prompt_version="v1",
            overall_score=0.9, dimension_scores_json={}, flags_json=[],
        )
    )
    db.commit()

    detail = safety_event_detail(db, row.id)
    assert detail["ticket_id"] == "ticket-1"
    assert detail["judge"]["judge_status"] == "JUDGE_COMPLETED"
    assert detail["conversation_id"] == "conv-1"
    assert detail["trace_id"] == "t1"


def test_safety_event_detail_returns_none_for_unknown_id(db):
    assert safety_event_detail(db, "does-not-exist") is None


# ---------------------------------------------------------------------------
# Judge secondary-signal correlation (BUILD-34 §4)
# ---------------------------------------------------------------------------


def test_judge_missed_risk_signal_fires_when_safety_silent_and_judge_flags_low_red_flag_handling(db):
    _add_run(db, "run-triage")
    db.commit()
    db.add(
        AgentRunJudge(
            agent_run_id="run-triage", trace_id="t-triage", judge_status="JUDGE_COMPLETED", eligibility_reason="RANDOM_SAMPLE",
            priority=4, execution_path="TRIAGE", judge_provider="openai", judge_model="gpt-4o", judge_config_json={},
            rubric_name="judge-triage", rubric_version="v1", judge_prompt_version="v1", overall_score=0.3,
            dimension_scores_json={"red_flag_handling": 0.2}, flags_json=["missing_red_flag_handling"],
        )
    )
    db.commit()
    # no AgentSafetyEvent row for run-triage -- Safety never triggered

    signals = judge_suspected_missed_risk_signals(db)
    assert len(signals) == 1
    assert signals[0]["signal"] == "REVIEW_SUSPECTED_MISSED_RISK"
    assert signals[0]["agent_run_id"] == "run-triage"


def test_judge_missed_risk_signal_does_not_fire_when_safety_already_triggered(db):
    _add_run(db, "run-triage-2")
    db.commit()
    db.add(
        AgentRunJudge(
            agent_run_id="run-triage-2", trace_id="t2", judge_status="JUDGE_COMPLETED", eligibility_reason="SAFETY_ANOMALY",
            priority=1, execution_path="TRIAGE", judge_provider="openai", judge_model="gpt-4o", judge_config_json={},
            rubric_name="judge-triage", rubric_version="v1", judge_prompt_version="v1", overall_score=0.2,
            dimension_scores_json={"red_flag_handling": 0.1}, flags_json=[],
        )
    )
    # Safety DID trigger this time -- a real AgentSafetyEvent exists.
    persist_safety_event(
        db, result=_fake_result(agent_run_id="run-triage-2", trace_id="t2"), conversation_id="c", patient_id="p", actor_id="a"
    )
    db.commit()

    signals = judge_suspected_missed_risk_signals(db)
    assert signals == []


def test_judge_missed_risk_signal_ignores_high_red_flag_handling_score(db):
    _add_run(db, "run-triage-3")
    db.commit()
    db.add(
        AgentRunJudge(
            agent_run_id="run-triage-3", trace_id="t3", judge_status="JUDGE_COMPLETED", eligibility_reason="RANDOM_SAMPLE",
            priority=4, execution_path="TRIAGE", judge_provider="openai", judge_model="gpt-4o", judge_config_json={},
            rubric_name="judge-triage", rubric_version="v1", judge_prompt_version="v1", overall_score=0.9,
            dimension_scores_json={"red_flag_handling": 0.9}, flags_json=[],
        )
    )
    db.commit()
    assert judge_suspected_missed_risk_signals(db) == []


def test_judge_missed_risk_signal_finds_sparse_matches_beyond_the_first_page(db):
    """Regression for a real completeness gap found in code review: a naive
    single over-fetch (LIMIT N, then filter in Python) can under-return real
    signals when matches are sparse -- e.g. the first `limit` candidates by
    recency are all high-scoring (filtered out) and the low scorers only
    start appearing after that. The paged loop must keep going instead of
    stopping after one page."""

    # 45 recent, high-scoring TRIAGE runs (never signals) -- deliberately
    # MORE than limit*4 (=40 for limit=10 below), the old single-over-fetch
    # cap: with that old implementation these alone would have filled the
    # entire fetch and the 3 real signals below would never be seen at all.
    for i in range(45):
        run_id = f"run-triage-high-{i}"
        _add_run(db, run_id)
        db.add(
            AgentRunJudge(
                agent_run_id=run_id, trace_id=f"t-high-{i}", judge_status="JUDGE_COMPLETED", eligibility_reason="RANDOM_SAMPLE",
                priority=4, execution_path="TRIAGE", judge_provider="openai", judge_model="gpt-4o", judge_config_json={},
                rubric_name="judge-triage", rubric_version="v1", judge_prompt_version="v1", overall_score=0.9,
                dimension_scores_json={"red_flag_handling": 0.9}, flags_json=[],
            )
        )
    # ... then 3 OLDER, low-scoring ones (real signals) -- given created_at
    # ordering (most-recent-first), these only appear on a later page when
    # `limit` is small (page_size below is max(limit, 20)).
    import datetime

    for i in range(3):
        run_id = f"run-triage-low-{i}"
        _add_run(db, run_id)
        db.add(
            AgentRunJudge(
                agent_run_id=run_id, trace_id=f"t-low-{i}", judge_status="JUDGE_COMPLETED", eligibility_reason="RANDOM_SAMPLE",
                priority=4, execution_path="TRIAGE", judge_provider="openai", judge_model="gpt-4o", judge_config_json={},
                rubric_name="judge-triage", rubric_version="v1", judge_prompt_version="v1", overall_score=0.2,
                dimension_scores_json={"red_flag_handling": 0.1}, flags_json=[],
                created_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC),  # much older -- sorts last
            )
        )
    db.commit()

    signals = judge_suspected_missed_risk_signals(db, limit=10)
    assert len(signals) == 3
    assert {s["agent_run_id"] for s in signals} == {"run-triage-low-0", "run-triage-low-1", "run-triage-low-2"}


def test_judge_missed_risk_signal_never_touches_safety_decision_or_creates_handoff():
    """Structural: the function has no db.add/db.commit at all -- purely
    read-only, confirmed by reading its own source for any write call."""

    import inspect

    import backend.services.agent_safety_monitoring as mod

    source = inspect.getsource(mod.judge_suspected_missed_risk_signals)
    assert "db.add(" not in source
    assert "db.commit(" not in source
    assert "SafetyDecision(" not in source


# ---------------------------------------------------------------------------
# Legacy compatibility (BUILD-34 §6)
# ---------------------------------------------------------------------------


def test_legacy_escalation_count_is_separate_and_never_summed_with_agent_v2(db):
    import datetime

    db.add(Escalation(id="esc-1", patient_id="p", severity="HIGH", trigger="safety_redflag", reason="r", created_at=datetime.datetime.now(datetime.UTC)))
    _add_run(db, "run-1")
    db.commit()
    persist_safety_event(db, result=_fake_result(agent_run_id="run-1", trace_id="t1"), conversation_id="c", patient_id="p", actor_id="a")

    legacy_count = legacy_escalation_count(db)
    metrics = safety_metrics_summary(db)
    assert legacy_count == 1
    assert metrics["safety_trigger_count"] == 1
    # Two structurally independent numbers -- neither includes the other.
    assert "legacy_escalation_count" not in metrics
