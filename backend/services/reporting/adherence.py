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


def ty_le_tuan_thu(taken: int, due: int) -> float | None:
    """Cong thuc chung, tach ra de moi noi tinh tuan thu deu dung DUNG mot
    phep chia - ke ca cho tinh theo lo (vd ca trang bao cao trong 1 truy van,
    xem reporting_routes.py::get_dose_summary) chu khong chi tinh tung nguoi.

    None khi due == 0: chua co lieu nao den han thi CHUA KET LUAN duoc, khac
    han "0% tuan thu"."""
    if due <= 0:
        return None
    return (taken / due) * 100


def compute_adherence_pct(
    db: Session,
    patient_id: str,
    *,
    now: datetime | None = None,
    since: datetime | None = None,
) -> float | None:
    """Tra ve None (KHONG phai 0.0) neu benh nhan chua co lieu nao den han -
    chua co du lieu de ket luan, khong phai "0% tuan thu".

    `since` (THEM 2026-08-23) gioi han xuong CHI cac lieu den han TU moc do -
    truoc day ham nay luon tinh tu truoc toi nay, nen the "Tuan thu trung
    binh" o trang bao cao bi cac lieu cu ton dong quyet dinh, trong khi cac
    bieu do canh no chi noi ve 7 ngay. Bo trong `since` giu nguyen hanh vi cu
    (toan bo lich su) cho cac man hinh dang goi san."""
    reference_time = now or datetime.now(UTC)

    dieu_kien = [DoseEvent.patient_id == patient_id, DoseEvent.window_end <= reference_time]
    if since is not None:
        dieu_kien.append(DoseEvent.window_end >= since)

    due_events = db.execute(select(DoseEvent.status).where(*dieu_kien)).scalars().all()

    return ty_le_tuan_thu(sum(1 for s in due_events if s == "TAKEN"), len(due_events))
