"""DB-4H policy resolution and persistence tests."""

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
    Ingredient,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    SafetyEvent,
)
from backend.services.safety_policy_domain.errors import DoseSafetyStateError
from backend.services.safety_policy_domain.service import (
    CATEGORY,
    DRUG_PRODUCT,
    INGREDIENT,
    LEGACY_CATEGORY_RULE,
    LEGACY_UNREVIEWED,
    REQUIRE_MEDICAL_REVIEW,
    REVIEWED,
    assess_dose_safety,
    seed_legacy_category_policies,
)

TABLES = (
    DrugProduct.__table__,
    Ingredient.__table__,
    DrugProductIngredient.__table__,
    DoseOccurrence.__table__,
    MedicationSafetyPolicy.__table__,
    MissedDoseAssessment.__table__,
    SafetyEvent.__table__,
    DoseEventLog.__table__,
)
NOW = datetime(2026, 8, 17, 1, 31, tzinfo=UTC)


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


def _product(db: Session, product_id: str = "product-1", category: str | None = "category-1") -> DrugProduct:
    product = DrugProduct(id=product_id, display_name=product_id, category_id=category, status="ACTIVE")
    db.add(product)
    return product


def _occurrence(
    db: Session, *, occurrence_id: str = "occurrence-1", product_id: str | None = "product-1", status: str = "MISSED"
) -> DoseOccurrence:
    occurrence = DoseOccurrence(
        id=occurrence_id,
        patient_id="patient-1",
        medication_plan_id="plan-1",
        drug_product_id=product_id,
        scheduled_at=NOW - timedelta(minutes=31),
        status=status,
        generation_key=f"generation-{occurrence_id}",
        metadata_json={},
    )
    db.add(occurrence)
    return occurrence


def _policy(
    db: Session,
    *,
    policy_id: str,
    scope_type: str,
    scope_id: str,
    risk_type: str = "MISSED_DOSE",
    risk_level: str = "LOW",
    action: str = "LOG_ONLY",
    review_status: str = REVIEWED,
    source_type: str = "CLINICAL_REVIEW",
    version: int = 1,
) -> MedicationSafetyPolicy:
    policy = MedicationSafetyPolicy(
        id=policy_id,
        scope_type=scope_type,
        scope_id=scope_id,
        risk_type=risk_type,
        risk_level=risk_level,
        action_policy=action,
        source_type=source_type,
        review_status=review_status,
        policy_version=version,
        valid_from=NOW - timedelta(days=1),
    )
    db.add(policy)
    return policy


def test_reviewed_product_policy_overrides_category_fallback(db: Session) -> None:
    _product(db)
    _occurrence(db)
    _policy(db, policy_id="category", scope_type=CATEGORY, scope_id="category-1")
    _policy(
        db,
        policy_id="product",
        scope_type=DRUG_PRODUCT,
        scope_id="product-1",
        risk_level="HIGH",
        action="ESCALATE_CLINICIAN",
    )

    result = assess_dose_safety(db, occurrence_id="occurrence-1", evaluated_at=NOW)

    assert result.assessment.policy_id == "product"
    assert result.assessment.risk_level == "HIGH"
    assert result.assessment.recommended_action == "ESCALATE_CLINICIAN"
    assert result.assessment.reason_code == "POLICY_DRUG_PRODUCT_MATCH"


def test_ingredient_policy_overrides_category_fallback(db: Session) -> None:
    _product(db)
    _occurrence(db)
    db.add(Ingredient(id="ingredient-1", name="Ingredient"))
    db.add(DrugProductIngredient(id="link-1", drug_product_id="product-1", ingredient_id="ingredient-1"))
    _policy(db, policy_id="category", scope_type=CATEGORY, scope_id="category-1", risk_level="LOW")
    _policy(
        db,
        policy_id="ingredient",
        scope_type=INGREDIENT,
        scope_id="ingredient-1",
        risk_level="MODERATE",
        action="WARN",
    )

    result = assess_dose_safety(db, occurrence_id="occurrence-1", evaluated_at=NOW)

    assert result.assessment.policy_id == "ingredient"
    assert result.assessment.reason_code == "POLICY_INGREDIENT_MATCH"
    assert result.assessment.risk_level == "MODERATE"


