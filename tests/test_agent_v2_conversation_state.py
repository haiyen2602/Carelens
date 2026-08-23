from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.conversation_state import (
    ActiveEntity,
    ConversationState,
    SuggestedAction,
    is_allowed_action,
    resolve_state_input,
    transition_state,
    validate_selected_action,
)
from backend.agents.v2.orchestrator import OrchestrationIntent, SemanticMedicalQuery
from backend.agents.v2.runtime import RunStatus
from backend.agents.v2.suggested_actions import build_suggested_actions
from backend.db.models import AgentRun
from backend.services.agent_conversation_state import AgentConversationStateStore


class _DrugInfoResult:
    name = "get_drug_info"
    data = {"results": [{"field": "cong_dung", "content": "Thông tin có nguồn"}]}


def _topic_actions(topic: str = "gan nhiễm mỡ") -> tuple[SuggestedAction, ...]:
    return build_suggested_actions(
        reply="Gan nhiễm mỡ là tình trạng mỡ tích tụ trong gan.",
        status=RunStatus.COMPLETED,
        intent=OrchestrationIntent.GENERAL_MEDICAL_INFORMATION,
        semantic_query=SemanticMedicalQuery("gan nhiễm mỡ là gì", "gan nhiễm mỡ là gì", "definition", topic),
        topic=topic,
        entity=None,
        selected_action=None,
        tool_results=(),
        safety_event=False,
    ).actions


def _drug_state() -> ConversationState:
    entity = ActiveEntity("drug", "long-huyet", "Long Huyết PH 2x12")
    actions = build_suggested_actions(
        reply="Đây là thông tin thuốc đã tìm được.",
        status=RunStatus.COMPLETED,
        intent=OrchestrationIntent.DRUG_INFORMATION,
        semantic_query=SemanticMedicalQuery("thông tin thuốc Long Huyết", "thông tin thuốc Long Huyết"),
        topic=None,
        entity=entity,
        selected_action=None,
        tool_results=(_DrugInfoResult(),),
        safety_event=False,
    ).actions
    return transition_state(
        ConversationState.empty("conversation-a"), intent="DRUG_INFORMATION", entity=entity, offered_actions=actions
    )


def test_disease_actions_are_dynamic_allowlisted_and_match_the_reply_offer():
    built = build_suggested_actions(
        reply="Gan nhiễm mỡ là tình trạng mỡ tích tụ trong gan.",
        status=RunStatus.COMPLETED,
        intent=OrchestrationIntent.GENERAL_MEDICAL_INFORMATION,
        semantic_query=SemanticMedicalQuery("gan nhiễm mỡ là gì", "gan nhiễm mỡ là gì", "definition", "gan nhiễm mỡ"),
        topic="gan nhiễm mỡ",
        entity=None,
        selected_action=None,
        tool_results=(),
        safety_event=False,
    )

    assert [action.value for action in built.actions] == ["causes", "treatment", "urgent_signs"]
    assert all(action.type == "topic_followup" and action.topic == "gan nhiễm mỡ" for action in built.actions)
    assert all(is_allowed_action(action) and action.label in built.reply for action in built.actions)


def test_drug_actions_require_real_drug_evidence_and_bind_canonical_entity():
    entity = ActiveEntity("drug", "long-huyet", "Long Huyết PH 2x12")
    no_evidence = build_suggested_actions(
        reply="Tôi đã nhận được câu hỏi.",
        status=RunStatus.COMPLETED,
        intent=OrchestrationIntent.DRUG_INFORMATION,
        semantic_query=SemanticMedicalQuery("Long Huyết", "Long Huyết"),
        topic=None,
        entity=entity,
        selected_action=None,
        tool_results=(),
        safety_event=False,
    )
    built = build_suggested_actions(
        reply="Đây là thông tin thuốc đã tìm được.",
        status=RunStatus.COMPLETED,
        intent=OrchestrationIntent.DRUG_INFORMATION,
        semantic_query=SemanticMedicalQuery("Long Huyết", "Long Huyết"),
        topic=None,
        entity=entity,
        selected_action=None,
        tool_results=(_DrugInfoResult(),),
        safety_event=False,
    )

    assert no_evidence.actions == ()
    assert [action.value for action in built.actions] == ["side_effects", "warnings", "administration"]
    assert all(action.type == "drug_followup" and action.entity_id == "long-huyet" for action in built.actions)
    assert all(action.label in built.reply for action in built.actions)


