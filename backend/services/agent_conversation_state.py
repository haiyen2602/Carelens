"""Persistence adapter for Agent V2's canonical conversation state.

State is kept in the existing durable ``AgentRun.metadata_json`` checkpoint
record.  This avoids a competing memory store while retaining the strict
actor/patient/conversation isolation boundary after restarts or deploys.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents.v2.conversation_state import ConversationState
from backend.db.models import AgentRun

_STATE_KEY = "conversation_state"


class AgentConversationStateStore:
    def load(self, db: Session, *, actor_id: str, patient_id: str, conversation_id: str) -> ConversationState:
        rows = db.execute(
            select(AgentRun)
            .where(AgentRun.patient_id == patient_id, AgentRun.conversation_id == conversation_id)
            .order_by(AgentRun.started_at.desc())
        ).scalars()
        for row in rows:
            state = ConversationState.from_dict(
                row.metadata_json.get(_STATE_KEY) if isinstance(row.metadata_json, dict) else None,
                actor_id=actor_id,
                patient_id=patient_id,
                conversation_id=conversation_id,
            )
            if state is not None:
                return state
        return ConversationState.empty(conversation_id)

    def save(
        self,
        db: Session,
        *,
        agent_run_id: str,
        actor_id: str,
        patient_id: str,
        state: ConversationState,
    ) -> None:
        run = db.get(AgentRun, agent_run_id)
        if run is None or run.patient_id != patient_id or run.conversation_id != state.conversation_id:
            raise ValueError("conversation state cannot be saved outside the authorized Agent run")
        metadata = dict(run.metadata_json or {})
        metadata[_STATE_KEY] = state.as_dict(actor_id=actor_id, patient_id=patient_id)
        run.metadata_json = metadata
        db.flush()


__all__ = ["AgentConversationStateStore"]