def test_legacy_category_seed_is_unreviewed_and_requires_medical_review(db: Session) -> None:
    _product(db)
    _occurrence(db)

    first = seed_legacy_category_policies(
        db,
        category_risks={"category-1": "HIGH"},
        source_reference="canonical-v2:test",
        valid_from=NOW - timedelta(days=1),
    )
    second = seed_legacy_category_policies(
        db,
        category_risks={"category-1": "HIGH"},
        source_reference="canonical-v2:test",
        valid_from=NOW - timedelta(days=1),
    )
    result = assess_dose_safety(db, occurrence_id="occurrence-1", evaluated_at=NOW)
    policy = db.execute(select(MedicationSafetyPolicy)).scalar_one()

    assert (first.created, second.existing) == (1, 1)
    assert (policy.scope_type, policy.risk_type, policy.source_type, policy.review_status) == (
        CATEGORY,
        "MISSED_DOSE",
        LEGACY_CATEGORY_RULE,
        LEGACY_UNREVIEWED,
    )
    assert result.assessment.reason_code == "LEGACY_UNREVIEWED_FALLBACK"
    assert result.assessment.recommended_action == REQUIRE_MEDICAL_REVIEW
    assert result.assessment.policy_source_type == LEGACY_CATEGORY_RULE
    assert result.assessment.policy_review_status == LEGACY_UNREVIEWED


def test_no_policy_and_ambiguous_drug_fail_closed(db: Session) -> None:
    _product(db)
    _occurrence(db, occurrence_id="no-policy")
    _occurrence(db, occurrence_id="ambiguous", product_id="missing-product")

    no_policy = assess_dose_safety(db, occurrence_id="no-policy", evaluated_at=NOW)
    ambiguous = assess_dose_safety(db, occurrence_id="ambiguous", evaluated_at=NOW)

    assert (no_policy.assessment.risk_level, no_policy.assessment.reason_code) == (
        "UNKNOWN",
        "NO_POLICY_SAFE_FALLBACK",
    )
    assert no_policy.assessment.recommended_action == REQUIRE_MEDICAL_REVIEW
    assert (ambiguous.assessment.risk_level, ambiguous.assessment.reason_code) == (
        "UNKNOWN",
        "AMBIGUOUS_DRUG_ID",
    )
    assert ambiguous.safety_event.event_type == "AMBIGUOUS_DRUG"


def test_rerun_creates_one_assessment_event_and_dose_log(db: Session) -> None:
    _product(db)
    _occurrence(db)
    _policy(db, policy_id="product", scope_type=DRUG_PRODUCT, scope_id="product-1")

    first = assess_dose_safety(db, occurrence_id="occurrence-1", evaluated_at=NOW)
    second = assess_dose_safety(db, occurrence_id="occurrence-1", evaluated_at=NOW + timedelta(minutes=1))

    assert (first.created, second.created) == (True, False)
    assert db.execute(select(MissedDoseAssessment)).scalars().all() == [first.assessment]
    assert db.execute(select(SafetyEvent)).scalars().all() == [first.safety_event]
    assert db.execute(select(DoseEventLog)).scalars().all()[0].event_type == "SAFETY_ASSESSMENT_CREATED"


def test_delayed_dose_requires_delayed_policy_and_invalid_state_is_rejected(db: Session) -> None:
    _product(db)
    _occurrence(db, status="DELAYED")
    _policy(
        db,
        policy_id="delayed-product",
        scope_type=DRUG_PRODUCT,
        scope_id="product-1",
        risk_type="DELAYED_DOSE",
        risk_level="MODERATE",
        action="WARN",
    )
    result = assess_dose_safety(db, occurrence_id="occurrence-1", evaluated_at=NOW)

    assert result.assessment.risk_type == "DELAYED_DOSE"
    assert result.assessment.policy_id == "delayed-product"

    _occurrence(db, occurrence_id="not-terminal", status="DUE")
    with pytest.raises(DoseSafetyStateError):
        assess_dose_safety(db, occurrence_id="not-terminal", evaluated_at=NOW)


def test_assessment_rolls_back_with_safety_and_dose_event(db: Session) -> None:
    _product(db)
    _occurrence(db)
    db.commit()
    with pytest.raises(RuntimeError), db.begin():
        assess_dose_safety(db, occurrence_id="occurrence-1", evaluated_at=NOW)
        raise RuntimeError("force rollback")

    assert db.execute(select(MissedDoseAssessment)).scalars().all() == []
    assert db.execute(select(SafetyEvent)).scalars().all() == []
    assert db.execute(select(DoseEventLog)).scalars().all() == []
