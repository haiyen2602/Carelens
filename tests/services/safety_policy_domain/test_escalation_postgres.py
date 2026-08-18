"""Opt-in PostgreSQL row-lock test for the DB-4I escalation boundary.

Run only against a disposable migrated database by setting
``DB4I_TEST_DATABASE_URL``.  The test intentionally does not fall back to the
developer's normal ``DATABASE_URL``.
"""

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
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    NotificationJob,
    SafetyEvent,
)
from backend.services.safety_policy_domain.escalation import ESCALATE_CLINICIAN, process_safety_escalation
from backend.services.safety_policy_domain.service import LEGACY_CATEGORY_RULE, LEGACY_UNREVIEWED, REVIEWED

DATABASE_URL = os.getenv("DB4I_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set DB4I_TEST_DATABASE_URL to a disposable migrated PostgreSQL database.",
)
NOW = datetime(2026, 8, 17, 2, 30, tzinfo=UTC)


def test_postgres_escalation_is_idempotent_and_serializes_by_assessment() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_size=3, max_overflow=0)
    suffix = uuid4().hex
    occurrence_id = f"db4i-occurrence-{suffix}"
    policy_id = f"db4i-policy-{suffix}"
    assessment_id = f"db4i-assessment-{suffix}"
    patient_id = f"db4i-patient-{suffix}"

    try:
        with Session(engine) as setup, setup.begin():
            setup.add(
                DoseOccurrence(
                    id=occurrence_id,
                    patient_id=patient_id,
                    medication_plan_id=f"db4i-plan-{suffix}",
                    drug_product_id=f"db4i-product-{suffix}",
                    scheduled_at=NOW - timedelta(minutes=30),
                    status="MISSED",
                    generation_key=f"db4i-generation-{suffix}",
                    metadata_json={},
                )
            )
            setup.add(
                MedicationSafetyPolicy(
                    id=policy_id,
                    scope_type="DRUG_PRODUCT",
                    scope_id=f"db4i-product-{suffix}",
                    risk_type="MISSED_DOSE",
                    risk_level="HIGH",
                    action_policy=ESCALATE_CLINICIAN,
                    source_type="CLINICAL_REVIEW",
                    review_status=REVIEWED,
                    policy_version=1,
                    valid_from=NOW - timedelta(days=1),
                )
            )
            setup.add(
                MissedDoseAssessment(
                    id=assessment_id,
                    patient_id=patient_id,
                    dose_occurrence_id=occurrence_id,
                    medication_plan_id=f"db4i-plan-{suffix}",
                    drug_product_id=f"db4i-product-{suffix}",
                    risk_type="MISSED_DOSE",
                    risk_level="HIGH",
                    recommended_action=ESCALATE_CLINICIAN,
                    policy_id=policy_id,
                    policy_source_type="CLINICAL_REVIEW",
                    policy_review_status=REVIEWED,
                    reason_code="DB4I_POSTGRES_TEST",
                    assessment_version="DB4H_SAFETY_V1",
                    evaluator="POLICY_ENGINE",
                    evaluated_at=NOW,
                    idempotency_key=f"db4i-assessment-key-{suffix}",
                )
            )

        first_session = Session(engine, expire_on_commit=False)
        first_transaction = first_session.begin()
        first = process_safety_escalation(first_session, assessment_id=assessment_id, decided_at=NOW)
        finished = threading.Event()
        result: dict[str, object] = {}

        def rerun_in_second_session() -> None:
            with Session(engine, expire_on_commit=False) as second_session, second_session.begin():
                result["result"] = process_safety_escalation(
                    second_session,
                    assessment_id=assessment_id,
                    decided_at=NOW + timedelta(minutes=1),
                )
            finished.set()

        worker = threading.Thread(target=rerun_in_second_session)
        worker.start()
        assert not finished.wait(timeout=0.25), "second transaction was not blocked by the assessment row lock"
        first_transaction.commit()
        first_session.close()
        worker.join(timeout=5)
        assert finished.is_set(), "second transaction did not complete after the row lock was released"
        assert first.created is True
        assert result["result"].created is False

        with Session(engine) as verify:
            assert verify.execute(
                select(func.count()).select_from(SafetyEvent).where(SafetyEvent.missed_dose_assessment_id == assessment_id)
            ).scalar_one() == 1
            assert verify.execute(
                select(func.count()).select_from(DoseEventLog).where(DoseEventLog.dose_occurrence_id == occurrence_id)
            ).scalar_one() == 1
            assert verify.execute(
                select(func.count())
                .select_from(NotificationJob)
                .where(NotificationJob.dose_occurrence_id == occurrence_id)
            ).scalar_one() == 1
    finally:
        engine.dispose()


