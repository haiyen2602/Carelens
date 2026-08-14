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

from backend.api.security import CurrentUser, get_current_user, require_role
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
    response_model=PatientSummary,
)
def get_my_patient_profile(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PatientSummary:
    """Benh nhan tu xem ho so CHINH minh (tuoi/ghi chu/gender/height/weight)
    - phan hoi review 2026-08-14: trang patient/health/page.tsx tung goi
    list_patients() (chi doctor/admin) de tim ho so chinh minh, luon 403 voi
    role=patient nen "tuoi · ghi chu" o dau trang luon rong (xac nhan qua DB
    production, BN-0000). Route rieng nay dung current_user.patient_id tu
    JWT (khong nhan patient_id tu client) - cung nguyen tac chong IDOR da
    dung o get_current_patient_id(), khong mo lai duong doc patient_id song
    song. KHONG dung require_role("doctor","admin") nhu list_patients() -
    bat ky role nao co patient_id gan voi tai khoan (thuc te chi role=patient)
    deu xem duoc DUNG ho so cua chinh minh, khong xem duoc nguoi khac."""
    if not current_user.patient_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Tài khoản không gắn với hồ sơ bệnh nhân nào"
        )
    patient = db.get(Patient, current_user.patient_id)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")
    return _to_summary(patient)


@patient_router.patch(
    "/patients/me",
    response_model=PatientProfileOut,
)
def update_my_profile(
    body: PatientProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("patient")),
) -> PatientProfileOut:
    """Onboarding: benh nhan tu dien thong tin ca nhan (migration 0023, xem
    Patient.date_of_birth/phone/address/profile_completed). Sau khi luu,
    `profile_completed=True` - trang onboarding (frontend/src/app/
    onboarding/profile/page.tsx) khong hoi lai nua, nhung van co the sua lai
    sau qua man hinh Cai dat (goi lai endpoint nay).

    Dang SAU "/patients/me" (GET, xem get_my_patient_profile o tren) trong
    file nay - Starlette khop route theo METHOD rieng, PATCH/GET tren cung 1
    path khong xung dot, nhung van dang truoc "/patients/{patient_id}" (co
    y): neu doi cho, PATCH /patients/me se roi vao update_patient_health voi
    patient_id="me" (403 vi endpoint do chi cho doctor/admin)."""
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
