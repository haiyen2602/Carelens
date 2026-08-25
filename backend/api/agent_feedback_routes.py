"""BUILD-29: patient-facing "Báo cáo câu trả lời" endpoint.

Deliberately its own tiny router (not folded into agent_v2_routes.py) --
this is a report ABOUT a prior Agent V2 turn, not a new orchestration call,
and does not touch AGENT_RUNTIME_ENABLED/canary/rollout gating at all: a
patient can report a bad reply from before that gate ever changes, and this
endpoint's own availability is not a rollout decision.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.rate_limit import SlidingWindowRateLimiter
from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.models.schemas import AgentFeedbackCreateRequest, AgentFeedbackTicketOut
from backend.services.agent_feedback import CrossPatientTraceError, create_ticket
from backend.services.agent_judge_worker import enqueue_ticket_judge

agent_feedback_router = APIRouter()

_default_limiter: SlidingWindowRateLimiter | None = None


def _get_default_limiter() -> SlidingWindowRateLimiter:
    """Lazy singleton, same pattern as backend/api/rate_limit.py's own --
    reads settings on first call, not at import time, so tests can override
    settings first."""
    global _default_limiter
    if _default_limiter is None:
        settings = get_settings()
        _default_limiter = SlidingWindowRateLimiter(
            max_requests=settings.agent_feedback_rate_limit_max_requests,
            window_seconds=settings.agent_feedback_rate_limit_window_seconds,
        )
    return _default_limiter


def reset_feedback_rate_limiter_for_tests() -> None:
    """CHI dung trong test - xem backend/api/rate_limit.py's twin for why."""
    global _default_limiter
    _default_limiter = None


@agent_feedback_router.post("/agent/v2/feedback", response_model=AgentFeedbackTicketOut, status_code=status.HTTP_201_CREATED)
def submit_feedback_report(
    payload: AgentFeedbackCreateRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
) -> AgentFeedbackTicketOut:
    """BUILD-29 §2/§3: a patient reporting one of their OWN assistant
    replies. ``actor.id``/``actor.patient_id`` are the only identity this
    endpoint ever trusts -- everything else (conversation_id/trace_id/
    agent_run_id/message text) comes from the request body, exactly as the
    client already received/rendered it, per this module's own docstring and
    ``backend.services.agent_feedback``'s.

    Only role=="patient" reports their own chat today (BUILD-29's own UI
    context is the patient assistant chat) -- a doctor/caregiver/admin
    caller gets a plain 403, not a silently-accepted report attributed to
    someone else.
    """
    if actor.role != "patient" or not actor.patient_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chi benh nhan moi co the bao cao cau tra loi cua chinh minh")

    _get_default_limiter().check(actor.id)

    try:
        ticket, created = create_ticket(db, actor=actor, payload=payload)
    except CrossPatientTraceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="trace_id khong thuoc ve tai khoan nay") from exc
    except Exception:
        db.rollback()
        raise

    db.commit()

    # BUILD-33 §3/§11: a reported turn is always Judge-eligible (never
    # subject to sampling) -- best-effort, its own commit, and only for a
    # genuinely NEW ticket (a duplicate/idempotent resubmit already has one
    # enqueued, or is already covered by AgentRunJudge's own unique index).
    if created:
        enqueue_ticket_judge(db, ticket=ticket, settings=get_settings())

    return AgentFeedbackTicketOut.model_validate(ticket)