def test_typed_number_and_attribute_bind_to_latest_resolved_drug():
    state = _drug_state()

    first = resolve_state_input(state, message="1", selected_action=None)
    named = resolve_state_input(state, message="tác dụng phụ", selected_action=None)
    follow_up = resolve_state_input(state, message="còn cách dùng", selected_action=None)

    assert first.used and first.selected_action == state.offered_actions[0]
    assert named.used and named.selected_action == state.offered_actions[0]
    assert follow_up.used and follow_up.selected_action == state.offered_actions[2]
    assert "Long Huyết PH 2x12" in first.query


def test_stale_or_forged_action_never_binds_a_client_supplied_drug_id():
    state = _drug_state()
    offered = state.offered_actions[0]
    forged = SuggestedAction(offered.action_id, offered.type, offered.label, offered.value, entity_id="another-drug")

    assert validate_selected_action(state, forged) is None
    assert not resolve_state_input(
        state, message="một yêu cầu mới", selected_action=validate_selected_action(state, forged)
    ).used


def test_topic_change_replaces_actions_and_cannot_apply_old_topic_selection():
    first = transition_state(
        ConversationState.empty("conversation-a"),
        intent="GENERAL_MEDICAL_INFORMATION",
        topic="gan nhiễm mỡ",
        offered_actions=_topic_actions(),
    )
    old_action = first.offered_actions[0]
    switched = transition_state(
        first, intent="GENERAL_MEDICAL_INFORMATION", topic="sỏi thận", offered_actions=_topic_actions("sỏi thận")
    )

    assert switched.active_topic and switched.active_topic.canonical_name == "sỏi thận"
    assert validate_selected_action(switched, old_action) is None
    assert all(action.topic == "sỏi thận" for action in switched.offered_actions)


def test_safety_or_no_suggestion_response_clears_actions():
    state = transition_state(
        ConversationState.empty("conversation-a"),
        intent="GENERAL_MEDICAL_INFORMATION",
        topic="gan nhiễm mỡ",
        offered_actions=_topic_actions(),
    )
    safe = build_suggested_actions(
        reply="Bạn cần được hỗ trợ khẩn cấp.",
        status=RunStatus.COMPLETED,
        intent=OrchestrationIntent.ACUTE_DANGER_ESCALATION,
        semantic_query=SemanticMedicalQuery("tôi vừa nôn ra máu", "tôi vừa nôn ra máu"),
        topic="gan nhiễm mỡ",
        entity=None,
        selected_action=None,
        tool_results=(),
        safety_event=True,
    )
    cleared = transition_state(state, intent="ACUTE_DANGER_ESCALATION", safety_event=True)

    assert safe.actions == ()
    assert cleared.offered_actions == ()


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
        assert (
            restarted_store.load(
                session, actor_id="actor-a", patient_id="patient-a", conversation_id="conversation-a"
            ).active_entity
            == state.active_entity
        )
        assert (
            restarted_store.load(
                session, actor_id="actor-b", patient_id="patient-a", conversation_id="conversation-a"
            ).active_entity
            is None
        )
        assert (
            restarted_store.load(
                session, actor_id="actor-a", patient_id="patient-b", conversation_id="conversation-a"
            ).active_entity
            is None
        )
        assert (
            restarted_store.load(
                session, actor_id="actor-a", patient_id="patient-a", conversation_id="conversation-b"
            ).active_entity
            is None
        )
    finally:
        session.close()
        engine.dispose()
