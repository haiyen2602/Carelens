"""APP-4 tests for the legacy-compatible V2 patient dose adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import DoseEventLog, DoseOccurrence, NotificationJob, Prescription, PrescriptionItem
from backend.services.scheduling.dose_state import TAKEN
from backend.services.scheduling.errors import InvalidDoseTransitionError
from backend.services.scheduling.runtime_adapter import (
    list_v2_dose_groups,
    transition_v2_dose_group,
)

TABLES = (
    Prescription.__table__,
    PrescriptionItem.__table__,
    DoseOccurrence.__table__,
    DoseEventLog.__table__,
    NotificationJob.__table__,
)
SCHEDULED_AT = datetime(2026, 8, 17, 1, tzinfo=UTC)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _grouped_occurrences(db: Session) -> tuple[DoseOccurrence, DoseOccurrence]:
    prescription = Prescription(
        id="prescription-1",
        patient_id="patient-1",
        doctor_id="doctor-1",
        status="active",
        start_date="2026-08-17",
        duration_days=1,
        items=[
            {"drug_id": "legacy-1", "ten_thuoc": "Drug one", "so_vien_moi_lan": 1},
            {"drug_id": "legacy-2", "ten_thuoc": "Drug two", "so_vien_moi_lan": 2},
        ],
    )
    items = [
        PrescriptionItem(
            id="item-1",
            prescription_id=prescription.id,
            patient_id=prescription.patient_id,
            legacy_drug_id="legacy-1",
            drug_display_name="Drug one",
            migration_item_index=0,
        ),
        PrescriptionItem(
            id="item-2",
            prescription_id=prescription.id,
            patient_id=prescription.patient_id,
            legacy_drug_id="legacy-2",
            drug_display_name="Drug two",
            migration_item_index=1,
        ),
    ]
    occurrences = [
        DoseOccurrence(
            id="occurrence-1",
            prescription_item_id="item-1",
            patient_id="patient-1",
            scheduled_at=SCHEDULED_AT,
            scheduled_local_date=date(2026, 8, 17),
            scheduled_local_time=time(8),
            timezone="Asia/Ho_Chi_Minh",
            status="SCHEDULED",
            generation_key="generation-1",
        ),
        DoseOccurrence(
            id="occurrence-2",
            prescription_item_id="item-2",
            patient_id="patient-1",
            scheduled_at=SCHEDULED_AT,
            scheduled_local_date=date(2026, 8, 17),
            scheduled_local_time=time(8),
            timezone="Asia/Ho_Chi_Minh",
            status="SCHEDULED",
            generation_key="generation-2",
        ),
    ]
    db.add_all((prescription, *items, *occurrences))
    db.commit()
    return tuple(occurrences)


def test_adapter_groups_multiple_drugs_without_losing_legacy_dto_fields(db: Session) -> None:
    _grouped_occurrences(db)

    groups = list_v2_dose_groups(db, patient_id="patient-1")

    assert len(groups) == 1
    assert groups[0].status == "PENDING"
    assert [item["so_vien"] for item in groups[0].expected_items] == [1, 2]
    assert groups[0].scheduled_at == SCHEDULED_AT


def test_adapter_transitions_every_occurrence_in_group_atomically(db: Session) -> None:
    _grouped_occurrences(db)
    group = list_v2_dose_groups(db, patient_id="patient-1")[0]

    updated = transition_v2_dose_group(
        db,
        dose_group_id=group.id,
        target_status=TAKEN,
        event_at=SCHEDULED_AT,
        source="PATIENT_DOSE_API",
        actor_type="PATIENT",
        actor_id="patient-1",
    )

    assert updated.status == TAKEN
    assert {row.status for row in db.execute(select(DoseOccurrence)).scalars()} == {TAKEN}
    assert db.execute(select(DoseEventLog)).scalars().all()


def test_adapter_fails_closed_for_divergent_group_statuses(db: Session) -> None:
    first, second = _grouped_occurrences(db)
    first.status = "TAKEN"
    second.status = "SCHEDULED"
    db.commit()

    with pytest.raises(InvalidDoseTransitionError, match="phân kỳ"):
        list_v2_dose_groups(db, patient_id="patient-1")
