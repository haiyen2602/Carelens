"""Typed, fail-closed boundary between Agent V2 and the Safety Domain.

The agent supplies a server-classified trigger and an occurrence identifier;
it never supplies a clinical conclusion.  Only the safety-domain adapter may
produce a decision.  A failed, late, or incomplete decision is terminal and
must be handled before a model is allowed to plan a response.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from backend.agents.v2.context import ContextAuthority, ContextItem, ContextLayer


class SafetyTrigger(StrEnum):
    """Trusted server-side classification; never inferred from model output."""

    GENERAL_INFORMATION = "GENERAL_INFORMATION"
    MISSED_DOSE = "MISSED_DOSE"
    DELAYED_DOSE = "DELAYED_DOSE"
    DOSE_ACTION = "DOSE_ACTION"
    SAFETY_ESCALATION = "SAFETY_ESCALATION"


_REQUIRES_SAFETY = frozenset(
    {
        SafetyTrigger.MISSED_DOSE,
        SafetyTrigger.DELAYED_DOSE,
        SafetyTrigger.DOSE_ACTION,
        SafetyTrigger.SAFETY_ESCALATION,
    }
)


class SafetyOutcome(StrEnum):
    SAFE = "SAFE"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    HANDOFF_REQUIRED = "HANDOFF_REQUIRED"


class SafetyAssessmentNotYetDueError(Exception):
    """The occurrence exists but is not (yet) in a state safety can assess.

    BUILD-20 hardening: distinct from every other domain failure (outage, bad
    data, timeout) so ``SafetyGateway.evaluate`` -- and therefore the message
    the runtime shows the user -- can tell "too early to ask" apart from
    "the safety domain is unavailable" (BUILD-19's P2 finding). Domain
    adapters (e.g. ``backend.services.agent_safety.SafetyDomainAdapter``)
    translate their own DB-layer exception for this exact case into this
    type; this module still never imports anything DB-touching itself.
    """


@dataclass(frozen=True)
class SafetyRequest:
    trigger: SafetyTrigger
    occurrence_id: str | None = None

    def __post_init__(self) -> None:
        if self.trigger in _REQUIRES_SAFETY and not self.occurrence_id:
            raise ValueError("SAFETY_OCCURRENCE_REQUIRED")


@dataclass(frozen=True)
class SafetyDomainDecision:
    """Auditable projection of an immutable DB-4H assessment."""

    assessment_id: str
    risk_level: str
    recommended_action: str
    reason_code: str
    policy_source_type: str | None
    policy_review_status: str | None
    evaluated_at: datetime


class SafetyDomain(Protocol):
    def assess(self, *, occurrence_id: str, evaluated_at: datetime) -> SafetyDomainDecision: ...


@dataclass(frozen=True)
class SafetyDecision:
    outcome: SafetyOutcome
    reason_code: str
    provenance: str
    assessment_id: str | None = None
    risk_level: str | None = None
    recommended_action: str | None = None
    policy_source_type: str | None = None
    policy_review_status: str | None = None
    evaluated_at: datetime | None = None

    def to_context_item(self) -> ContextItem:
        """Safety context is protected and cannot be overwritten downstream."""

        content = (
            f"Safety outcome: {self.outcome}; reason: {self.reason_code}; "
            f"assessment: {self.assessment_id or 'none'}; "
            f"risk: {self.risk_level or 'unknown'}; "
            f"action: {self.recommended_action or 'none'}."
        )
        return ContextItem(
            id=f"safety:{self.assessment_id or self.reason_code}",
            layer=ContextLayer.TOOL,
            content=content,
            token_count=max(1, len(content.split())),
            authority=ContextAuthority.SAFETY_DOMAIN,
            priority=100,
            provenance=self.provenance,
            freshness=self.evaluated_at,
            relevance=1.0,
        )


class SafetyGateway:
    """Maps Safety Domain decisions to immutable Agent V2 terminal outcomes."""

    def __init__(
        self,
        domain: SafetyDomain,
        *,
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("AGENT_SAFETY_TIMEOUT_SECONDS must be positive")
        self._domain = domain
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._now = now

    @classmethod
    def from_settings(cls, domain: SafetyDomain, settings: object) -> SafetyGateway:
        return cls(domain, timeout_seconds=float(getattr(settings, "agent_safety_timeout_seconds")))

    @staticmethod
    def requires_safety(trigger: SafetyTrigger) -> bool:
        return trigger in _REQUIRES_SAFETY

    def evaluate(self, request: SafetyRequest) -> SafetyDecision:
        if not self.requires_safety(request.trigger):
            return SafetyDecision(
                outcome=SafetyOutcome.SAFE,
                reason_code="SAFETY_NOT_REQUIRED",
                provenance="safety-domain:not-applicable",
                evaluated_at=self._now(),
            )

        # __post_init__ makes this assertion true for all public callers.
        assert request.occurrence_id is not None
        started = self._clock()
        try:
            decision = self._domain.assess(occurrence_id=request.occurrence_id, evaluated_at=self._now())
        except SafetyAssessmentNotYetDueError:
            # Still fail-closed (SAFETY_BLOCKED) -- this is not a SAFE
            # disposition -- but with a reason_code the runtime can use to
            # tell the user "too early", not "something is broken".
            return SafetyDecision(
                outcome=SafetyOutcome.SAFETY_BLOCKED,
                reason_code="DOSE_NOT_YET_ASSESSABLE",
                provenance="safety-domain:not-yet-due",
            )
        except Exception:
            return SafetyDecision(
                outcome=SafetyOutcome.SAFETY_BLOCKED,
                reason_code="SAFETY_DOMAIN_UNAVAILABLE",
                provenance="safety-domain:unavailable",
            )
        if self._clock() - started > self._timeout_seconds:
            return SafetyDecision(
                outcome=SafetyOutcome.SAFETY_BLOCKED,
                reason_code="SAFETY_DOMAIN_TIMEOUT",
                provenance="safety-domain:timeout",
            )

        provenance = f"safety-domain:{decision.assessment_id}"
        result = SafetyDecision(
            outcome=self._route(decision),
            reason_code=decision.reason_code,
            provenance=provenance,
            assessment_id=decision.assessment_id,
            risk_level=decision.risk_level,
            recommended_action=decision.recommended_action,
            policy_source_type=decision.policy_source_type,
            policy_review_status=decision.policy_review_status,
            evaluated_at=decision.evaluated_at,
        )
        return result

    @staticmethod
    def _route(decision: SafetyDomainDecision) -> SafetyOutcome:
        # Only an explicitly reviewed, non-medical-review decision may let a
        # read-only agent continue.  Legacy and default policy outputs are
        # deliberately never converted into model advice.
        if (
            decision.risk_level == "UNKNOWN"
            or decision.recommended_action == "REQUIRE_MEDICAL_REVIEW"
            or decision.policy_review_status != "REVIEWED"
        ):
            return SafetyOutcome.HANDOFF_REQUIRED
        return SafetyOutcome.SAFE


__all__ = [
    "SafetyDecision",
    "SafetyDomain",
    "SafetyDomainDecision",
    "SafetyGateway",
    "SafetyOutcome",
    "SafetyRequest",
    "SafetyTrigger",
]
