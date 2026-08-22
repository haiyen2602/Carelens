from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.conversation_state import (
    ActiveEntity,
    ConversationState,
    SuggestedAction,
    resolve_state_input,
    transition_state,
    validate_selected_action,
)
from backend.db.models import AgentRun
from backend.services.agent_conversation_state import AgentConversationStateStore


def _drug_state() -> ConversationState:
    return transition_state(
        ConversationState.empty("conversation-a"),
        intent="DRUG_INFORMATION",
        entity=ActiveEntity("drug", "long-huyet", "Long Huyết"),
    )


def test_typed_number_and_attribute_bind_to_latest_resolved_drug():
    state = _drug_state()

    first = resolve_state_input(state, message="1", selected_action=None)
    named = resolve_state_input(state, message="công dụng", selected_action=None)
    follow_up = resolve_state_input(state, message="còn tác dụng phụ?", selected_action=None)

    assert first.used and first.selected_action == state.offered_actions[0]
    assert named.used and named.selected_action == state.offered_actions[0]
    assert follow_up.used and follow_up.selected_action == state.offered_actions[2]
    assert "Long Huyết" in first.query


def test_stale_or_forged_action_never_binds_a_client_supplied_drug_id():
    state = _drug_state()
    offered = state.offered_actions[0]
    forged = SuggestedAction(
        action_id=offered.action_id,
        type=offered.type,
        label=offered.label,
        value=offered.value,
        entity_id="another-drug",
    )

    assert validate_selected_action(state, forged) is None
    assert not resolve_state_input(state, message="một yêu cầu mới", selected_action=validate_selected_action(state, forged)).used


def test_topic_change_replaces_actions_and_cannot_apply_old_topic_selection():
    state = transition_state(ConversationState.empty("conversation-a"), intent="GENERAL_MEDICAL_INFORMATION", topic="gan nhiem mo")
    old_action = state.offered_actions[0]
    switched = transition_state(state, intent="GENERAL_MEDICAL_INFORMATION", topic="soi than")

    assert switched.active_topic and switched.active_topic.canonical_name == "soi than"
    assert validate_selected_action(switched, old_action) is None
    assert all(action.topic == "soi than" for action in switched.offered_actions)


def test_state_is_isolated_by_actor_patient_and_conversation_and_survives_a_new_store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AgentRun.__table__.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        state = _drug_state()
        session.add(
            AgentRun(
                id="run-a",
                patient_id="patient-a",
                conversation_id="conversation-a",
                request_id="request-a",
                intent="DRUG_INFORMATION",
                status="COMPLETED",
                started_at=datetime.now(UTC),
                metadata_json={},
            )
        )
        store = AgentConversationStateStore()
        store.save(session, agent_run_id="run-a", actor_id="actor-a", patient_id="patient-a", state=state)
        session.commit()

        restarted_store = AgentConversationStateStore()
        assert restarted_store.load(session, actor_id="actor-a", patient_id="patient-a", conversation_id="conversation-a").active_entity == state.active_entity
        assert restarted_store.load(session, actor_id="actor-b", patient_id="patient-a", conversation_id="conversation-a").active_entity is None
        assert restarted_store.load(session, actor_id="actor-a", patient_id="patient-b", conversation_id="conversation-a").active_entity is None
        assert restarted_store.load(session, actor_id="actor-a", patient_id="patient-a", conversation_id="conversation-b").active_entity is None
    finally:
        session.close()
        engine.dispose()
