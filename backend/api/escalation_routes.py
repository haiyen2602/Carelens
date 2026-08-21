"""POST /api/v1/escalations/{id}/ack (api-contracts.md §6, vong 2 muc 13) -
danh dau 1 escalation da duoc xu ly. Day chinh la co che DUNG nhac lai
(escalation_reminder.py::check_and_send_reminders() chi quet status="OPEN")
- KHONG them cot resolved:bool rieng, dung lai `status` da co san tren
Escalation (OPEN|ACKED|RESOLVED) chuyen sang "RESOLVED".

Idempotent co y: goi lai nhieu lan (vd 2 nguoi cung ack gan nhau) chi CAP
NHAT lai resolved_at/resolved_by, khong loi - tranh xu ly race condition
phuc tap cho 1 hanh dong vo hai (xac nhan lai)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.api.security import (
    CurrentUser,
    get_current_patient_id,
    get_current_user,
)
from backend.db.base import get_db
from backend.db.models import Account, CaregiverLink, Escalation
from backend.models.schemas import CurrentEscalationResponse, EscalationAckResponse

escalation_router = APIRouter()


@dataclass
class _PatientIdQuery:
    """Adapter de tai dung get_current_patient_id() (backend/api/security.py)
    cho endpoint GET khong co request body - Protocol _HasPatientId chi can
    1 thuoc tinh .patient_id, khong bat buoc phai la Pydantic model that."""

    patient_id: str


@escalation_router.post(
    "/escalations/{escalation_id}/ack",
    response_model=EscalationAckResponse,
)
async def ack_escalation(
    escalation_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EscalationAckResponse:
    """Quyen: doctor/caregiver/admin (quan tri chung), HOAC role=patient
    dang xem NHU nguoi than cua benh nhan nay (co CaregiverLink accepted) -
    truong hop pho bien nhat trong app (1 tai khoan role=patient theo doi
    nguoi than khac, xem patient/family/[id]/page.tsx), truoc day bi
    require_role() chan nham vi khong nam trong 3 role liet ke san. Cung
    pattern voi update_dose_status (backend/api/dose_routes.py:123-139).

    `resolved_by` truoc day nhan tu request body (TODO tam thoi luc chua co
    JWT that, xem EscalationAckResponse) - gio doc thang tu current_user,
    khong tin client gui len nua."""
    row = db.get(Escalation, escalation_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Escalation không tồn tại")

    authorized = current_user.role in ("doctor", "caregiver", "admin")
    if not authorized and current_user.role == "patient":
        link = (
            db.query(CaregiverLink)
            .filter(
                CaregiverLink.caregiver_account_id == current_user.id,
                CaregiverLink.patient_id == row.patient_id,
                CaregiverLink.status == "accepted",
            )
            .first()
        )
        authorized = link is not None
    if not authorized:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền xử lý cảnh báo này")

    account = db.get(Account, current_user.id)
    resolved_by = account.full_name if account is not None else current_user.id

    row.status = "RESOLVED"
    row.resolved_at = datetime.now(UTC)
    row.resolved_by = resolved_by
    db.commit()

    return EscalationAckResponse(
        id=row.id,
        status=row.status,
        resolved_at=row.resolved_at.isoformat(),
        resolved_by=row.resolved_by,
    )


@escalation_router.get("/escalations/current")
async def get_current_escalation(
    patient_id: str | None = Query(
        default=None, description="Bat buoc neu role khong phai patient (doctor/caregiver goi ho)"
    ),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentEscalationResponse | None:
    """Vong 2 muc 4 y 4 (CAN CHOT, PM chot shape 2026-08-12) - escalation
    OPEN gan nhat cua benh nhan, de FE quyet dinh hien banner "de xuat goi
    cap cuu" lien tuc tu t=15p (escalation_reminder.py) toi khi resolved.
    Tra None (khong phai 404) neu khong co escalation OPEN nao - day la
    trang thai binh thuong (khong co gi khan cap), khong phai loi.

    Dung dung 1 cho noi get_current_patient_id() (qua adapter _PatientIdQuery)
    nhu moi endpoint dung patient_id khac trong TASK-010 - benh nhan chi xem
    duoc escalation CUA CHINH HO, khong tu go patient_id nguoi khac vao query
    string ma doc duoc."""
    if current_user.role != "patient" and not patient_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="patient_id bat buoc trong query string cho role khong phai patient",
        )
    resolved_patient_id = get_current_patient_id(_PatientIdQuery(patient_id=patient_id or ""), current_user)

    row = (
        db.query(Escalation)
        .filter(Escalation.patient_id == resolved_patient_id, Escalation.status == "OPEN")
        .order_by(desc(Escalation.created_at))
        .first()
    )
    if row is None:
        return None

    return CurrentEscalationResponse(
        status=row.status,
        severity=row.severity,
        reminder_count=row.reminder_count,
        created_at=row.created_at.isoformat(),
    )
