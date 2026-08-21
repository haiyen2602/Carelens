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

from backend.db.models import Account, DoctorReviewRequest, Patient


class HandoffStatus(StrEnum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"


class VerifiedContextSource(StrEnum):
    SAFETY_DOMAIN = "SAFETY_DOMAIN"
    OPERATIONAL_DB = "OPERATIONAL_DB"
    DOCTOR = "DOCTOR"
    DRUG_KNOWLEDGE_V2 = "DRUG_KNOWLEDGE_V2"


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


def cancel_doctor_review_request(db: Session, *, request_id: str, cancelled_at: datetime) -> DoctorReviewRequest:
    cancelled_at = _utc(cancelled_at)
    request = db.execute(
        select(DoctorReviewRequest).where(DoctorReviewRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise HandoffNotFoundError("doctor handoff was not found")
    if request.status not in {HandoffStatus.PENDING, HandoffStatus.ASSIGNED}:
        raise InvalidHandoffTransitionError("only pending or assigned handoffs can be cancelled")
    request.status = HandoffStatus.CANCELLED
    request.cancelled_at = cancelled_at
    db.flush()
    return request


__all__ = [
    "DoctorAuthorizationError",
    "DoctorHandoffError",
    "HandoffCreateCommand",
    "HandoffIdempotencyConflictError",
    "HandoffResult",
    "HandoffStatus",
    "InvalidHandoffTransitionError",
    "VerifiedContextRef",
    "VerifiedContextSource",
    "answer_doctor_review_request",
    "assign_doctor_review_request",
    "cancel_doctor_review_request",
    "create_doctor_review_request",
    "resolve_approved_doctor",
]
