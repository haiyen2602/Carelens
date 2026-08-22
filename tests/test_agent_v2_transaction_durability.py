"""BUILD-18B defect 3 regression: the orchestrate route must actually commit.

Every test here opens genuinely *independent* SQLAlchemy engines/sessions
bound to the same on-disk SQLite file (never one shared, still-open session)
so that "does this durably persist" can only pass if a real commit happened
-- exactly the gap live Railway staging testing found (BUILD-18): every
write-path scenario returned a correct-looking HTTP response while
``agent_run``/``agent_run_checkpoint``/``doctor_review_request`` stayed
empty, because ``run_agent_orchestration`` never called ``db.commit()``.

All tests use a ``DOCTOR_REVIEW``-classified message ("đổi liều thuốc").
This intent bypasses Safety Domain and reaches ``HANDOFF_CREATED`` before
any Main Model call (see ``backend/agents/v2/runtime.py``'s ``handoff_result
is not None`` short-circuit), so these tests need no OpenAI credentials and
make no network call, while still exercising the full checkpoint -> safety
-> handoff -> commit path this defect broke.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.agents.v2.checkpoint import CheckpointedSafetyGateway
from backend.agents.v2.handoff import AgentHandoffResult, DoctorHandoffGateway, DoctorHandoffRequest
from backend.agents.v2.model_gateway import ModelPlan
from backend.agents.v2.orchestrator import AgentOrchestrator, OrchestrationRequest
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyDecision, SafetyOutcome
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway
from backend.api.agent_v2_routes import run_agent_orchestration
from backend.api.security import CurrentUser
from backend.config import get_settings
from backend.db.models import AgentIdempotencyKey, AgentRun, AgentRunCheckpoint, DoctorReviewRequest, Patient
from backend.models.schemas import AgentV2OrchestrateRequest
from backend.services.agent_checkpoint import (
    CheckpointCreateCommand,
    claim_resume,
    create_or_load_checkpoint,
)
from tests.test_agent_v2_orchestrator import _SpyModelGateway, _context_manager, _limits, _tools

TABLES = (
    Patient.__table__,
    AgentRun.__table__,
    AgentRunCheckpoint.__table__,
    DoctorReviewRequest.__table__,
    AgentIdempotencyKey.__table__,
)


@pytest.fixture(autouse=True)
def _agent_runtime_enabled(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "durability.db")
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    for table in TABLES:
        table.create(engine)
    engine.dispose()
    return path


def _new_session(db_path: str) -> Session:
    """A genuinely independent engine + session bound to the same file."""
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    return Session(engine, expire_on_commit=False)


def _seed_patient(db_path: str, patient_id: str = "patient-1") -> None:
    session = _new_session(db_path)
    try:
        session.add(Patient(id=patient_id, full_name="Test Patient"))
        session.commit()
    finally:
        session.close()


def _actor(patient_id: str = "patient-1") -> CurrentUser:
    return CurrentUser(id="account-1", role="patient", patient_id=patient_id, doctor_id=None)


def _http_request(patient_id: str = "patient-1", **overrides) -> AgentV2OrchestrateRequest:
    values = dict(patient_id=patient_id, message="Toi muon doi lieu thuoc sang 2 vien")
    values.update(overrides)
    return AgentV2OrchestrateRequest(**values)


# ---------------------------------------------------------------------------
# agent_run / checkpoint / handoff persist after commit, seen from a NEW session
# ---------------------------------------------------------------------------


def test_agent_run_persists_and_is_visible_from_an_independent_session(db_path):
    _seed_patient(db_path)
    session_a = _new_session(db_path)
    try:
        response = run_agent_orchestration(_http_request(), db=session_a, actor=_actor())
    finally:
        session_a.close()

    assert response.status == "HANDOFF_CREATED"

    session_b = _new_session(db_path)
    try:
        run = session_b.get(AgentRun, response.agent_run_id)
        assert run is not None
        assert run.status == "HANDOFF_CREATED"
        assert run.patient_id == "patient-1"
    finally:
        session_b.close()


def test_checkpoint_persists_and_is_visible_from_an_independent_session(db_path):
    _seed_patient(db_path)
    session_a = _new_session(db_path)
    try:
        response = run_agent_orchestration(_http_request(), db=session_a, actor=_actor())
    finally:
        session_a.close()

    session_b = _new_session(db_path)
    try:
        checkpoint = session_b.execute(
            select(AgentRunCheckpoint).where(AgentRunCheckpoint.agent_run_id == response.agent_run_id)
        ).scalar_one()
        assert checkpoint.terminal_status == "HANDOFF_CREATED"
        assert checkpoint.safety_disposition == "HANDOFF_REQUIRED"
        # No prompt/message content -- only ids/provenance, per BUILD-12's invariant.
        assert "doi lieu" not in str(checkpoint.completed_tools) + str(checkpoint.verified_context_refs)
    finally:
        session_b.close()


def test_handoff_persists_and_is_visible_from_an_independent_session(db_path):
    _seed_patient(db_path)
    session_a = _new_session(db_path)
    try:
        response = run_agent_orchestration(_http_request(), db=session_a, actor=_actor())
    finally:
        session_a.close()

    assert response.handoff_id is not None

    session_b = _new_session(db_path)
    try:
        rows = session_b.execute(select(DoctorReviewRequest)).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == response.handoff_id
        assert rows[0].patient_id == "patient-1"
    finally:
        session_b.close()


# ---------------------------------------------------------------------------
# exception rollback: nothing durable survives a mid-run failure
# ---------------------------------------------------------------------------


def test_exception_during_orchestration_rolls_back_everything(db_path, monkeypatch):
    _seed_patient(db_path)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated failure after checkpoint creation")

    # create_or_load_checkpoint (which flushes a real AgentRun + checkpoint
    # row) is allowed to run for real; the NEXT checkpoint step is made to
    # raise, so there is genuine flushed-but-uncommitted state a correct
    # rollback must actually undo (not merely "nothing happened").
    monkeypatch.setattr("backend.agents.v2.orchestrator.claim_resume", _boom)

    session_a = _new_session(db_path)
    try:
        with pytest.raises(RuntimeError, match="simulated failure"):
            run_agent_orchestration(_http_request(), db=session_a, actor=_actor())
    finally:
        session_a.close()

    session_b = _new_session(db_path)
    try:
        assert session_b.execute(select(AgentRun)).scalars().all() == []
        assert session_b.execute(select(AgentRunCheckpoint)).scalars().all() == []
        assert session_b.execute(select(DoctorReviewRequest)).scalars().all() == []
    finally:
        session_b.close()


# ---------------------------------------------------------------------------
# commit failure: fail-closed, never a fabricated success
# ---------------------------------------------------------------------------


def test_commit_failure_is_fail_closed_not_a_fabricated_success(db_path, monkeypatch):
    _seed_patient(db_path)
    session_a = _new_session(db_path)

    def _commit_boom():
        raise RuntimeError("simulated commit failure")

    rollback_calls = []
    real_rollback = session_a.rollback

    def _spy_rollback():
        rollback_calls.append(True)
        return real_rollback()

    monkeypatch.setattr(session_a, "commit", _commit_boom)
    monkeypatch.setattr(session_a, "rollback", _spy_rollback)

    try:
        with pytest.raises(HTTPException) as exc:
            run_agent_orchestration(_http_request(), db=session_a, actor=_actor())
        assert exc.value.status_code == 503
    finally:
        session_a.close()

    assert rollback_calls, "a failed commit must still roll back, not leave the transaction dangling"

    session_b = _new_session(db_path)
    try:
        # The handoff was fully built in memory (flushed) before the commit
        # was attempted and failed -- it must not have become durable.
        assert session_b.execute(select(DoctorReviewRequest)).scalars().all() == []
    finally:
        session_b.close()


# ---------------------------------------------------------------------------
# identical retry does not duplicate a durable handoff (real cross-session commits)
# ---------------------------------------------------------------------------


def test_identical_retry_with_the_same_agent_run_id_does_not_duplicate_the_handoff(db_path):
    """Exercises the orchestrator directly (crash-recovery resume identity,
    not a client-supplied HTTP idempotency key -- see
    ``test_http_retry_with_the_same_idempotency_key_does_not_duplicate_the_handoff``
    below for the BUILD-22 HTTP-level version of this same guarantee) with two
    independent, really-committed sessions, and the REAL database-backed
    handoff domain (not an in-memory fake) so a duplicate would actually show
    up as a second row, not just a second call."""

    from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter

    agent_run_id = "run-retry-1"

    def _orchestrator(session: Session) -> AgentOrchestrator:
        return AgentOrchestrator(
            runtime=ReadOnlyAgentRuntime(_SpyModelGateway(ModelPlan(response="ignored")), limits=_limits()),
            context_manager=_context_manager(),
            safety_gateway=_safety_gateway_never_consulted(),
            handoff_gateway=DoctorHandoffGateway(AuthorizedDoctorHandoffAdapter(session, _actor())),
        )

    def _request_obj() -> OrchestrationRequest:
        return OrchestrationRequest(
            message="Toi muon doi lieu thuoc sang 2 vien",
            actor_id="account-1", actor_role="patient", patient_id="patient-1",
            conversation_id="conversation-1", session_id="session-1", agent_run_id=agent_run_id,
        )

    _seed_patient(db_path)

    session_a = _new_session(db_path)
    try:
        result_a = _orchestrator(session_a).run(_request_obj(), tools=_tools(), checkpoint_db=session_a)
        session_a.commit()
    finally:
        session_a.close()
    assert result_a.status is RunStatus.HANDOFF_CREATED

    # A genuinely new session/engine, simulating a retried request that
    # reuses the same agent_run_id (the crash-resume identity BUILD-12/16
    # define; a client-visible HTTP retry key is a separate, out-of-scope
    # feature -- see the module docstring).
    session_b = _new_session(db_path)
    try:
        with pytest.raises(Exception):
            # The checkpoint for agent_run_id is already terminal; a second
            # attempt to run the *same* logical run must be rejected outright
            # (claim_resume's own CheckpointTerminalError guard), not silently
            # re-executed -- proving no duplicate is even attempted.
            claim_resume(session_b, agent_run_id=agent_run_id, max_age=__import__("datetime").timedelta(minutes=5))
        session_b.rollback()
    finally:
        session_b.close()

    session_c = _new_session(db_path)
    try:
        rows = session_c.execute(select(DoctorReviewRequest)).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == result_a.handoff_result.request_id
    finally:
        session_c.close()


def _safety_gateway_never_consulted():
    """DOCTOR_REVIEW bypasses Safety Domain entirely; asserts that holds."""
    from backend.agents.v2.safety import SafetyGateway

    class _Domain:
        def assess(self, *, occurrence_id, evaluated_at):
            raise AssertionError("Safety Domain must not be consulted for a DOCTOR_REVIEW-bypass request")

    return SafetyGateway(_Domain(), timeout_seconds=5.0)


# ---------------------------------------------------------------------------
# checkpoint resume across independent sessions (crash before handoff creation)
# ---------------------------------------------------------------------------


def test_checkpoint_resume_across_independent_sessions_after_a_real_commit(db_path):
    """Real wall-clock throughout (not the fixed ``NOW``): ``CheckpointedSafetyGateway``
    has no ``now`` override, so mixing a fixed timestamp with its real-clock
    write would make ``claim_resume``'s staleness check flaky depending on
    how far the fixed timestamp drifts from the moment the test actually
    runs. A fast test keeps every real-clock call within milliseconds of each
    other, well under ``max_age``."""

    from datetime import timedelta as _timedelta

    from backend.agents.v2.checkpoint import CheckpointedDoctorHandoffGateway
    from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter

    _seed_patient(db_path)
    agent_run_id = "run-resume-cross-session"

    # Phase 1 ("the process that crashed"): create the checkpoint, resolve
    # the HANDOFF_REQUIRED safety disposition, and commit for real -- then
    # close the session, simulating the crash before handoff creation.
    session_1 = _new_session(db_path)
    try:
        create_or_load_checkpoint(
            session_1,
            command=CheckpointCreateCommand(
                agent_run_id=agent_run_id, patient_id="patient-1", conversation_id="conversation-1",
                request_id="session-1", intent="DOCTOR_REVIEW",
            ),
        )
        lease = claim_resume(session_1, agent_run_id=agent_run_id, max_age=_timedelta(minutes=5))
        safety = SafetyDecision(
            outcome=SafetyOutcome.HANDOFF_REQUIRED, reason_code="DOCTOR_REVIEW_REQUESTED",
            provenance="agent-orchestrator:doctor-review",
        )
        CheckpointedSafetyGateway(session_1).record(agent_run_id=agent_run_id, lease_token=lease.lease_token, safety=safety)
        session_1.commit()
    finally:
        session_1.close()

    # Phase 2 ("the resuming process", a genuinely different session/engine):
    # complete only the still-missing handoff creation step, using the REAL
    # DB-backed handoff domain (not an in-memory fake) so persistence is
    # actually exercised, not just the in-process call count.
    session_2 = _new_session(db_path)
    try:
        assert session_2.execute(select(DoctorReviewRequest)).scalars().all() == []  # nothing yet, proves phase 1 alone didn't create it

        lease_2 = claim_resume(session_2, agent_run_id=agent_run_id, max_age=_timedelta(minutes=5))
        handoff_request = DoctorHandoffRequest(
            patient_id="patient-1", actor_id="account-1", patient_question="Toi muon doi lieu thuoc",
            idempotency_key=f"agent-run:{agent_run_id}:handoff",
        )
        safety = SafetyDecision(
            outcome=SafetyOutcome.HANDOFF_REQUIRED, reason_code="DOCTOR_REVIEW_REQUESTED",
            provenance="agent-orchestrator:doctor-review",
        )
        result: AgentHandoffResult = CheckpointedDoctorHandoffGateway(
            session_2, DoctorHandoffGateway(AuthorizedDoctorHandoffAdapter(session_2, _actor()))
        ).create(agent_run_id=agent_run_id, lease_token=lease_2.lease_token, request=handoff_request, safety=safety)
        session_2.commit()
    finally:
        session_2.close()

    session_3 = _new_session(db_path)
    try:
        checkpoint = session_3.execute(
            select(AgentRunCheckpoint).where(AgentRunCheckpoint.agent_run_id == agent_run_id)
        ).scalar_one()
        assert checkpoint.terminal_status == "HANDOFF_CREATED"
        rows = session_3.execute(select(DoctorReviewRequest)).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == result.request_id
    finally:
        session_3.close()


# ---------------------------------------------------------------------------
# BUILD-22: HTTP-level idempotency key, through the real route, with real
# independent commits -- closes the scope gap the retry test above documents.
# ---------------------------------------------------------------------------


def test_http_retry_with_the_same_idempotency_key_does_not_duplicate_the_handoff(db_path):
    _seed_patient(db_path)

    session_a = _new_session(db_path)
    try:
        first = run_agent_orchestration(_http_request(idempotency_key="retry-key-1"), db=session_a, actor=_actor())
    finally:
        session_a.close()
    assert first.status == "HANDOFF_CREATED"
    assert first.handoff_id is not None

    # A genuinely new session/engine/HTTP call -- e.g. a client that timed
    # out waiting for the first response and resubmitted the same request.
    session_b = _new_session(db_path)
    try:
        second = run_agent_orchestration(_http_request(idempotency_key="retry-key-1"), db=session_b, actor=_actor())
    finally:
        session_b.close()

    assert second == first  # byte-for-byte the same response, not just "also HANDOFF_CREATED"

    session_c = _new_session(db_path)
    try:
        rows = session_c.execute(select(DoctorReviewRequest)).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == first.handoff_id
    finally:
        session_c.close()


def test_http_retry_with_a_different_idempotency_key_is_a_genuinely_independent_second_run(db_path):
    """Sanity check that the mechanism dedupes on the key, not on the message
    or the patient -- otherwise the prior test would be vacuous."""
    _seed_patient(db_path)

    session_a = _new_session(db_path)
    try:
        first = run_agent_orchestration(_http_request(idempotency_key="key-a"), db=session_a, actor=_actor())
    finally:
        session_a.close()

    session_b = _new_session(db_path)
    try:
        second = run_agent_orchestration(_http_request(idempotency_key="key-b"), db=session_b, actor=_actor())
    finally:
        session_b.close()

    assert first.agent_run_id != second.agent_run_id
    assert first.handoff_id != second.handoff_id

    session_c = _new_session(db_path)
    try:
        assert len(session_c.execute(select(DoctorReviewRequest)).scalars().all()) == 2
    finally:
        session_c.close()


def test_http_without_an_idempotency_key_is_unchanged_from_pre_build22_behavior(db_path):
    """Omitting the (optional) key preserves the original BUILD-16 contract:
    every call is its own independent run, exactly like before this build."""
    _seed_patient(db_path)

    session_a = _new_session(db_path)
    try:
        first = run_agent_orchestration(_http_request(), db=session_a, actor=_actor())
    finally:
        session_a.close()

    session_b = _new_session(db_path)
    try:
        second = run_agent_orchestration(_http_request(), db=session_b, actor=_actor())
    finally:
        session_b.close()

    assert first.agent_run_id != second.agent_run_id

    session_c = _new_session(db_path)
    try:
        assert len(session_c.execute(select(DoctorReviewRequest)).scalars().all()) == 2
        assert session_c.execute(select(AgentIdempotencyKey)).scalars().all() == []
    finally:
        session_c.close()


def test_http_idempotency_key_is_bound_to_the_authenticated_actor_and_patient(db_path):
    """The identical key string from a different (actor, patient) pair must
    never replay this run's cached result -- it authorizes independently and
    starts its own, unrelated run."""
    _seed_patient(db_path, patient_id="patient-1")
    _seed_patient(db_path, patient_id="patient-2")

    session_a = _new_session(db_path)
    try:
        owner = run_agent_orchestration(
            _http_request(patient_id="patient-1", idempotency_key="shared-key"), db=session_a, actor=_actor("patient-1")
        )
    finally:
        session_a.close()

    session_b = _new_session(db_path)
    try:
        other_actor = CurrentUser(id="account-2", role="patient", patient_id="patient-2", doctor_id=None)
        other = run_agent_orchestration(
            _http_request(patient_id="patient-2", idempotency_key="shared-key"), db=session_b, actor=other_actor
        )
    finally:
        session_b.close()

    assert other.agent_run_id != owner.agent_run_id
    assert other.handoff_id != owner.handoff_id

    session_c = _new_session(db_path)
    try:
        assert len(session_c.execute(select(DoctorReviewRequest)).scalars().all()) == 2
    finally:
        session_c.close()
