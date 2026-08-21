"""DB-4E tests for V2 clinician schedule persistence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    DrugIdMap,
    DrugProduct,
    MedicationPlan,
    NotificationJob,
    Patient,
    Prescription,
    PrescriptionItem,
    ScheduleRule,
    ScheduleRuleCycle,
    ScheduleRuleTime,
)
from backend.models.schemas import PrescriptionItemIn
from backend.services.scheduling.write_path import (
    activate_prescription_schedule,
    stop_prescription_schedule,
    sync_prescription_schedule,
)

TABLES = (
    Patient.__table__,
    Prescription.__table__,
    DrugProduct.__table__,
    DrugIdMap.__table__,
    PrescriptionItem.__table__,
    MedicationPlan.__table__,
    ScheduleRule.__table__,
    ScheduleRuleTime.__table__,
    ScheduleRuleCycle.__table__,
    DoseOccurrence.__table__,
    DoseEventLog.__table__,
    NotificationJob.__table__,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine)
    try:
        session.add(Patient(id="patient-1", full_name="Test patient", timezone="Asia/Ho_Chi_Minh"))
        session.add(
            DrugProduct(
                id="product-1",
                legacy_drug_id="legacy-1",
                display_name="Test product",
                status="ACTIVE",
            )
        )
        session.add(
            DrugIdMap(
                id="map-1",
                legacy_drug_id="legacy-1",
                drug_product_id="product-1",
                mapping_status="ACTIVE",
            )
        )
        session.commit()
        yield session
    finally:
        session.close()
        engine.dispose()


def _prescription(items: list[dict]) -> Prescription:
    return Prescription(
        id="prescription-1",
        patient_id="patient-1",
        doctor_id="doctor-1",
        status="draft",
        start_date="2026-08-17",
        duration_days=7,
        items=items,
    )


def _valid_item() -> dict:
    return {
        "drug_id": "legacy-1",
        "ten_thuoc": "Test product",
        "lieu_dung": "1 tablet",
        "thoi_diem_dung": "Sau ăn",
        "gio_nhac": ["08:00", "20:00"],
        "doses_per_day": 2,
        "has_cycle": True,
        "cycle_on_days": 5,
        "cycle_off_days": 2,
    }


def test_write_path_persists_valid_normalized_schedule_idempotently(db: Session) -> None:
    prescription = _prescription([_valid_item()])
    db.add(prescription)
    db.flush()

    sync_prescription_schedule(db, prescription)
    sync_prescription_schedule(db, prescription)
    activate_prescription_schedule(db, prescription.id)
    db.commit()

    item = db.execute(select(PrescriptionItem)).scalar_one()
    plan = db.execute(select(MedicationPlan)).scalar_one()
    rule = db.execute(select(ScheduleRule)).scalar_one()
    cycle = db.execute(select(ScheduleRuleCycle)).scalar_one()
    times = db.execute(select(ScheduleRuleTime).order_by(ScheduleRuleTime.local_time)).scalars().all()

    assert item.drug_product_id == "product-1"
    assert item.doses_per_day == 2
    assert item.meal_instruction_code == "AFTER_MEAL"
    assert item.start_date.isoformat() == "2026-08-17"
    assert item.end_date.isoformat() == "2026-08-23"
    assert plan.status == "ACTIVE"
    assert rule.status == "ACTIVE"
    assert [row.local_time.isoformat() for row in times] == ["08:00:00", "20:00:00"]
    assert (cycle.anchor_date.isoformat(), cycle.on_days, cycle.off_days) == ("2026-08-17", 5, 2)
    assert db.execute(select(DoseOccurrence)).scalars().all() == []


def test_unresolved_or_invalid_schedule_stays_review_required(db: Session) -> None:
    invalid = _valid_item() | {
        "drug_id": "unknown-drug",
        "gio_nhac": ["08:00", "08:00"],
        "doses_per_day": 2,
    }
    prescription = _prescription([invalid])
    db.add(prescription)
    db.flush()

    sync_prescription_schedule(db, prescription)
    activate_prescription_schedule(db, prescription.id)
    db.commit()

    assert db.execute(select(PrescriptionItem)).scalar_one().status == "REVIEW_REQUIRED"
    assert db.execute(select(MedicationPlan)).scalar_one().status == "REVIEW_REQUIRED"
    assert db.execute(select(ScheduleRule)).scalar_one().status == "REVIEW_REQUIRED"
    assert db.execute(select(ScheduleRuleTime)).scalars().all() == []


def test_caller_transaction_rolls_back_all_v2_rows(db: Session) -> None:
    prescription = _prescription([_valid_item()])
    db.add(prescription)
    db.commit()

    with pytest.raises(RuntimeError), db.begin():
        sync_prescription_schedule(db, prescription)
        raise RuntimeError("force rollback")

    assert db.execute(select(PrescriptionItem)).scalars().all() == []
    assert db.execute(select(MedicationPlan)).scalars().all() == []
    assert db.execute(select(ScheduleRule)).scalars().all() == []
    assert db.execute(select(ScheduleRuleTime)).scalars().all() == []
    assert db.execute(select(ScheduleRuleCycle)).scalars().all() == []


def test_legacy_request_remains_valid_without_db4e_fields() -> None:
    item = PrescriptionItemIn.model_validate(
        {
            # `drug_id` bat buoc tu 2026-08-20 (FB-14) - khong lien quan den
            # muc dich cua test nay (client cu duoc phep bo qua truong DB-4E),
            # chi la dieu kien de payload qua duoc validation.
            "drug_id": "legacy-compatible-medicine",
            "ten_thuoc": "Legacy-compatible medicine",
            "lieu_dung": "1 tablet",
            "gio_nhac": ["08:00"],
        }
    )

    assert item.doses_per_day is None
    assert item.has_cycle is False
    assert item.cycle_on_days is None
    assert item.cycle_off_days is None


def test_stop_marks_v2_schedule_intent_without_occurrences(db: Session) -> None:
    prescription = _prescription([_valid_item()])
    db.add(prescription)
    db.flush()
    sync_prescription_schedule(db, prescription)
    activate_prescription_schedule(db, prescription.id)

    stop_prescription_schedule(db, prescription.id)
    db.commit()

    assert db.execute(select(PrescriptionItem)).scalar_one().status == "STOPPED"
    assert db.execute(select(MedicationPlan)).scalar_one().status == "STOPPED"
    assert db.execute(select(ScheduleRule)).scalar_one().status == "STOPPED"


def test_stop_cancels_future_v2_occurrence_and_preserves_history(db: Session) -> None:
    prescription = _prescription([_valid_item()])
    db.add(prescription)
    db.flush()
    sync_prescription_schedule(db, prescription)
    item = db.execute(select(PrescriptionItem)).scalar_one()
    db.add(
        DoseOccurrence(
            id="occurrence-1",
            prescription_item_id=item.id,
                patient_id="patient-1",
                scheduled_at=datetime(2026, 8, 17, 1, tzinfo=UTC),
                status="SCHEDULED",
                generation_key="test-occurrence-1",
        )
    )
    db.commit()

    cancelled = stop_prescription_schedule(
        db, prescription.id, event_at=datetime(2026, 8, 16, 1, tzinfo=UTC)
    )

    assert cancelled == 1
    assert db.get(DoseOccurrence, "occurrence-1").status == "CANCELLED"
    assert db.execute(select(PrescriptionItem)).scalar_one().status == "STOPPED"
