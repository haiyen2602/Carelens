"""Ty le tuan thu (adherence %) cua 1 benh nhan, tinh tu DoseEvent - dung
chung cho ca dashboard bac si (backend/api/reporting_routes.py) va man hinh
"nguoi than dang theo doi" cua caregiver (backend/api/caregiver_routes.py),
1 CHO NOI DUY NHAT cho phep tinh nay de khong lech cong thuc giua 2 man hinh.

Cong thuc: so lieu status=="TAKEN" / tong so lieu DA DEN HAN (window_end da
qua so voi thoi diem tinh) * 100. CHI tinh lieu da den han - lieu con
PENDING/AWAITING_CAREGIVER trong tuong lai chua co ket qua, dua vao mau se
lam sai lech ty le (vd benh nhan moi bat dau phac do, hau het lieu con
PENDING, tinh ca vao mau se cho ra ty le rat thap gia tao dung nhu benh
nhan bo thuoc)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DoseEvent


def compute_adherence_pct(db: Session, patient_id: str, *, now: datetime | None = None) -> float | None:
    """Tra ve None (KHONG phai 0.0) neu benh nhan chua co lieu nao den han -
    chua co du lieu de ket luan, khong phai "0% tuan thu"."""
    reference_time = now or datetime.now(UTC)

    due_events = db.execute(
        select(DoseEvent.status).where(
            DoseEvent.patient_id == patient_id,
            DoseEvent.window_end <= reference_time,
        )
    ).scalars().all()

    if not due_events:
        return None

    taken_count = sum(1 for status in due_events if status == "TAKEN")
    return (taken_count / len(due_events)) * 100
