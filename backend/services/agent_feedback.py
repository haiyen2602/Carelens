"""BUILD-29: user feedback ticket creation + trace/priority correlation.

Reuses the existing Agent V2 telemetry buffer (``backend.services.telemetry``)
for trace correlation -- deliberately does NOT build a new persistence layer
or a second Trace Explorer. Agent V2 itself has no durable server-side
message log (short-term memory is process-local/ephemeral by design, see
``backend.agents.v2.short_term_memory``), so ``conversation_id``/``trace_id``/
``agent_run_id`` and the reported message text all come from the client --
exactly what it already received back from the real
``/agent/v2/orchestrate`` call being reported. ``actor_id``/``patient_id``
are the one thing NEVER taken from the client: always bound here from the
authenticated ``CurrentUser``.

Idempotency mirrors ``backend.services.agent_idempotency``'s savepoint +
unique-index + ``IntegrityError`` pattern (see
``AgentFeedbackTicket.uq_agent_feedback_ticket_actor_run_reason``): a
double-click or retried submit for the same (actor, assistant turn, reason)
returns the existing ticket rather than inserting a duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser
from backend.db.models import AgentFeedbackTicket
from backend.models.schemas import (
    AgentFeedbackCreateRequest,
    AgentFeedbackReason,
    AgentFeedbackSessionMessageOut,
    AgentFeedbackTraceSummaryOut,
)
from backend.services.telemetry import TraceRecord, get_local_traces, hash_identifier

_MAX_CLAIM_ATTEMPTS = 3

# BUILD-28's schedule composer and the router's own ACUTE_DANGER_ESCALATION/
# DOCTOR_REVIEW intents are the two real, deterministic Agent V2 signals
# closest to "unsafe clinical output" -- see classify_priority's own
# docstring for the honest limits of this (no free-text/NLP detection of
# "cross-patient"/"data integrity" concerns; those are also structurally
# prevented at submission time by verify_trace_ownership below, so a ticket
# claiming to be about a mismatched trace never gets created at all).
_UNSAFE_SIGNAL_INTENTS = frozenset({"ACUTE_DANGER_ESCALATION", "DOCTOR_REVIEW"})


class FeedbackTicketError(RuntimeError):
    """Base class; callers map subclasses to specific HTTP statuses."""


class CrossPatientTraceError(FeedbackTicketError):
    """The supplied trace_id exists in the telemetry buffer but belongs to a
    different account -- fail closed (BUILD-29 §10's explicit "cross-patient
    report attempt -> denied" requirement), never silently accepted."""


@dataclass(frozen=True)
class TraceOwnershipResult:
    trace: TraceRecord | None
    found: bool
    owned: bool  # True when not found (nothing to contradict) or found+matches


def verify_trace_ownership(trace_id: str | None, *, actor_id: str) -> TraceOwnershipResult:
    """Look up ``trace_id`` in the same in-memory buffer ``/admin/rag/traces``
    reads. ``TraceRecord.user_id`` is already a one-way hash of the real
    actor id (``hash_identifier``, set in ``TelemetryService.create_trace``)
    -- recompute the same hash here rather than ever storing/comparing a raw
    account id against it.

    Three real outcomes, not two: no ``trace_id`` given, or one the buffer no
    longer holds (BUILD-25's documented ring-buffer limit -- at most the last
    200 traces process-wide, reset on every deploy) both come back
    ``found=False, owned=True`` (nothing to verify against, so nothing to
    reject -- the ticket still carries the client's own reported text and
    remains useful even without a live trace to cross-check). Only a trace
    that *is* found and whose owner hash does NOT match is ``owned=False`` --
    that is the one case ``create_ticket`` fails closed on.
    """
    if not trace_id:
        return TraceOwnershipResult(trace=None, found=False, owned=True)
    for trace in get_local_traces():
        if trace.id == trace_id:
            return TraceOwnershipResult(trace=trace, found=True, owned=trace.user_id == hash_identifier(actor_id))
    return TraceOwnershipResult(trace=None, found=False, owned=True)


def classify_priority(reason: AgentFeedbackReason, *, trace: TraceRecord | None) -> tuple[str, bool]:
    """Deterministic priority + P0-review flag (BUILD-29 §7). Never based on
    free-text ``user_note`` -- only the structured reason the user picked and
    the real trace's own structured signals, same "no NLP guesswork on a
    safety-adjacent decision" principle every other Agent V2 deterministic
    backstop in this project already follows.

    - UNSAFE_OR_INAPPROPRIATE (the user's own explicit "not safe/appropriate"
      pick), or a trace whose real intent was ACUTE_DANGER_ESCALATION/
      DOCTOR_REVIEW (the closest deterministic proxy this telemetry buffer
      has for "unsafe clinical output") -> P0, p0_review_required=True.
    - WRONG_MEDICATION_INFO -> P1 (a factual medication/schedule error is
      more urgent than a generic wrong answer, less urgent than a safety one).
    - WRONG_ANSWER / NOT_UNDERSTOOD / TECHNICAL_ERROR -> P2.
    - OTHER -> P3.

    Known, deliberate limitation: "cross-patient/auth issue" and "data
    integrity" (also named in §7) are not auto-classified from free text
    here -- cross-patient attribution is instead structurally prevented at
    submission time (see ``verify_trace_ownership``/``CrossPatientTraceError``
    above), and a genuine data-integrity report currently lands as whatever
    reason the user picked (most likely OTHER or WRONG_MEDICATION_INFO) --
    an Admin reviewing the ticket's real linked trace is still the authority,
    same as for any other P1-and-below ticket.
    """
    if reason == "UNSAFE_OR_INAPPROPRIATE":
        return "P0", True
    if trace is not None and trace.metadata.get("intent") in _UNSAFE_SIGNAL_INTENTS:
        return "P0", True
    if reason == "WRONG_MEDICATION_INFO":
        return "P1", False
    if reason in ("WRONG_ANSWER", "NOT_UNDERSTOOD", "TECHNICAL_ERROR"):
        return "P2", False
    return "P3", False


def _existing_ticket(db: Session, *, actor_id: str, agent_run_id: str, reason: str) -> AgentFeedbackTicket | None:
    for row in db.new:
        if (
            isinstance(row, AgentFeedbackTicket)
            and row.actor_id == actor_id
            and row.agent_run_id == agent_run_id
            and row.reason == reason
        ):
            return row
    return db.execute(
        select(AgentFeedbackTicket).where(
            AgentFeedbackTicket.actor_id == actor_id,
            AgentFeedbackTicket.agent_run_id == agent_run_id,
            AgentFeedbackTicket.reason == reason,
        )
    ).scalar_one_or_none()


def create_ticket(
    db: Session, *, actor: CurrentUser, payload: AgentFeedbackCreateRequest, now: datetime | None = None
) -> tuple[AgentFeedbackTicket, bool]:
    """Create (or idempotently return) a feedback ticket for ``actor``'s own
    conversation. Returns ``(ticket, created)`` -- ``created=False`` means an
    identical prior submission's ticket was returned instead of a duplicate.

    Raises ``CrossPatientTraceError`` (caller maps to 403) when the supplied
    ``trace_id`` is found in the telemetry buffer but belongs to a different
    account -- see ``verify_trace_ownership``.
    """
    at = (now or datetime.now(UTC)).astimezone(UTC)
    ownership = verify_trace_ownership(payload.trace_id, actor_id=actor.id)
    if not ownership.owned:
        raise CrossPatientTraceError("trace_id does not belong to the reporting account")

    priority, p0_review_required = classify_priority(payload.reason, trace=ownership.trace)
    patient_id = actor.patient_id or actor.id

    for _attempt in range(_MAX_CLAIM_ATTEMPTS):
        existing = _existing_ticket(db, actor_id=actor.id, agent_run_id=payload.agent_run_id, reason=payload.reason)
        if existing is not None:
            return existing, False

        row = AgentFeedbackTicket(
            actor_id=actor.id,
            patient_id=patient_id,
            conversation_id=payload.conversation_id,
            trace_id=payload.trace_id,
            agent_run_id=payload.agent_run_id,
            user_message=payload.user_message,
            assistant_message=payload.assistant_message,
            reason=payload.reason,
            user_note=payload.user_note,
            chatbot_version="agent-v2",
            status="OPEN",
            priority=priority,
            p0_review_required=p0_review_required,
            admin_note=None,
            created_at=at,
            updated_at=at,
            resolved_at=None,
        )
        # Savepoint mirrors backend.services.agent_idempotency.claim_or_replay:
        # a genuinely concurrent double-submit blocks on the DB-level unique
        # index until the first request's outer transaction commits, then
        # this branch re-reads and returns that row instead of erroring.
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            continue
        return row, True

    raise FeedbackTicketError("could not create feedback ticket after retrying contention")


def trace_summary_out(trace_id: str | None, *, actor_id_hint: str | None = None) -> AgentFeedbackTraceSummaryOut:
    """Sanitized trace detail for a ticket's admin-facing detail view --
    same fields already exposed by GET /admin/rag/traces/{trace_id}, never
    hidden chain-of-thought (Agent V2's telemetry never records that to
    begin with -- see module docstring)."""
    if not trace_id:
        return AgentFeedbackTraceSummaryOut(trace_id="", found=False)
    for trace in get_local_traces():
        if trace.id != trace_id:
            continue
        tools = [obs.name.removeprefix("tool.") for obs in trace.observations if obs.name.startswith("tool.")]
        tool_results = [
            {"name": obs.name.removeprefix("tool."), "output": obs.output}
            for obs in trace.observations
            if obs.name.startswith("tool.")
        ]
        safety_outcome = next(
            (obs.output.get("outcome") for obs in trace.observations if obs.name == "safety.decision" and isinstance(obs.output, dict)),
            None,
        )
        handoff_created = any(obs.name == "handoff.created" for obs in trace.observations)
        final_response = trace.output.get("response") if isinstance(trace.output, dict) else None
        return AgentFeedbackTraceSummaryOut(
            trace_id=trace_id,
            found=True,
            intent=trace.metadata.get("intent"),
            tools=tools,
            tool_results=tool_results,
            safety_outcome=safety_outcome,
            handoff_created=handoff_created,
            model=trace.metadata.get("model"),
            latency_ms=trace.duration_ms,
            scores=dict(trace.scores),
            final_response=final_response,
            status=trace.status,
        )
    return AgentFeedbackTraceSummaryOut(trace_id=trace_id, found=False)


def session_messages(conversation_id: str, *, limit: int, offset: int, highlight_trace_id: str | None = None) -> tuple[list[AgentFeedbackSessionMessageOut], int]:
    """Every trace whose ``session_id`` matches ``conversation_id``, oldest
    first, paginated -- the Admin session view (BUILD-29 §6). Sourced from
    the SAME telemetry buffer as ``/admin/rag/traces``, subject to the same
    process-local/200-entry ring-buffer limitation (a turn from before the
    last deploy, or beyond the buffer's capacity, will not appear here even
    though it really happened)."""
    matching = sorted(
        (trace for trace in get_local_traces() if trace.session_id == conversation_id),
        key=lambda t: t.start_time,
    )
    total = len(matching)
    page = matching[offset : offset + limit]
    items = [
        AgentFeedbackSessionMessageOut(
            trace_id=trace.id,
            timestamp=datetime.fromtimestamp(trace.start_time, tz=UTC),
            query_preview=str(trace.input.get("message", "")) if isinstance(trace.input, dict) else "",
            final_answer_preview=str(trace.output.get("response", "")) if isinstance(trace.output, dict) else "",
            status=trace.status,
            is_reported_turn=trace.id == highlight_trace_id,
        )
        for trace in page
    ]
    return items, total


__all__ = [
    "CrossPatientTraceError",
    "FeedbackTicketError",
    "TraceOwnershipResult",
    "classify_priority",
    "create_ticket",
    "session_messages",
    "trace_summary_out",
    "verify_trace_ownership",
]
