"""DB-4I V2 escalation-decision and notification-outbox boundary.

This service records an escalation decision; it does not deliver a provider
message and does not write the legacy ``escalation`` table or invoke an Agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    NotificationJob,
    SafetyEvent,
)
from backend.services.safety_policy_domain.errors import SafetyAssessmentNotFoundError
from backend.services.safety_policy_domain.service import REQUIRE_MEDICAL_REVIEW, REVIEWED

LOG_ONLY = "LOG_ONLY"
REMIND = "REMIND"
WARN = "WARN"
ESCALATE_CAREGIVER = "ESCALATE_CAREGIVER"
ESCALATE_CLINICIAN = "ESCALATE_CLINICIAN"

LOW = "LOW"
MODERATE = "MODERATE"
HIGH = "HIGH"
CRITICAL = "CRITICAL"
UNKNOWN = "UNKNOWN"

PATIENT = "PATIENT"
CAREGIVER = "CAREGIVER"
CLINICIAN = "CLINICIAN"
QUEUED = "QUEUED"
POLICY_ENGINE = "POLICY_ENGINE"
ESCALATION_VERSION = "DB4I_ESCALATION_V1"

_ELIGIBLE_SOURCES = frozenset({"CLINICAL_REVIEW", "DRUG_LABEL", "GUIDELINE"})
_ACTIONS_BY_RISK = {
    LOW: frozenset({LOG_ONLY, REMIND, WARN}),
    MODERATE: frozenset({LOG_ONLY, REMIND, WARN, ESCALATE_CAREGIVER}),
    HIGH: frozenset({LOG_ONLY, REMIND, WARN, ESCALATE_CAREGIVER, ESCALATE_CLINICIAN}),
    CRITICAL: frozenset({LOG_ONLY, REMIND, WARN, ESCALATE_CAREGIVER, ESCALATE_CLINICIAN}),
}
_NOTIFICATION_TARGETS = {
    REMIND: (PATIENT, "DOSE_SAFETY_REMINDER"),
    WARN: (PATIENT, "DOSE_SAFETY_WARNING"),
    ESCALATE_CAREGIVER: (CAREGIVER, "DOSE_SAFETY_ESCALATION"),
    ESCALATE_CLINICIAN: (CLINICIAN, "DOSE_SAFETY_ESCALATION"),
}


@dataclass(frozen=True)
class EscalationDecision:
    """The effective action after provenance and risk/action guards."""

    action: str
    reason_code: str
    auto_delivery_allowed: bool


@dataclass(frozen=True)
class EscalationResult:
    """One idempotent escalation persistence result."""

    safety_event: SafetyEvent
    notification_job: NotificationJob | None
    created: bool


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"vmec04:{kind}:{key}"))


def _find_staged_or_persisted(
    db: Session, model: type[SafetyEvent] | type[NotificationJob] | type[DoseEventLog], key: str
) -> SafetyEvent | NotificationJob | DoseEventLog | None:
    for row in db.new:
        if isinstance(row, model) and row.idempotency_key == key:
            return row
    return db.execute(select(model).where(model.idempotency_key == key)).scalar_one_or_none()


def _locked_assessment(db: Session, assessment_id: str) -> MissedDoseAssessment:
    assessment = db.execute(
        select(MissedDoseAssessment).where(MissedDoseAssessment.id == assessment_id).with_for_update()
    ).scalar_one_or_none()
    if assessment is None:
        raise SafetyAssessmentNotFoundError("Safety assessment was not found.", assessment_id=assessment_id)
    return assessment


def _current_policy_allows(assessment: MissedDoseAssessment) -> bool:
    """Assess immutable snapshot eligibility; current policy is checked by caller."""

    return (
        assessment.policy_id is not None
        and assessment.policy_review_status == REVIEWED
        and assessment.policy_source_type in _ELIGIBLE_SOURCES
    )


def decide_escalation(
    assessment: MissedDoseAssessment, policy: MedicationSafetyPolicy | None
) -> EscalationDecision:
    """Apply provenance and risk/action gates without changing the assessment."""

    if not assessment.drug_product_id:
        return EscalationDecision(REQUIRE_MEDICAL_REVIEW, "AMBIGUOUS_DRUG_ID", False)
    if not _current_policy_allows(assessment):
        return EscalationDecision(REQUIRE_MEDICAL_REVIEW, "POLICY_NOT_AUTO_ESCALATABLE", False)
    if (
        policy is None
        or policy.id != assessment.policy_id
        or policy.review_status != REVIEWED
        or policy.source_type != assessment.policy_source_type
        or policy.source_type not in _ELIGIBLE_SOURCES
    ):
        return EscalationDecision(REQUIRE_MEDICAL_REVIEW, "POLICY_PROVENANCE_MISMATCH", False)
    if assessment.recommended_action == REQUIRE_MEDICAL_REVIEW:
        return EscalationDecision(REQUIRE_MEDICAL_REVIEW, "POLICY_REQUIRES_MEDICAL_REVIEW", False)
    if assessment.risk_level == UNKNOWN:
        return EscalationDecision(REQUIRE_MEDICAL_REVIEW, "UNKNOWN_RISK_FAIL_CLOSED", False)
    allowed_actions = _ACTIONS_BY_RISK.get(assessment.risk_level)
    if allowed_actions is None or assessment.recommended_action not in allowed_actions:
        return EscalationDecision(REQUIRE_MEDICAL_REVIEW, "RISK_ACTION_REVIEW_REQUIRED", False)
    return EscalationDecision(assessment.recommended_action, "REVIEWED_POLICY_ACTION", True)


def _append_dose_event(
    db: Session,
    occurrence: DoseOccurrence | None,
    assessment: MissedDoseAssessment,
    decision: EscalationDecision,
    evaluated_at: datetime,
) -> None:
    if occurrence is None:
        return
    key = f"assessment:{assessment.id}:escalation-decision:{ESCALATION_VERSION}"
    if _find_staged_or_persisted(db, DoseEventLog, key) is not None:
        return
    db.add(
        DoseEventLog(
            id=_stable_id("dose-event", key),
            dose_occurrence_id=occurrence.id,
            patient_id=occurrence.patient_id,
            medication_plan_id=occurrence.medication_plan_id,
            drug_product_id=occurrence.drug_product_id,
            event_type="SAFETY_ESCALATION_DECIDED",
            event_at=evaluated_at,
            source=POLICY_ENGINE,
            idempotency_key=key,
            metadata_json={"assessment_id": assessment.id, "action": decision.action, "reason": decision.reason_code},
        )
    )


def _create_notification_job(
    db: Session,
    *,
    event: SafetyEvent,
    assessment: MissedDoseAssessment,
    action: str,
    scheduled_at: datetime,
) -> NotificationJob | None:
    target = _NOTIFICATION_TARGETS.get(action)
    if target is None:
        return None
    recipient_type, notification_type = target
    # Caregiver/clinician account resolution is a later dispatch concern; do
    # not infer a recipient ID from legacy identity data. Patient notifications
    # can use the existing occurrence/assessment patient ID directly.
    recipient_id = assessment.patient_id if recipient_type == PATIENT else None
    key = f"safety-event:{event.id}:notification:{notification_type}:recipient:{recipient_type}:{recipient_id or 'ROLE'}"
    existing = _find_staged_or_persisted(db, NotificationJob, key)
    if isinstance(existing, NotificationJob):
        return existing
    job = NotificationJob(
        id=_stable_id("notification-job", key),
        patient_id=assessment.patient_id,
        dose_occurrence_id=assessment.dose_occurrence_id,
        notification_type=notification_type,
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        scheduled_at=scheduled_at,
        status=QUEUED,
        idempotency_key=key,
        payload={
            "safety_event_id": event.id,
            "assessment_id": assessment.id,
            "action": action,
            "risk_level": assessment.risk_level,
        },
    )
    db.add(job)
    return job


def process_safety_escalation(
    db: Session, *, assessment_id: str, decided_at: datetime
) -> EscalationResult:
    """Persist an audited escalation/outbox decision for one DB-4H assessment."""

    decided_at = _utc(decided_at, "decided_at")
    assessment = _locked_assessment(db, assessment_id)
    occurrence = (
        db.execute(
            select(DoseOccurrence).where(DoseOccurrence.id == assessment.dose_occurrence_id).with_for_update()
        ).scalar_one_or_none()
    )
    policy = db.get(MedicationSafetyPolicy, assessment.policy_id) if assessment.policy_id else None
    decision = decide_escalation(assessment, policy)
    event_key = f"assessment:{assessment.id}:escalation:{ESCALATION_VERSION}"
    existing_event = _find_staged_or_persisted(db, SafetyEvent, event_key)
    created = False
    if isinstance(existing_event, SafetyEvent):
        event = existing_event
    else:
        event = SafetyEvent(
            id=_stable_id("safety-event", event_key),
            patient_id=assessment.patient_id,
            dose_occurrence_id=assessment.dose_occurrence_id,
            drug_product_id=assessment.drug_product_id,
            missed_dose_assessment_id=assessment.id,
            event_type="SAFETY_ESCALATION_DECIDED",
            severity=assessment.risk_level,
            decision=decision.action,
            reason=decision.reason_code,
            source=POLICY_ENGINE,
            idempotency_key=event_key,
            metadata_json={
                "policy_id": assessment.policy_id,
                "policy_source_type": assessment.policy_source_type,
                "policy_review_status": assessment.policy_review_status,
            },
            created_at=decided_at,
        )
        db.add(event)
        created = True
    _append_dose_event(db, occurrence, assessment, decision, decided_at)
    job = _create_notification_job(
        db,
        event=event,
        assessment=assessment,
        action=decision.action if decision.auto_delivery_allowed else REQUIRE_MEDICAL_REVIEW,
        scheduled_at=decided_at,
    )
    db.flush()
    return EscalationResult(event, job, created=created)


__all__ = [
    "CAREGIVER",
    "CLINICIAN",
    "ESCALATE_CAREGIVER",
    "ESCALATE_CLINICIAN",
    "HIGH",
    "LOG_ONLY",
    "LOW",
    "MODERATE",
    "REMIND",
    "REQUIRE_MEDICAL_REVIEW",
    "UNKNOWN",
    "WARN",
    "EscalationDecision",
    "EscalationResult",
    "decide_escalation",
    "process_safety_escalation",
]
