"""BUILD-22C: two-step human clinical review workflow for
``MedicationSafetyPolicy``.

Deliberately two separate functions with two separate callers in mind:

``propose_policy``
    May be run by anyone/anything preparing a draft (an engineer citing an
    authoritative source, a future admin UI). Always lands in
    ``REVIEW_REQUIRED`` -- the exact status
    ``backend/agents/v2/safety.py::SafetyGateway._route`` already treats as
    "not yet safe to auto-resolve" (it requires
    ``policy_review_status == "REVIEWED"`` before a `SAFE` outcome is even
    considered). This function alone can therefore never unlock `SAFE` for
    any patient, no matter what content is proposed.

``approve_policy``
    The ONLY function that can set ``review_status=REVIEWED``. Requires a
    non-empty, explicitly-supplied ``reviewed_by`` (a real clinical
    reviewer's name/role) and ``reviewed_at`` -- there is no default for
    either, by design: nothing in this codebase may synthesize a reviewer
    identity. This module has no technical way to verify the caller actually
    holds clinical authority; that responsibility is procedural, not
    technical. It must only ever be invoked at a real human reviewer's
    explicit direction -- see ``scripts/agent_v2/approve_safety_policy.py``,
    which documents this requirement at the call site, and report
    ``28-build-22c`` for how this was actually used in production.

Neither function ever fabricates ``risk_level``/``action_policy`` content: a
proposal's clinical content must come from the caller (ideally citing an
authoritative external source in ``source_reference``), and approval never
edits that content -- it only records that a real reviewer looked at exactly
what was proposed and signed off on it as-is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.db.models import MedicationSafetyPolicy
from backend.services.safety_policy_domain.errors import PolicyReviewError
from backend.services.safety_policy_domain.service import REVIEW_REQUIRED, REVIEWED

_TERMINAL_REVIEW_STATUSES = frozenset({REVIEWED, "REJECTED", "RETIRED"})


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ProposedPolicy:
    scope_type: str
    scope_id: str
    risk_type: str
    risk_level: str
    action_policy: str
    source_type: str
    source_reference: str
    created_by: str
    valid_from: datetime
    policy_version: int = 1

    def __post_init__(self) -> None:
        required = (
            self.scope_type, self.scope_id, self.risk_type, self.risk_level,
            self.action_policy, self.source_type, self.source_reference, self.created_by,
        )
        if not all(str(value).strip() for value in required):
            raise ValueError("a proposed policy requires every provenance field to be non-empty")
        if self.action_policy == "REQUIRE_MEDICAL_REVIEW":
            # Even once REVIEWED, this action can never resolve to SAFE (see
            # SafetyGateway._route) -- a proposal claiming it makes no sense
            # to route through human review as though it might unlock SAFE.
            raise ValueError("a proposal intended to unlock SAFE cannot itself request REQUIRE_MEDICAL_REVIEW")


def propose_policy(db: Session, *, proposal: ProposedPolicy) -> MedicationSafetyPolicy:
    """Stage a DRAFT policy in ``REVIEW_REQUIRED``.

    Safe for any caller to run: on its own this can never produce a `SAFE`
    disposition for any patient (the Safety Gateway ignores
    ``REVIEW_REQUIRED`` policies for that purpose the same way it ignores a
    missing policy -- both fail closed to Doctor Handoff).
    """
    valid_from = _utc(proposal.valid_from, "valid_from")
    policy = MedicationSafetyPolicy(
        scope_type=proposal.scope_type,
        scope_id=proposal.scope_id,
        risk_type=proposal.risk_type,
        risk_level=proposal.risk_level,
        action_policy=proposal.action_policy,
        source_type=proposal.source_type,
        source_reference=proposal.source_reference,
        review_status=REVIEW_REQUIRED,
        policy_version=proposal.policy_version,
        valid_from=valid_from,
        created_by=proposal.created_by,
    )
    db.add(policy)
    db.flush()
    return policy


def approve_policy(db: Session, *, policy_id: str, reviewed_by: str, reviewed_at: datetime) -> MedicationSafetyPolicy:
    """The only path to ``review_status=REVIEWED``.

    ``reviewed_by`` must be the real name/role of the human clinical
    reviewer approving this -- there is no default and none should ever be
    added. This function only performs the mechanical state transition; it
    has no way to verify actual clinical authority, which is why it must
    only ever be invoked at a human reviewer's explicit direction.
    """
    if not reviewed_by or not reviewed_by.strip():
        raise PolicyReviewError("reviewed_by is required and must identify a real clinical reviewer")
    reviewed_at = _utc(reviewed_at, "reviewed_at")
    policy = db.get(MedicationSafetyPolicy, policy_id)
    if policy is None:
        raise PolicyReviewError("policy not found", policy_id=policy_id)
    if policy.review_status in _TERMINAL_REVIEW_STATUSES:
        raise PolicyReviewError(
            "policy is already in a terminal review state", policy_id=policy_id, review_status=policy.review_status
        )
    policy.review_status = REVIEWED
    policy.reviewed_by = reviewed_by.strip()
    policy.reviewed_at = reviewed_at
    db.flush()
    return policy


def reject_policy(db: Session, *, policy_id: str, reviewed_by: str, reviewed_at: datetime) -> MedicationSafetyPolicy:
    """A real reviewer may also decline a proposal -- completes the workflow
    without ever forcing every proposal down the approve path."""
    if not reviewed_by or not reviewed_by.strip():
        raise PolicyReviewError("reviewed_by is required and must identify a real clinical reviewer")
    reviewed_at = _utc(reviewed_at, "reviewed_at")
    policy = db.get(MedicationSafetyPolicy, policy_id)
    if policy is None:
        raise PolicyReviewError("policy not found", policy_id=policy_id)
    if policy.review_status in _TERMINAL_REVIEW_STATUSES:
        raise PolicyReviewError(
            "policy is already in a terminal review state", policy_id=policy_id, review_status=policy.review_status
        )
    policy.review_status = "REJECTED"
    policy.reviewed_by = reviewed_by.strip()
    policy.reviewed_at = reviewed_at
    db.flush()
    return policy


__all__ = ["ProposedPolicy", "approve_policy", "propose_policy", "reject_policy"]
