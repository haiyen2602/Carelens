"""Doctor Handoff domain: authorized, idempotent clinical-review requests.

This boundary neither determines clinical risk nor selects a doctor from a
general watch list.  Safety supplies the disposition and the patient's
explicit responsible doctor relationship is the only automatic assignment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import Account, DoctorReviewMessage, DoctorReviewRequest, Patient


class HandoffStatus(StrEnum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"
    # BUILD-44: additive -- the takeover lifecycle. ASSIGNED means only that
    # a doctor now owns this request (auto-assigned at creation, or claimed
    # from the general queue -- see claim_doctor_review_request below); the
    # bot keeps answering normally until the SAME doctor explicitly
    # activates (ACTIVE is the only status that suppresses Agent V2 -- see
    # backend/services/agent_doctor_takeover.py). ANSWERED (above) is a
    # SEPARATE, pre-existing "quick answer, no takeover" terminal state
    # (BUILD-10) -- RESOLVED is takeover's own terminal state, reached only
    # from ACTIVE.
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class MessageSenderRole(StrEnum):
    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    SYSTEM = "SYSTEM"


class VerifiedContextSource(StrEnum):
    SAFETY_DOMAIN = "SAFETY_DOMAIN"
    OPERATIONAL_DB = "OPERATIONAL_DB"
    DOCTOR = "DOCTOR"
    DRUG_KNOWLEDGE_V2 = "DRUG_KNOWLEDGE_V2"
    # BUILD-42: mirrors HandoffContextSource.ANSWERABILITY_GATE
    # (backend/agents/v2/handoff.py) -- this domain-layer enum and that
    # agent-facing one are kept in sync by convention (see
    # agent_doctor_handoff.py::_context_ref, the one place a value crosses
    # from one to the other); found missing via real local E2E (a raw
    # ValueError, not caught by any earlier code review), not by inspection.
    ANSWERABILITY_GATE = "ANSWERABILITY_GATE"


class DoctorHandoffError(RuntimeError):
    code = "DOCTOR_HANDOFF_ERROR"


class HandoffNotFoundError(DoctorHandoffError):
    code = "HANDOFF_NOT_FOUND"


class InvalidHandoffTransitionError(DoctorHandoffError):
    code = "INVALID_HANDOFF_TRANSITION"


class DoctorAuthorizationError(DoctorHandoffError):
    code = "DOCTOR_HANDOFF_FORBIDDEN"


class HandoffIdempotencyConflictError(DoctorHandoffError):
    code = "HANDOFF_IDEMPOTENCY_CONFLICT"


@dataclass(frozen=True)
class VerifiedContextRef:
    source: VerifiedContextSource
    reference_id: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.reference_id or not self.provenance:
            raise ValueError("verified context reference requires id and provenance")

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "reference_id": self.reference_id, "provenance": self.provenance}


@dataclass(frozen=True)
class HandoffCreateCommand:
    patient_id: str
    actor_id: str
    patient_question: str
    reason_code: str
    risk_disposition: str
    idempotency_key: str
    verified_context_refs: tuple[VerifiedContextRef, ...]
    conversation_id: str | None = None
    source_message_id: str | None = None

    def __post_init__(self) -> None:
        if not all((self.patient_id, self.actor_id, self.patient_question, self.reason_code, self.risk_disposition, self.idempotency_key)):
            raise ValueError("handoff command requires patient, actor, question, safety disposition, and idempotency key")


@dataclass(frozen=True)
class HandoffResult:
    request: DoctorReviewRequest
    created: bool


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("handoff timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _stable_id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"vmec04:doctor-handoff:{key}"))


def _staged_or_persisted(db: Session, key: str) -> DoctorReviewRequest | None:
    for row in db.new:
        if isinstance(row, DoctorReviewRequest) and row.idempotency_key == key:
            return row
    return db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.idempotency_key == key)
    ).scalar_one_or_none()


def resolve_approved_doctor(db: Session, patient_id: str) -> str | None:
    """Resolve exactly the patient's active, explicitly responsible doctor.

    ``DoctorWatch`` is intentionally not consulted: it is broadly populated
    for alert visibility and is not a treating-doctor/care-team assignment.
    Multiple matching accounts are treated as ambiguous rather than selected.
    """

    patient = db.get(Patient, patient_id)
    if patient is None or not patient.doctor_id:
        return None
    doctor_ids = db.execute(
        select(Account.doctor_id).where(
            Account.role == "doctor",
            Account.status == "active",
            Account.doctor_id == patient.doctor_id,
        )
    ).scalars().all()
    unique = set(doctor_ids)
    return next(iter(unique)) if len(unique) == 1 else None


def _summary(command: HandoffCreateCommand) -> str:
    refs = ", ".join(ref.reference_id for ref in command.verified_context_refs) or "none"
    return (
        f"Safety disposition: {command.risk_disposition}. Reason code: {command.reason_code}. "
        f"Verified context references: {refs}."
    )


def _provenance(refs: Sequence[VerifiedContextRef]) -> list[dict[str, str]]:
    return [ref.as_dict() for ref in refs]


def create_doctor_review_request(
    db: Session, *, command: HandoffCreateCommand, created_at: datetime
) -> HandoffResult:
    """Create one review request, safely returning the durable prior retry."""

    created_at = _utc(created_at)
    existing = _staged_or_persisted(db, command.idempotency_key)
    if existing is not None:
        if existing.patient_id != command.patient_id or existing.created_by_actor_id != command.actor_id:
            raise HandoffIdempotencyConflictError("idempotency key belongs to a different authorized context")
        return HandoffResult(existing, created=False)

    doctor_id = resolve_approved_doctor(db, command.patient_id)
    request = DoctorReviewRequest(
        id=_stable_id(command.idempotency_key),
        patient_id=command.patient_id,
        conversation_id=command.conversation_id,
        source_message_id=command.source_message_id,
        assigned_doctor_id=doctor_id,
        created_by_actor_id=command.actor_id,
        reason_code=command.reason_code,
        risk_disposition=command.risk_disposition,
        patient_question=command.patient_question,
        agent_summary=_summary(command),
        summary_provenance=_provenance(command.verified_context_refs),
        verified_context_refs=_provenance(command.verified_context_refs),
        status=HandoffStatus.ASSIGNED if doctor_id else HandoffStatus.PENDING,
        idempotency_key=command.idempotency_key,
        created_at=created_at,
        assigned_at=created_at if doctor_id else None,
    )
    # The savepoint preserves an enclosing Safety/Agent transaction when a
    # concurrent retry wins the unique idempotency key.
    try:
        with db.begin_nested():
            db.add(request)
            db.flush()
    except IntegrityError:
        existing = _staged_or_persisted(db, command.idempotency_key)
        if existing is None:
            raise
        if existing.patient_id != command.patient_id or existing.created_by_actor_id != command.actor_id:
            raise HandoffIdempotencyConflictError("idempotency key belongs to a different authorized context")
        return HandoffResult(existing, created=False)
    return HandoffResult(request, created=True)


def assign_doctor_review_request(
    db: Session, *, request_id: str, doctor_id: str, assigned_at: datetime
) -> DoctorReviewRequest:
    assigned_at = _utc(assigned_at)
    request = db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HandoffNotFoundError("doctor handoff was not found")
    if request.status != HandoffStatus.PENDING:
        raise InvalidHandoffTransitionError("only pending handoffs can be assigned")
    approved = resolve_approved_doctor(db, request.patient_id)
    if approved is None or approved != doctor_id:
        raise DoctorAuthorizationError("doctor is not the approved treating doctor")
    request.assigned_doctor_id = doctor_id
    request.status = HandoffStatus.ASSIGNED
    request.assigned_at = assigned_at
    db.flush()
    return request


def claim_doctor_review_request(
    db: Session, *, request_id: str, doctor_id: str, claimed_at: datetime
) -> DoctorReviewRequest:
    """Claim a PENDING request from the general doctor queue (BUILD-44).

    Deliberately NOT the same authorization rule as ``assign_doctor_review_
    request`` above: that function requires the caller to be the patient's
    one specific, pre-approved treating doctor (``resolve_approved_
    doctor``) -- but ``create_doctor_review_request`` only ever leaves a
    row PENDING when that function already returned ``None`` (no unique
    treating doctor to auto-assign to). Calling ``assign_doctor_review_
    request`` on a genuinely PENDING row therefore always fails
    authorization, for any doctor, by construction -- confirmed by audit,
    not assumed (see the BUILD-44 report). A real general queue needs a
    DIFFERENT rule: any currently-active doctor account may claim a
    PENDING item (the row-level ``with_for_update()`` lock below, not a
    treating-doctor check, is what prevents two doctors claiming the same
    request -- see SS6 of the report / the concurrency test). Doctor-
    identity verification (real account, role, active status) is the
    caller's job (the route layer), matching every other actor-derived
    check in this codebase -- this function trusts ``doctor_id`` the same
    way ``assign_doctor_review_request`` already does.
    """
    claimed_at = _utc(claimed_at)
    request = db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HandoffNotFoundError("doctor handoff was not found")
    if request.status != HandoffStatus.PENDING:
        raise InvalidHandoffTransitionError("only pending handoffs can be claimed")
    request.assigned_doctor_id = doctor_id
    request.status = HandoffStatus.ASSIGNED
    request.assigned_at = claimed_at
    db.flush()
    return request


def activate_doctor_review_request(
    db: Session, *, request_id: str, doctor_id: str, activated_at: datetime
) -> DoctorReviewRequest:
    """ASSIGNED -> ACTIVE: the moment Agent V2 must stop answering for this
    patient (see backend/services/agent_doctor_takeover.py). Idempotent for
    a repeat call by the SAME already-active doctor (SS26-E) -- a network
    retry or a doctor double-clicking "start" must not raise."""
    activated_at = _utc(activated_at)
    request = db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HandoffNotFoundError("doctor handoff was not found")
    if request.status == HandoffStatus.ACTIVE and request.assigned_doctor_id == doctor_id:
        return request
    if request.status != HandoffStatus.ASSIGNED:
        raise InvalidHandoffTransitionError("only assigned handoffs can be activated")
    if request.assigned_doctor_id != doctor_id:
        raise DoctorAuthorizationError("only the assigned doctor can activate this handoff")
    request.status = HandoffStatus.ACTIVE
    request.activated_at = activated_at
    db.flush()
    return request


def resolve_doctor_review_request(
    db: Session, *, request_id: str, doctor_id: str, resolved_at: datetime
) -> DoctorReviewRequest:
    """ACTIVE -> RESOLVED: bot may resume for this patient on their next
    turn (see agent_doctor_takeover.py) -- no automatic bot message is
    generated here (SS12). Idempotent for a repeat call by the SAME doctor
    who already resolved it (SS26-F)."""
    resolved_at = _utc(resolved_at)
    request = db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HandoffNotFoundError("doctor handoff was not found")
    if request.status == HandoffStatus.RESOLVED and request.resolved_by_doctor_id == doctor_id:
        return request
    if request.status != HandoffStatus.ACTIVE:
        raise InvalidHandoffTransitionError("only active handoffs can be resolved")
    if request.assigned_doctor_id != doctor_id:
        raise DoctorAuthorizationError("only the assigned doctor can resolve this handoff")
    request.status = HandoffStatus.RESOLVED
    request.resolved_at = resolved_at
    request.resolved_by_doctor_id = doctor_id
    db.flush()
    return request


def answer_doctor_review_request(
    db: Session, *, request_id: str, doctor_id: str, answer: str, answered_at: datetime
) -> DoctorReviewRequest:
    answered_at = _utc(answered_at)
    if not answer:
        raise ValueError("doctor answer is required")
    request = db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HandoffNotFoundError("doctor handoff was not found")
    if request.status != HandoffStatus.ASSIGNED:
        raise InvalidHandoffTransitionError("only assigned handoffs can be answered")
    if request.assigned_doctor_id != doctor_id:
        raise DoctorAuthorizationError("only the assigned doctor can answer")
    request.status = HandoffStatus.ANSWERED
    request.doctor_answer = answer
    request.answered_by_doctor_id = doctor_id
    request.answered_at = answered_at
    db.flush()
    return request


def cancel_doctor_review_request(
    db: Session, *, request_id: str, cancelled_at: datetime, doctor_id: str | None = None
) -> DoctorReviewRequest:
    """``doctor_id`` (BUILD-44, optional -- omitted callers get the
    original, pre-BUILD-44 unconditional behavior): when given, a claimed
    request (ASSIGNED/ACTIVE) may only be cancelled by the doctor it is
    assigned to; an unclaimed PENDING request may be cancelled by any
    caller that reached this far (route-level ``require_active_doctor``
    already establishes that). Checked inside the SAME row lock as the
    transition itself -- no separate read-then-act window."""
    cancelled_at = _utc(cancelled_at)
    request = db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HandoffNotFoundError("doctor handoff was not found")
    # BUILD-44: widened to also allow cancelling an ACTIVE takeover (e.g. the
    # doctor determines mid-conversation this was opened in error) -- PENDING/
    # ASSIGNED/ANSWERED semantics from this check are entirely unchanged.
    if request.status not in {HandoffStatus.PENDING, HandoffStatus.ASSIGNED, HandoffStatus.ACTIVE}:
        raise InvalidHandoffTransitionError("only pending, assigned, or active handoffs can be cancelled")
    if (
        doctor_id is not None
        and request.status in {HandoffStatus.ASSIGNED, HandoffStatus.ACTIVE}
        and request.assigned_doctor_id != doctor_id
    ):
        raise DoctorAuthorizationError("only the assigned doctor can cancel a claimed handoff")
    request.status = HandoffStatus.CANCELLED
    request.cancelled_at = cancelled_at
    db.flush()
    return request


_ACTIVE_TAKEOVER_STATUS = HandoffStatus.ACTIVE
# BUILD-44: which statuses represent a queue entry a doctor might still act
# on -- used by the queue listing service, kept here (not duplicated) so the
# route layer and any future caller share one definition.
_OPEN_QUEUE_STATUSES = (HandoffStatus.PENDING, HandoffStatus.ASSIGNED, HandoffStatus.ACTIVE)


def get_active_takeover(db: Session, *, patient_id: str) -> DoctorReviewRequest | None:
    """The one ACTIVE handoff for this patient, if any -- BUILD-42's own
    cross-run dedup is patient-scoped (see agent_doctor_handoff.py), so by
    construction at most one row can be ACTIVE for a given patient at a
    time; this is the single query both the Agent V2 bot-suppression check
    (agent_doctor_takeover.py) and the doctor-facing status view use."""
    return db.execute(
        select(DoctorReviewRequest).where(
            DoctorReviewRequest.patient_id == patient_id,
            DoctorReviewRequest.status == _ACTIVE_TAKEOVER_STATUS,
        )
    ).scalars().first()


def record_doctor_review_message(
    db: Session,
    *,
    handoff_id: str,
    patient_id: str,
    sender_role: MessageSenderRole,
    actor_id: str | None,
    content: str,
    created_at: datetime,
) -> DoctorReviewMessage:
    if not content or not content.strip():
        raise ValueError("message content is required")
    message = DoctorReviewMessage(
        handoff_id=handoff_id,
        patient_id=patient_id,
        sender_role=sender_role.value,
        actor_id=actor_id,
        content=content,
        created_at=_utc(created_at),
    )
    db.add(message)
    db.flush()
    return message


def list_doctor_review_messages(db: Session, *, handoff_id: str) -> list[DoctorReviewMessage]:
    """Server timestamp + row-insertion order only (SS19) -- never a
    client-supplied timestamp."""
    return db.execute(
        select(DoctorReviewMessage)
        .where(DoctorReviewMessage.handoff_id == handoff_id)
        .order_by(DoctorReviewMessage.created_at, DoctorReviewMessage.id)
    ).scalars().all()


__all__ = [
    "DoctorAuthorizationError",
    "DoctorHandoffError",
    "HandoffCreateCommand",
    "HandoffIdempotencyConflictError",
    "HandoffResult",
    "HandoffStatus",
    "InvalidHandoffTransitionError",
    "MessageSenderRole",
    "VerifiedContextRef",
    "VerifiedContextSource",
    "activate_doctor_review_request",
    "answer_doctor_review_request",
    "assign_doctor_review_request",
    "cancel_doctor_review_request",
    "claim_doctor_review_request",
    "create_doctor_review_request",
    "get_active_takeover",
    "list_doctor_review_messages",
    "record_doctor_review_message",
    "resolve_approved_doctor",
    "resolve_doctor_review_request",
]
