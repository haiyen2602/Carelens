"""Server-authorized adapter from Agent V2 into the Doctor Handoff domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.agents.v2.handoff import AgentHandoffResult, HandoffContextRef
from backend.agents.v2.handoff import HandoffCreateCommand as AgentHandoffCreateCommand
from backend.api.security import CurrentUser
from backend.services.agent_authorization import require_agent_patient_access
from backend.services.doctor_handoff import (
    HandoffCreateCommand,
    VerifiedContextRef,
    VerifiedContextSource,
    create_doctor_review_request,
)


class AuthorizedDoctorHandoffAdapter:
    """Binds the JWT actor before durable creation; no client chooses a doctor."""

    def __init__(self, db: Session, actor: CurrentUser) -> None:
        self._db = db
        self._actor = actor

    def create(self, command: AgentHandoffCreateCommand, *, created_at: datetime) -> AgentHandoffResult:
        patient_id = require_agent_patient_access(self._db, self._actor, command.patient_id)
        if command.actor_id != self._actor.id:
            raise PermissionError("DOCTOR_HANDOFF_ACTOR_MISMATCH")
        if patient_id != command.patient_id:
            raise PermissionError("DOCTOR_HANDOFF_PATIENT_MISMATCH")
        result = create_doctor_review_request(
            self._db,
            command=HandoffCreateCommand(
                patient_id=command.patient_id,
                actor_id=command.actor_id,
                patient_question=command.patient_question,
                reason_code=command.reason_code,
                risk_disposition=command.risk_disposition,
                idempotency_key=command.idempotency_key,
                verified_context_refs=tuple(_context_ref(ref) for ref in command.verified_context_refs),
                conversation_id=command.conversation_id,
                source_message_id=command.source_message_id,
            ),
            created_at=created_at,
        )
        request = result.request
        return AgentHandoffResult(request.id, request.status, request.assigned_doctor_id, result.created)


def _context_ref(value: HandoffContextRef) -> VerifiedContextRef:
    return VerifiedContextRef(
        source=VerifiedContextSource(value.source),
        reference_id=value.reference_id,
        provenance=value.provenance,
    )


__all__ = ["AuthorizedDoctorHandoffAdapter"]
