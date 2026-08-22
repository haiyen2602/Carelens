"""POST /api/v1/nudges + GET /api/v1/nudges/unseen - loi nhac nhe nguoi than
gui cho benh nhan dang theo doi qua sheet "Nhac nhe"
(frontend/src/app/patient/family/page.tsx). THEM 2026-08-20.

Repo chua co ha tang realtime (WebSocket/SSE) - benh nhan poll
GET /nudges/unseen dinh ky (frontend), moi request tra ve cac nhac CHUA xem
va danh dau seen NGAY trong cung request do (kieu "pop khoi hang doi") -
khong can endpoint ack rieng, xem ghi chu day du tren backend/db/models.py::
Nudge."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_role
from backend.db.base import get_db
from backend.db.models import Account, CaregiverLink, Nudge, Patient
from backend.models.schemas import NudgeCreateRequest, NudgeOut
from backend.services.push import send_push_to_patient

nudge_router = APIRouter()


def _to_out(row: Nudge, caregiver_name: str) -> NudgeOut:
    return NudgeOut(
        id=row.id,
        caregiver_account_id=row.caregiver_account_id,
        caregiver_name=caregiver_name,
        patient_id=row.patient_id,
        message=row.message,
        created_at=row.created_at.isoformat(),
    )


@nudge_router.post("/nudges", response_model=NudgeOut, status_code=http_status.HTTP_201_CREATED)
def send_nudge(
    body: NudgeCreateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> NudgeOut:
    """Chi nguoi than DANG theo doi that (CaregiverLink.status="accepted")
    moi gui duoc - loi moi con "pending" chua tinh, cung dieu kien voi
    _list_monitored_patients() trong caregiver_routes.py, tranh gui nhac cho
    benh nhan chua dong y chia se du lieu."""
    if db.get(Patient, body.patient_id) is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bệnh nhân")

    link = (
        db.query(CaregiverLink)
        .filter(
            CaregiverLink.caregiver_account_id == current_user.id,
            CaregiverLink.patient_id == body.patient_id,
            CaregiverLink.status == "accepted",
        )
        .first()
    )
    if link is None:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Bạn chưa theo dõi bệnh nhân này",
        )

    row = Nudge(caregiver_account_id=current_user.id, patient_id=body.patient_id, message=body.message)
    db.add(row)
    db.commit()
    db.refresh(row)

    caregiver_name = current_user.id
    account = db.get(Account, current_user.id)
    if account is not None:
        caregiver_name = account.full_name

    # Day them Web Push (THEM 2026-08-22) - truoc do nudge chi ghi DB, benh
    # nhan phai dang mo tab va cho poll GET /nudges/unseen (8s/lan, xem
    # capy-shell.tsx) moi thay. Cung ha tang voi dose_push_reminder.py
    # (send_push_to_patient tu no neu chua cau hinh VAPID hoac benh nhan chua
    # dang ky push tren may nao - khong lam gian doan viec gui nudge).
    send_push_to_patient(db, body.patient_id, "CapyMedi", f"{caregiver_name}: {body.message}")
    db.commit()

    return _to_out(row, caregiver_name)


@nudge_router.get("/nudges/unseen", response_model=list[NudgeOut])
def list_unseen_nudges(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("patient")),
) -> list[NudgeOut]:
    """Chi benh nhan dang dang nhap goi duoc, luon doc theo
    `current_user.patient_id` cua chinh ho - khong nhan patient_id tu query,
    cung ly do voi list_pending_invites() trong caregiver_routes.py (khong
    cho doc ho nhac cua nguoi khac)."""
    if not current_user.patient_id:
        return []

    rows = (
        db.query(Nudge)
        .filter(Nudge.patient_id == current_user.patient_id, Nudge.seen_at.is_(None))
        .order_by(Nudge.created_at)
        .all()
    )
    if not rows:
        return []

    caregiver_ids = {r.caregiver_account_id for r in rows}
    accounts = db.execute(select(Account).where(Account.id.in_(caregiver_ids))).scalars().all()
    name_by_id = {a.id: a.full_name for a in accounts}

    now = datetime.now(UTC)
    result = [_to_out(r, name_by_id.get(r.caregiver_account_id, r.caregiver_account_id)) for r in rows]
    for r in rows:
        r.seen_at = now
    db.commit()

    return result
