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

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import require_internal_secret
from backend.db.base import get_db
from backend.db.models import DoseEvent
from backend.models.schemas import DoseSummary

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
