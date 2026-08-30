"""Tao 1 Escalation bao NGUOI THAN - 1 CHO NOI DUY NHAT (THEM 2026-08-20).

Truoc do logic nay nam thang trong backend/api/health_log_routes.py. Tach ra
khi co nguoi goi thu 2 (backend/services/dose_push_reminder.py - moc +30 phut
ma benh nhan van chua xac nhan uong thuoc): 2 noi cung tao Escalation thi
phai dung CHUNG 1 ham, khong copy 2 ban roi lech nhau ve sau.

KHONG tai dung `escalate_fn`/`build_db_escalate_fn` (backend/services/
escalation.py) - ham do la closure gan voi vong doi 1 lan chay LangGraph
agent (`_pending` dict chi song trong pham vi do), goi tu 1 REST route hay 1
job dinh ky se tao dong TRUNG LAP thay vi cap nhat dong da co. Cung ly do da
ghi ro trong docstring escalation_reminder.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.db.models import Escalation
from backend.services.telegram import send_telegram_to_caregivers

logger = logging.getLogger("caregiver_escalation")


def tao_canh_bao_cho_nguoi_than(
    db: Session,
    *,
    patient_id: str,
    severity: str,
    trigger: str,
    reason: str,
    dose_event_id: str | None = None,
) -> Escalation:
    """Tao 1 dong Escalation OPEN, da danh dau la "da bao nguoi than".

    KHONG commit - nguoi goi quyet dinh ranh gioi giao dich (route thi commit
    ngay, job dinh ky thi gom nhieu viec trong 1 lan commit).
    """
    row = Escalation(
        patient_id=patient_id,
        dose_event_id=dose_event_id,
        severity=severity,
        trigger=trigger,
        reason=reason,
        status="OPEN",
        notified=["caregiver"],
        reminder_count=1,  # da bao lan dau (chinh lan nay), chua tinh nhac lai
        last_reminder_at=datetime.now(UTC),
    )
    db.add(row)

    # DAY THAT toi nguoi than, khong chi ghi DB roi cho ho tu mo app (THEM
    # 2026-08-28). Truoc do `notified=["caregiver"]` o tren la mot loi hua
    # SUONG: dong Escalation duoc danh dau "da bao" nhung khong co tin nao roi
    # khoi may chu - nguoi than chi thay neu tu vao tab Gia dinh. Voi canh bao
    # bo lieu/dau hieu nguy hiem thi do la do tre hang gio.
    #
    # KHONG raise khi gui hong: canh bao PHAI duoc ghi vao DB du Telegram co
    # loi mang hay nguoi than chua ghep tai khoan. Man hinh Gia dinh van la
    # duong nhan tin cuoi cung, Telegram chi la duong NHANH hon.
    try:
        send_telegram_to_caregivers(
            db,
            patient_id=patient_id,
            title="⚠️ Cảnh báo",
            body=reason,
        )
    except Exception:  # noqa: BLE001 - gui hong khong duoc lam mat canh bao
        logger.exception("Khong gui duoc canh bao Telegram cho nguoi than cua %s", patient_id)

    return row
