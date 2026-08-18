"""APP-5 integration coverage from V2 dose state through safety outbox."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    DrugProduct,
    DrugProductIngredient,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    NotificationJob,
    Prescription,
    PrescriptionItem,
    SafetyEvent,
)
from backend.services.safety_policy_domain.service import REVIEWED
from backend.services.scheduling.dose_state import MISSED
from backend.services.scheduling.runtime_adapter import list_v2_dose_groups, transition_v2_dose_group

SCHEDULED_AT = datetime(2026, 8, 17, 1, tzinfo=UTC)
TABLES = (
    Prescription.__table__,
    PrescriptionItem.__table__,
    DrugProduct.__table__,
    DrugProductIngredient.__table__,
    DoseOccurrence.__table__,
    MedicationSafetyPolicy.__table__,
    MissedDoseAssessment.__table__,
    SafetyEvent.__table__,
    DoseEventLog.__table__,
    NotificationJob.__table__,
)


def test_missed_group_runs_audited_safety_only_in_shadow(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    db = Session(engine, expire_on_commit=False)
    monkeypatch.setenv("SAFETY_RUNTIME_MODE", "shadow")
    get_settings.cache_clear()
    try:
        db.add(DrugProduct(id="product-1", display_name="Runtime drug", status="ACTIVE"))
        db.add(
            Prescription(
                id="prescription-1",
                patient_id="patient-1",
                doctor_id="doctor-1",
                status="active",
                start_date="2026-08-17",
                duration_days=1,
                items=[{"drug_id": "legacy-1", "ten_thuoc": "Runtime drug"}],
            )
        )
        db.add(
            PrescriptionItem(
                id="item-1",
                prescription_id="prescription-1",
                patient_id="patient-1",
                drug_product_id="product-1",
                legacy_drug_id="legacy-1",
                migration_item_index=0,
            )
        )
        db.add(
            DoseOccurrence(
                id="occurrence-1",
                prescription_item_id="item-1",
                patient_id="patient-1",
                drug_product_id="product-1",
                scheduled_at=SCHEDULED_AT,
                scheduled_local_date=date(2026, 8, 17),
                scheduled_local_time=time(8),
                timezone="Asia/Ho_Chi_Minh",
                status="SCHEDULED",
                generation_key="runtime-safety-occurrence-1",
            )
        )
        db.add(
            MedicationSafetyPolicy(
                id="reviewed-policy",
                scope_type="DRUG_PRODUCT",
                scope_id="product-1",
                risk_type="MISSED_DOSE",
                risk_level="HIGH",
                action_policy="ESCALATE_CLINICIAN",
                source_type="CLINICAL_REVIEW",
                review_status=REVIEWED,
                policy_version=1,
                valid_from=SCHEDULED_AT - timedelta(days=1),
            )
        )
        db.commit()
        group = list_v2_dose_groups(db, patient_id="patient-1")[0]

        transition_v2_dose_group(
            db,
            dose_group_id=group.id,
            target_status=MISSED,
            event_at=SCHEDULED_AT + timedelta(hours=1),
            source="PATIENT_DOSE_API",
            actor_type="PATIENT",
            actor_id="patient-1",
        )
        db.commit()

        assert db.get(DoseOccurrence, "occurrence-1").status == MISSED
        assert db.execute(select(MissedDoseAssessment)).scalar_one().risk_level == "HIGH"
        decisions = db.execute(select(SafetyEvent).order_by(SafetyEvent.event_type)).scalars().all()
        assert [event.event_type for event in decisions] == ["MISSED_DOSE_ASSESSED", "SAFETY_ESCALATION_DECIDED"]
        assert db.execute(select(NotificationJob)).scalar_one().recipient_type == "CLINICIAN"
        assert len(db.execute(select(DoseEventLog)).scalars().all()) == 4
    finally:
        db.close()
        engine.dispose()
        get_settings.cache_clear()
