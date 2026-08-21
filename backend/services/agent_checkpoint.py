"""Durable, sanitized checkpoint state for Agent V2 execution recovery.

Checkpoints are deliberately limited to identifiers, enum states, and verified
provenance. They must never contain a prompt, model chain-of-thought, tool
arguments/results, secrets, or raw patient conversation content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import AgentRun, AgentRunCheckpoint


class CheckpointWorkflowState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    TOOL_IN_FLIGHT = "TOOL_IN_FLIGHT"
    WAITING_FOR_SAFETY = "WAITING_FOR_SAFETY"
    WAITING_FOR_HANDOFF = "WAITING_FOR_HANDOFF"
    TERMINAL = "TERMINAL"


class PendingAction(StrEnum):
    NONE = "NONE"
    PLAN = "PLAN"
    TOOL = "TOOL"
    SAFETY = "SAFETY"
    HANDOFF = "HANDOFF"


_TERMINAL_STATUSES = frozenset(
    {
        "COMPLETED",
        "FAILED",
        "BUDGET_EXCEEDED",
        "TIMEOUT",
        "SAFETY_BLOCKED",
        "HANDOFF_REQUIRED",
        "HANDOFF_CREATED",
        "CANCELLED",
    }
)
_SAFETY_DISPOSITIONS = frozenset({"SAFE", "SAFETY_BLOCKED", "HANDOFF_REQUIRED"})


class CheckpointError(RuntimeError):
    """Safe checkpoint failure; callers must not expose internal state."""


class CheckpointBusyError(CheckpointError):
    """Another worker owns a current resume lease."""


class StaleCheckpointError(CheckpointError):
    """A non-running stale checkpoint is not safe to continue."""


class CheckpointTerminalError(CheckpointError):
    """A terminal Agent run cannot be resumed or mutated."""


@dataclass(frozen=True)
class VerifiedReference:
    source: str
    reference_id: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.source or not self.reference_id or not self.provenance:
            raise ValueError("verified checkpoint reference requires source, id, and provenance")

    def as_json(self) -> dict[str, str]:
        return {"source": self.source, "id": self.reference_id, "provenance": self.provenance}


@dataclass(frozen=True)
class ResolvedEntity:
    kind: str
    entity_id: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.kind or not self.entity_id or not self.provenance:
            raise ValueError("resolved checkpoint entity requires kind, id, and provenance")

    def as_json(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.entity_id, "provenance": self.provenance}


@dataclass(frozen=True)
class CompletedTool:
    name: str
    idempotency_key: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.name or not self.idempotency_key or not self.provenance:
            raise ValueError("completed tool requires name, idempotency key, and provenance")

    def as_json(self) -> dict[str, str]:
        return {
            "name": self.name,
            "idempotency_key": self.idempotency_key,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class CheckpointCreateCommand:
    agent_run_id: str
    patient_id: str | None
    conversation_id: str | None
    request_id: str | None
    intent: str | None
    initial_action: PendingAction = PendingAction.PLAN

    def __post_init__(self) -> None:
        if not self.agent_run_id or not self.agent_run_id.strip():
            raise ValueError("agent_run_id is required")


@dataclass(frozen=True)
class CheckpointSnapshot:
    checkpoint_id: str
    agent_run_id: str
    step_number: int
    workflow_state: CheckpointWorkflowState
    completed_tools: tuple[CompletedTool, ...]
    resolved_entities: tuple[ResolvedEntity, ...]
    verified_context_refs: tuple[VerifiedReference, ...]
    safety_disposition: str | None
    pending_action: PendingAction
    terminal_status: str | None
    revision: int
    updated_at: datetime


@dataclass(frozen=True)
class ResumeLease:
    snapshot: CheckpointSnapshot
    lease_token: str


@dataclass(frozen=True)
class ToolPermit:
    agent_run_id: str
    step_number: int
    tool_name: str
    idempotency_key: str
    lease_token: str
    already_completed: bool


def create_or_load_checkpoint(
    db: Session,
    *,
    command: CheckpointCreateCommand,
    now: datetime | None = None,
) -> tuple[CheckpointSnapshot, bool]:
    """Create one checkpoint per run, or return exactly the same run state."""
    at = now or datetime.now(UTC)
    existing = _locked_checkpoint(db, command.agent_run_id)
    if existing is not None:
        run = db.get(AgentRun, command.agent_run_id)
        if run is None or not _same_run(run, command):
            raise CheckpointError("agent run id cannot be reused for different authorized context")
        return _snapshot(existing), False

    run = db.get(AgentRun, command.agent_run_id)
    if run is not None and not _same_run(run, command):
        raise CheckpointError("agent run id cannot be reused for different authorized context")
    if run is None:
        db.add(
            AgentRun(
                id=command.agent_run_id,
                patient_id=command.patient_id,
                conversation_id=command.conversation_id,
                request_id=command.request_id,
                intent=command.intent,
                status="RUNNING",
                started_at=at,
                metadata_json={},
            )
        )
        db.flush()
    checkpoint = AgentRunCheckpoint(
        agent_run_id=command.agent_run_id,
        step_number=0,
        workflow_state=CheckpointWorkflowState.PENDING,
        completed_tools=[],
        resolved_entities=[],
        verified_context_refs=[],
        safety_disposition=None,
        pending_action=command.initial_action,
        terminal_status=None,
        lease_token=None,
        revision=0,
        created_at=at,
        updated_at=at,
    )
    db.add(checkpoint)
    db.flush()
    return _snapshot(checkpoint), True


def claim_resume(
    db: Session,
    *,
    agent_run_id: str,
    max_age: timedelta,
    now: datetime | None = None,
) -> ResumeLease:
    """Claim a short-lived lease so only one worker can resume a run."""
    if max_age <= timedelta(0):
        raise ValueError("checkpoint max_age must be positive")
    at = now or datetime.now(UTC)
    checkpoint = _require_checkpoint(db, agent_run_id)
    if checkpoint.terminal_status is not None:
        raise CheckpointTerminalError("terminal agent run cannot resume")
    age = at - _as_utc(checkpoint.updated_at)
    if checkpoint.lease_token and age <= max_age:
        raise CheckpointBusyError("agent run is already being resumed")
    if not checkpoint.lease_token and age > max_age:
        _terminalize(db, checkpoint, status="TIMEOUT", now=at)
        raise StaleCheckpointError("checkpoint is stale and was closed safely")

    token = str(uuid.uuid4())
    checkpoint.lease_token = token
    checkpoint.workflow_state = CheckpointWorkflowState.RUNNING
    # A crash after begin_tool must resume with the same deterministic action
    # key. Only a new planning step advances the counter.
    if checkpoint.pending_action == PendingAction.PLAN:
        checkpoint.step_number += 1
    checkpoint.revision += 1
    checkpoint.updated_at = at
    db.flush()
    return ResumeLease(_snapshot(checkpoint), token)


def begin_tool(
    db: Session,
    *,
    agent_run_id: str,
    lease_token: str,
    tool_name: str,
    now: datetime | None = None,
) -> ToolPermit:
    """Return a deterministic key; completed tools are never replayed."""
    if not tool_name or not tool_name.strip():
        raise ValueError("tool_name is required")
    checkpoint = _owned_checkpoint(db, agent_run_id, lease_token)
    _ensure_nonterminal(checkpoint)
    if checkpoint.pending_action == PendingAction.TOOL and checkpoint.workflow_state == CheckpointWorkflowState.TOOL_IN_FLIGHT:
        raise CheckpointBusyError("a tool is already in flight for this checkpoint")
    key = f"agent-run:{agent_run_id}:step:{checkpoint.step_number}:tool:{tool_name}"
    completed = any(
        item.get("name") == tool_name and item.get("idempotency_key") == key
        for item in checkpoint.completed_tools
    )
    if not completed:
        # Persist the exact in-flight action before invoking a side effect. A
        # crash can therefore reclaim this lease and reuse the same key.
        checkpoint.pending_action = PendingAction.TOOL
        checkpoint.workflow_state = CheckpointWorkflowState.TOOL_IN_FLIGHT
        checkpoint.revision += 1
        checkpoint.updated_at = now or datetime.now(UTC)
        db.flush()
    return ToolPermit(agent_run_id, checkpoint.step_number, tool_name, key, lease_token, completed)


def complete_tool(
    db: Session,
    *,
    permit: ToolPermit,
    provenance: str,
    verified_context_refs: tuple[VerifiedReference, ...] = (),
    resolved_entities: tuple[ResolvedEntity, ...] = (),
    now: datetime | None = None,
) -> CheckpointSnapshot:
    """Mark a successful tool once without persisting its input or output."""
    checkpoint = _owned_checkpoint(db, permit.agent_run_id, permit.lease_token)
    _ensure_nonterminal(checkpoint)
    if permit.already_completed:
        raise CheckpointError("completed tool cannot be completed again")
    expected_key = f"agent-run:{permit.agent_run_id}:step:{permit.step_number}:tool:{permit.tool_name}"
    if permit.idempotency_key != expected_key or checkpoint.step_number != permit.step_number:
        raise CheckpointError("tool permit does not match current checkpoint step")
    tool = CompletedTool(permit.tool_name, permit.idempotency_key, provenance)
    checkpoint.completed_tools = [*checkpoint.completed_tools, tool.as_json()]
    checkpoint.verified_context_refs = _merge_references(checkpoint.verified_context_refs, verified_context_refs)
    checkpoint.resolved_entities = _merge_entities(checkpoint.resolved_entities, resolved_entities)
    _release(checkpoint, pending_action=PendingAction.PLAN, now=now)
    db.flush()
    return _snapshot(checkpoint)


def record_safety_disposition(
    db: Session,
    *,
    agent_run_id: str,
    lease_token: str,
    disposition: str,
    verified_context_refs: tuple[VerifiedReference, ...],
    now: datetime | None = None,
) -> CheckpointSnapshot:
    """Persist only a Safety Domain outcome and verified source references."""
    if disposition not in _SAFETY_DISPOSITIONS:
        raise ValueError("invalid safety disposition")
    if not verified_context_refs:
        raise ValueError("safety checkpoint requires verified Safety provenance")
    checkpoint = _owned_checkpoint(db, agent_run_id, lease_token)
    _ensure_nonterminal(checkpoint)
    checkpoint.safety_disposition = disposition
    checkpoint.verified_context_refs = _merge_references(checkpoint.verified_context_refs, verified_context_refs)
    at = now or datetime.now(UTC)
    if disposition == "SAFETY_BLOCKED":
        _terminalize(db, checkpoint, status="SAFETY_BLOCKED", now=at)
    elif disposition == "HANDOFF_REQUIRED":
        checkpoint.workflow_state = CheckpointWorkflowState.WAITING_FOR_HANDOFF
        _release(checkpoint, pending_action=PendingAction.HANDOFF, now=at)
    else:
        _release(checkpoint, pending_action=PendingAction.PLAN, now=at)
    db.flush()
    return _snapshot(checkpoint)


def handoff_idempotency_key(db: Session, *, agent_run_id: str, lease_token: str) -> str:
    """Expose the stable domain idempotency key only after Safety requires it."""
    checkpoint = _owned_checkpoint(db, agent_run_id, lease_token)
    _ensure_nonterminal(checkpoint)
    if checkpoint.safety_disposition != "HANDOFF_REQUIRED" or checkpoint.pending_action != PendingAction.HANDOFF:
        raise CheckpointError("handoff is not authorized by the current safety disposition")
    return f"agent-run:{agent_run_id}:handoff"


def record_handoff_created(
    db: Session,
    *,
    agent_run_id: str,
    lease_token: str,
    handoff_id: str,
    provenance: str,
    now: datetime | None = None,
) -> CheckpointSnapshot:
    """Close the run only after the Safety-authorized handoff exists."""
    if not handoff_id or not provenance:
        raise ValueError("handoff id and provenance are required")
    checkpoint = _owned_checkpoint(db, agent_run_id, lease_token)
    _ensure_nonterminal(checkpoint)
    if checkpoint.safety_disposition != "HANDOFF_REQUIRED":
        raise CheckpointError("handoff requires HANDOFF_REQUIRED safety disposition")
    checkpoint.resolved_entities = _merge_entities(
        checkpoint.resolved_entities,
        (ResolvedEntity("doctor_review_request", handoff_id, provenance),),
    )
    _terminalize(db, checkpoint, status="HANDOFF_CREATED", now=now or datetime.now(UTC))
    db.flush()
    return _snapshot(checkpoint)


def finish_run(
    db: Session,
    *,
    agent_run_id: str,
    lease_token: str,
    status: str,
    now: datetime | None = None,
) -> CheckpointSnapshot:
    """Persist one of the public terminal states without a hidden pending run."""
    if status not in _TERMINAL_STATUSES:
        raise ValueError("invalid terminal agent run status")
    checkpoint = _owned_checkpoint(db, agent_run_id, lease_token)
    _ensure_nonterminal(checkpoint)
    if status == "HANDOFF_CREATED":
        raise CheckpointError("HANDOFF_CREATED must be recorded through the Doctor Handoff gateway")
    _terminalize(db, checkpoint, status=status, now=now or datetime.now(UTC))
    db.flush()
    return _snapshot(checkpoint)


def _require_checkpoint(db: Session, agent_run_id: str) -> AgentRunCheckpoint:
    checkpoint = _locked_checkpoint(db, agent_run_id)
    if checkpoint is None:
        raise CheckpointError("agent checkpoint was not found")
    _validate_sanitized_row(checkpoint)
    return checkpoint


def _locked_checkpoint(db: Session, agent_run_id: str) -> AgentRunCheckpoint | None:
    return db.execute(
        select(AgentRunCheckpoint).where(AgentRunCheckpoint.agent_run_id == agent_run_id).with_for_update()
    ).scalar_one_or_none()


def _owned_checkpoint(db: Session, agent_run_id: str, lease_token: str) -> AgentRunCheckpoint:
    if not lease_token:
        raise CheckpointError("resume lease is required")
    checkpoint = _require_checkpoint(db, agent_run_id)
    if checkpoint.lease_token != lease_token:
        raise CheckpointBusyError("agent run lease is not owned by this worker")
    return checkpoint


def _ensure_nonterminal(checkpoint: AgentRunCheckpoint) -> None:
    if checkpoint.terminal_status is not None:
        raise CheckpointTerminalError("terminal agent run cannot be mutated")


def _release(checkpoint: AgentRunCheckpoint, *, pending_action: PendingAction, now: datetime | None) -> None:
    checkpoint.lease_token = None
    checkpoint.pending_action = pending_action
    checkpoint.workflow_state = CheckpointWorkflowState.PENDING
    checkpoint.revision += 1
    checkpoint.updated_at = now or datetime.now(UTC)


def _terminalize(db: Session, checkpoint: AgentRunCheckpoint, *, status: str, now: datetime) -> None:
    checkpoint.workflow_state = CheckpointWorkflowState.TERMINAL
    checkpoint.pending_action = PendingAction.NONE
    checkpoint.terminal_status = status
    checkpoint.lease_token = None
    checkpoint.revision += 1
    checkpoint.updated_at = now
    run = db.get(AgentRun, checkpoint.agent_run_id)
    if run is not None:
        run.status = status
        run.completed_at = now


def _merge_references(
    existing: list[dict[str, str]], additions: tuple[VerifiedReference, ...]
) -> list[dict[str, str]]:
    values = [*existing]
    seen = {(item["source"], item["id"], item["provenance"]) for item in existing}
    for reference in additions:
        value = reference.as_json()
        key = (value["source"], value["id"], value["provenance"])
        if key not in seen:
            values.append(value)
            seen.add(key)
    return values


def _merge_entities(existing: list[dict[str, str]], additions: tuple[ResolvedEntity, ...]) -> list[dict[str, str]]:
    values = [*existing]
    seen = {(item["kind"], item["id"], item["provenance"]) for item in existing}
    for entity in additions:
        value = entity.as_json()
        key = (value["kind"], value["id"], value["provenance"])
        if key not in seen:
            values.append(value)
            seen.add(key)
    return values


def _snapshot(checkpoint: AgentRunCheckpoint) -> CheckpointSnapshot:
    return CheckpointSnapshot(
        checkpoint_id=checkpoint.id,
        agent_run_id=checkpoint.agent_run_id,
        step_number=checkpoint.step_number,
        workflow_state=CheckpointWorkflowState(checkpoint.workflow_state),
        completed_tools=tuple(CompletedTool(item["name"], item["idempotency_key"], item["provenance"]) for item in checkpoint.completed_tools),
        resolved_entities=tuple(ResolvedEntity(item["kind"], item["id"], item["provenance"]) for item in checkpoint.resolved_entities),
        verified_context_refs=tuple(VerifiedReference(item["source"], item["id"], item["provenance"]) for item in checkpoint.verified_context_refs),
        safety_disposition=checkpoint.safety_disposition,
        pending_action=PendingAction(checkpoint.pending_action),
        terminal_status=checkpoint.terminal_status,
        revision=checkpoint.revision,
        updated_at=_as_utc(checkpoint.updated_at),
    )


def _validate_sanitized_row(checkpoint: AgentRunCheckpoint) -> None:
    _validate_json_items(checkpoint.completed_tools, {"name", "idempotency_key", "provenance"})
    _validate_json_items(checkpoint.resolved_entities, {"kind", "id", "provenance"})
    _validate_json_items(checkpoint.verified_context_refs, {"source", "id", "provenance"})


def _validate_json_items(values: object, allowed_keys: set[str]) -> None:
    if not isinstance(values, list):
        raise CheckpointError("checkpoint persisted state is malformed")
    for value in values:
        if not isinstance(value, dict) or set(value) - allowed_keys or not set(value) == allowed_keys:
            raise CheckpointError("checkpoint persisted state contains prohibited data")
        if any(not isinstance(item, str) or not item for item in value.values()):
            raise CheckpointError("checkpoint persisted state is malformed")


def _same_run(run: AgentRun, command: CheckpointCreateCommand) -> bool:
    return (
        run.patient_id == command.patient_id
        and run.conversation_id == command.conversation_id
        and run.request_id == command.request_id
        and run.intent == command.intent
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "CheckpointBusyError",
    "CheckpointCreateCommand",
    "CheckpointError",
    "CheckpointSnapshot",
    "CheckpointTerminalError",
    "CheckpointWorkflowState",
    "CompletedTool",
    "PendingAction",
    "ResolvedEntity",
    "ResumeLease",
    "StaleCheckpointError",
    "ToolPermit",
    "VerifiedReference",
    "begin_tool",
    "claim_resume",
    "complete_tool",
    "create_or_load_checkpoint",
    "finish_run",
    "handoff_idempotency_key",
    "record_handoff_created",
    "record_safety_disposition",
]
