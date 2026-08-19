"""PostgreSQL serialization coverage for the APP-5 runtime bridge."""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    DrugProduct,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    NotificationJob,
    SafetyEvent,
)
from backend.services.safety_policy_domain.runtime import process_dose_safety_runtime
from backend.services.safety_policy_domain.service import REVIEWED

DATABASE_URL = os.getenv("APP5_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set APP5_TEST_DATABASE_URL to a disposable migrated PostgreSQL database.",
)
NOW = datetime(2026, 8, 17, 3, tzinfo=UTC)


def test_runtime_serializes_assessment_and_escalation_per_occurrence() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_size=3, max_overflow=0)
    suffix = uuid4().hex
    product_id = f"app5-product-{suffix}"
    occurrence_id = f"app5-occurrence-{suffix}"
    policy_id = f"app5-policy-{suffix}"
    first_session = Session(engine, expire_on_commit=False)
    second_session = Session(engine, expire_on_commit=False)
    try:
        with Session(engine) as setup, setup.begin():
            setup.add(DrugProduct(id=product_id, display_name="APP-5 test product", status="ACTIVE"))
            setup.add(
                DoseOccurrence(
                    id=occurrence_id,
                    patient_id=f"app5-patient-{suffix}",
                    medication_plan_id=f"app5-plan-{suffix}",
                    drug_product_id=product_id,
                    scheduled_at=NOW - timedelta(hours=1),
                    status="MISSED",
                    generation_key=f"app5-generation-{suffix}",
                    metadata_json={},
                )
            )
            setup.add(
                MedicationSafetyPolicy(
                    id=policy_id,
                    scope_type="DRUG_PRODUCT",
                    scope_id=product_id,
                    risk_type="MISSED_DOSE",
                    risk_level="HIGH",
                    action_policy="ESCALATE_CLINICIAN",
                    source_type="CLINICAL_REVIEW",
                    review_status=REVIEWED,
                    policy_version=1,
                    valid_from=NOW - timedelta(days=1),
                )
            )

        first_transaction = first_session.begin()
        first = process_dose_safety_runtime(first_session, occurrence_id=occurrence_id, evaluated_at=NOW)
        finished = threading.Event()
        result: dict[str, object] = {}

        def run_retry() -> None:
            with second_session.begin():
                result["value"] = process_dose_safety_runtime(
                    second_session,
                    occurrence_id=occurrence_id,
                    evaluated_at=NOW + timedelta(minutes=1),
                )
            finished.set()

        worker = threading.Thread(target=run_retry)
        worker.start()
        assert not finished.wait(timeout=0.25), "second safety transaction did not wait for occurrence lock"
        first_transaction.commit()
        worker.join(timeout=5)
        assert finished.is_set(), "second safety transaction did not complete after the lock was released"
        assert first.assessment.created is True
        assert first.escalation.created is True
        assert result["value"].assessment.created is False
        assert result["value"].escalation.created is False

        with Session(engine) as verify:
            assert verify.execute(
                select(func.count()).select_from(MissedDoseAssessment).where(
                    MissedDoseAssessment.dose_occurrence_id == occurrence_id
                )
            ).scalar_one() == 1
            assert verify.execute(
                select(func.count()).select_from(SafetyEvent).where(
                    SafetyEvent.dose_occurrence_id == occurrence_id
                )
            ).scalar_one() == 2
            assert verify.execute(
                select(func.count()).select_from(NotificationJob).where(
                    NotificationJob.dose_occurrence_id == occurrence_id
                )
            ).scalar_one() == 1
            assert verify.execute(
                select(func.count()).select_from(DoseEventLog).where(
                    DoseEventLog.dose_occurrence_id == occurrence_id
                )
            ).scalar_one() == 2
    finally:
        first_session.rollback()
        second_session.rollback()
        first_session.close()
        second_session.close()
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.query(NotificationJob).filter(NotificationJob.dose_occurrence_id == occurrence_id).delete(
                synchronize_session=False
            )
            cleanup.query(DoseEventLog).filter(DoseEventLog.dose_occurrence_id == occurrence_id).delete(
                synchronize_session=False
            )
            cleanup.query(SafetyEvent).filter(SafetyEvent.dose_occurrence_id == occurrence_id).delete(
                synchronize_session=False
            )
            cleanup.query(MissedDoseAssessment).filter(
                MissedDoseAssessment.dose_occurrence_id == occurrence_id
            ).delete(synchronize_session=False)
            cleanup.query(DoseOccurrence).filter(DoseOccurrence.id == occurrence_id).delete(synchronize_session=False)
            cleanup.query(MedicationSafetyPolicy).filter(MedicationSafetyPolicy.id == policy_id).delete(
                synchronize_session=False
            )
            cleanup.query(DrugProduct).filter(DrugProduct.id == product_id).delete(synchronize_session=False)
        engine.dispose()
