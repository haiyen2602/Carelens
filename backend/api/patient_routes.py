"""
Danh sách bệnh nhân — cho form kê đơn của bác sĩ chọn người nhận.

CHƯA CÓ TRONG api-contracts.md, cùng lý do với drug_routes.py: cần thêm vào
§2 và review trước khi coi là ổn định.

Không lọc theo bác sĩ đang đăng nhập — chưa có auth-api để biết ai đang gọi.
Khi có JWT thật, lọc theo `doctor_id` là việc thêm một điều kiện `WHERE`, chỗ
duy nhất cần sửa là ở đây.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import require_internal_secret
from backend.db.base import get_db
from backend.db.models import Patient
from backend.models.schemas import PatientSummary

patient_router = APIRouter()


@patient_router.get(
    "/patients",
    response_model=list[PatientSummary],
    dependencies=[Depends(require_internal_secret)],
)
def list_patients(db: Session = Depends(get_db)) -> list[PatientSummary]:
    rows = db.execute(select(Patient).order_by(Patient.full_name)).scalars().all()
    return [
        PatientSummary(id=p.id, full_name=p.full_name, year_of_birth=p.year_of_birth, note=p.note)
        for p in rows
    ]
