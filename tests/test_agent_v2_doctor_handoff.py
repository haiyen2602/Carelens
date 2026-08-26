"""BUILD-10 Doctor Handoff lifecycle, authorization, and terminal integration."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from backend.agents.v2.handoff import (
    AgentHandoffResult,
    DoctorHandoffGateway,
    DoctorHandoffRequest,
    HandoffContextRef,
    HandoffContextSource,
)
from backend.agents.v2.model_gateway import ModelPlan
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyDecision, SafetyOutcome
from backend.api.security import CurrentUser
from backend.db.models import Account, CaregiverLink, DoctorReviewRequest, DoctorWatch, Patient
from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter
from backend.services.doctor_handoff import (
    DoctorAuthorizationError,
    HandoffCreateCommand,
    HandoffStatus,
    InvalidHandoffTransitionError,
    VerifiedContextRef,
    VerifiedContextSource,
    answer_doctor_review_request,
    assign_doctor_review_request,
    cancel_doctor_review_request,
    create_doctor_review_request,
    resolve_approved_doctor,
)

NOW = datetime(2026, 8, 18, tzinfo=UTC)
TABLES = (Patient.__table__, Account.__table__, CaregiverLink.__table__, DoctorWatch.__table__, DoctorReviewRequest.__table__)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def _sqlite_btrim(connection, _record) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip() if value else value, deterministic=True)
    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patient(db: Session, *, patient_id="patient-1", doctor_id="doctor-1") -> None:
    db.add(Patient(id=patient_id, full_name="Patient", doctor_id=doctor_id))


def _doctor(db: Session, *, doctor_id="doctor-1", account_id="doctor-account") -> None:
    db.add(
        Account(
            id=account_id,
            full_name="Doctor",
            email=f"{account_id}@example.local",
            password_hash="not-a-password",
            role="doctor",
            doctor_id=doctor_id,
            status="active",
        )
    )


def _command(**changes: object) -> HandoffCreateCommand:
    values: dict[str, object] = {
        "patient_id": "patient-1",
        "actor_id": "patient-account",
        "patient_question": "Toi quen lieu sang nay, toi can bac si xem xet.",
        "reason_code": "NO_POLICY_SAFE_FALLBACK",
        "risk_disposition": "HANDOFF_REQUIRED",
        "idempotency_key": "run:1:handoff",
        "verified_context_refs": (
            VerifiedContextRef(VerifiedContextSource.SAFETY_DOMAIN, "assessment-1", "safety-domain:assessment-1"),
        ),
    }
    values.update(changes)
    return HandoffCreateCommand(**values)  # type: ignore[arg-type]


def _safety() -> SafetyDecision:
    return SafetyDecision(
        outcome=SafetyOutcome.HANDOFF_REQUIRED,
        reason_code="NO_POLICY_SAFE_FALLBACK",
        provenance="safety-domain:assessment-1",
        assessment_id="assessment-1",
        risk_level="UNKNOWN",
        recommended_action="REQUIRE_MEDICAL_REVIEW",
        policy_source_type="SYSTEM_DEFAULT",
        policy_review_status="REVIEW_REQUIRED",
        evaluated_at=NOW,
    )


def test_handoff_assigns_only_explicit_active_treating_doctor_and_preserves_provenance(db):
    _patient(db)
    _doctor(db)
    result = create_doctor_review_request(db, command=_command(), created_at=NOW)

    request = result.request
    assert (result.created, request.status, request.assigned_doctor_id) == (True, HandoffStatus.ASSIGNED, "doctor-1")
    assert request.agent_summary == (
        "Safety disposition: HANDOFF_REQUIRED. Reason code: NO_POLICY_SAFE_FALLBACK. "
        "Verified context references: assessment-1."
    )
    assert request.patient_question not in request.agent_summary
    assert request.summary_provenance == request.verified_context_refs
    assert request.verified_context_refs[0]["provenance"] == "safety-domain:assessment-1"


def test_missing_or_broad_watch_doctor_remains_pending_and_never_randomly_assigns(db):
    _patient(db, doctor_id=None)
    _doctor(db, doctor_id="watch-only")
    db.add(DoctorWatch(doctor_id="watch-only", patient_id="patient-1"))

    result = create_doctor_review_request(db, command=_command(), created_at=NOW)
    assert resolve_approved_doctor(db, "patient-1") is None
    assert (result.request.status, result.request.assigned_doctor_id) == (HandoffStatus.PENDING, None)


def test_duplicate_retry_is_idempotent_and_conflicting_context_is_rejected(db):
    _patient(db)
    _doctor(db)
    first = create_doctor_review_request(db, command=_command(), created_at=NOW)
    second = create_doctor_review_request(db, command=_command(), created_at=NOW)

    assert (first.created, second.created, first.request.id, second.request.id) == (True, False, first.request.id, first.request.id)
    assert db.execute(select(func.count()).select_from(DoctorReviewRequest)).scalar_one() == 1
    with pytest.raises(Exception, match="different authorized context"):
        create_doctor_review_request(db, command=_command(patient_id="patient-2"), created_at=NOW)


def test_lifecycle_allows_only_valid_transitions_and_assigned_doctor_answer(db):
    _patient(db, doctor_id=None)
    _doctor(db)
    pending = create_doctor_review_request(db, command=_command(), created_at=NOW).request
    with pytest.raises(DoctorAuthorizationError):
        assign_doctor_review_request(db, request_id=pending.id, doctor_id="doctor-1", assigned_at=NOW)

    db.get(Patient, "patient-1").doctor_id = "doctor-1"
    assigned = assign_doctor_review_request(db, request_id=pending.id, doctor_id="doctor-1", assigned_at=NOW)
    with pytest.raises(DoctorAuthorizationError):
        answer_doctor_review_request(db, request_id=assigned.id, doctor_id="other", answer="review", answered_at=NOW)
    answered = answer_doctor_review_request(db, request_id=assigned.id, doctor_id="doctor-1", answer="Doctor response", answered_at=NOW)
    assert answered.status == HandoffStatus.ANSWERED
    with pytest.raises(InvalidHandoffTransitionError):
        cancel_doctor_review_request(db, request_id=answered.id, cancelled_at=NOW)


def test_cancellation_is_terminal_and_rolls_back_with_outer_transaction(db):
    _patient(db)
    _doctor(db)
    db.commit()
    with pytest.raises(RuntimeError), db.begin():
        # SQLite starts its actual outer transaction lazily; force a write
        # before the domain's idempotency savepoint. PostgreSQL starts at BEGIN.
        db.execute(text("UPDATE patient SET full_name = full_name WHERE id = 'patient-1'"))
        created = create_doctor_review_request(db, command=_command(), created_at=NOW).request
        cancel_doctor_review_request(db, request_id=created.id, cancelled_at=NOW)
        raise RuntimeError("force rollback")
    assert db.execute(select(DoctorReviewRequest)).scalars().all() == []


def test_safety_triggered_gateway_binds_authorized_actor_and_denies_cross_patient(db):
    _patient(db)
    _doctor(db)
    actor = CurrentUser(id="patient-account", role="patient", patient_id="patient-1", doctor_id=None)
    gateway = DoctorHandoffGateway(AuthorizedDoctorHandoffAdapter(db, actor))
    result = gateway.create(
        request=DoctorHandoffRequest(
            patient_id="patient-1",
            actor_id="patient-account",
            patient_question="Can bac si xem xet",
            idempotency_key="agent-run:1",
            verified_context_refs=(HandoffContextRef(HandoffContextSource.SAFETY_DOMAIN, "assessment-1", "safety-domain:assessment-1"),),
        ),
        safety=_safety(),
        created_at=NOW,
    )
    assert (result.created, result.status) == (True, HandoffStatus.ASSIGNED)

    with pytest.raises(Exception):
        gateway.create(
            request=DoctorHandoffRequest("patient-2", "patient-account", "question", "agent-run:2"),
            safety=_safety(),
            created_at=NOW,
        )


def test_adapter_reuses_an_active_uncertainty_handoff_instead_of_duplicating(db):
    """BUILD-44 defensive fix: ``_ACTIVE_HANDOFF_STATUSES`` (agent_doctor_
    handoff.py) did not include ``ACTIVE`` -- a status this build introduced
    -- so a patient whose existing UNCERTAINTY_HANDOFF row a doctor has
    already claimed AND activated would not have been reused by this dedup
    check, creating a second, rival ``DoctorReviewRequest`` for the same
    episode. In the real production route this branch is currently
    unreachable while ACTIVE (agent_v2_routes.py's own takeover check
    returns first, see the BUILD-44 report SS7) -- this test exercises the
    adapter directly, the way a future caller or refactor might, so the
    dedup logic is correct on its own terms, not only by accident of call
    order elsewhere."""
    from backend.agents.v2.handoff import HandoffCreateCommand as AgentHandoffCreateCommand

    _patient(db)
    active = DoctorReviewRequest(
        id="active-1", patient_id="patient-1", created_by_actor_id="acct-1",
        reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF",
        patient_question="q", agent_summary="s", status=HandoffStatus.ACTIVE,
        idempotency_key="key-active-1", assigned_doctor_id="doctor-1",
    )
    db.add(active)
    db.commit()

    actor = CurrentUser(id="acct-1", role="patient", patient_id="patient-1", doctor_id=None)
    result = AuthorizedDoctorHandoffAdapter(db, actor).create(
        AgentHandoffCreateCommand(
            patient_id="patient-1", actor_id="acct-1", patient_question="another turn",
            reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF",
            idempotency_key="key-active-2", verified_context_refs=(),
        ),
        created_at=NOW,
    )
    assert result.created is False
    assert result.request_id == "active-1"
    assert db.execute(select(func.count()).select_from(DoctorReviewRequest)).scalar_one() == 1


def test_gateway_rejects_non_safety_handoff_and_runtime_stops_before_model():
    class _Domain:
        def create(self, command, *, created_at):
            return AgentHandoffResult("request-1", HandoffStatus.ASSIGNED, "doctor-1", True)

    with pytest.raises(ValueError, match="REQUIRES_SAFETY_HANDOFF"):
        DoctorHandoffGateway(_Domain()).create(
            request=DoctorHandoffRequest("patient-1", "actor", "question", "key"),
            safety=SafetyDecision(SafetyOutcome.SAFE, "OK", "safety-domain:1"),
        )

    class _Model:
        calls = 0

        def plan_read_only(self, *, message, actor_role):
            self.calls += 1
            return ModelPlan(response="must not run")

    model = _Model()
    result = ReadOnlyAgentRuntime(model, limits=AgentRunLimits(100, 4, 2, 2, 0, 5, 10)).run(
        message="unsafe", actor_role="patient", tools=object(), handoff_result=AgentHandoffResult("request-1", "ASSIGNED", "doctor-1", True)
    )
    assert result.status is RunStatus.HANDOFF_CREATED
    assert model.calls == 0
