"""BUILD-44: Doctor Chat Queue & Takeover.

Consumes the handoff decisions BUILD-42/43 already produce
(``DoctorReviewRequest``, created by ``backend.services.doctor_handoff``'s
existing ``create_doctor_review_request`` -- Safety-sourced or
Answerability-Gate-sourced, both untouched here). This module adds the
doctor-facing workflow on top: queue -> claim -> activate -> converse ->
resolve. No Safety/Answerability semantics are changed by this file.

Every route is ``require_role("doctor")`` plus ``require_active_doctor``
(a fresh, per-request DB check that the account is still real and active
-- never trusted from JWT claims alone, matching ``resolve_approved_
doctor``'s own discipline). Patient identity/authorization is derived
exclusively from the authenticated principal, never from the request body.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents.tools.chat_history_tool import get_chat_history_for_display
from backend.agents.v2.answerability import handoff_type_for
from backend.api.security import CurrentUser, get_current_user, require_role
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import DoctorReviewImageAttachment, DoctorReviewMessage, DoctorReviewRequest, Patient
from backend.models.schemas import (
    DoctorReviewDetailOut,
    DoctorReviewMessageOut,
    DoctorReviewQueueItemOut,
    DoctorReviewQueueResponse,
    DoctorReviewSendMessageRequest,
    PatientHandoffStatusOut,
)
from backend.services.agent_authorization import require_agent_patient_access
from backend.services.agent_doctor_takeover import get_active_takeover, require_active_doctor
from backend.services.doctor_handoff import (
    DOCTOR_CONVERSATION_STOP_MESSAGE,
    DoctorAuthorizationError,
    DoctorHandoffError,
    HandoffNotFoundError,
    HandoffStatus,
    InvalidHandoffTransitionError,
    activate_doctor_review_request,
    cancel_doctor_review_request,
    claim_doctor_review_request,
    list_doctor_review_messages,
    resolve_doctor_review_request,
    send_active_doctor_message,
    stop_active_doctor_review_request,
)
from backend.services.drug_image_chat import private_takeover_upload_path

doctor_review_router = APIRouter(prefix="/doctor/reviews", tags=["doctor-review"])
patient_handoff_router = APIRouter(tags=["agent-v2-handoff-status"])

_require_doctor = require_role("doctor")
_OPEN_STATUSES = (HandoffStatus.PENDING, HandoffStatus.ASSIGNED, HandoffStatus.ACTIVE)

# BUILD-44 SS4: Safety-sourced handoffs sort ahead of Uncertainty/User-
# request ones -- the Safety Domain already made that urgency call
# upstream (see answerability.py); this is a display-ordering choice, not
# a NEW medical-urgency judgment invented here.
_TYPE_SORT_RANK = {"SAFETY": 0, "USER_REQUEST": 1, "UNCERTAINTY": 2}


def _handoff_type(row: DoctorReviewRequest) -> str:
    return handoff_type_for(reason_code=row.reason_code, risk_disposition=row.risk_disposition).value


def _patient_name(db: Session, patient_id: str) -> str:
    patient = db.get(Patient, patient_id)
    return patient.full_name if patient is not None else patient_id


def _queue_item(db: Session, row: DoctorReviewRequest) -> DoctorReviewQueueItemOut:
    return DoctorReviewQueueItemOut(
        handoff_id=row.id,
        patient_id=row.patient_id,
        patient_name=_patient_name(db, row.patient_id),
        conversation_id=row.conversation_id,
        handoff_type=_handoff_type(row),
        reason_code=row.reason_code,
        risk_disposition=row.risk_disposition,
        status=row.status,
        patient_question=row.patient_question,
        created_at=row.created_at,
        assigned_doctor_id=row.assigned_doctor_id,
        assigned_at=row.assigned_at,
        activated_at=row.activated_at,
        resolved_at=row.resolved_at,
    )


def _detail(db: Session, row: DoctorReviewRequest) -> DoctorReviewDetailOut:
    messages = list_doctor_review_messages(db, handoff_id=row.id)
    chat_history = get_chat_history_for_display(db, row.patient_id)
    attachments = {
        item.message_id: item.id
        for item in db.scalars(
            select(DoctorReviewImageAttachment).where(DoctorReviewImageAttachment.handoff_id == row.id)
        )
    }
    return DoctorReviewDetailOut(
        handoff_id=row.id,
        patient_id=row.patient_id,
        patient_name=_patient_name(db, row.patient_id),
        conversation_id=row.conversation_id,
        handoff_type=_handoff_type(row),
        reason_code=row.reason_code,
        risk_disposition=row.risk_disposition,
        status=row.status,
        patient_question=row.patient_question,
        created_at=row.created_at,
        assigned_doctor_id=row.assigned_doctor_id,
        assigned_at=row.assigned_at,
        activated_at=row.activated_at,
        resolved_at=row.resolved_at,
        resolved_by_doctor_id=row.resolved_by_doctor_id,
        messages=[
            DoctorReviewMessageOut(
                id=m.id,
                sender_role=m.sender_role,
                actor_id=m.actor_id,
                content=m.content,
                created_at=m.created_at,
                image_attachment_id=attachments.get(m.id),
            )
            for m in messages
        ],
        chat_history=chat_history,
    )


def _get_or_404(db: Session, handoff_id: str) -> DoctorReviewRequest:
    row = db.get(DoctorReviewRequest, handoff_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay yeu cau")
    return row


def _map_domain_error(exc: DoctorHandoffError) -> HTTPException:
    if isinstance(exc, HandoffNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay yeu cau")
    if isinstance(exc, DoctorAuthorizationError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen tren yeu cau nay")
    if isinstance(exc, InvalidHandoffTransitionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or "Trang thai khong hop le")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc) or "Yeu cau khong hop le")


@doctor_review_router.get("", response_model=DoctorReviewQueueResponse)
def list_queue(
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(_require_doctor),
    status_filter: str | None = Query(default=None, alias="status"),
    handoff_type: str | None = Query(default=None),
    assigned_to_me: bool = Query(default=False),
) -> DoctorReviewQueueResponse:
    doctor_id = require_active_doctor(db, actor)
    stmt = select(DoctorReviewRequest)
    if status_filter:
        stmt = stmt.where(DoctorReviewRequest.status == status_filter)
    else:
        stmt = stmt.where(DoctorReviewRequest.status.in_([s.value for s in _OPEN_STATUSES]))
    if assigned_to_me:
        stmt = stmt.where(DoctorReviewRequest.assigned_doctor_id == doctor_id)
    rows = db.execute(stmt).scalars().all()
    items = [_queue_item(db, row) for row in rows]
    if handoff_type:
        items = [item for item in items if item.handoff_type == handoff_type]
    items.sort(key=lambda item: (_TYPE_SORT_RANK.get(item.handoff_type, 99), item.created_at))
    return DoctorReviewQueueResponse(items=items, total=len(items))


@doctor_review_router.get("/{handoff_id}", response_model=DoctorReviewDetailOut)
def get_review_detail(
    handoff_id: str, db: Session = Depends(get_db), actor: CurrentUser = Depends(_require_doctor)
) -> DoctorReviewDetailOut:
    require_active_doctor(db, actor)
    row = _get_or_404(db, handoff_id)
    return _detail(db, row)


@doctor_review_router.get("/{handoff_id}/image-attachments/{attachment_id}")
def get_private_image_attachment(
    handoff_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(_require_doctor),
) -> FileResponse:
    """Serve a B-07 image only to the real doctor assigned to this handoff."""

    doctor_id = require_active_doctor(db, actor)
    handoff = _get_or_404(db, handoff_id)
    if handoff.assigned_doctor_id != doctor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen tren tep rieng tu nay")
    attachment = db.get(DoctorReviewImageAttachment, attachment_id)
    if attachment is None or attachment.handoff_id != handoff_id or attachment.patient_id != handoff.patient_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay tep rieng tu")
    if attachment.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Tep rieng tu da het han")
    path = private_takeover_upload_path(
        storage_dir=Path(get_settings().drug_image_chat_doctor_storage_dir), storage_key=attachment.storage_key
    )
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay tep rieng tu")
    return FileResponse(path, media_type=attachment.mime_type, filename="patient-package-image")


@doctor_review_router.post("/{handoff_id}/claim", response_model=DoctorReviewDetailOut)
def claim_review(
    handoff_id: str, db: Session = Depends(get_db), actor: CurrentUser = Depends(_require_doctor)
) -> DoctorReviewDetailOut:
    doctor_id = require_active_doctor(db, actor)
    try:
        row = claim_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, claimed_at=datetime.now(UTC))
        db.commit()
    except DoctorHandoffError as exc:
        db.rollback()
        raise _map_domain_error(exc) from exc
    return _detail(db, row)


@doctor_review_router.post("/{handoff_id}/activate", response_model=DoctorReviewDetailOut)
def activate_review(
    handoff_id: str, db: Session = Depends(get_db), actor: CurrentUser = Depends(_require_doctor)
) -> DoctorReviewDetailOut:
    doctor_id = require_active_doctor(db, actor)
    try:
        row = activate_doctor_review_request(
            db, request_id=handoff_id, doctor_id=doctor_id, activated_at=datetime.now(UTC)
        )
        db.commit()
    except DoctorHandoffError as exc:
        db.rollback()
        raise _map_domain_error(exc) from exc
    return _detail(db, row)


@doctor_review_router.post("/{handoff_id}/messages", response_model=DoctorReviewDetailOut)
def send_doctor_message(
    handoff_id: str,
    request: DoctorReviewSendMessageRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(_require_doctor),
) -> DoctorReviewDetailOut:
    doctor_id = require_active_doctor(db, actor)
    # PR #134 review: the status/assignment check and the message insert
    # must happen under the SAME row lock, not a plain db.get() read
    # followed by a separate write -- a concurrent resolve (itself
    # correctly with_for_update()-locked) could otherwise commit in
    # between and leave an orphaned message on an already-RESOLVED
    # handoff. Confirmed via a real reproduction before this fix; see
    # send_active_doctor_message's own docstring. SS24: doctor text is
    # human-authored -- persisted verbatim, never rewritten through the
    # Main Model before delivery.
    try:
        message = send_active_doctor_message(
            db, request_id=handoff_id, doctor_id=doctor_id, actor_id=actor.id,
            content=request.content, created_at=datetime.now(UTC),
        )
    except DoctorHandoffError as exc:
        db.rollback()
        raise _map_domain_error(exc) from exc
    db.commit()
    return _detail(db, db.get(DoctorReviewRequest, message.handoff_id))


@doctor_review_router.post("/{handoff_id}/resolve", response_model=DoctorReviewDetailOut)
def resolve_review(
    handoff_id: str, db: Session = Depends(get_db), actor: CurrentUser = Depends(_require_doctor)
) -> DoctorReviewDetailOut:
    doctor_id = require_active_doctor(db, actor)
    try:
        row = resolve_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, resolved_at=datetime.now(UTC))
        db.commit()
    except DoctorHandoffError as exc:
        db.rollback()
        raise _map_domain_error(exc) from exc
    return _detail(db, row)


@doctor_review_router.post("/{handoff_id}/cancel", response_model=DoctorReviewDetailOut)
def cancel_review(
    handoff_id: str, db: Session = Depends(get_db), actor: CurrentUser = Depends(_require_doctor)
) -> DoctorReviewDetailOut:
    doctor_id = require_active_doctor(db, actor)
    try:
        row = cancel_doctor_review_request(
            db, request_id=handoff_id, cancelled_at=datetime.now(UTC), doctor_id=doctor_id
        )
        db.commit()
    except DoctorHandoffError as exc:
        db.rollback()
        raise _map_domain_error(exc) from exc
    return _detail(db, row)


# ---------------------------------------------------------------------------
# Patient-facing: the patient's own view of their current handoff.
# ---------------------------------------------------------------------------


@patient_handoff_router.get("/agent/v2/handoff/status", response_model=PatientHandoffStatusOut)
def get_handoff_status(
    patient_id: str = Query(...), db: Session = Depends(get_db), actor: CurrentUser = Depends(get_current_user)
) -> PatientHandoffStatusOut:
    resolved_patient_id = require_agent_patient_access(db, actor, patient_id)
    row = get_active_takeover(db, patient_id=resolved_patient_id)
    if row is None:
        return PatientHandoffStatusOut(has_active_handoff=False)
    return _patient_handoff_detail(db, row)


def _patient_handoff_detail(db: Session, row: DoctorReviewRequest) -> PatientHandoffStatusOut:
    messages = db.execute(
        select(DoctorReviewMessage)
        .where(DoctorReviewMessage.handoff_id == row.id)
        .order_by(DoctorReviewMessage.created_at, DoctorReviewMessage.id)
    ).scalars().all()
    return PatientHandoffStatusOut(
        has_active_handoff=row.status == HandoffStatus.ACTIVE,
        handoff_id=row.id,
        handoff_type=_handoff_type(row),
        status=row.status,
        created_at=row.created_at,
        activated_at=row.activated_at,
        messages=[
            DoctorReviewMessageOut(
                id=m.id, sender_role=m.sender_role, actor_id=m.actor_id, content=m.content, created_at=m.created_at
            )
            for m in messages
            # SYSTEM is reserved for internal bookkeeping. The explicitly
            # contractually-visible terminal notice is the sole exception.
            if m.sender_role in ("PATIENT", "DOCTOR")
            or (m.sender_role == "SYSTEM" and m.content == DOCTOR_CONVERSATION_STOP_MESSAGE)
        ],
    )


@patient_handoff_router.get("/agent/v2/handoffs/{handoff_id}", response_model=PatientHandoffStatusOut)
def get_patient_handoff_detail(
    handoff_id: str, db: Session = Depends(get_db), actor: CurrentUser = Depends(get_current_user)
) -> PatientHandoffStatusOut:
    row = _get_or_404(db, handoff_id)
    require_agent_patient_access(db, actor, row.patient_id)
    return _patient_handoff_detail(db, row)


@patient_handoff_router.post("/agent/v2/handoffs/{handoff_id}/stop", response_model=PatientHandoffStatusOut)
def stop_patient_handoff(
    handoff_id: str, db: Session = Depends(get_db), actor: CurrentUser = Depends(get_current_user)
) -> PatientHandoffStatusOut:
    row = _get_or_404(db, handoff_id)
    patient_id = require_agent_patient_access(db, actor, row.patient_id)
    try:
        row = stop_active_doctor_review_request(
            db, request_id=handoff_id, patient_id=patient_id, stopped_at=datetime.now(UTC)
        )
        db.commit()
    except DoctorHandoffError as exc:
        db.rollback()
        raise _map_domain_error(exc) from exc
    return _patient_handoff_detail(db, row)


__all__ = ["doctor_review_router", "patient_handoff_router"]
