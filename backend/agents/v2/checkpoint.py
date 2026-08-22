"""Agent V2 adapters that bind durable checkpoints to typed domain gateways.

These adapters intentionally persist references and idempotency keys only. The
caller owns the surrounding database transaction; no adapter commits by itself.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from sqlalchemy.orm import Session

from backend.agents.v2.handoff import AgentHandoffResult, DoctorHandoffGateway, DoctorHandoffRequest
from backend.agents.v2.model_gateway import ToolCall
from backend.agents.v2.observability import AgentTelemetry, TraceComponent, TraceContext
from backend.agents.v2.runtime import RunResult
from backend.agents.v2.safety import SafetyDecision
from backend.agents.v2.tools import ToolGateway, ToolResult
from backend.services.agent_checkpoint import (
    CheckpointSnapshot,
    ResolvedEntity,
    VerifiedReference,
    begin_tool,
    complete_tool,
    finish_run,
    handoff_idempotency_key,
    record_handoff_created,
    record_safety_disposition,
)


class CompletedToolReplayError(RuntimeError):
    """A completed tool must be rehydrated from verified references, not replayed."""


class CheckpointedToolGateway:
    """Execute a typed tool once and checkpoint only its verified references."""

    def __init__(self, db: Session, tools: ToolGateway, *, telemetry: AgentTelemetry | None = None) -> None:
        self._db = db
        self._tools = tools
        self._telemetry = telemetry

    def execute(
        self,
        *,
        agent_run_id: str,
        lease_token: str,
        call: ToolCall,
        resolved_entities: tuple[ResolvedEntity, ...] = (),
        trace: TraceContext | None = None,
    ) -> ToolResult:
        permit = begin_tool(
            self._db,
            agent_run_id=agent_run_id,
            lease_token=lease_token,
            tool_name=call.name,
        )
        if permit.already_completed:
            raise CompletedToolReplayError("completed tool cannot be replayed during checkpoint resume")
        if self._telemetry is not None and trace is not None:
            with self._telemetry.span(trace, TraceComponent.TOOL, operation="checkpointed_execute", attributes={"tool_name": call.name}):
                result = self._tools.execute(call.name, call.arguments)
            self._telemetry.event(trace, TraceComponent.CHECKPOINT, "agent_checkpoint.tool_completed", tool_name=call.name)
        else:
            result = self._tools.execute(call.name, call.arguments)
        complete_tool(
            self._db,
            permit=permit,
            provenance=result.provenance,
            verified_context_refs=(
                VerifiedReference(
                    source="TOOL_GATEWAY",
                    reference_id=permit.idempotency_key,
                    provenance=result.provenance,
                ),
            ),
            resolved_entities=resolved_entities,
        )
        return result


class CheckpointedSafetyGateway:
    """Persist an already-authoritative Safety result without reinterpretation."""

    def __init__(self, db: Session, *, telemetry: AgentTelemetry | None = None) -> None:
        self._db = db
        self._telemetry = telemetry

    def record(
        self,
        *,
        agent_run_id: str,
        lease_token: str,
        safety: SafetyDecision,
        trace: TraceContext | None = None,
    ) -> CheckpointSnapshot:
        if self._telemetry is not None and trace is not None:
            self._telemetry.event(
                trace,
                TraceComponent.SAFETY,
                "agent_safety.completed",
                safety_disposition=safety.outcome.value,
                provenance=safety.provenance,
            )
        return record_safety_disposition(
            self._db,
            agent_run_id=agent_run_id,
            lease_token=lease_token,
            disposition=safety.outcome.value,
            verified_context_refs=(
                VerifiedReference(
                    source="SAFETY_DOMAIN",
                    reference_id=safety.assessment_id or safety.reason_code,
                    provenance=safety.provenance,
                ),
            ),
        )


class CheckpointedDoctorHandoffGateway:
    """Use one checkpoint-derived key for every retry of a Safety handoff."""

    def __init__(self, db: Session, handoff_gateway: DoctorHandoffGateway, *, telemetry: AgentTelemetry | None = None) -> None:
        self._db = db
        self._handoff_gateway = handoff_gateway
        self._telemetry = telemetry

    def create(
        self,
        *,
        agent_run_id: str,
        lease_token: str,
        request: DoctorHandoffRequest,
        safety: SafetyDecision,
        created_at: datetime | None = None,
        trace: TraceContext | None = None,
    ) -> AgentHandoffResult:
        key = handoff_idempotency_key(
            self._db,
            agent_run_id=agent_run_id,
            lease_token=lease_token,
        )
        result = self._handoff_gateway.create(
            request=replace(request, idempotency_key=key),
            safety=safety,
            created_at=created_at,
        )
        record_handoff_created(
            self._db,
            agent_run_id=agent_run_id,
            lease_token=lease_token,
            handoff_id=result.request_id,
            provenance="doctor-handoff:request",
        )
        if self._telemetry is not None and trace is not None:
            self._telemetry.event(trace, TraceComponent.HANDOFF, "agent_handoff.created", handoff_outcome="CREATED")
        return result


class CheckpointedTerminalStateRecorder:
    """Mirror the existing runtime terminal status into durable checkpoint state."""

    def __init__(self, db: Session, *, telemetry: AgentTelemetry | None = None) -> None:
        self._db = db
        self._telemetry = telemetry

    def record(
        self, *, agent_run_id: str, lease_token: str, result: RunResult, trace: TraceContext | None = None
    ) -> CheckpointSnapshot:
        snapshot = finish_run(
            self._db,
            agent_run_id=agent_run_id,
            lease_token=lease_token,
            status=result.status.value,
        )
        if self._telemetry is not None and trace is not None:
            self._telemetry.event(trace, TraceComponent.CHECKPOINT, "agent_checkpoint.terminal", terminal_status=result.status.value)
        return snapshot


__all__ = [
    "CheckpointedDoctorHandoffGateway",
    "CheckpointedSafetyGateway",
    "CheckpointedTerminalStateRecorder",
    "CheckpointedToolGateway",
    "CompletedToolReplayError",
]
