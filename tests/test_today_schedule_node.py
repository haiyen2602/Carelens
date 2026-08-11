"""Phase 6 - build_today_schedule_node() nhanh hoi "hom nay toi uong thuoc
gi" (muc 6 thiet ke) - khong LLM, query dose_event that. Can Postgres that."""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.conversation_nodes import NO_SCHEDULE_TODAY_MESSAGE, build_today_schedule_node  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import DoseEvent, Prescription  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.mark.asyncio
async def test_today_schedule_lists_dose_events_for_the_right_patient_only():
    db = SessionLocal()
    patient_id = f"test-sched-{uuid.uuid4().hex[:8]}"
    other_patient_id = f"test-sched-other-{uuid.uuid4().hex[:8]}"
    try:
        presc = Prescription(
            patient_id=patient_id,
            doctor_id="doc-1",
            status="approved",
            items=[],
            start_date="2026-08-01",
            duration_days=7,
        )
        other_presc = Prescription(
            patient_id=other_patient_id,
            doctor_id="doc-1",
            status="approved",
            items=[],
            start_date="2026-08-01",
            duration_days=7,
        )
        db.add_all([presc, other_presc])
        db.commit()

        now = datetime.now(UTC)
        dose = DoseEvent(
            prescription_id=presc.id,
            patient_id=patient_id,
            scheduled_at=now,
            window_start=now,
            window_end=now,
            status="PENDING",
            expected_items=[{"drug_id": "d1", "ten_thuoc": "Panadol", "so_vien": 1}],
        )
        other_dose = DoseEvent(
            prescription_id=other_presc.id,
            patient_id=other_patient_id,
            scheduled_at=now,
            window_start=now,
            window_end=now,
            status="PENDING",
            expected_items=[{"drug_id": "d2", "ten_thuoc": "Thuốc Khác", "so_vien": 1}],
        )
        db.add_all([dose, other_dose])
        db.commit()

        node = build_today_schedule_node(db)
        result = await node({"patient_id": patient_id, "intent": "today_schedule", "utterance": "x", "trace": []})

        assert "Panadol" in result["response"]
        assert "Thuốc Khác" not in result["response"], "khong duoc lo lich cua benh nhan khac"
        entry = result["trace"][-1]
        assert entry["step"] == "today_schedule"
        assert entry["dose_event_count"] == 1
    finally:
        db.query(DoseEvent).filter(DoseEvent.patient_id.in_([patient_id, other_patient_id])).delete(
            synchronize_session=False
        )
        db.query(Prescription).filter(Prescription.patient_id.in_([patient_id, other_patient_id])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_today_schedule_no_events_gives_explicit_message_not_empty_string():
    db = SessionLocal()
    patient_id = f"test-sched-empty-{uuid.uuid4().hex[:8]}"
    try:
        node = build_today_schedule_node(db)
        result = await node({"patient_id": patient_id, "intent": "today_schedule", "utterance": "x", "trace": []})
        assert result["response"] == NO_SCHEDULE_TODAY_MESSAGE
        assert result["trace"][-1]["dose_event_count"] == 0
    finally:
        db.close()
