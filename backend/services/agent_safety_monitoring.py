"""BUILD-34: Safety & Handoff monitoring domain for Agent V2.

Canonical, durable ``AgentSafetyEvent`` write path (best-effort, post-
response, pure function of an already-completed ``OrchestrationResult`` --
never influences Safety/Handoff runtime behavior) plus every read/aggregate
query the Admin monitoring surface needs. Nothing in this module is called
from ``backend/agents/v2/safety.py``, ``orchestrator.py``, ``runtime.py``,
or ``handoff.py`` -- monitoring only, per BUILD-34 §12.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.agents.v2.evaluation_v2 import EvaluationPath, dispatch_evaluation
from backend.db.models import (
    AgentFeedbackTicket,
    AgentRun,
    AgentRunJudge,
    AgentSafetyEvent,
    DoctorReviewRequest,
    Escalation,
)

logger = logging.getLogger("agent_safety_monitoring")

# BUILD-34 §2/§6: prefer the Safety Domain's OWN risk_level (DB-4H's real
# policy-engine output, MISSED_DOSE/DELAYED_DOSE path) whenever the
# SafetyDecision carries one -- this map is only the deterministic fallback
# for the reason codes that never go through DB-4H at all (the orchestrator-
# level bypass branches: acute danger, possible overdose, doctor review
# request, unresolved dose, domain outage). Never inferred from free text.
_SEVERITY_BY_REASON_CODE: dict[str, str] = {
    "ACUTE_DANGER_DETECTED": "CRITICAL",
    "POSSIBLE_OVERDOSE_REPORTED": "HIGH",
    "SAFETY_DOMAIN_UNAVAILABLE": "HIGH",
    "SAFETY_DOMAIN_TIMEOUT": "HIGH",
    "DOCTOR_REVIEW_REQUESTED": "MEDIUM",
    "DOSE_UNRESOLVED": "MEDIUM",
    "DOSE_NOT_YET_ASSESSABLE": "LOW",
}
_DEFAULT_SEVERITY = "MEDIUM"  # never LOW by default -- an unrecognized reason_code must not be under-reported

# Only these two SafetyOutcome values are "actionable" safety events worth a
# durable row -- a plain SAFE outcome is the overwhelming majority of
# traffic and gets no row at all, by design (mirrors BUILD-33's own "not
# 100% of traffic" eligibility spirit).
_ACTIONABLE_OUTCOMES = frozenset({"SAFETY_BLOCKED", "HANDOFF_REQUIRED"})

_HANDOFF_RESOLVED_STATUSES = frozenset({"ANSWERED", "CANCELLED"})


def classify_severity(*, reason_code: str, risk_level: str | None) -> tuple[str, str]:
    """Pure function -- returns ``(severity, source)``. ``source`` is
    ``"risk_level_field"`` when the Safety Domain itself supplied one,
    ``"reason_code_mapped"`` when derived from the deterministic table
    above, or ``"unmapped_default"`` for a reason_code this build does not
    yet recognize (never silently guessed from message text)."""

    if risk_level:
        return risk_level.upper(), "risk_level_field"
    mapped = _SEVERITY_BY_REASON_CODE.get(reason_code)
    if mapped:
        return mapped, "reason_code_mapped"
    return _DEFAULT_SEVERITY, "unmapped_default"


def build_safety_event(
    *, result: Any, conversation_id: str | None, patient_id: str | None, actor_id: str | None
) -> AgentSafetyEvent | None:
    """Pure builder (no I/O) -- ``None`` when this run's outcome was not
    actionable (SAFE, or no safety_decision at all). ``OrchestrationResult``
    itself carries no conversation/patient/actor identity (only trace_id/
    agent_run_id/intent/status/...) -- those come from the request/actor
    already in scope at the real call site
    (``agent_v2_routes.run_agent_orchestration``), same as
    ``_persist_durable_trace`` receives ``actor`` explicitly rather than
    trying to read it off ``result``."""

    safety_decision = getattr(result, "safety_decision", None)
    if safety_decision is None:
        return None
    outcome = getattr(getattr(safety_decision, "outcome", None), "value", str(getattr(safety_decision, "outcome", "")))
    if outcome not in _ACTIONABLE_OUTCOMES:
        return None

    reason_code = str(getattr(safety_decision, "reason_code", "") or "")
    risk_level = getattr(safety_decision, "risk_level", None)
    severity, severity_source = classify_severity(reason_code=reason_code, risk_level=risk_level)

    evaluation = dispatch_evaluation(result=result)
    handoff_result = getattr(result, "handoff_result", None)

    return AgentSafetyEvent(
        agent_run_id=result.agent_run_id,
        trace_id=result.trace_id,
        conversation_id=conversation_id,
        patient_id=patient_id,
        actor_id=actor_id,
        outcome=outcome,
        reason_code=reason_code,
        severity=severity,
        severity_source=severity_source,
        safety_path=evaluation.path.value,
        provenance=str(getattr(safety_decision, "provenance", "") or "") or None,
        handoff_required=outcome == "HANDOFF_REQUIRED",
        handoff_created=bool(handoff_result is not None and getattr(handoff_result, "created", False)),
        handoff_id=getattr(handoff_result, "request_id", None) if handoff_result is not None else None,
        handoff_status=getattr(handoff_result, "status", None) if handoff_result is not None else None,
        error_code=getattr(result, "error_code", None),
        evaluation_version=str(evaluation.as_dict().get("evaluator_version") or "") or None,
    )


def persist_safety_event(
    db: Session, *, result: Any, conversation_id: str | None, patient_id: str | None, actor_id: str | None
) -> AgentSafetyEvent | None:
    """Best-effort, self-contained (own try/except/rollback/log) -- same
    shape as ``agent_v2_routes._persist_durable_trace``/``agent_judge_
    worker.enqueue_run_judge``, safe to call directly with no extra
    wrapping at the call site. Never raises; a failure here can never break
    the real chat response already returned."""

    try:
        row = build_safety_event(result=result, conversation_id=conversation_id, patient_id=patient_id, actor_id=actor_id)
        if row is None:
            return None
        db.add(row)
        db.commit()
        return row
    except Exception:  # noqa: BLE001 -- observability must never break the real response
        db.rollback()
        logger.exception("Safety event persistence failed for agent_run_id=%s", getattr(result, "agent_run_id", "?"))
        return None


# ---------------------------------------------------------------------------
# Admin reads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HandoffLiveStatus:
    """Live view of a DoctorReviewRequest, joined at read time -- never
    trusted from AgentSafetyEvent's own stale snapshot columns."""

    status: str | None
    resolved: bool
    resolved_at: datetime | None
    time_to_review_seconds: float | None
    assigned_doctor_id: str | None


