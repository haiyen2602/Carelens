"""BUILD-22C: propose/approve/reject clinical review workflow for
``MedicationSafetyPolicy`` (backend.services.safety_policy_domain.review_workflow).

The central property under test: ``propose_policy`` alone can NEVER produce
a policy the Safety Gateway resolves to SAFE (it always lands in
REVIEW_REQUIRED); only ``approve_policy``, given an explicit, non-empty
``reviewed_by``, can flip that -- and it refuses to fabricate one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from sqlalchemy.orm import Session

from backend.agents.v2.safety import SafetyGateway
from backend.db.models import MedicationSafetyPolicy
from backend.services.safety_policy_domain.errors import PolicyReviewError
from backend.services.safety_policy_domain.review_workflow import (
    ProposedPolicy,
    approve_policy,
    propose_policy,
    reject_policy,
)
from backend.services.safety_policy_domain.service import DRUG_PRODUCT, MISSED_DOSE

NOW = datetime(2026, 8, 22, 10, tzinfo=UTC)
TABLES = (MedicationSafetyPolicy.__table__,)


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


def _proposal(**overrides) -> ProposedPolicy:
    values = dict(
        scope_type=DRUG_PRODUCT,
        scope_id="drug-1",
        risk_type=MISSED_DOSE,
        risk_level="LOW",
        action_policy="SAFE_NO_ACTION_NEEDED",
        source_type="EXTERNAL_REFERENCE",
        source_reference="https://example.invalid/authoritative-drug-label",
        created_by="build-22c-draft",
        valid_from=NOW,
    )
    values.update(overrides)
    return ProposedPolicy(**values)


# ---------------------------------------------------------------------------
# propose_policy
# ---------------------------------------------------------------------------


def test_propose_lands_in_review_required(db):
    policy = propose_policy(db, proposal=_proposal())
    assert policy.review_status == "REVIEW_REQUIRED"
    assert policy.reviewed_by is None
    assert policy.reviewed_at is None


def test_propose_rejects_an_action_policy_of_require_medical_review():
    with pytest.raises(ValueError):
        _proposal(action_policy="REQUIRE_MEDICAL_REVIEW")


@pytest.mark.parametrize(
    "field", ["scope_type", "scope_id", "risk_type", "risk_level", "action_policy", "source_type", "source_reference", "created_by"]
)
def test_propose_rejects_any_empty_provenance_field(field):
    with pytest.raises(ValueError):
        _proposal(**{field: ""})


def test_a_proposed_policy_alone_cannot_resolve_to_safe(db):
    """The central safety property: REVIEW_REQUIRED is never SAFE, no matter
    how favorable the proposed content looks."""
    policy = propose_policy(db, proposal=_proposal(risk_level="LOW", action_policy="SAFE_NO_ACTION_NEEDED"))
    outcome = SafetyGateway._route(
        _FakeDecision(risk_level=policy.risk_level, recommended_action=policy.action_policy, policy_review_status=policy.review_status)
    )
    from backend.agents.v2.safety import SafetyOutcome

    assert outcome is SafetyOutcome.HANDOFF_REQUIRED


# ---------------------------------------------------------------------------
# approve_policy
# ---------------------------------------------------------------------------


def test_approve_requires_a_real_non_empty_reviewer(db):
    policy = propose_policy(db, proposal=_proposal())
    with pytest.raises(PolicyReviewError):
        approve_policy(db, policy_id=policy.id, reviewed_by="", reviewed_at=NOW)
    with pytest.raises(PolicyReviewError):
        approve_policy(db, policy_id=policy.id, reviewed_by="   ", reviewed_at=NOW)


def test_approve_flips_to_reviewed_with_the_supplied_identity(db):
    policy = propose_policy(db, proposal=_proposal())
    approved = approve_policy(db, policy_id=policy.id, reviewed_by="Dr. Real Reviewer, MD", reviewed_at=NOW)
    assert approved.review_status == "REVIEWED"
    assert approved.reviewed_by == "Dr. Real Reviewer, MD"
    assert approved.reviewed_at == NOW


def test_approved_policy_content_is_exactly_what_was_proposed_unedited(db):
    policy = propose_policy(db, proposal=_proposal(risk_level="LOW", action_policy="SAFE_NO_ACTION_NEEDED"))
    approved = approve_policy(db, policy_id=policy.id, reviewed_by="Dr. Real Reviewer, MD", reviewed_at=NOW)
    assert approved.risk_level == "LOW"
    assert approved.action_policy == "SAFE_NO_ACTION_NEEDED"


def test_approve_now_resolves_to_safe(db):
    policy = propose_policy(db, proposal=_proposal(risk_level="LOW", action_policy="SAFE_NO_ACTION_NEEDED"))
    approved = approve_policy(db, policy_id=policy.id, reviewed_by="Dr. Real Reviewer, MD", reviewed_at=NOW)
    from backend.agents.v2.safety import SafetyOutcome

    outcome = SafetyGateway._route(
        _FakeDecision(risk_level=approved.risk_level, recommended_action=approved.action_policy, policy_review_status=approved.review_status)
    )
    assert outcome is SafetyOutcome.SAFE


def test_approve_unknown_policy_id_fails_closed(db):
    with pytest.raises(PolicyReviewError):
        approve_policy(db, policy_id="does-not-exist", reviewed_by="Dr. Real Reviewer, MD", reviewed_at=NOW)


def test_approve_twice_is_rejected_not_silently_reapplied(db):
    policy = propose_policy(db, proposal=_proposal())
    approve_policy(db, policy_id=policy.id, reviewed_by="Dr. First Reviewer", reviewed_at=NOW)
    with pytest.raises(PolicyReviewError):
        approve_policy(db, policy_id=policy.id, reviewed_by="Dr. Second Reviewer", reviewed_at=NOW)


# ---------------------------------------------------------------------------
# reject_policy
# ---------------------------------------------------------------------------


def test_reject_requires_a_real_reviewer_too(db):
    policy = propose_policy(db, proposal=_proposal())
    with pytest.raises(PolicyReviewError):
        reject_policy(db, policy_id=policy.id, reviewed_by="", reviewed_at=NOW)


def test_reject_marks_rejected_not_reviewed(db):
    policy = propose_policy(db, proposal=_proposal())
    rejected = reject_policy(db, policy_id=policy.id, reviewed_by="Dr. Real Reviewer, MD", reviewed_at=NOW)
    assert rejected.review_status == "REJECTED"
    assert rejected.reviewed_by == "Dr. Real Reviewer, MD"


def test_a_rejected_policy_cannot_later_be_approved(db):
    policy = propose_policy(db, proposal=_proposal())
    reject_policy(db, policy_id=policy.id, reviewed_by="Dr. Real Reviewer, MD", reviewed_at=NOW)
    with pytest.raises(PolicyReviewError):
        approve_policy(db, policy_id=policy.id, reviewed_by="Dr. Real Reviewer, MD", reviewed_at=NOW)


class _FakeDecision:
    def __init__(self, *, risk_level, recommended_action, policy_review_status):
        self.risk_level = risk_level
        self.recommended_action = recommended_action
        self.policy_review_status = policy_review_status
