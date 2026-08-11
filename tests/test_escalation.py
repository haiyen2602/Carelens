"""Phase 6 - build_db_escalate_fn() phai ghi THAT vao bang `escalation`
(api-contracts.md §6/§8), gop 2 lan goi (family, doctor) tu
trigger_emergency_escalation() thanh DUNG 1 dong voi notified=["caregiver",
"doctor"] - khong phai 2 dong trung lap. Can Postgres that."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Escalation  # noqa: E402
from backend.services.escalation import build_db_escalate_fn, trigger_emergency_escalation  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.fixture
def db_session():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.mark.asyncio
async def test_trigger_emergency_escalation_writes_one_row_with_both_targets_notified(db_session):
    patient_id = f"test-esc-patient-{uuid.uuid4().hex[:8]}"
    dose_event_id = f"test-esc-dose-{uuid.uuid4().hex[:8]}"
    escalate_fn = build_db_escalate_fn(db_session)

    await trigger_emergency_escalation(
        escalate_fn,
        patient_id,
        dose_event_id,
        severity="Nguy hiểm",
        urgent=True,
        trigger="safety_redflag",
        reason="test redflag",
    )

    rows = db_session.execute(select(Escalation).where(Escalation.patient_id == patient_id)).scalars().all()
    assert len(rows) == 1, f"phai gop thanh 1 dong Escalation, khong phai {len(rows)}"
    row = rows[0]
    assert set(row.notified) == {"caregiver", "doctor"}
    assert row.severity == "HIGH", "phai chuyen doi Nguy hiem -> HIGH (api-contracts.md quy uoc tieng Anh)"
    assert row.trigger == "safety_redflag"
    assert row.status == "OPEN"
    assert row.dose_event_id == dose_event_id

    db_session.delete(row)
    db_session.commit()


@pytest.mark.asyncio
async def test_medium_severity_maps_to_english_and_missed_dose_trigger(db_session):
    patient_id = f"test-esc-patient-{uuid.uuid4().hex[:8]}"
    escalate_fn = build_db_escalate_fn(db_session)

    await trigger_emergency_escalation(
        escalate_fn,
        patient_id,
        None,
        severity="Trung bình",
        urgent=False,
        trigger="missed_dose",
        reason="test medium",
    )

    row = db_session.execute(select(Escalation).where(Escalation.patient_id == patient_id)).scalar_one()
    assert row.severity == "MEDIUM"
    assert row.trigger == "missed_dose"
    assert set(row.notified) == {"caregiver", "doctor"}

    db_session.delete(row)
    db_session.commit()


@pytest.mark.asyncio
async def test_two_separate_events_never_get_merged_into_same_row(db_session):
    """2 patient_id KHAC NHAU escalate cung luc - khong duoc lan vao nhau
    (dict `_pending` trong closure phai phan biet dung theo key)."""
    patient_a = f"test-esc-a-{uuid.uuid4().hex[:8]}"
    patient_b = f"test-esc-b-{uuid.uuid4().hex[:8]}"
    escalate_fn = build_db_escalate_fn(db_session)

    await trigger_emergency_escalation(escalate_fn, patient_a, None, "Nguy hiểm", True, "safety_redflag", "a")
    await trigger_emergency_escalation(escalate_fn, patient_b, None, "Nguy hiểm", True, "safety_redflag", "b")

    rows_a = db_session.execute(select(Escalation).where(Escalation.patient_id == patient_a)).scalars().all()
    rows_b = db_session.execute(select(Escalation).where(Escalation.patient_id == patient_b)).scalars().all()
    assert len(rows_a) == 1
    assert len(rows_b) == 1
    assert set(rows_a[0].notified) == {"caregiver", "doctor"}
    assert set(rows_b[0].notified) == {"caregiver", "doctor"}

    for row in [*rows_a, *rows_b]:
        db_session.delete(row)
    db_session.commit()
