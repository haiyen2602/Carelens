"""DB-4I escalation-decision and notification-outbox boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    NotificationJob,
    SafetyEvent,
)
from backend.services.safety_policy_domain.escalation import (
    ESCALATE_CAREGIVER,
    ESCALATE_CLINICIAN,
    LOG_ONLY,
    REQUIRE_MEDICAL_REVIEW,
    WARN,
    process_safety_escalation,
)
from backend.services.safety_policy_domain.service import LEGACY_CATEGORY_RULE, LEGACY_UNREVIEWED, REVIEWED

TABLES = (
    DoseOccurrence.__table__,
    MedicationSafetyPolicy.__table__,
    MissedDoseAssessment.__table__,
    SafetyEvent.__table__,
    DoseEventLog.__table__,
    NotificationJob.__table__,
)
NOW = datetime(2026, 8, 17, 2, 0, tzinfo=UTC)


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


def _occurrence(db: Session, occurrence_id: str = "occurrence-1") -> DoseOccurrence:
    occurrence = DoseOccurrence(
        id=occurrence_id,
        patient_id="patient-1",
        medication_plan_id="plan-1",
        drug_product_id="product-1",
        scheduled_at=NOW - timedelta(minutes=30),
        status="MISSED",
        generation_key=f"generation-{occurrence_id}",
        metadata_json={},
    )
    db.add(occurrence)
    return occurrence


def _policy(
    db: Session,
    *,
    policy_id: str = "policy-1",
    risk_level: str = "LOW",
    action: str = LOG_ONLY,
    source_type: str = "CLINICAL_REVIEW",
    review_status: str = REVIEWED,
) -> MedicationSafetyPolicy:
    policy = MedicationSafetyPolicy(
        id=policy_id,
        scope_type="DRUG_PRODUCT",
        scope_id="product-1",
        risk_type="MISSED_DOSE",
        risk_level=risk_level,
        action_policy=action,
        source_type=source_type,
        review_status=review_status,
        policy_version=1,
        valid_from=NOW - timedelta(days=1),
    )
    db.add(policy)
    return policy


def _assessment(
    db: Session,
    *,
    assessment_id: str = "assessment-1",
    occurrence_id: str = "occurrence-1",
    policy: MedicationSafetyPolicy | None,
    risk_level: str = "LOW",
    action: str = LOG_ONLY,
    policy_source_type: str | None = "CLINICAL_REVIEW",
    policy_review_status: str | None = REVIEWED,
    drug_product_id: str | None = "product-1",
) -> MissedDoseAssessment:
    assessment = MissedDoseAssessment(
        id=assessment_id,
        patient_id="patient-1",
        dose_occurrence_id=occurrence_id,
        medication_plan_id="plan-1",
        drug_product_id=drug_product_id,
        risk_type="MISSED_DOSE",
        risk_level=risk_level,
        recommended_action=action,
        policy_id=policy.id if policy else None,
        policy_source_type=policy_source_type,
        policy_review_status=policy_review_status,
        reason_code="TEST_ASSESSMENT",
        assessment_version="DB4H_SAFETY_V1",
        evaluator="POLICY_ENGINE",
        evaluated_at=NOW,
        idempotency_key=f"assessment:{assessment_id}",
    )
    db.add(assessment)
    return assessment


@pytest.mark.parametrize(
    ("risk_level", "action", "expected_action", "recipient_type"),
    [
        ("LOW", LOG_ONLY, LOG_ONLY, None),
        ("LOW", ESCALATE_CAREGIVER, REQUIRE_MEDICAL_REVIEW, None),
        ("MODERATE", ESCALATE_CAREGIVER, ESCALATE_CAREGIVER, "CAREGIVER"),
        ("HIGH", ESCALATE_CLINICIAN, ESCALATE_CLINICIAN, "CLINICIAN"),
        ("UNKNOWN", WARN, REQUIRE_MEDICAL_REVIEW, None),
    ],
)
def test_risk_action_matrix_only_creates_permitted_outbox(
    db: Session, risk_level: str, action: str, expected_action: str, recipient_type: str | None
) -> None:
    _occurrence(db)
    policy = _policy(db, risk_level=risk_level, action=action)
    _assessment(db, policy=policy, risk_level=risk_level, action=action)

    result = process_safety_escalation(db, assessment_id="assessment-1", decided_at=NOW)

    assert result.safety_event.decision == expected_action
    assert result.notification_job is None if recipient_type is None else result.notification_job is not None
    if recipient_type is not None:
        assert result.notification_job.recipient_type == recipient_type
    assert db.execute(select(DoseEventLog)).scalar_one().event_type == "SAFETY_ESCALATION_DECIDED"


def test_legacy_unreviewed_fallback_cannot_auto_escalate(db: Session) -> None:
    _occurrence(db)
    policy = _policy(
        db,
        risk_level="HIGH",
        action=ESCALATE_CLINICIAN,
        source_type=LEGACY_CATEGORY_RULE,
        review_status=LEGACY_UNREVIEWED,
    )
    _assessment(
        db,
        policy=policy,
        risk_level="HIGH",
        action=ESCALATE_CLINICIAN,
        policy_source_type=LEGACY_CATEGORY_RULE,
        policy_review_status=LEGACY_UNREVIEWED,
    )

    result = process_safety_escalation(db, assessment_id="assessment-1", decided_at=NOW)

    assert result.safety_event.decision == REQUIRE_MEDICAL_REVIEW
    assert result.safety_event.reason == "POLICY_NOT_AUTO_ESCALATABLE"
    assert result.notification_job is None


def test_missing_drug_identity_cannot_auto_escalate(db: Session) -> None:
    _occurrence(db)
    policy = _policy(db, risk_level="HIGH", action=ESCALATE_CLINICIAN)
    _assessment(
        db,
        policy=policy,
        risk_level="HIGH",
        action=ESCALATE_CLINICIAN,
        drug_product_id=None,
    )

    result = process_safety_escalation(db, assessment_id="assessment-1", decided_at=NOW)

    assert result.safety_event.decision == REQUIRE_MEDICAL_REVIEW
    assert result.safety_event.reason == "AMBIGUOUS_DRUG_ID"
    assert result.notification_job is None


def test_rerun_creates_one_event_log_and_notification_job(db: Session) -> None:
    _occurrence(db)
    policy = _policy(db, risk_level="HIGH", action=ESCALATE_CLINICIAN)
    _assessment(db, policy=policy, risk_level="HIGH", action=ESCALATE_CLINICIAN)

    first = process_safety_escalation(db, assessment_id="assessment-1", decided_at=NOW)
    second = process_safety_escalation(db, assessment_id="assessment-1", decided_at=NOW + timedelta(minutes=1))

    assert (first.created, second.created) == (True, False)
    assert db.execute(select(SafetyEvent)).scalars().all() == [first.safety_event]
    assert db.execute(select(DoseEventLog)).scalars().all()[0].event_type == "SAFETY_ESCALATION_DECIDED"
    assert db.execute(select(NotificationJob)).scalars().all() == [first.notification_job]


def test_escalation_rows_roll_back_as_one_transaction(db: Session) -> None:
    _occurrence(db)
    policy = _policy(db, risk_level="MODERATE", action=ESCALATE_CAREGIVER)
    _assessment(db, policy=policy, risk_level="MODERATE", action=ESCALATE_CAREGIVER)
    db.commit()

    with pytest.raises(RuntimeError), db.begin():
        process_safety_escalation(db, assessment_id="assessment-1", decided_at=NOW)
        raise RuntimeError("force rollback")

    assert db.execute(select(SafetyEvent)).scalars().all() == []
    assert db.execute(select(DoseEventLog)).scalars().all() == []
    assert db.execute(select(NotificationJob)).scalars().all() == []
