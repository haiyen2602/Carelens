"""Vong 2, muc 13 (chatbot-rag-design.md) - co che nhac lai escalation. Test
bat buoc theo kickoff: gia lap thoi gian (KHONG sleep() that 45 phut), case
resolved giua chung dung nhac tiep, case het 4 lan van khong tu dong RESOLVED."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Escalation  # noqa: E402
from backend.services.escalation_reminder import check_and_send_reminders, is_reminder_due  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


# ---------------------------------------------------------------------------
# Logic thuan - khong can DB
# ---------------------------------------------------------------------------


def test_reminder_not_due_before_threshold():
    assert is_reminder_due(reminder_count=1, elapsed_minutes=14.9) is False


def test_reminder_due_exactly_at_threshold():
    assert is_reminder_due(reminder_count=1, elapsed_minutes=15.0) is True


def test_reminder_due_progression_through_thresholds():
    assert is_reminder_due(1, 15.0) is True   # -> nhac lan 2
    assert is_reminder_due(2, 25.0) is True   # -> nhac lan 3
    assert is_reminder_due(3, 35.0) is True   # -> nhac lan 4 (cuoi)


def test_reminder_count_4_never_due_again():
    """reminder_count=4 la LAN CUOI - khong co nguong nao o tren, du elapsed
    bao lau cung KHONG nhac them (dung y kickoff: dung han o t=45p)."""
    assert is_reminder_due(4, elapsed_minutes=1000.0) is False


# ---------------------------------------------------------------------------
# check_and_send_reminders - can DB that
# ---------------------------------------------------------------------------


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_open_escalation(db, patient_id: str, created_at, reminder_count: int = 1) -> str:
    row = Escalation(
        patient_id=patient_id,
        dose_event_id=None,
        severity="HIGH",
        trigger="safety_redflag",
        raw_utterance="test",
        reason="test escalation for reminder logic",
        status="OPEN",
        notified=["caregiver", "doctor"],
        reminder_count=reminder_count,
        last_reminder_at=created_at,
        created_at=created_at,
    )
    db.add(row)
    db.commit()
    return row.id


@pytest.mark.asyncio
async def test_resolved_between_reminders_stops_further_reminders():
    """Kickoff: 'Case: resolved ở t=20p (giữa lần nhắc 2 và 3) → job không
    gửi lần 3/4 nữa.' - mo phong bang cach dat status=RESOLVED truoc khi
    goi check_and_send_reminders o moc t=25p (dang le se nhac lan 3).

    Luu y: check_and_send_reminders() quet TOAN CUC (dung y that cua 1
    background job production, khong loc theo patient_id) - DB that co san
    vai dong OPEN tu cac phien thu tay/test truoc (demo-patient-01,
    test-patient-01, khong phai cua test nay, khong tu y xoa) - assertion
    phai loc theo escalation_id CU THE cua test nay, khong gia dinh DB rong."""
    db = SessionLocal()
    patient_id = f"test-reminder-resolved-{uuid.uuid4().hex[:8]}"
    notified_calls: list[tuple] = []

    async def spy_notify(target, patient_id_, dose_event_id, escalation_id, reminder_count):
        notified_calls.append((escalation_id, target, reminder_count))

    try:
        t0 = datetime(2026, 8, 9, 8, 0, 0, tzinfo=UTC)
        esc_id = _seed_open_escalation(db, patient_id, created_at=t0, reminder_count=2)  # da qua vong nhac lan 2

        # Benh nhan da duoc "resolved" luc t=20p (truoc khi t=25p toi)
        row = db.get(Escalation, esc_id)
        row.status = "RESOLVED"
        row.resolved_at = t0 + timedelta(minutes=20)
        row.resolved_by = "doctor"
        db.commit()

        # Gia lap thoi gian toi t=25p (dang le trigger nhac lan 3 neu VAN OPEN)
        await check_and_send_reminders(db, now=t0 + timedelta(minutes=25), notify_fn=spy_notify, patient_id=patient_id)

        calls_for_this_escalation = [c for c in notified_calls if c[0] == esc_id]
        assert calls_for_this_escalation == [], "escalation da RESOLVED khong duoc nhac lai"

        row = db.get(Escalation, esc_id)
        assert row.reminder_count == 2, "reminder_count khong duoc tang them sau khi da resolved"
    finally:
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_exhausting_all_4_reminders_does_not_auto_resolve():
    """Kickoff: 'Case: đủ 4 lần, không ai resolved → dừng gửi ở t=45p, nhưng
    query lại escalation vẫn thấy resolved=false (không tự đóng).' - o day
    la status VAN la 'OPEN' (khong tu chuyen RESOLVED)."""
    db = SessionLocal()
    patient_id = f"test-reminder-exhaust-{uuid.uuid4().hex[:8]}"
    notified_calls: list[tuple] = []

    async def spy_notify(target, patient_id_, dose_event_id, escalation_id, reminder_count):
        notified_calls.append((escalation_id, target, reminder_count))

    try:
        t0 = datetime(2026, 8, 9, 8, 0, 0, tzinfo=UTC)
        esc_id = _seed_open_escalation(db, patient_id, created_at=t0, reminder_count=1)

        # Gia lap tuan tu qua ca 3 moc nhac (t=15p, t=25p, t=35p), khong ai resolved
        await check_and_send_reminders(db, now=t0 + timedelta(minutes=15), notify_fn=spy_notify, patient_id=patient_id)
        await check_and_send_reminders(db, now=t0 + timedelta(minutes=25), notify_fn=spy_notify, patient_id=patient_id)
        await check_and_send_reminders(db, now=t0 + timedelta(minutes=35), notify_fn=spy_notify, patient_id=patient_id)

        row = db.get(Escalation, esc_id)
        assert row.reminder_count == 4, "phai dung o 4 (1 goc + 3 lan nhac)"
        calls_for_this_escalation = [c for c in notified_calls if c[0] == esc_id]
        assert len(calls_for_this_escalation) == 6, "3 lan nhac x 2 target (family+doctor) = 6 lan goi notify_fn"

        # Gia lap toi t=45p va xa hon - KHONG con nhac them, VA status KHONG
        # tu chuyen RESOLVED (dung y kickoff "khong tu dong").
        notified_calls.clear()
        await check_and_send_reminders(db, now=t0 + timedelta(minutes=45), notify_fn=spy_notify, patient_id=patient_id)
        await check_and_send_reminders(db, now=t0 + timedelta(minutes=100), notify_fn=spy_notify, patient_id=patient_id)
        assert [c for c in notified_calls if c[0] == esc_id] == [], "khong con nhac them sau reminder_count=4"

        row = db.get(Escalation, esc_id)
        assert row.status == "OPEN", "KHONG duoc tu dong chuyen RESOLVED chi vi het 4 lan nhac"
        assert row.reminder_count == 4, "khong tang qua 4"
        assert row.resolved_at is None
    finally:
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_notify_failure_on_one_target_does_not_block_the_other():
    """1 kenh loi (vd doctor push that bai) khong duoc lam mat lan nhac cua
    kenh con lai (family) - dung nguyen tac da ap dung cho trigger_emergency_
    escalation() goc (return_exceptions=True)."""
    db = SessionLocal()
    patient_id = f"test-reminder-partial-fail-{uuid.uuid4().hex[:8]}"
    notified_calls: list[tuple] = []

    async def flaky_notify(target, patient_id_, dose_event_id, escalation_id, reminder_count):
        if target == "doctor":
            raise RuntimeError("push doctor thất bại (mô phỏng)")
        notified_calls.append((escalation_id, target))

    try:
        t0 = datetime(2026, 8, 9, 8, 0, 0, tzinfo=UTC)
        esc_id = _seed_open_escalation(db, patient_id, created_at=t0, reminder_count=1)

        await check_and_send_reminders(db, now=t0 + timedelta(minutes=15), notify_fn=flaky_notify, patient_id=patient_id)

        calls_for_this_escalation = [c for c in notified_calls if c[0] == esc_id]
        assert calls_for_this_escalation == [(esc_id, "family")], "family van phai duoc goi du doctor loi"

        row = db.get(Escalation, esc_id)
        assert row.reminder_count == 2, "reminder_count van tang du 1 kenh loi"
    finally:
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()