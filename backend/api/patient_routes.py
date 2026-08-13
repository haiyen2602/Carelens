"""
Danh sách bệnh nhân — cho form kê đơn của bác sĩ chọn người nhận.

CHƯA CÓ TRONG api-contracts.md, cùng lý do với drug_routes.py: cần thêm vào
§2 và review trước khi coi là ổn định.

Không lọc theo bác sĩ đang đăng nhập: bất kỳ bác sĩ nào cũng quản lý được
toàn bộ bệnh nhân (không còn ràng buộc theo patient.doctor_id), tìm bằng
tham số `search` (khớp theo ID hoặc tên).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
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
def list_patients(
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
) -> list[PatientSummary]:
    query = select(Patient)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Patient.id.ilike(pattern), Patient.full_name.ilike(pattern)))
    rows = db.execute(query.order_by(Patient.full_name)).scalars().all()
    return [
        PatientSummary(id=p.id, full_name=p.full_name, year_of_birth=p.year_of_birth, note=p.note)
        for p in rows
    ]
