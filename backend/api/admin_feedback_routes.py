"""BUILD-29: Admin "Chatbot Issues / User Reports" ticket explorer.

Every route here is admin-only (``require_role("admin")`` -- the same
BUILD-29 security fix applied to ``rag_monitoring_routes.py``). BUILD-32:
ticket detail/session now correlate against the durable ``AgentRun``/
``AgentRunSpan`` tables first (``backend.services.agent_feedback``), with the
in-memory Agent V2 telemetry ring buffer only as a fallback for a trace that
predates BUILD-32 or has not been durably flushed yet -- still no separate
Trace Explorer built here, per the original BUILD-29 instruction.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import require_role
from backend.db.base import get_db
from backend.db.models import AgentFeedbackTicket
from backend.models.schemas import (
    AgentFeedbackSessionOut,
    AgentFeedbackTicketDetailOut,
    AgentFeedbackTicketListOut,
    AgentFeedbackTicketOut,
    AgentFeedbackTicketUpdateRequest,
)
from backend.services.agent_feedback import (
    evaluation_result_out,
    judge_result_out,
    safety_result_out,
    session_messages,
    trace_summary_out,
)

admin_feedback_router = APIRouter(prefix="/admin/tickets", tags=["admin-feedback-tickets"])

_require_admin = require_role("admin")


@admin_feedback_router.get("", response_model=AgentFeedbackTicketListOut)
def list_tickets(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    reason: str | None = Query(default=None),
    chatbot_version: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AgentFeedbackTicketListOut:
    stmt = select(AgentFeedbackTicket)
    if status_filter:
        stmt = stmt.where(AgentFeedbackTicket.status == status_filter)
    if priority:
        stmt = stmt.where(AgentFeedbackTicket.priority == priority)
    if reason:
        stmt = stmt.where(AgentFeedbackTicket.reason == reason)
    if chatbot_version:
        stmt = stmt.where(AgentFeedbackTicket.chatbot_version == chatbot_version)
    if date_from:
        stmt = stmt.where(AgentFeedbackTicket.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(AgentFeedbackTicket.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))

    total = len(db.execute(stmt).scalars().all())
    rows = (
        db.execute(stmt.order_by(AgentFeedbackTicket.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return AgentFeedbackTicketListOut(
        items=[AgentFeedbackTicketOut.model_validate(row) for row in rows], total=total, limit=limit, offset=offset
    )


def _get_ticket_or_404(db: Session, ticket_id: str) -> AgentFeedbackTicket:
    ticket = db.get(AgentFeedbackTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay ticket")
    return ticket


@admin_feedback_router.get("/{ticket_id}", response_model=AgentFeedbackTicketDetailOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db), _admin=Depends(_require_admin)) -> AgentFeedbackTicketDetailOut:
    """Ticket -> its exact conversation/message -> its exact trace (BUILD-29
    §5): the trace summary here is intentionally the same sanitized shape as
    GET /admin/rag/traces/{trace_id} (intent, tools, sanitized tool results,
    Safety/Handoff outcome, model, latency, scores, final response) -- never
    the model's own hidden chain-of-thought, which Agent V2's telemetry never
    records to begin with."""
    ticket = _get_ticket_or_404(db, ticket_id)
    trace = trace_summary_out(db, ticket.trace_id)
    judge = judge_result_out(db, ticket.agent_run_id)
    # BUILD-36: completes the correlation chain the spec's own §16 asks for
    # (reported message -> session -> trace -> Evaluation V2 -> Judge ->
    # Safety/Handoff) -- both were previously entirely absent from ticket
    # detail (Evaluation V2 was never read here at all; Safety was only a
    # coarse status string inferred from AgentRun.status, never the real
    # AgentSafetyEvent row).
    evaluation = evaluation_result_out(db, ticket.agent_run_id)
    safety = safety_result_out(db, ticket.agent_run_id)
    return AgentFeedbackTicketDetailOut(
        ticket=AgentFeedbackTicketOut.model_validate(ticket), trace=trace, judge=judge, evaluation=evaluation, safety=safety
    )


@admin_feedback_router.get("/{ticket_id}/session", response_model=AgentFeedbackSessionOut)
def get_ticket_session(
    ticket_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AgentFeedbackSessionOut:
    """BUILD-29 §6: turns before/after the reported one, same
    ``conversation_id`` -- bounded/paginated (never the full unbounded
    history), each entry carries its own ``trace_id`` for the Admin to click
    through to the existing Trace Explorer. Sourced from the telemetry
    buffer, so a turn from before the last deploy (or evicted past the
    buffer's 200-entry cap) will not appear even though it really happened --
    a pre-existing limitation of the buffer this feature deliberately reuses
    rather than replaces."""
    ticket = _get_ticket_or_404(db, ticket_id)
    items, total = session_messages(
        db, ticket.conversation_id, limit=limit, offset=offset, highlight_trace_id=ticket.trace_id
    )
    return AgentFeedbackSessionOut(conversation_id=ticket.conversation_id, items=items, total=total, limit=limit, offset=offset)


@admin_feedback_router.patch("/{ticket_id}", response_model=AgentFeedbackTicketOut)
def update_ticket(
    ticket_id: str,
    payload: AgentFeedbackTicketUpdateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
) -> AgentFeedbackTicketOut:
    """BUILD-29 §4/§5: status/priority/admin_note -- the only fields an Admin
    can change after creation. ``resolved_at`` is set/cleared here purely as
    a side effect of the status transition, not a separately-settable field
    (avoids an Admin marking something "resolved" at a timestamp that
    doesn't match its actual status)."""
    ticket = _get_ticket_or_404(db, ticket_id)
    if payload.status is not None:
        ticket.status = payload.status
        if payload.status in ("FIXED", "CLOSED", "WONT_FIX"):
            if ticket.resolved_at is None:
                ticket.resolved_at = datetime.now(timezone.utc)
        else:
            ticket.resolved_at = None
    if payload.priority is not None:
        ticket.priority = payload.priority
    if payload.admin_note is not None:
        ticket.admin_note = payload.admin_note
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return AgentFeedbackTicketOut.model_validate(ticket)
