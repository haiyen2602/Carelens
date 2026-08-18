"""APP-6 clean-PostgreSQL comparison of legacy and V2 schedule projections."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.config import get_settings
from backend.db.base import SessionLocal, engine
from backend.db.models import (
    DoseEvent,
    DoseEventLog,
    DoseOccurrence,
    MedicationPlan,
    NotificationJob,
    Patient,
    Prescription,
    PrescriptionItem,
    ScheduleRule,
    ScheduleRuleCycle,
    ScheduleRuleTime,
)
from backend.services.drug_knowledge.v2_agent import get_v2_agent_knowledge_service
from backend.services.prescription.service import duyet_phac_do, tao_phac_do
from backend.services.scheduling.occurrence_generator import generate_prescription_dose_occurrences
from backend.services.scheduling.runtime_adapter import list_v2_dose_groups


def _database_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM drug_product LIMIT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(),
    reason="Requires a migrated PostgreSQL database with imported Final Canonical V2 artifacts.",
)


def test_shadow_prescription_schedule_matches_legacy_grouped_projection(monkeypatch) -> None:
    """Compare the same approved prescription without making legacy reads V2-primary."""

    monkeypatch.setenv("DRUG_KNOWLEDGE_BACKEND", "v2")
    monkeypatch.setenv("PRESCRIPTION_V2_MODE", "shadow")
    monkeypatch.setenv("DOSE_RUNTIME_MODE", "shadow")
    monkeypatch.setenv("SAFETY_RUNTIME_MODE", "legacy")
    get_settings.cache_clear()
    db = SessionLocal()
    patient_id = f"app6-patient-{uuid.uuid4().hex}"
    prescription_id: str | None = None
    try:
        products = get_v2_agent_knowledge_service().catalog_items[:2]
        assert len(products) == 2
        db.add(Patient(id=patient_id, full_name="APP-6 shadow comparison"))
        db.commit()
        start_date = (date.today() + timedelta(days=1)).isoformat()
        items = [
            {
                "drug_id": product.id,
                "ten_thuoc": product.ten_thuoc,
                "lieu_dung": "1 dose",
                "thoi_diem_dung": "Sau ăn",
                "so_vien_moi_lan": index + 1,
                "gio_nhac": ["08:00"],
                "doses_per_day": 1,
            }
            for index, product in enumerate(products)
        ]
        prescription = tao_phac_do(
            db,
            patient_id=patient_id,
            doctor_id="app6-doctor",
            items=items,
            start_date=start_date,
            duration_days=2,
        )
        prescription_id = prescription.id
        duyet_phac_do(db, prescription_id, doctor_id="app6-doctor")

        legacy_rows = (
            db.query(DoseEvent)
            .filter(DoseEvent.prescription_id == prescription_id)
            .order_by(DoseEvent.scheduled_at)
            .all()
        )
        v2_groups = list_v2_dose_groups(db, patient_id=patient_id)
        v2_rows = db.query(DoseOccurrence).filter(DoseOccurrence.patient_id == patient_id).all()

        assert len(legacy_rows) == 2
        assert len(v2_rows) == 4
        assert len(v2_groups) == len(legacy_rows)
        assert [group.scheduled_at for group in v2_groups] == [row.scheduled_at for row in legacy_rows]
        assert all(group.status == "PENDING" for group in v2_groups)
        assert all(row.status == "PENDING" for row in legacy_rows)
        assert [
            [item["drug_id"] for item in group.expected_items] for group in v2_groups
        ] == [[item["drug_id"] for item in row.expected_items] for row in legacy_rows]

        retried = generate_prescription_dose_occurrences(
            db,
            prescription_id=prescription_id,
            now=datetime.now(UTC),
        )
        db.commit()
        assert (retried.inserted, retried.existing) == (0, 4)
        assert db.query(DoseOccurrence).filter(DoseOccurrence.patient_id == patient_id).count() == 4
    finally:
        item_ids = [row[0] for row in db.query(PrescriptionItem.id).filter(PrescriptionItem.patient_id == patient_id).all()]
        plan_ids = [row[0] for row in db.query(MedicationPlan.id).filter(MedicationPlan.patient_id == patient_id).all()]
        rule_ids = (
            [row[0] for row in db.query(ScheduleRule.id).filter(ScheduleRule.medication_plan_id.in_(plan_ids)).all()]
            if plan_ids
            else []
        )
        db.query(NotificationJob).filter(NotificationJob.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseEventLog).filter(DoseEventLog.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseOccurrence).filter(DoseOccurrence.patient_id == patient_id).delete(synchronize_session=False)
        if rule_ids:
            db.query(ScheduleRuleTime).filter(ScheduleRuleTime.schedule_rule_id.in_(rule_ids)).delete(
                synchronize_session=False
            )
            db.query(ScheduleRuleCycle).filter(ScheduleRuleCycle.schedule_rule_id.in_(rule_ids)).delete(
                synchronize_session=False
            )
            db.query(ScheduleRule).filter(ScheduleRule.id.in_(rule_ids)).delete(synchronize_session=False)
        if plan_ids:
            db.query(MedicationPlan).filter(MedicationPlan.id.in_(plan_ids)).delete(synchronize_session=False)
        if item_ids:
            db.query(PrescriptionItem).filter(PrescriptionItem.id.in_(item_ids)).delete(synchronize_session=False)
        if prescription_id:
            db.query(DoseEvent).filter(DoseEvent.prescription_id == prescription_id).delete(synchronize_session=False)
            db.query(Prescription).filter(Prescription.id == prescription_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()
        get_settings.cache_clear()
