"""
Danh sách bệnh nhân — cho form kê đơn của bác sĩ chọn người nhận.

CHƯA CÓ TRONG api-contracts.md, cùng lý do với drug_routes.py: cần thêm vào
§2 và review trước khi coi là ổn định.

Bác sĩ nào cũng xem được toàn bộ bệnh nhân (quyết định PM 2026-08-14 - kê
đơn/theo dõi không giới hạn theo `patient.doctor_id`; "chỉ định riêng" là
bác sĩ tự bấm nút "Theo dõi" trên dashboard báo cáo, xem `watch` ở
reporting_routes.py, KHÔNG phải lọc theo doctor_id ở đây). Tìm bằng tham số
`search` (khớp theo ID hoặc tên).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.db.base import get_db
from backend.db.models import Patient
from backend.models.schemas import (
    PatientHealthUpdateRequest,
    PatientProfileOut,
    PatientProfileUpdateRequest,
    PatientSummary,
)

patient_router = APIRouter()


def _to_profile(p: Patient) -> PatientProfileOut:
    return PatientProfileOut(
        id=p.id,
        full_name=p.full_name,
        date_of_birth=p.date_of_birth,
        year_of_birth=p.year_of_birth,
        phone=p.phone,
        address=p.address,
        gender=p.gender,
        height_cm=p.height_cm,
        weight_kg=p.weight_kg,
        profile_completed=p.profile_completed,
    )


def _to_summary(p: Patient) -> PatientSummary:
    return PatientSummary(
        id=p.id,
        full_name=p.full_name,
        year_of_birth=p.year_of_birth,
        note=p.note,
        gender=p.gender,
        height_cm=p.height_cm,
        weight_kg=p.weight_kg,
    )


@patient_router.get(
    "/patients",
    response_model=list[PatientSummary],
)
def list_patients(
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor", "admin")),
) -> list[PatientSummary]:
    query = select(Patient)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Patient.id.ilike(pattern), Patient.full_name.ilike(pattern)))
    rows = db.execute(query.order_by(Patient.full_name)).scalars().all()
    return [_to_summary(p) for p in rows]


@patient_router.get(
    "/patients/me",
    response_model=PatientProfileOut,
)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("patient")),
) -> PatientProfileOut:
    # Dang truoc "/patients/{patient_id}" trong file nay (co y) - Starlette
    # khop route theo THU TU dang ky, khong theo do cu the: neu doi cho,
    # PATCH /patients/me se roi vao update_patient_health voi patient_id="me"
    # (403 vi endpoint do chi cho doctor/admin).
    patient = db.get(Patient, current_user.patient_id)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")
    return _to_profile(patient)


@patient_router.patch(
    "/patients/me",
    response_model=PatientProfileOut,
)
def update_my_profile(
    body: PatientProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("patient")),
) -> PatientProfileOut:
    """Onboarding: benh nhan tu dien thong tin ca nhan (migration 0022).
    Sau khi luu, `profile_completed=True` - trang onboarding
    (frontend/src/app/onboarding/profile/page.tsx) khong hoi lai nua, nhung
    van co the sua lai sau qua man hinh Cai dat (goi lai endpoint nay)."""
    patient = db.get(Patient, current_user.patient_id)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")

    for field in ("phone", "address", "gender", "height_cm", "weight_kg"):
        value = getattr(body, field)
        if value is not None:
            setattr(patient, field, value)

    if body.date_of_birth is not None:
        patient.date_of_birth = body.date_of_birth
        patient.year_of_birth = body.date_of_birth.year

    patient.profile_completed = True

    db.commit()
    db.refresh(patient)
    return _to_profile(patient)


@patient_router.patch(
    "/patients/{patient_id}",
    response_model=PatientSummary,
)
def update_patient_health(
    patient_id: str,
    body: PatientHealthUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor", "admin")),
) -> PatientSummary:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")

    for field in ("note", "gender", "height_cm", "weight_kg"):
        value = getattr(body, field)
        if value is not None:
            setattr(patient, field, value)

    db.commit()
    db.refresh(patient)
    return _to_summary(patient)
