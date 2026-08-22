"""Typed Agent V2 bridge for Doctor Handoff; no model-selected recipient."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from backend.agents.v2.safety import SafetyDecision, SafetyOutcome


class HandoffContextSource(StrEnum):
    SAFETY_DOMAIN = "SAFETY_DOMAIN"
    OPERATIONAL_DB = "OPERATIONAL_DB"
    DOCTOR = "DOCTOR"
    DRUG_KNOWLEDGE_V2 = "DRUG_KNOWLEDGE_V2"


@dataclass(frozen=True)
class HandoffContextRef:
    source: HandoffContextSource
    reference_id: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.reference_id or not self.provenance:
            raise ValueError("handoff context reference requires id and provenance")


@dataclass(frozen=True)
class HandoffCreateCommand:
    patient_id: str
    actor_id: str
    patient_question: str
    reason_code: str
    risk_disposition: str
    idempotency_key: str
    verified_context_refs: tuple[HandoffContextRef, ...]
    conversation_id: str | None = None
    source_message_id: str | None = None


@dataclass(frozen=True)
class AgentHandoffResult:
    request_id: str
    status: str
    assigned_doctor_id: str | None
    created: bool


class DoctorHandoffDomain(Protocol):
    def create(self, command: HandoffCreateCommand, *, created_at: datetime) -> AgentHandoffResult: ...


@dataclass(frozen=True)
class DoctorHandoffRequest:
    patient_id: str
    actor_id: str
    patient_question: str
    idempotency_key: str
    verified_context_refs: tuple[HandoffContextRef, ...] = ()
    conversation_id: str | None = None
    source_message_id: str | None = None


class DoctorHandoffGateway:
    """Create a handoff only from the Safety Domain's terminal disposition."""

    def __init__(self, domain: DoctorHandoffDomain) -> None:
        self._domain = domain

    def create(
        self,
        *,
        request: DoctorHandoffRequest,
        safety: SafetyDecision,
        created_at: datetime | None = None,
    ) -> AgentHandoffResult:
        if safety.outcome is not SafetyOutcome.HANDOFF_REQUIRED:
            raise ValueError("DOCTOR_HANDOFF_REQUIRES_SAFETY_HANDOFF")
        if not safety.reason_code or not safety.provenance:
            raise ValueError("DOCTOR_HANDOFF_REQUIRES_SAFETY_PROVENANCE")
        safety_ref = HandoffContextRef(
            HandoffContextSource.SAFETY_DOMAIN,
            safety.assessment_id or safety.reason_code,
            safety.provenance,
        )
        refs = request.verified_context_refs
        if safety_ref not in refs:
            refs = (*refs, safety_ref)
        command = HandoffCreateCommand(
            patient_id=request.patient_id,
            actor_id=request.actor_id,
            patient_question=request.patient_question,
            reason_code=safety.reason_code,
            risk_disposition=safety.outcome,
            idempotency_key=request.idempotency_key,
            verified_context_refs=refs,
            conversation_id=request.conversation_id,
            source_message_id=request.source_message_id,
        )
        return self._domain.create(command, created_at=created_at or datetime.now(UTC))


__all__ = [
    "AgentHandoffResult",
    "DoctorHandoffGateway",
    "DoctorHandoffRequest",
    "HandoffContextRef",
    "HandoffContextSource",
]