def _live_handoff_status(db: Session, handoff_id: str | None, *, created_at: datetime | None) -> HandoffLiveStatus:
    if not handoff_id:
        return HandoffLiveStatus(status=None, resolved=False, resolved_at=None, time_to_review_seconds=None, assigned_doctor_id=None)
    request = db.get(DoctorReviewRequest, handoff_id)
    if request is None:
        return HandoffLiveStatus(status=None, resolved=False, resolved_at=None, time_to_review_seconds=None, assigned_doctor_id=None)
    resolved_at = request.answered_at or request.cancelled_at
    ttr = None
    if resolved_at is not None and created_at is not None:
        ttr = max(0.0, (resolved_at - created_at).total_seconds())
    return HandoffLiveStatus(
        status=request.status,
        resolved=request.status in _HANDOFF_RESOLVED_STATUSES,
        resolved_at=resolved_at,
        time_to_review_seconds=ttr,
        assigned_doctor_id=request.assigned_doctor_id,
    )


def _agent_v2_total_runs(db: Session, *, date_from: datetime | None, date_to: datetime | None) -> int:
    """Durable denominator (BUILD-32's own ``agent_run`` table) -- never the
    in-memory ring buffer, so a safety rate here does not depend on it still
    holding the relevant traces (BUILD-34 §10's own restart-durability
    requirement)."""

    stmt = select(func.count()).select_from(AgentRun)
    if date_from is not None:
        stmt = stmt.where(AgentRun.started_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AgentRun.started_at <= date_to)
    return int(db.execute(stmt).scalar_one() or 0)


