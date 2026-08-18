"""APP-5 transactional runtime bridge for audited V2 safety services.

This module deliberately makes no risk or escalation decision.  It connects
a terminal V2 dose state to the already-audited DB-4H and DB-4I boundaries;
the caller owns the surrounding transaction and no provider is invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.services.safety_policy_domain.escalation import EscalationResult, process_safety_escalation
from backend.services.safety_policy_domain.service import SafetyAssessmentResult, assess_dose_safety


@dataclass(frozen=True)
class SafetyRuntimeResult:
    """The durable assessment and escalation outcomes for one occurrence."""

    assessment: SafetyAssessmentResult
    escalation: EscalationResult


def process_dose_safety_runtime(
    db: Session, *, occurrence_id: str, evaluated_at: datetime
) -> SafetyRuntimeResult:
    """Assess and decide escalation atomically for one MISSED/DELAYED occurrence.

    ``assess_dose_safety`` rejects non-terminal states, resolves policy
    provenance, and fails closed.  ``process_safety_escalation`` then applies
    the reviewed-policy guard before it can create a notification outbox row.
    Neither service commits, so a caller rollback removes state, assessment,
    events, escalation decision, and any queued job together.
    """

    assessment = assess_dose_safety(db, occurrence_id=occurrence_id, evaluated_at=evaluated_at)
    escalation = process_safety_escalation(
        db, assessment_id=assessment.assessment.id, decided_at=evaluated_at
    )
    return SafetyRuntimeResult(assessment=assessment, escalation=escalation)


__all__ = ["SafetyRuntimeResult", "process_dose_safety_runtime"]
