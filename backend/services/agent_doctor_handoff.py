"""Server-authorized adapter from Agent V2 into the Doctor Handoff domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents.v2.handoff import AgentHandoffResult, HandoffContextRef
from backend.agents.v2.handoff import HandoffCreateCommand as AgentHandoffCreateCommand
from backend.api.security import CurrentUser
from backend.db.models import DoctorReviewRequest, Patient
from backend.services.agent_authorization import require_agent_patient_access
from backend.services.doctor_handoff import (
    HandoffCreateCommand,
    VerifiedContextRef,
    VerifiedContextSource,
    create_doctor_review_request,
)

# BUILD-42 SS12: an active (not yet resolved) review request for the same
# patient. Deliberately scoped to Answerability-Gate-created handoffs only
# (see the ``risk_disposition == "UNCERTAINTY_HANDOFF"`` check in ``create``
# below) -- the pre-existing Safety-Domain-sourced path has no such
# cross-run dedup today (per-agent-run idempotency only, see
# ``doctor_handoff.py``) and this build does not change that.
_ACTIVE_HANDOFF_STATUSES = ("PENDING", "ASSIGNED")


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
        # BUILD-42 SS12: reuse an already-active Answerability-Gate handoff
        # for this patient instead of creating a new row every turn. Scoped
        # to risk_disposition == UNCERTAINTY_HANDOFF only -- a Safety-sourced
        # command never has this value (always "HANDOFF_REQUIRED"), so this
        # branch never fires for -- and never changes -- the Safety path.
        if command.risk_disposition == "UNCERTAINTY_HANDOFF":
            # PR #127 review: this reuse check is a plain check-then-act --
            # without a lock, two DIFFERENT concurrent agent runs for the
            # SAME patient (e.g. a rapid double-send, each its own agent_run_
            # id and therefore its own idempotency_key) could both see no
            # existing active row before either commits its insert, creating
            # two handoff rows for the same episode. The idempotency_key
            # unique constraint (doctor_handoff.py) only protects a retry of
            # the SAME agent run, not this cross-run case. Locking the
            # Patient row here (it always exists -- already fetched, un-
            # locked, by require_agent_patient_access above) serializes
            # concurrent creation attempts for the same patient without a
            # new migration or touching the shared, heavily-reused
            # require_agent_patient_access helper itself. No-op contention
            # for any other patient; released at this transaction's commit.
            self._db.execute(select(Patient.id).where(Patient.id == command.patient_id).with_for_update())
            existing = self._db.execute(
                select(DoctorReviewRequest)
                .where(
                    DoctorReviewRequest.patient_id == command.patient_id,
                    DoctorReviewRequest.status.in_(_ACTIVE_HANDOFF_STATUSES),
                )
                .order_by(DoctorReviewRequest.created_at.desc())
            ).scalars().first()
            if existing is not None:
                return AgentHandoffResult(existing.id, existing.status, existing.assigned_doctor_id, created=False)
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
