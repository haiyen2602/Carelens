"""APP-5 runtime bridge tests; policy decisions remain in the DB-4H/DB-4I services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    DrugProduct,
    DrugProductIngredient,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    NotificationJob,
    SafetyEvent,
)
from backend.services.safety_policy_domain.runtime import process_dose_safety_runtime
from backend.services.safety_policy_domain.service import (
    CATEGORY,
    LEGACY_CATEGORY_RULE,
    LEGACY_UNREVIEWED,
    REQUIRE_MEDICAL_REVIEW,
    REVIEWED,
)

NOW = datetime(2026, 8, 17, 2, tzinfo=UTC)
TABLES = (
    DrugProduct.__table__,
    DrugProductIngredient.__table__,
    DoseOccurrence.__table__,
    MedicationSafetyPolicy.__table__,
    MissedDoseAssessment.__table__,
    SafetyEvent.__table__,
    DoseEventLog.__table__,
    NotificationJob.__table__,
)


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


def _occurrence(db: Session, *, product_id: str | None = "product-1") -> DoseOccurrence:
    if product_id:
        db.add(DrugProduct(id=product_id, display_name="Runtime product", category_id="category-1", status="ACTIVE"))
    occurrence = DoseOccurrence(
        id="occurrence-1",
        patient_id="patient-1",
        medication_plan_id="plan-1",
        drug_product_id=product_id,
        scheduled_at=NOW - timedelta(hours=1),
        status="MISSED",
        generation_key="runtime-occurrence-1",
        metadata_json={},
    )
    db.add(occurrence)
    return occurrence


def _policy(
    db: Session,
    *,
    source_type: str = "CLINICAL_REVIEW",
    review_status: str = REVIEWED,
    scope_type: str = "DRUG_PRODUCT",
    scope_id: str = "product-1",
) -> MedicationSafetyPolicy:
    policy = MedicationSafetyPolicy(
        id="policy-1",
        scope_type=scope_type,
        scope_id=scope_id,
        risk_type="MISSED_DOSE",
        risk_level="HIGH",
        action_policy="ESCALATE_CLINICIAN",
        source_type=source_type,
        review_status=review_status,
        policy_version=1,
        valid_from=NOW - timedelta(days=1),
    )
    db.add(policy)
    return policy


def test_runtime_assesses_and_escalates_reviewed_policy_idempotently(db: Session) -> None:
    _occurrence(db)
    _policy(db)

    first = process_dose_safety_runtime(db, occurrence_id="occurrence-1", evaluated_at=NOW)
    second = process_dose_safety_runtime(db, occurrence_id="occurrence-1", evaluated_at=NOW + timedelta(minutes=1))

    assert first.assessment.assessment.risk_level == "HIGH"
    assert first.escalation.safety_event.decision == "ESCALATE_CLINICIAN"
    assert first.escalation.notification_job is not None
    assert (first.assessment.created, first.escalation.created) == (True, True)
    assert (second.assessment.created, second.escalation.created) == (False, False)
    assert len(db.execute(select(MissedDoseAssessment)).scalars().all()) == 1
    assert len(db.execute(select(SafetyEvent)).scalars().all()) == 2
    assert len(db.execute(select(NotificationJob)).scalars().all()) == 1


def test_runtime_legacy_unreviewed_policy_stays_fail_closed(db: Session) -> None:
    _occurrence(db)
    _policy(
        db,
        source_type=LEGACY_CATEGORY_RULE,
        review_status=LEGACY_UNREVIEWED,
        scope_type=CATEGORY,
        scope_id="category-1",
    )

    result = process_dose_safety_runtime(db, occurrence_id="occurrence-1", evaluated_at=NOW)

    assert result.assessment.assessment.recommended_action == REQUIRE_MEDICAL_REVIEW
    assert result.escalation.safety_event.decision == REQUIRE_MEDICAL_REVIEW
    assert result.escalation.notification_job is None


def test_runtime_unknown_identity_stays_fail_closed(db: Session) -> None:
    _occurrence(db, product_id=None)

    result = process_dose_safety_runtime(db, occurrence_id="occurrence-1", evaluated_at=NOW)

    assert result.assessment.assessment.reason_code == "AMBIGUOUS_DRUG_ID"
    assert result.escalation.safety_event.decision == REQUIRE_MEDICAL_REVIEW
    assert result.escalation.notification_job is None


def test_runtime_rows_roll_back_with_the_caller_transaction(db: Session) -> None:
    _occurrence(db)
    _policy(db)
    db.commit()

    with pytest.raises(RuntimeError), db.begin():
        process_dose_safety_runtime(db, occurrence_id="occurrence-1", evaluated_at=NOW)
        raise RuntimeError("force rollback")

    assert db.execute(select(MissedDoseAssessment)).scalars().all() == []
    assert db.execute(select(SafetyEvent)).scalars().all() == []
    assert db.execute(select(DoseEventLog)).scalars().all() == []
    assert db.execute(select(NotificationJob)).scalars().all() == []