def test_postgres_legacy_policy_fails_closed_and_rolls_back() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    suffix = uuid4().hex
    occurrence_id = f"db4i-legacy-occurrence-{suffix}"
    policy_id = f"db4i-legacy-policy-{suffix}"
    assessment_id = f"db4i-legacy-assessment-{suffix}"
    patient_id = f"db4i-legacy-patient-{suffix}"

    try:
        with Session(engine) as setup, setup.begin():
            setup.add(
                DoseOccurrence(
                    id=occurrence_id,
                    patient_id=patient_id,
                    scheduled_at=NOW - timedelta(minutes=30),
                    status="MISSED",
                    generation_key=f"db4i-legacy-generation-{suffix}",
                    metadata_json={},
                )
            )
            setup.add(
                MedicationSafetyPolicy(
                    id=policy_id,
                    scope_type="CATEGORY",
                    scope_id=f"db4i-legacy-category-{suffix}",
                    risk_type="MISSED_DOSE",
                    risk_level="HIGH",
                    action_policy=ESCALATE_CLINICIAN,
                    source_type=LEGACY_CATEGORY_RULE,
                    review_status=LEGACY_UNREVIEWED,
                    policy_version=1,
                    valid_from=NOW - timedelta(days=1),
                )
            )
            setup.add(
                MissedDoseAssessment(
                    id=assessment_id,
                    patient_id=patient_id,
                    dose_occurrence_id=occurrence_id,
                    drug_product_id=f"db4i-legacy-product-{suffix}",
                    risk_type="MISSED_DOSE",
                    risk_level="HIGH",
                    recommended_action=ESCALATE_CLINICIAN,
                    policy_id=policy_id,
                    policy_source_type=LEGACY_CATEGORY_RULE,
                    policy_review_status=LEGACY_UNREVIEWED,
                    reason_code="DB4I_LEGACY_POSTGRES_TEST",
                    assessment_version="DB4H_SAFETY_V1",
                    evaluator="POLICY_ENGINE",
                    evaluated_at=NOW,
                    idempotency_key=f"db4i-legacy-assessment-key-{suffix}",
                )
            )

        with pytest.raises(RuntimeError), Session(engine) as rollback_session, rollback_session.begin():
            process_safety_escalation(rollback_session, assessment_id=assessment_id, decided_at=NOW)
            raise RuntimeError("force rollback")

        with Session(engine) as verify:
            assert verify.execute(
                select(func.count()).select_from(SafetyEvent).where(SafetyEvent.missed_dose_assessment_id == assessment_id)
            ).scalar_one() == 0
            assert verify.execute(
                select(func.count()).select_from(DoseEventLog).where(DoseEventLog.dose_occurrence_id == occurrence_id)
            ).scalar_one() == 0
            assert verify.execute(
                select(func.count())
                .select_from(NotificationJob)
                .where(NotificationJob.dose_occurrence_id == occurrence_id)
            ).scalar_one() == 0

        with Session(engine) as rerun, rerun.begin():
            result = process_safety_escalation(rerun, assessment_id=assessment_id, decided_at=NOW)
            assert result.safety_event.decision == "REQUIRE_MEDICAL_REVIEW"
            assert result.notification_job is None
    finally:
        engine.dispose()
