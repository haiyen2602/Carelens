"""
Danh sách liều thuốc trong ngày — cho trang bệnh nhân biết liều nào đang chờ
và cần thuốc gì để chụp ảnh xác nhận.

CHƯA CÓ TRONG api-contracts.md ở dạng đầy đủ (§3 có `reminder_level` và
`evidence`, hai trường không có cột tương ứng trong `dose_event` hiện tại —
`reminder_level` do escalation_reminder theo dõi trên bảng `escalation`, không
phải `dose_event`). `DoseSummary` chỉ trả đủ cho nhu cầu hiện tại; cần Architect
duyệt trước khi coi là ổn định (ADR-0003).

Chỉ ĐỌC. Không lọc theo bác sĩ/quan hệ liên kết — chưa có auth-api để biết ai
đang gọi (cùng giới hạn với patient_routes.py/prescription_routes.py).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_internal_secret
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import CaregiverLink, DoseEvent, Patient
from backend.models.schemas import DoseStatusUpdateRequest, DoseSummary
from backend.services.prescription.errors import VmecError
from backend.services.scheduling.runtime_adapter import (
    DoseRuntimeGroup,
    get_v2_dose_group,
    list_v2_dose_groups,
    transition_v2_dose_group,
)

dose_router = APIRouter()


@dose_router.get(
    "/doses",
    response_model=list[DoseSummary],
    dependencies=[Depends(require_internal_secret)],
)
def list_doses(
    patient_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> list[DoseSummary]:
    if get_settings().dose_runtime_mode == "v2":
        return [_v2_dose_summary(group) for group in list_v2_dose_groups(db, patient_id=patient_id)]
    rows = db.execute(
        select(DoseEvent).where(DoseEvent.patient_id == patient_id).order_by(DoseEvent.scheduled_at)
    ).scalars().all()
    return [
        DoseSummary(
            id=r.id,
            prescription_id=r.prescription_id,
            scheduled_at=r.scheduled_at.isoformat(),
            window_start=r.window_start.isoformat(),
            window_end=r.window_end.isoformat(),
            status=r.status,
            expected_items=r.expected_items,
        )
        for r in rows
    ]


def _dose_summary(r: DoseEvent) -> DoseSummary:
    return DoseSummary(
        id=r.id,
        prescription_id=r.prescription_id,
        scheduled_at=r.scheduled_at.isoformat(),
        window_start=r.window_start.isoformat(),
        window_end=r.window_end.isoformat(),
        status=r.status,
        expected_items=r.expected_items,
    )


def _v2_dose_summary(group: DoseRuntimeGroup) -> DoseSummary:
    return DoseSummary(
        id=group.id,
        prescription_id=group.prescription_id,
        scheduled_at=group.scheduled_at.isoformat(),
        window_start=group.window_start.isoformat(),
        window_end=group.window_end.isoformat(),
        status=group.status,
        expected_items=group.expected_items,
    )


@dose_router.patch("/doses/{dose_id}", response_model=DoseSummary)
def update_dose_status(
    dose_id: str,
    body: DoseStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DoseSummary:
    """Benh nhan/nguoi than/bac si tu cap nhat trang thai 1 lieu (vd tu bao
    "da uong" khong qua chatbot, hoac nguoi than duyet 1 lieu AWAITING_CAREGIVER
    sau khi xem anh - patient/family/[id]/page.tsx). Phan quyen (KHONG dung
    require_internal_secret - can biet DUNG ai dang goi de kiem tra quan he,
    xem cac nhanh ben duoi):
      - Lieu CUA CHINH MINH (dose_event.patient_id == current_user.patient_id):
        luon sua duoc, bat ke role - ap dung ca cho tai khoan role=patient
        dang tu bao trang thai lieu cua ho.
      - role=caregiver HOAC role=patient dang theo doi nguoi khac (1 benh
        nhan co the dong thoi la nguoi than cua benh nhan khac, xem ghi chu
        MonitoredRelative trong frontend/src/lib/proto-store.tsx): sua duoc
        lieu cua benh nhan co CaregiverLink DA CHAP NHAN (status=accepted)
        toi chinh tai khoan dang goi - loi moi con "pending" KHONG cho quyen
        gi (xem POST /caregiver-links/invites).
      - role=doctor: sua duoc lieu cua BAT KY benh nhan nao (khong con rang
        buoc theo patient.doctor_id - bac si quan ly toan bo benh nhan qua
        tim kiem theo ID, xem patient_routes.py).
    404 neu dose_event khong ton tai (kiem tra TRUOC 403 - khong lo thong tin
    "co ton tai nhung ban khong co quyen" cho lieu khong ton tai)."""
    if get_settings().dose_runtime_mode == "v2":
        return _update_v2_dose_status(dose_id, body, db, current_user)

    dose = db.get(DoseEvent, dose_id)
    if dose is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Liều thuốc không tồn tại")

    authorized = current_user.patient_id == dose.patient_id
    if not authorized and current_user.role == "doctor":
        authorized = db.get(Patient, dose.patient_id) is not None
    if not authorized:
        link = (
            db.query(CaregiverLink)
            .filter(
                CaregiverLink.caregiver_account_id == current_user.id,
                CaregiverLink.patient_id == dose.patient_id,
                CaregiverLink.status == "accepted",
            )
            .first()
        )
        authorized = link is not None

    if not authorized:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền sửa liều này")

    dose.status = body.status
    db.commit()
    db.refresh(dose)
    return _dose_summary(dose)


def _update_v2_dose_status(
    dose_id: str, body: DoseStatusUpdateRequest, db: Session, current_user: CurrentUser
) -> DoseSummary:
    """Authorize and transition a grouped V2 dose through the scheduling boundary."""

    try:
        group = get_v2_dose_group(db, dose_group_id=dose_id)
    except VmecError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.to_contract()["error"]) from exc

    authorized = current_user.patient_id == group.patient_id
    if not authorized and current_user.role == "doctor":
        authorized = db.get(Patient, group.patient_id) is not None
    if not authorized:
        link = (
            db.query(CaregiverLink)
            .filter(
                CaregiverLink.caregiver_account_id == current_user.id,
                CaregiverLink.patient_id == group.patient_id,
                CaregiverLink.status == "accepted",
            )
            .first()
        )
        authorized = link is not None
    if not authorized:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền sửa liều này")

    try:
        updated = transition_v2_dose_group(
            db,
            dose_group_id=dose_id,
            target_status=body.status,
            event_at=datetime.now(UTC),
            source="PATIENT_DOSE_API",
            actor_type=current_user.role.upper(),
            actor_id=current_user.id,
        )
        db.commit()
    except VmecError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.http_status, detail=exc.to_contract()["error"]) from exc
    return _v2_dose_summary(updated)
