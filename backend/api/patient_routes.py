"""
Danh sách bệnh nhân — cho form kê đơn của bác sĩ chọn người nhận.

CHƯA CÓ TRONG api-contracts.md, cùng lý do với drug_routes.py: cần thêm vào
§2 và review trước khi coi là ổn định.

Lọc theo bác sĩ đang đăng nhập (doctor_id): bác sĩ chỉ thấy bệnh nhân của
mình (patient.doctor_id == current_user.doctor_id). Admin thấy tất cả.
Tìm bằng tham số `search` (khớp theo ID hoặc tên).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_role
from backend.db.base import get_db
from backend.db.models import Patient
from backend.models.schemas import PatientHealthUpdateRequest, PatientSummary

patient_router = APIRouter()


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
    if current_user.role == "doctor" and current_user.doctor_id:
        query = query.where(Patient.doctor_id == current_user.doctor_id)
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
