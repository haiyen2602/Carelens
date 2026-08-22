"""Safety Domain adapter used by Agent V2; the agent never accesses ORM data."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.agents.v2.safety import SafetyAssessmentNotYetDueError, SafetyDomainDecision
from backend.services.safety_policy_domain.service import DoseSafetyStateError, assess_dose_safety


class SafetyDomainAdapter:
    """Project DB-4H's idempotent assessment into the typed Agent boundary.

    This intentionally does not call escalation, create a handoff, or deliver
    a notification.  Those remain separate future domains.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def assess(self, *, occurrence_id: str, evaluated_at: datetime) -> SafetyDomainDecision:
        try:
            result = assess_dose_safety(self._db, occurrence_id=occurrence_id, evaluated_at=evaluated_at)
        except DoseSafetyStateError as exc:
            # BUILD-20: this is the one DB-layer exception this adapter
            # translates rather than lets propagate raw -- it means "not due
            # yet", not "the domain is down", and the agent-layer boundary
            # (backend/agents/v2/safety.py) must never import this
            # DB-touching exception type itself to tell the two apart.
            raise SafetyAssessmentNotYetDueError(str(exc)) from exc
        assessment = result.assessment
        return SafetyDomainDecision(
            assessment_id=assessment.id,
            risk_level=assessment.risk_level,
            recommended_action=assessment.recommended_action,
            reason_code=assessment.reason_code,
            policy_source_type=assessment.policy_source_type,
            policy_review_status=assessment.policy_review_status,
            evaluated_at=assessment.evaluated_at,
        )


__all__ = ["SafetyDomainAdapter"]
