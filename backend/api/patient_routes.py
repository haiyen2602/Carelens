"""
Danh sách bệnh nhân — cho form kê đơn của bác sĩ chọn người nhận.

CHƯA CÓ TRONG api-contracts.md, cùng lý do với drug_routes.py: cần thêm vào
§2 và review trước khi coi là ổn định.

Không lọc theo bác sĩ đang đăng nhập: bất kỳ bác sĩ nào cũng quản lý được
toàn bộ bệnh nhân (không còn ràng buộc theo patient.doctor_id), tìm bằng
tham số `search` (khớp theo ID hoặc tên).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.api.security import require_internal_secret
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
    dependencies=[Depends(require_internal_secret)],
)
def list_patients(
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
) -> list[PatientSummary]:
    query = select(Patient)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Patient.id.ilike(pattern), Patient.full_name.ilike(pattern)))
    rows = db.execute(query.order_by(Patient.full_name)).scalars().all()
    return [_to_summary(p) for p in rows]


@patient_router.patch(
    "/patients/{patient_id}",
    response_model=PatientSummary,
    dependencies=[Depends(require_internal_secret)],
)
def update_patient_health(
    patient_id: str, body: PatientHealthUpdateRequest, db: Session = Depends(get_db)
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