def safety_metrics_summary(db: Session, *, date_from: datetime | None = None, date_to: datetime | None = None) -> dict[str, Any]:
    """BUILD-34 §3 -- every metric has an explicit denominator; N/A stays a
    distinct status from 0 wherever the underlying count is genuinely
    unmeasured (never the case here -- ``agent_safety_event``/``agent_run``
    are always queryable once migrated, so every metric below is either a
    real number or a real 0, never fabricated)."""

    stmt = select(AgentSafetyEvent)
    if date_from is not None:
        stmt = stmt.where(AgentSafetyEvent.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AgentSafetyEvent.created_at <= date_to)
    events = list(db.execute(stmt).scalars().all())

    total_runs = _agent_v2_total_runs(db, date_from=date_from, date_to=date_to)
    trigger_count = len(events)
    handoff_required = [e for e in events if e.handoff_required]
    handoff_created = [e for e in events if e.handoff_created]
    handoff_failed = [e for e in events if e.handoff_required and not e.handoff_created and e.error_code == "HANDOFF_FAILURE"]

    severity_distribution: dict[str, int] = {}
    reason_code_distribution: dict[str, int] = {}
    for event in events:
        severity_distribution[event.severity] = severity_distribution.get(event.severity, 0) + 1
        reason_code_distribution[event.reason_code] = reason_code_distribution.get(event.reason_code, 0) + 1

    handoff_status_distribution: dict[str, int] = {}
    unresolved_count = 0
    review_seconds: list[float] = []
    for event in handoff_created:
        live = _live_handoff_status(db, event.handoff_id, created_at=event.created_at)
        label = live.status or "UNKNOWN"
        handoff_status_distribution[label] = handoff_status_distribution.get(label, 0) + 1
        if not live.resolved:
            unresolved_count += 1
        if live.time_to_review_seconds is not None:
            review_seconds.append(live.time_to_review_seconds)

    time_to_review_avg_seconds = (sum(review_seconds) / len(review_seconds)) if review_seconds else None

    return {
        "denominator_agent_v2_total_runs": total_runs,
        "safety_trigger_count": trigger_count,
        "safety_trigger_rate": round(trigger_count / total_runs, 4) if total_runs else None,
        "handoff_required_count": len(handoff_required),
        "handoff_required_rate": round(len(handoff_required) / total_runs, 4) if total_runs else None,
        "handoff_created_count": len(handoff_created),
        "handoff_created_rate": round(len(handoff_created) / len(handoff_required), 4) if handoff_required else None,
        "handoff_failure_count": len(handoff_failed),
        "handoff_failure_rate": round(len(handoff_failed) / len(handoff_required), 4) if handoff_required else None,
        "unresolved_handoff_count": unresolved_count,
        "time_to_review_avg_seconds": time_to_review_avg_seconds,
        "time_to_review_sample_count": len(review_seconds),
        "severity_distribution": severity_distribution,
        "reason_code_distribution": reason_code_distribution,
        "handoff_status_distribution": handoff_status_distribution,
    }


def list_safety_events(
    db: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    severity: str | None = None,
    reason_code: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """BUILD-34 §5 -- list view for the metric -> event drill-down. Live
    handoff status joined per row so an Admin never sees a stale snapshot."""

    stmt = select(AgentSafetyEvent).order_by(AgentSafetyEvent.created_at.desc())
    if severity:
        stmt = stmt.where(AgentSafetyEvent.severity == severity)
    if reason_code:
        stmt = stmt.where(AgentSafetyEvent.reason_code == reason_code)

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one() or 0)
    rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())

    items = []
    for event in rows:
        live = _live_handoff_status(db, event.handoff_id, created_at=event.created_at)
        items.append(_event_summary(event, live))
    return items, total


