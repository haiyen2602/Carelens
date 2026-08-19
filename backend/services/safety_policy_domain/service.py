"""DB-4H resolver and durable evaluator for missed/delayed V2 doses.

The service is deliberately isolated from the legacy escalation runtime and
from the agent.  It records an auditable decision but never emits catch-up
dose advice or a real notification.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    DrugProduct,
    DrugProductIngredient,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    SafetyEvent,
)
from backend.services.safety_policy_domain.errors import (
    DoseSafetyOccurrenceNotFoundError,
    DoseSafetyStateError,
    LegacyPolicySeedError,
)

MISSED = "MISSED"
DELAYED = "DELAYED"
MISSED_DOSE = "MISSED_DOSE"
DELAYED_DOSE = "DELAYED_DOSE"

DRUG_PRODUCT = "DRUG_PRODUCT"
INGREDIENT = "INGREDIENT"
CATEGORY = "CATEGORY"
REVIEWED = "REVIEWED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
LEGACY_UNREVIEWED = "LEGACY_UNREVIEWED"
REJECTED = "REJECTED"
RETIRED = "RETIRED"
LEGACY_CATEGORY_RULE = "LEGACY_CATEGORY_RULE"
SYSTEM_DEFAULT = "SYSTEM_DEFAULT"

UNKNOWN = "UNKNOWN"
REQUIRE_MEDICAL_REVIEW = "REQUIRE_MEDICAL_REVIEW"
POLICY_ENGINE = "POLICY_ENGINE"
ASSESSMENT_VERSION = "DB4H_POLICY_ENGINE_V1"

_RISK_BY_OCCURRENCE_STATUS = {MISSED: MISSED_DOSE, DELAYED: DELAYED_DOSE}
_USABLE_REVIEW_STATUSES = frozenset({REVIEWED, REVIEW_REQUIRED, LEGACY_UNREVIEWED})


@dataclass(frozen=True)
class PolicyResolution:
    """One policy decision before it becomes an immutable assessment."""

    policy: MedicationSafetyPolicy | None
    risk_level: str
    recommended_action: str
    reason_code: str
    policy_source_type: str
    policy_review_status: str


@dataclass(frozen=True)
class SafetyAssessmentResult:
    """Result from one idempotent safety assessment command."""

    assessment: MissedDoseAssessment
    safety_event: SafetyEvent
    created: bool


@dataclass(frozen=True)
class LegacySeedResult:
    """Counts from a legacy category seed operation."""

    created: int
    existing: int


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"vmec04:{kind}:{key}"))


def _find_staged_or_persisted(
    db: Session, model: type[MissedDoseAssessment] | type[SafetyEvent] | type[DoseEventLog], key: str
) -> MissedDoseAssessment | SafetyEvent | DoseEventLog | None:
    for row in db.new:
        if isinstance(row, model) and row.idempotency_key == key:
            return row
    return db.execute(select(model).where(model.idempotency_key == key)).scalar_one_or_none()


def _locked_occurrence(db: Session, occurrence_id: str) -> DoseOccurrence:
    occurrence = db.execute(
        select(DoseOccurrence).where(DoseOccurrence.id == occurrence_id).with_for_update()
    ).scalar_one_or_none()
    if occurrence is None:
        raise DoseSafetyOccurrenceNotFoundError("Không tìm thấy liều V2.", occurrence_id=occurrence_id)
    return occurrence


def _active_scope_policy(
    db: Session, *, scope_type: str, scope_id: str, risk_type: str, evaluated_at: datetime
) -> MedicationSafetyPolicy | None:
    """Resolve one scope, preferring reviewed then the highest policy version."""

    policies = db.execute(
        select(MedicationSafetyPolicy).where(
            MedicationSafetyPolicy.scope_type == scope_type,
            MedicationSafetyPolicy.scope_id == scope_id,
            MedicationSafetyPolicy.risk_type == risk_type,
            MedicationSafetyPolicy.valid_from <= evaluated_at,
            (MedicationSafetyPolicy.valid_to.is_(None)) | (MedicationSafetyPolicy.valid_to >= evaluated_at),
        )
    ).scalars()
    candidates = [
        policy
        for policy in policies
        if policy.review_status in _USABLE_REVIEW_STATUSES and _policy_shape_is_safe(policy)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda policy: (policy.review_status == REVIEWED, policy.policy_version, policy.id),
    )


def _policy_shape_is_safe(policy: MedicationSafetyPolicy) -> bool:
    """Reject malformed legacy policies instead of accidentally elevating them."""

    if policy.source_type != LEGACY_CATEGORY_RULE:
        return True
    return (
        policy.scope_type == CATEGORY
        and policy.risk_type == MISSED_DOSE
        and policy.review_status == LEGACY_UNREVIEWED
    )


def _resolution_from_policy(policy: MedicationSafetyPolicy, reason_code: str) -> PolicyResolution:
    if policy.review_status == REVIEWED:
        return PolicyResolution(
            policy=policy,
            risk_level=policy.risk_level,
            recommended_action=policy.action_policy,
            reason_code=reason_code,
            policy_source_type=policy.source_type,
            policy_review_status=policy.review_status,
        )
    return PolicyResolution(
        policy=policy,
        risk_level=policy.risk_level,
        recommended_action=REQUIRE_MEDICAL_REVIEW,
        reason_code=("LEGACY_UNREVIEWED_FALLBACK" if policy.source_type == LEGACY_CATEGORY_RULE else "POLICY_REVIEW_REQUIRED"),
        policy_source_type=policy.source_type,
        policy_review_status=policy.review_status,
    )


def _system_default(reason_code: str) -> PolicyResolution:
    """Fail closed without treating missing evidence as low clinical risk."""

    return PolicyResolution(
        policy=None,
        risk_level=UNKNOWN,
        recommended_action=REQUIRE_MEDICAL_REVIEW,
        reason_code=reason_code,
        policy_source_type=SYSTEM_DEFAULT,
        policy_review_status=REVIEW_REQUIRED,
    )


def resolve_policy(
    db: Session, *, occurrence: DoseOccurrence, risk_type: str, evaluated_at: datetime
) -> PolicyResolution:
    """Resolve product, ingredient, category, then a conservative default."""

    if not occurrence.drug_product_id:
        return _system_default("AMBIGUOUS_DRUG_ID")
    product = db.get(DrugProduct, occurrence.drug_product_id)
    if product is None or product.status != "ACTIVE":
        return _system_default("AMBIGUOUS_DRUG_ID")

    product_policy = _active_scope_policy(
        db,
        scope_type=DRUG_PRODUCT,
        scope_id=product.id,
        risk_type=risk_type,
        evaluated_at=evaluated_at,
    )
    if product_policy is not None:
        return _resolution_from_policy(product_policy, "POLICY_DRUG_PRODUCT_MATCH")

    ingredient_ids = db.execute(
        select(DrugProductIngredient.ingredient_id).where(
            DrugProductIngredient.drug_product_id == product.id
        )
    ).scalars()
    ingredient_policies = [
        policy
        for ingredient_id in ingredient_ids
        if (
            policy := _active_scope_policy(
                db,
                scope_type=INGREDIENT,
                scope_id=ingredient_id,
                risk_type=risk_type,
                evaluated_at=evaluated_at,
            )
        )
        is not None
    ]
    if len(ingredient_policies) == 1:
        return _resolution_from_policy(ingredient_policies[0], "POLICY_INGREDIENT_MATCH")
    if len(ingredient_policies) > 1:
        return _system_default("AMBIGUOUS_INGREDIENT_POLICY")

    if product.category_id:
        category_policy = _active_scope_policy(
            db,
            scope_type=CATEGORY,
            scope_id=product.category_id,
            risk_type=risk_type,
            evaluated_at=evaluated_at,
        )
        if category_policy is not None:
            return _resolution_from_policy(category_policy, "POLICY_CATEGORY_FALLBACK")
    return _system_default("NO_POLICY_SAFE_FALLBACK")


def _append_dose_event(
    db: Session, occurrence: DoseOccurrence, assessment: MissedDoseAssessment, evaluated_at: datetime
) -> None:
    key = f"dose:{occurrence.id}:safety-assessment:{assessment.risk_type}:{ASSESSMENT_VERSION}"
    if _find_staged_or_persisted(db, DoseEventLog, key) is not None:
        return
    db.add(
        DoseEventLog(
            id=_stable_id("dose-event", key),
            dose_occurrence_id=occurrence.id,
            patient_id=occurrence.patient_id,
            medication_plan_id=occurrence.medication_plan_id,
            drug_product_id=occurrence.drug_product_id,
            event_type="SAFETY_ASSESSMENT_CREATED",
            event_at=evaluated_at,
            source=POLICY_ENGINE,
            idempotency_key=key,
            metadata_json={"assessment_id": assessment.id, "reason_code": assessment.reason_code},
        )
    )


def _create_safety_event(
    db: Session, occurrence: DoseOccurrence, assessment: MissedDoseAssessment, evaluated_at: datetime
) -> SafetyEvent:
    key = f"dose:{occurrence.id}:safety-event:{assessment.risk_type}:{ASSESSMENT_VERSION}"
    existing = _find_staged_or_persisted(db, SafetyEvent, key)
    if isinstance(existing, SafetyEvent):
        return existing
    event_type = "AMBIGUOUS_DRUG" if assessment.reason_code == "AMBIGUOUS_DRUG_ID" else f"{assessment.risk_type}_ASSESSED"
    event = SafetyEvent(
        id=_stable_id("safety-event", key),
        patient_id=occurrence.patient_id,
        dose_occurrence_id=occurrence.id,
        drug_product_id=occurrence.drug_product_id,
        missed_dose_assessment_id=assessment.id,
        event_type=event_type,
        severity=assessment.risk_level,
        decision=assessment.recommended_action,
        reason=assessment.reason_code,
        source=POLICY_ENGINE,
        idempotency_key=key,
        metadata_json={
            "policy_id": assessment.policy_id,
            "policy_source_type": assessment.policy_source_type,
            "policy_review_status": assessment.policy_review_status,
        },
        created_at=evaluated_at,
    )
    db.add(event)
    return event


def assess_dose_safety(
    db: Session, *, occurrence_id: str, evaluated_at: datetime
) -> SafetyAssessmentResult:
    """Persist one idempotent policy assessment for a terminal V2 dose state."""

    evaluated_at = _utc(evaluated_at, "evaluated_at")
    occurrence = _locked_occurrence(db, occurrence_id)
    risk_type = _RISK_BY_OCCURRENCE_STATUS.get(occurrence.status or "")
    if risk_type is None:
        raise DoseSafetyStateError(
            "Chỉ liều MISSED hoặc DELAYED mới được đánh giá safety.",
            occurrence_id=occurrence.id,
            status=occurrence.status,
        )
    assessment_key = f"dose:{occurrence.id}:assessment:{risk_type}:{ASSESSMENT_VERSION}"
    existing = _find_staged_or_persisted(db, MissedDoseAssessment, assessment_key)
    if isinstance(existing, MissedDoseAssessment):
        event = _create_safety_event(db, occurrence, existing, evaluated_at)
        _append_dose_event(db, occurrence, existing, evaluated_at)
        db.flush()
        return SafetyAssessmentResult(existing, event, created=False)

    resolution = resolve_policy(
        db, occurrence=occurrence, risk_type=risk_type, evaluated_at=evaluated_at
    )
    assessment = MissedDoseAssessment(
        id=_stable_id("safety-assessment", assessment_key),
        patient_id=occurrence.patient_id,
        dose_occurrence_id=occurrence.id,
        medication_plan_id=occurrence.medication_plan_id,
        drug_product_id=occurrence.drug_product_id,
        risk_type=risk_type,
        risk_level=resolution.risk_level,
        recommended_action=resolution.recommended_action,
        policy_id=resolution.policy.id if resolution.policy else None,
        policy_source_type=resolution.policy_source_type,
        policy_review_status=resolution.policy_review_status,
        reason_code=resolution.reason_code,
        assessment_version=ASSESSMENT_VERSION,
        evaluator=POLICY_ENGINE,
        evaluated_at=evaluated_at,
        idempotency_key=assessment_key,
    )
    db.add(assessment)
    _append_dose_event(db, occurrence, assessment, evaluated_at)
    event = _create_safety_event(db, occurrence, assessment, evaluated_at)
    db.flush()
    return SafetyAssessmentResult(assessment, event, created=True)


def seed_legacy_category_policies(
    db: Session,
    *,
    category_risks: Mapping[str, str],
    source_reference: str,
    valid_from: datetime,
) -> LegacySeedResult:
    """Seed only valid legacy category `MISSED_DOSE` fallbacks idempotently."""

    valid_from = _utc(valid_from, "valid_from")
    created = 0
    existing = 0
    for category_id, risk_level in sorted(category_risks.items()):
        if not category_id or not risk_level:
            raise LegacyPolicySeedError("Legacy category/risk không được rỗng.")
        policy_key = f"legacy-category:{category_id}:{MISSED_DOSE}:1"
        policy_id = _stable_id("safety-policy", policy_key)
        policy = db.get(MedicationSafetyPolicy, policy_id)
        if policy is not None:
            if not _policy_shape_is_safe(policy):
                raise LegacyPolicySeedError("Legacy policy hiện có có shape không an toàn.", policy_id=policy.id)
            existing += 1
            continue
        db.add(
            MedicationSafetyPolicy(
                id=policy_id,
                scope_type=CATEGORY,
                scope_id=category_id,
                risk_type=MISSED_DOSE,
                risk_level=risk_level,
                action_policy=REQUIRE_MEDICAL_REVIEW,
                source_type=LEGACY_CATEGORY_RULE,
                source_reference=source_reference,
                review_status=LEGACY_UNREVIEWED,
                policy_version=1,
                valid_from=valid_from,
            )
        )
        created += 1
    db.flush()
    return LegacySeedResult(created=created, existing=existing)


__all__ = [
    "ASSESSMENT_VERSION",
    "CATEGORY",
    "DELAYED_DOSE",
    "DRUG_PRODUCT",
    "INGREDIENT",
    "LEGACY_CATEGORY_RULE",
    "LEGACY_UNREVIEWED",
    "MISSED_DOSE",
    "REQUIRE_MEDICAL_REVIEW",
    "REVIEWED",
    "SafetyAssessmentResult",
    "assess_dose_safety",
    "resolve_policy",
    "seed_legacy_category_policies",
]
