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

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.db.models import Escalation


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
    return row