def _event_summary(event: AgentSafetyEvent, live: HandoffLiveStatus) -> dict[str, Any]:
    return {
        "id": event.id,
        "agent_run_id": event.agent_run_id,
        "trace_id": event.trace_id,
        "conversation_id": event.conversation_id,
        "outcome": event.outcome,
        "reason_code": event.reason_code,
        "severity": event.severity,
        "severity_source": event.severity_source,
        "handoff_required": event.handoff_required,
        "handoff_created": event.handoff_created,
        "handoff_id": event.handoff_id,
        "handoff_status_live": live.status,
        "handoff_resolved": live.resolved,
        "handoff_resolved_at": live.resolved_at.isoformat() if live.resolved_at else None,
        "time_to_review_seconds": live.time_to_review_seconds,
        "error_code": event.error_code,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def safety_event_detail(db: Session, event_id: str) -> dict[str, Any] | None:
    """BUILD-34 §5 -- event -> trace/session/handoff/ticket, all real ids
    the Admin UI can follow without copying anything by hand."""

    event = db.get(AgentSafetyEvent, event_id)
    if event is None:
        return None
    live = _live_handoff_status(db, event.handoff_id, created_at=event.created_at)
    summary = _event_summary(event, live)
    summary["assigned_doctor_id"] = live.assigned_doctor_id

    ticket = db.execute(
        select(AgentFeedbackTicket.id).where(AgentFeedbackTicket.agent_run_id == event.agent_run_id)
    ).scalar_one_or_none()
    summary["ticket_id"] = ticket

    judge = db.execute(
        select(AgentRunJudge)
        .where(AgentRunJudge.agent_run_id == event.agent_run_id)
        .order_by(AgentRunJudge.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    summary["judge"] = (
        {
            "judge_status": judge.judge_status,
            "overall_score": judge.overall_score,
            "flags": judge.flags_json,
        }
        if judge is not None
        else None
    )
    return summary


# BUILD-34 §4: Judge is a secondary signal only -- this NEVER writes
# anything, never touches SafetyDecision/AgentSafetyEvent, and never
# triggers a handoff. It is a read-only correlation for Admin review between
# two ALREADY-independent, already-persisted facts: "did Safety trigger on
# this run" (no AgentSafetyEvent row) and "did Judge flag red-flag handling
# as weak" (a real, already-scored numeric dimension -- never a free-text
# flag-string match). Scoped to TRIAGE-path runs for this build: judge_
# rubrics.py's judge-triage rubric is the one rubric with a dimension
# directly analogous to "possible missed acute risk" (`red_flag_handling`);
# extending this to every rubric is a real future widening, not silently
# assumed here.
_MISSED_RISK_DIMENSION = "red_flag_handling"


def judge_suspected_missed_risk_signals(
    db: Session, *, threshold: float = 0.5, limit: int = 50
) -> list[dict[str, Any]]:
    """BUILD-34 §4 -- REVIEW_SUSPECTED_MISSED_RISK. A run is a signal when:
    (1) Judge scored it JUDGE_COMPLETED on the TRIAGE rubric, AND
    (2) its `red_flag_handling` dimension is below `threshold`, AND
    (3) Safety did NOT trigger on this run (no AgentSafetyEvent row) --
    i.e. exactly "deterministic Safety = no escalation, but Judge suspects
    a missed risk" (§4's own example)."""

    # "Safety did NOT trigger" is pushed into the query itself as a real SQL
    # NOT EXISTS anti-join (one round-trip, not N+1 -- portable across both
    # Postgres and the SQLite this module's own tests use). Only the
    # dimension-score threshold stays in Python: `dimension_scores_json` is
    # a JSON column, and comparing a JSON field numerically is not
    # expressible identically across both dialects.
    no_safety_event = ~select(AgentSafetyEvent.id).where(AgentSafetyEvent.agent_run_id == AgentRunJudge.agent_run_id).exists()
    stmt = (
        select(AgentRunJudge)
        .where(
            AgentRunJudge.judge_status == "JUDGE_COMPLETED",
            AgentRunJudge.execution_path == EvaluationPath.TRIAGE.value,
            no_safety_event,
        )
        .order_by(AgentRunJudge.created_at.desc())
        .limit(limit * 4)  # over-fetch before the (Python-side) dimension-score filter, same idiom as a cheap pre-filter
    )
    candidates = list(db.execute(stmt).scalars().all())

    signals: list[dict[str, Any]] = []
    for judge in candidates:
        score = (judge.dimension_scores_json or {}).get(_MISSED_RISK_DIMENSION)
        if score is None or float(score) >= threshold:
            continue
        signals.append(
            {
                "signal": "REVIEW_SUSPECTED_MISSED_RISK",
                "agent_run_id": judge.agent_run_id,
                "trace_id": judge.trace_id,
                "dimension": _MISSED_RISK_DIMENSION,
                "dimension_score": score,
                "judge_flags": judge.flags_json,
                "judge_model": judge.judge_model,
                "created_at": judge.created_at.isoformat() if judge.created_at else None,
            }
        )
        if len(signals) >= limit:
            break
    return signals


def legacy_escalation_count(db: Session, *, date_from: datetime | None = None, date_to: datetime | None = None) -> int:
    """BUILD-34 §6: legacy chat's own count, kept structurally separate from
    ``agent_safety_event`` -- the two tables are written by two entirely
    different code paths (legacy LangGraph chat vs. Agent V2's orchestrator)
    and are never summed together into one number anywhere in this module."""

    stmt = select(func.count()).select_from(Escalation)
    if date_from is not None:
        stmt = stmt.where(Escalation.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Escalation.created_at <= date_to)
    return int(db.execute(stmt).scalar_one() or 0)


__all__ = [
    "HandoffLiveStatus",
    "build_safety_event",
    "classify_severity",
    "judge_suspected_missed_risk_signals",
    "legacy_escalation_count",
    "list_safety_events",
    "persist_safety_event",
    "safety_event_detail",
    "safety_metrics_summary",
]
