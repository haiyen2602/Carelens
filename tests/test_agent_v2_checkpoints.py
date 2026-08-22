"""BUILD-12 durable checkpoint, recovery, idempotency, and safety tests."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.agents.v2.checkpoint import (
    CheckpointedDoctorHandoffGateway,
    CheckpointedSafetyGateway,
    CheckpointedTerminalStateRecorder,
    CheckpointedToolGateway,
    CompletedToolReplayError,
)
from backend.agents.v2.handoff import AgentHandoffResult, DoctorHandoffGateway, DoctorHandoffRequest
from backend.agents.v2.model_gateway import ToolCall
from backend.agents.v2.runtime import RunMetrics, RunResult, RunStatus
from backend.agents.v2.safety import SafetyDecision, SafetyOutcome
from backend.agents.v2.tools import ToolResult
from backend.db.models import AgentRun, AgentRunCheckpoint
from backend.services.agent_checkpoint import (
    CheckpointBusyError,
    CheckpointCreateCommand,
    CheckpointError,
    CheckpointTerminalError,
    PendingAction,
    ResolvedEntity,
    StaleCheckpointError,
    VerifiedReference,
    begin_tool,
    claim_resume,
    complete_tool,
    create_or_load_checkpoint,
    record_handoff_created,
)

NOW = datetime(2026, 8, 18, 10, tzinfo=UTC)
TABLES = (AgentRun.__table__, AgentRunCheckpoint.__table__)


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


def _command(run_id="run-1") -> CheckpointCreateCommand:
    return CheckpointCreateCommand(
        agent_run_id=run_id,
        patient_id="patient-1",
        conversation_id="conversation-1",
        request_id="request-1",
        intent="MEDICATION_QUESTION",
    )


def _claim(db: Session, run_id="run-1", now=NOW):
    return claim_resume(db, agent_run_id=run_id, max_age=timedelta(seconds=30), now=now)


def _safety(outcome=SafetyOutcome.HANDOFF_REQUIRED) -> SafetyDecision:
    return SafetyDecision(
        outcome=outcome,
        reason_code="REQUIRES_REVIEW",
        provenance="safety-domain:assessment-1",
        assessment_id="assessment-1",
    )


def test_checkpoint_is_durable_idempotent_and_contains_no_prompt_or_raw_tool_payload(db):
    first, created = create_or_load_checkpoint(db, command=_command(), now=NOW)
    second, repeated = create_or_load_checkpoint(db, command=_command(), now=NOW)
    assert created and not repeated
    assert first.checkpoint_id == second.checkpoint_id
    row = db.get(AgentRunCheckpoint, first.checkpoint_id)
    assert row is not None
    assert row.completed_tools == row.resolved_entities == row.verified_context_refs == []
    assert "message" not in AgentRunCheckpoint.__table__.c
    assert db.get(AgentRun, "run-1").status == "RUNNING"
    with pytest.raises(CheckpointError, match="different authorized context"):
        create_or_load_checkpoint(
            db,
            command=CheckpointCreateCommand("run-1", "patient-2", "conversation-1", "request-1", "OTHER"),
            now=NOW,
        )


def test_crash_before_tool_can_resume_but_crash_after_tool_reuses_the_same_key_without_replay(db):
    create_or_load_checkpoint(db, command=_command(), now=NOW)
    before = _claim(db)
    # Crash before begin_tool: no action happened, so a stale lease can resume.
    resumed_before = _claim(db, now=NOW + timedelta(seconds=31))
    assert resumed_before.snapshot.step_number == before.snapshot.step_number + 1

    permit = begin_tool(
        db,
        agent_run_id="run-1",
        lease_token=resumed_before.lease_token,
        tool_name="get_today_doses",
        now=NOW + timedelta(seconds=31),
    )
    with pytest.raises(CheckpointBusyError, match="in flight"):
        begin_tool(
            db,
            agent_run_id="run-1",
            lease_token=resumed_before.lease_token,
            tool_name="get_today_doses",
            now=NOW + timedelta(seconds=31),
        )
    # Simulate a crash after the external/domain call but before checkpoint completion.
    resumed_after = _claim(db, now=NOW + timedelta(seconds=62))
    retry_permit = begin_tool(
        db,
        agent_run_id="run-1",
        lease_token=resumed_after.lease_token,
        tool_name="get_today_doses",
    )
    assert retry_permit.idempotency_key == permit.idempotency_key
    completed = complete_tool(
        db,
        permit=retry_permit,
        provenance="operational-db:dose-occurrence:today",
        verified_context_refs=(VerifiedReference("OPERATIONAL_DB", "today-1", "operational-db:today"),),
    )
    assert completed.completed_tools[0].idempotency_key == permit.idempotency_key


def test_completed_tool_is_not_replayed_and_only_reference_metadata_is_persisted(db):
    create_or_load_checkpoint(db, command=_command(), now=NOW)
    lease = _claim(db)
    permit = begin_tool(db, agent_run_id="run-1", lease_token=lease.lease_token, tool_name="search_drug")
    complete_tool(
        db,
        permit=permit,
        provenance="canonical-drug-v2:catalog",
        resolved_entities=(ResolvedEntity("drug_product", "product-1", "canonical-drug-v2:catalog"),),
    )
    # The next workflow step may plan, but it has no raw search query/result to replay.
    next_lease = _claim(db, now=NOW + timedelta(seconds=1))
    gateway = CheckpointedToolGateway(db, _ToolGateway())
    # Re-create the exact already-completed step in a controlled row state to
    # prove the adapter refuses a duplicate execution instead of invoking ToolGateway.
    row = db.execute(select(AgentRunCheckpoint).where(AgentRunCheckpoint.agent_run_id == "run-1")).scalar_one()
    row.step_number = permit.step_number
    row.pending_action = PendingAction.TOOL
    row.workflow_state = "RUNNING"
    with pytest.raises(CompletedToolReplayError):
        gateway.execute(
            agent_run_id="run-1",
            lease_token=next_lease.lease_token,
            call=ToolCall("search_drug", {"query": "must-not-persist", "limit": 1}),
        )
    assert gateway._tools.calls == []
    persisted = db.get(AgentRunCheckpoint, row.id)
    assert "must-not-persist" not in str(persisted.completed_tools)


def test_concurrent_resume_lease_and_stale_unleased_checkpoint_fail_closed(db):
    create_or_load_checkpoint(db, command=_command(), now=NOW)
    _claim(db)
    with pytest.raises(CheckpointBusyError):
        _claim(db, now=NOW + timedelta(seconds=1))

    create_or_load_checkpoint(db, command=_command("run-stale"), now=NOW)
    with pytest.raises(StaleCheckpointError):
        _claim(db, run_id="run-stale", now=NOW + timedelta(minutes=2))
    stale = db.execute(select(AgentRunCheckpoint).where(AgentRunCheckpoint.agent_run_id == "run-stale")).scalar_one()
    assert stale.terminal_status == "TIMEOUT"


def test_safety_handoff_and_all_terminal_states_integrate_without_model_reinterpretation(db):
    create_or_load_checkpoint(db, command=_command(), now=NOW)
    safety_lease = _claim(db)
    safety_checkpoint = CheckpointedSafetyGateway(db).record(
        agent_run_id="run-1", lease_token=safety_lease.lease_token, safety=_safety()
    )
    assert safety_checkpoint.pending_action is PendingAction.HANDOFF
    assert safety_checkpoint.safety_disposition == SafetyOutcome.HANDOFF_REQUIRED

    terminal_lease = _claim(db, now=NOW + timedelta(seconds=1))
    terminal = CheckpointedTerminalStateRecorder(db).record(
        agent_run_id="run-1",
        lease_token=terminal_lease.lease_token,
        result=RunResult(RunStatus.HANDOFF_REQUIRED, "no clinical answer", (), RunMetrics()),
    )
    assert terminal.terminal_status == "HANDOFF_REQUIRED"
    with pytest.raises(CheckpointTerminalError):
        _claim(db, now=NOW + timedelta(seconds=2))

    create_or_load_checkpoint(db, command=_command("run-handoff-created"), now=NOW)
    handoff_safety_lease = _claim(db, run_id="run-handoff-created")
    CheckpointedSafetyGateway(db).record(
        agent_run_id="run-handoff-created", lease_token=handoff_safety_lease.lease_token, safety=_safety()
    )
    handoff_lease = _claim(db, run_id="run-handoff-created", now=NOW + timedelta(seconds=1))
    handoff_terminal = record_handoff_created(
        db,
        agent_run_id="run-handoff-created",
        lease_token=handoff_lease.lease_token,
        handoff_id="handoff-1",
        provenance="doctor-handoff:request",
    )
    assert handoff_terminal.terminal_status == "HANDOFF_CREATED"

    create_or_load_checkpoint(db, command=_command("run-handoff-gateway"), now=NOW)
    gateway_safety_lease = _claim(db, run_id="run-handoff-gateway")
    CheckpointedSafetyGateway(db).record(
        agent_run_id="run-handoff-gateway", lease_token=gateway_safety_lease.lease_token, safety=_safety()
    )
    gateway_lease = _claim(db, run_id="run-handoff-gateway", now=NOW + timedelta(seconds=1))
    domain = _HandoffDomain()
    gateway_result = CheckpointedDoctorHandoffGateway(db, DoctorHandoffGateway(domain)).create(
        agent_run_id="run-handoff-gateway",
        lease_token=gateway_lease.lease_token,
        request=DoctorHandoffRequest("patient-1", "actor-1", "question not checkpointed", "client-key"),
        safety=_safety(),
        created_at=NOW,
    )
    assert gateway_result.request_id == "handoff-domain-1"
    assert domain.idempotency_keys == ["agent-run:run-handoff-gateway:handoff"]

    for status in RunStatus:
        if status is RunStatus.HANDOFF_CREATED:
            continue
        run_id = f"run-{status.value.lower()}"
        create_or_load_checkpoint(db, command=_command(run_id), now=NOW)
        lease = _claim(db, run_id=run_id)
        snapshot = CheckpointedTerminalStateRecorder(db).record(
            agent_run_id=run_id,
            lease_token=lease.lease_token,
            result=RunResult(status, "safe terminal", (), RunMetrics()),
        )
        assert snapshot.terminal_status == status.value


def test_outer_transaction_rollback_removes_run_and_checkpoint(db):
    with pytest.raises(RuntimeError), db.begin():
        create_or_load_checkpoint(db, command=_command("run-rollback"), now=NOW)
        raise RuntimeError("force rollback")
    assert db.get(AgentRun, "run-rollback") is None
    assert db.execute(select(AgentRunCheckpoint).where(AgentRunCheckpoint.agent_run_id == "run-rollback")).scalar_one_or_none() is None


class _ToolGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append(name)
        return ToolResult(name=name, data={"items": []}, provenance="canonical-drug-v2:catalog")


class _HandoffDomain:
    def __init__(self) -> None:
        self.idempotency_keys: list[str] = []

    def create(self, command, *, created_at):
        self.idempotency_keys.append(command.idempotency_key)
        return AgentHandoffResult("handoff-domain-1", "PENDING", None, True)
