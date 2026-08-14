"""Vong 2, muc 13 (chatbot-rag-design.md) - co che nhac lai escalation theo
moc thoi gian co dinh, tach LOGIC QUYET DINH thuan (khong I/O, test duoc
bang mock-clock, khong can APScheduler/DB that) khoi PHAN QUET+GHI THAT
(can DB that) - giong tinh than tach fuse_rrf() thuan khoi hybrid_search()
co I/O (Phase 4).

QUAN TRONG - KHONG dung lai `EscalateFn`/`build_db_escalate_fn` (escalation.py)
cho nhac lai: ham do thiet ke de TAO MOI 1 dong Escalation (hoac cap nhat
`notified` qua `_pending` dict CHI song trong pham vi 1 lan goi build_db_
escalate_fn(db)/1 request) - goi lai tu 1 scheduler chay SAU, VOI 1 instance
escalate_fn MOI (`_pending` rong), se TAO DONG TRUNG LAP thay vi cap nhat
dong da co. Nhac lai phai CAP NHAT dong Escalation DA TON TAI (reminder_count,
last_reminder_at), khong tao dong moi - can 1 co che rieng, KHONG phai
EscalateFn.

Moc thoi gian DA CHOT (tinh TUYET DOI tu created_at, khong phai khoang cach
giua 2 lan nhac):
  t=0    -> escalate lan 1 (da co, trigger_emergency_escalation) - reminder_count=1
  t=15p  -> nhac lan 2 (reminder_count: 1 -> 2)
  t=25p  -> nhac lan 3 (reminder_count: 2 -> 3)
  t=35p  -> nhac lan 4, LAN CUOI (reminder_count: 3 -> 4)
  t=45p  -> KHONG nhac them (reminder_count da la 4, khong co nguong nao o
            tren 4) - nhung status VAN o "OPEN" cho toi khi co nguoi /ack."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Escalation

logger = logging.getLogger("escalation_reminder")

# reminder_count HIEN TAI -> so phut TUYET DOI tu created_at de nhac lan KE
# TIEP. Khong co key cho 4 - reminder_count=4 la LAN CUOI, khong nhac them.
_REMINDER_THRESHOLDS_MINUTES: dict[int, float] = {1: 15.0, 2: 25.0, 3: 35.0}


def is_reminder_due(reminder_count: int, elapsed_minutes: float) -> bool:
    """Ham THUAN - khong I/O, test duoc truc tiep voi elapsed_minutes gia
    lap (khong can mock clock/sleep that o tang nay)."""
    threshold = _REMINDER_THRESHOLDS_MINUTES.get(reminder_count)
    if threshold is None:
        return False
    return elapsed_minutes >= threshold


class ReminderNotifyFn(Protocol):
    async def __call__(
        self, target: str, patient_id: str, dose_event_id: str | None, escalation_id: str, reminder_count: int
    ) -> None: ...


async def default_reminder_notify(
    target: str, patient_id: str, dose_event_id: str | None, escalation_id: str, reminder_count: int
) -> None:
    """STUB - dung tinh than `build_db_escalate_fn` (escalation.py): CHUA co
    ha tang push/SMS that trong repo nay, KHONG gia vo goi 1 API ngoai chua
    ton tai. `reminder_count`/`last_reminder_at` tren `Escalation` (cap nhat
    o `check_and_send_reminders` ben duoi) DA LA ket qua THAT quan sat duoc
    cua lan nhac nay (audit duoc qua DB) - ham nay la 1 CHO NOI (extension
    point) cho khi co push/SMS that, khong phai hanh vi chinh can test."""
    logger.info(
        "Nhac lai escalation #%d: target=%s patient_id=%s escalation_id=%s",
        reminder_count, target, patient_id, escalation_id,
    )  # fmt: skip


async def check_and_send_reminders(
    db: Session,
    now: datetime | None = None,
    notify_fn: ReminderNotifyFn = default_reminder_notify,
    patient_id: str | None = None,
) -> int:
    """Quet TOAN BO escalation dang `status="OPEN"`, nhac lai hang nao da den
    moc (is_reminder_due) - goi `notify_fn` cho CA family LAN doctor (dung y
    BR-3.5 "khong xep hang", giong lan escalate goc), roi CAP NHAT dong
    Escalation DA CO (khong tao dong moi). Tra ve so luong da nhac.

    `now` injectable (mac dinh None -> datetime.now(UTC)) - CHO TEST dung
    mock-clock (gia lap thoi gian, KHONG sleep() that 45 phut) - dung y
    kickoff: "Giả lập thời gian... không phải test chạy thật theo đồng hồ
    hệ thống".

    `patient_id` injectable, CHI DE TEST TIEN LOI (mac dinh None = quet toan
    cuc, dung hanh vi that cua 1 background job production) - tranh test vo
    tinh dung/cap nhat cac dong OPEN con lai tu phien thu tay/test khac
    (demo-patient-01, test-patient-01...) khong lien quan toi test dang chay."""
    now = now or datetime.now(UTC)
    stmt = select(Escalation).where(Escalation.status == "OPEN")
    if patient_id is not None:
        stmt = stmt.where(Escalation.patient_id == patient_id)
    open_escalations = db.execute(stmt).scalars().all()

    reminded_count = 0
    for esc in open_escalations:
        elapsed_minutes = (now - esc.created_at).total_seconds() / 60
        if not is_reminder_due(esc.reminder_count, elapsed_minutes):
            continue

        new_reminder_count = esc.reminder_count + 1
        for target in ("family", "doctor"):
            try:
                await notify_fn(target, esc.patient_id, esc.dose_event_id, esc.id, new_reminder_count)
            except Exception:  # noqa: BLE001 - 1 kenh loi khong duoc lam mat lan nhac cua kenh kia
                logger.exception("Nhac lai escalation that bai: escalation_id=%s target=%s", esc.id, target)

        esc.reminder_count = new_reminder_count
        esc.last_reminder_at = now
        db.commit()
        reminded_count += 1

    return reminded_count
