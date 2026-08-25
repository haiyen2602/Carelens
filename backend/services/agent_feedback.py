"""BUILD-29: user feedback ticket creation + trace/priority correlation.

BUILD-32: trace/session correlation now queries the durable
``AgentRun``/``AgentRunSpan``/``AgentRunEvaluation`` tables FIRST -- the
in-memory telemetry ring buffer (``backend.services.telemetry``, capped at
200 traces process-wide, reset on every restart/deploy) is now only a
fallback for a trace that predates BUILD-32 or has not been durably flushed
yet, never the source of truth. Agent V2 itself has no durable server-side
*message* log (short-term memory is process-local/ephemeral by design, see
``backend.agents.v2.short_term_memory``), so ``conversation_id``/``trace_id``/
``agent_run_id`` and the reported message text still come from the client --
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

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser
from backend.db.models import AgentFeedbackTicket, AgentRun, AgentRunJudge, AgentRunSpan
from backend.models.schemas import (
    AgentFeedbackCreateRequest,
    AgentFeedbackJudgeOut,
    AgentFeedbackReason,
    AgentFeedbackSessionMessageOut,
    AgentFeedbackTraceSummaryOut,
)
from backend.services.telemetry import get_local_traces, hash_identifier

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
    found: bool
    owned: bool  # True when not found (nothing to contradict) or found+matches
    # Durable AgentRun.intent (or the ring-buffer fallback's own
    # trace.metadata["intent"]) when a real trace was found -- classify_priority's
    # only use of the resolved trace, so this replaces carrying the whole
    # ring-buffer-specific TraceRecord type through this module.
    intent: str | None = None


def verify_trace_ownership(db: Session, trace_id: str | None, *, actor_id: str) -> TraceOwnershipResult:
    """BUILD-32: query the durable ``AgentRun`` table first (by ``trace_id``,
    indexed); fall back to the in-memory ring buffer
    (``backend.services.telemetry``, capped at 200 traces, reset on every
    restart/deploy) only for a trace that predates BUILD-32 or has not been
    durably flushed yet. ``TraceRecord.user_id``/``AgentRun.actor_id`` both
    ultimately trace back to the same authenticated actor -- the ring-buffer
    copy is a one-way hash (``hash_identifier``), the durable column is the
    real id (never exposed outside this authenticated, server-side check).

    Three real outcomes, not two: no ``trace_id`` given, or one neither
    source holds, both come back ``found=False, owned=True`` (nothing to
    verify against, so nothing to reject -- the ticket still carries the
    client's own reported text and remains useful even without a live trace
    to cross-check). Only a trace that *is* found and whose owner does NOT
    match is ``owned=False`` -- that is the one case ``create_ticket`` fails
    closed on. A durable row found with ``actor_id IS NULL`` (a run recorded
    before BUILD-32, or whose durable-persistence step never completed) is
    treated the same as "nothing to verify" rather than a false deny.
    """
    if not trace_id:
        return TraceOwnershipResult(found=False, owned=True)
    try:
        run = db.execute(select(AgentRun).where(AgentRun.trace_id == trace_id)).scalar_one_or_none()
    except Exception as durable_err:  # noqa: BLE001 -- a durable read failure must degrade to the ring-buffer
        # check below, never break ticket creation outright.
        logging.getLogger(__name__).warning("BUILD-32 durable verify_trace_ownership lookup failed: %s", durable_err)
        run = None
    if run is not None:
        owned = run.actor_id is None or run.actor_id == actor_id
        return TraceOwnershipResult(found=True, owned=owned, intent=run.intent)
    for trace in get_local_traces():
        if trace.id == trace_id:
            return TraceOwnershipResult(
                found=True, owned=trace.user_id == hash_identifier(actor_id), intent=trace.metadata.get("intent")
            )
    return TraceOwnershipResult(found=False, owned=True)


def classify_priority(reason: AgentFeedbackReason, *, intent: str | None) -> tuple[str, bool]:
    """Deterministic priority + P0-review flag (BUILD-29 §7). Never based on
    free-text ``user_note`` -- only the structured reason the user picked and
    the real run's own structured signal, same "no NLP guesswork on a
    safety-adjacent decision" principle every other Agent V2 deterministic
    backstop in this project already follows.

    - UNSAFE_OR_INAPPROPRIATE (the user's own explicit "not safe/appropriate"
      pick), or a run whose real intent was ACUTE_DANGER_ESCALATION/
      DOCTOR_REVIEW (the closest deterministic proxy available for "unsafe
      clinical output") -> P0, p0_review_required=True.
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
    if intent in _UNSAFE_SIGNAL_INTENTS:
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
    ownership = verify_trace_ownership(db, payload.trace_id, actor_id=actor.id)
    if not ownership.owned:
        raise CrossPatientTraceError("trace_id does not belong to the reporting account")

    priority, p0_review_required = classify_priority(payload.reason, intent=ownership.intent)
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


def trace_summary_out(
    db: Session, trace_id: str | None, *, actor_id_hint: str | None = None
) -> AgentFeedbackTraceSummaryOut:
    """Sanitized trace detail for a ticket's admin-facing detail view.

    BUILD-32 bugfix: the ring buffer is checked FIRST (same priority as
    ``session_messages``/``/admin/rag/traces/{trace_id}``), durable
    ``AgentRun``/``AgentRunSpan`` only as a fallback for a trace the buffer
    no longer holds (aged out past 200 entries, or from before a restart).
    An earlier version of this function checked durable first -- since
    ``AgentRun`` is written at checkpoint time on essentially every request
    (has been since well before BUILD-32), that made the ring buffer branch
    below nearly unreachable, so every ticket's detail view silently lost
    its real ``final_response``/tool-output/scores (present in the buffer,
    never carried into the durable/sanitized telemetry attributes) even
    while the richer data was still sitting right there in the buffer.

    Honest scope note (still true for the durable fallback branch): the
    durable ``AgentTelemetry`` event pipeline
    (``backend.agents.v2.observability``) deliberately never carries a tool
    call's raw output or the final reply text into telemetry attributes
    (privacy-minimization already built into that module's own sanitizer)
    -- so the durable path's ``tool_results`` carry tool names only (no
    ``output``) and ``final_response`` is ``None``. Not a functional loss
    for the ticket-detail view that is this function's only real caller
    (``admin_feedback_routes.get_ticket``): the actual reported reply text
    is already durable on the ticket row itself
    (``AgentFeedbackTicket.assistant_message``), independent of the trace.
    """
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

    try:
        run = db.execute(select(AgentRun).where(AgentRun.trace_id == trace_id)).scalar_one_or_none()
    except Exception as durable_err:  # noqa: BLE001 -- a durable read failure must degrade, never break the page
        logging.getLogger(__name__).warning("BUILD-32 durable trace_summary_out lookup failed: %s", durable_err)
        run = None
    if run is not None:
        try:
            tool_spans = (
                db.execute(
                    select(AgentRunSpan).where(AgentRunSpan.agent_run_id == run.id, AgentRunSpan.span_type == "TOOL")
                )
                .scalars()
                .all()
            )
        except Exception as durable_err:  # noqa: BLE001
            logging.getLogger(__name__).warning("BUILD-32 durable span lookup failed: %s", durable_err)
            tool_spans = []
        tools = [str(span.metadata_json.get("tool_name") or span.span_name) for span in tool_spans]
        return AgentFeedbackTraceSummaryOut(
            trace_id=trace_id,
            found=True,
            intent=run.intent,
            tools=tools,
            tool_results=[{"name": name} for name in tools],
            safety_outcome=(
                run.status if run.status in ("SAFETY_BLOCKED", "HANDOFF_REQUIRED", "HANDOFF_CREATED") else None
            ),
            handoff_created=run.status == "HANDOFF_CREATED",
            model=run.model,
            latency_ms=run.duration_ms,
            scores={},
            final_response=None,
            status=run.status,
        )
    return AgentFeedbackTraceSummaryOut(trace_id=trace_id, found=False)


def judge_result_out(db: Session, agent_run_id: str | None) -> AgentFeedbackJudgeOut | None:
    """BUILD-33 §11: ticket detail's view of this run's durable Judge V2
    result (backend.db.models.AgentRunJudge), when one exists. ``None`` when
    no row exists (Judge not enabled, run not eligible, or not yet enqueued)
    -- never a fabricated ``JUDGE_PENDING`` placeholder for a run that was
    never actually enqueued. A run with more than one row (a deliberate
    re-evaluation under a different model/rubric/prompt version, see
    ``AgentRunJudge``'s unique index) returns the most recently created one.
    """

    if not agent_run_id:
        return None
    try:
        row = db.execute(
            select(AgentRunJudge)
            .where(AgentRunJudge.agent_run_id == agent_run_id)
            .order_by(AgentRunJudge.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    except Exception as durable_err:  # noqa: BLE001 -- a read failure hides the Judge panel, never breaks the ticket page
        logging.getLogger(__name__).warning("BUILD-33 judge_result_out lookup failed: %s", durable_err)
        return None
    if row is None:
        return None
    return AgentFeedbackJudgeOut(
        judge_status=row.judge_status,
        judge_provider=row.judge_provider,
        judge_model=row.judge_model,
        rubric_name=row.rubric_name,
        rubric_version=row.rubric_version,
        judge_prompt_version=row.judge_prompt_version,
        eligibility_reason=row.eligibility_reason,
        overall_score=row.overall_score,
        dimension_scores=dict(row.dimension_scores_json or {}),
        flags=list(row.flags_json or []),
        confidence=row.confidence,
        failure_reason=row.failure_reason,
        evaluated_at=row.evaluated_at,
    )


_NO_PREVIEW_RETAINED = "(nội dung không còn được lưu tạm -- xem trace để biết thêm chi tiết)"


def session_messages(
    db: Session, conversation_id: str, *, limit: int, offset: int, highlight_trace_id: str | None = None
) -> tuple[list[AgentFeedbackSessionMessageOut], int]:
    """Every turn in this conversation, oldest first, paginated -- the Admin
    session view (BUILD-29 §6).

    BUILD-32: merges the ring buffer (rich -- still carries a real query/
    answer text preview, but capped at 200 traces process-wide and reset on
    every restart/deploy) with durable ``AgentRun`` rows for this
    conversation the buffer no longer holds. Honest scope note: message/reply
    TEXT is deliberately not part of BUILD-32's durable schema (that is
    Conversation/Message's job, out of scope here -- see the BUILD-32 report)
    -- a durable-only turn is still shown (so Admin can see a turn happened,
    when, its status, and its trace_id to drill into further) with a fixed
    placeholder instead of a fabricated preview.
    """
    buffered = {trace.id: trace for trace in get_local_traces() if trace.session_id == conversation_id}
    try:
        durable_runs = (
            db.execute(
                select(AgentRun)
                .where(AgentRun.conversation_id == conversation_id, AgentRun.trace_id.isnot(None))
                .order_by(AgentRun.started_at.asc())
            )
            .scalars()
            .all()
        )
    except Exception as durable_err:  # noqa: BLE001 -- degrade to ring-buffer-only turns, never break this view
        logging.getLogger(__name__).warning("BUILD-32 durable session_messages lookup failed: %s", durable_err)
        durable_runs = []

    entries: list[tuple[datetime, AgentFeedbackSessionMessageOut]] = []
    seen_trace_ids: set[str] = set()
    for run in durable_runs:
        trace_id = run.trace_id
        if trace_id is None or trace_id in seen_trace_ids:
            continue
        seen_trace_ids.add(trace_id)
        buffered_trace = buffered.get(trace_id)
        if buffered_trace is not None:
            entries.append((
                run.started_at,
                AgentFeedbackSessionMessageOut(
                    trace_id=trace_id,
                    timestamp=run.started_at,
                    query_preview=str(buffered_trace.input.get("message", "")) if isinstance(buffered_trace.input, dict) else "",
                    final_answer_preview=str(buffered_trace.output.get("response", "")) if isinstance(buffered_trace.output, dict) else "",
                    status=run.status,
                    is_reported_turn=trace_id == highlight_trace_id,
                ),
            ))
        else:
            entries.append((
                run.started_at,
                AgentFeedbackSessionMessageOut(
                    trace_id=trace_id,
                    timestamp=run.started_at,
                    query_preview=_NO_PREVIEW_RETAINED,
                    final_answer_preview=_NO_PREVIEW_RETAINED,
                    status=run.status,
                    is_reported_turn=trace_id == highlight_trace_id,
                ),
            ))
    # Ring-buffer-only turns (not yet durably flushed, or from before
    # BUILD-32) still appear, richly, same as before this build.
    for trace_id, trace in buffered.items():
        if trace_id in seen_trace_ids:
            continue
        entries.append((
            datetime.fromtimestamp(trace.start_time, tz=UTC),
            AgentFeedbackSessionMessageOut(
                trace_id=trace_id,
                timestamp=datetime.fromtimestamp(trace.start_time, tz=UTC),
                query_preview=str(trace.input.get("message", "")) if isinstance(trace.input, dict) else "",
                final_answer_preview=str(trace.output.get("response", "")) if isinstance(trace.output, dict) else "",
                status=trace.status,
                is_reported_turn=trace_id == highlight_trace_id,
            ),
        ))

    entries.sort(key=lambda pair: pair[0])
    matching = [item for _ts, item in entries]
    total = len(matching)
    items = matching[offset : offset + limit]
    return items, total


__all__ = [
    "CrossPatientTraceError",
    "FeedbackTicketError",
    "TraceOwnershipResult",
    "classify_priority",
    "create_ticket",
    "judge_result_out",
    "session_messages",
    "trace_summary_out",
    "verify_trace_ownership",
]
