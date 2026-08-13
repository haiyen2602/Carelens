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

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_internal_secret
from backend.db.base import get_db
from backend.db.models import CaregiverLink, DoseEvent, Patient
from backend.models.schemas import DoseStatusUpdateRequest, DoseSummary

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


@dose_router.patch("/doses/{dose_id}", response_model=DoseSummary)
def update_dose_status(
    dose_id: str,
    body: DoseStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DoseSummary:
    """Benh nhan/nguoi than/bac si tu cap nhat trang thai 1 lieu (vd tu bao
    "da uong" khong qua chatbot). Phan quyen (KHONG dung require_internal_secret
    - can biet DUNG ai dang goi de kiem tra quan he, xem docstring 2 nhanh
    ben duoi):
      - role=patient: chi sua duoc lieu CUA CHINH MINH (dose_event.patient_id
        == current_user.patient_id).
      - role=caregiver: chi sua duoc lieu cua benh nhan co CaregiverLink toi
        chinh tai khoan dang goi (specs/user-roles.md).
      - role=doctor: sua duoc lieu cua BAT KY benh nhan nao (khong con rang
        buoc theo patient.doctor_id - bac si quan ly toan bo benh nhan qua
        tim kiem theo ID, xem patient_routes.py).
    404 neu dose_event khong ton tai (kiem tra TRUOC 403 - khong lo thong tin
    "co ton tai nhung ban khong co quyen" cho lieu khong ton tai)."""
    dose = db.get(DoseEvent, dose_id)
    if dose is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Liều thuốc không tồn tại")

    authorized = False
    if current_user.role == "patient":
        authorized = current_user.patient_id == dose.patient_id
    elif current_user.role == "caregiver":
        link = (
            db.query(CaregiverLink)
            .filter(
                CaregiverLink.caregiver_account_id == current_user.id,
                CaregiverLink.patient_id == dose.patient_id,
            )
            .first()
        )
        authorized = link is not None
    elif current_user.role == "doctor":
        authorized = db.get(Patient, dose.patient_id) is not None

    if not authorized:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền sửa liều này")

    dose.status = body.status
    db.commit()
    db.refresh(dose)
    return _dose_summary(dose)
