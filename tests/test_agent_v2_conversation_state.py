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
from backend.agents.v2.orchestrator import (
    OrchestrationIntent,
    SemanticMedicalQuery,
    classify_intent,
    normalize_semantic_medical_query,
)
from backend.agents.v2.runtime import RunStatus
from backend.agents.v2.suggested_actions import build_suggested_actions
from backend.api.agent_v2_routes import _authoritative_topic_for_turn
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


def test_topic_followup_query_is_ephemeral_and_cannot_corrupt_canonical_topic():
    state = transition_state(
        ConversationState.empty("conversation-a"),
        intent="GENERAL_MEDICAL_INFORMATION",
        topic="sỏi thận",
        offered_actions=_topic_actions("sỏi thận"),
    )
    urgent = next(action for action in state.offered_actions if action.value == "urgent_signs")

    resolution = resolve_state_input(state, message=urgent.label, selected_action=urgent)
    semantic = normalize_semantic_medical_query(resolution.query)

    assert resolution.query == "dấu hiệu nguy hiểm của sỏi thận cần đi khám ngay"
    # Semantic normalization remains retrieval-local and is never eligible
    # to become durable topic state, even when it folds Vietnamese text.
    assert semantic.topic == "nguy hiem cua soi than can di kham ngay"
    former_query = "Dấu hiệu nào của sỏi thận cần đi khám ngay?"
    assert normalize_semantic_medical_query(former_query).topic == "nao cua soi than can di kham ngay"
    assert (
        _authoritative_topic_for_turn(
            state,
            selected_action=resolution.selected_action,
            semantic_topic=semantic.topic,
            is_general_medical_turn=True,
            resolved_entity=None,
        )
        is None
    )

    after = transition_state(
        state,
        intent="GENERAL_MEDICAL_INFORMATION",
        selected_action=resolution.selected_action,
        offered_actions=_topic_actions("sỏi thận"),
    )

    assert after.active_topic is not None
    assert after.active_topic.canonical_name == "sỏi thận"
    assert after.active_topic.display_name == "sỏi thận"
    assert after.active_topic.normalized_key == "soi than"
    assert after.requested_aspect == "urgent_signs"
    assert all("nao cua soi than" not in action.label for action in after.offered_actions)


def test_multiple_topic_followups_change_only_requested_aspect_until_explicit_switch():
    state = transition_state(
        ConversationState.empty("conversation-a"),
        intent="GENERAL_MEDICAL_INFORMATION",
        topic="sỏi thận",
        offered_actions=(
            SuggestedAction("monitor", "topic_followup", "Cần theo dõi gì?", "monitoring", topic="sỏi thận"),
        ),
    )
    monitoring = resolve_state_input(state, message="Cần theo dõi gì?", selected_action=None)
    state = transition_state(
        state,
        intent="GENERAL_MEDICAL_INFORMATION",
        selected_action=monitoring.selected_action,
        offered_actions=state.offered_actions,
    )
    causes = resolve_state_input(state, message="còn nguyên nhân?", selected_action=None)
    state = transition_state(
        state,
        intent="GENERAL_MEDICAL_INFORMATION",
        selected_action=causes.selected_action,
        offered_actions=state.offered_actions,
    )

    assert monitoring.used and monitoring.query == "cần theo dõi gì khi bị sỏi thận"
    assert causes.used and causes.query == "nguyên nhân gây sỏi thận"
    assert state.active_topic and state.active_topic.display_name == "sỏi thận"
    assert state.requested_aspect == "causes"

    switched = transition_state(
        state,
        intent="GENERAL_MEDICAL_INFORMATION",
        topic="gan nhiễm mỡ",
        offered_actions=_topic_actions("gan nhiễm mỡ"),
    )
    assert switched.active_topic and switched.active_topic.display_name == "gan nhiễm mỡ"
    assert validate_selected_action(switched, state.offered_actions[0]) is None


def test_legacy_action_can_seed_missing_state_but_client_topic_is_not_authoritative_afterward():
    action = SuggestedAction("urgent", "topic_followup", "Dấu hiệu cần đi khám ngay", "urgent_signs", topic="sỏi thận")
    state = ConversationState(conversation_id="conversation-a", offered_actions=(action,))
    resolution = resolve_state_input(state, message=action.label, selected_action=action)

    assert resolution.query == "dấu hiệu nguy hiểm của sỏi thận cần đi khám ngay"
    assert (
        _authoritative_topic_for_turn(
            state,
            selected_action=action,
            semantic_topic="corrupted retrieval words",
            is_general_medical_turn=True,
            resolved_entity=None,
        )
        == "sỏi thận"
    )


def test_drug_display_and_normalized_key_survive_followups_and_serialization():
    entity = ActiveEntity("drug", "long-huyet", "LONG Huyết PH 2x12")
    state = transition_state(
        ConversationState.empty("conversation-a"), intent="DRUG_INFORMATION", entity=entity, offered_actions=_drug_state().offered_actions
    )
    selected = state.offered_actions[0]
    after = transition_state(
        state, intent="DRUG_INFORMATION", selected_action=selected, offered_actions=state.offered_actions
    )
    restored = ConversationState.from_dict(
        after.as_dict(actor_id="actor-a", patient_id="patient-a"),
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
    )

    assert after.active_entity and after.active_entity.display_name == "LONG Huyết PH 2x12"
    assert after.active_entity.normalized_key == "long huyet ph 2x12"
    assert after.requested_aspect == selected.value
    assert restored and restored.active_entity == after.active_entity


def test_fallback_transition_preserves_canonical_topic():
    state = transition_state(
        ConversationState.empty("conversation-a"),
        intent="GENERAL_MEDICAL_INFORMATION",
        topic="sỏi thận",
        offered_actions=_topic_actions("sỏi thận"),
    )
    urgent = next(action for action in state.offered_actions if action.value == "urgent_signs")

    fallback = transition_state(
        state,
        intent="GENERAL_MEDICAL_INFORMATION",
        selected_action=urgent,
        offered_actions=(),
    )

    assert fallback.active_topic and fallback.active_topic.display_name == "sỏi thận"
    assert fallback.requested_aspect == "urgent_signs"
    assert fallback.offered_actions == ()


def test_explicit_topic_resolution_preserves_vietnamese_display_and_switches_topic():
    initial = normalize_semantic_medical_query("bệnh sỏi thận là gì")
    switched = normalize_semantic_medical_query("gan nhiễm mỡ thì sao?")

    assert initial.topic == "soi than"
    assert initial.display_topic == "sỏi thận"
    assert switched.display_topic == "gan nhiễm mỡ"
    assert classify_intent("gan nhiễm mỡ thì sao?").intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION
    assert (
        _authoritative_topic_for_turn(
            ConversationState.empty("conversation-a"),
            selected_action=None,
            semantic_topic=switched.display_topic,
            is_general_medical_turn=True,
            resolved_entity=None,
        )
        == "gan nhiễm mỡ"
    )


def test_drug_attribute_question_never_becomes_a_display_topic():
    """BUILD-29D.3 regression (found via real local E2E, 2026-08-23):
    "<phrase> la gi" also matches a drug-attribute question with no
    disease/topic shape at all -- "Cong dung cua thuoc Long Huyet P/H la gi"
    used to extract "Cong dung cua thuoc Long Huyet P/H" as a display_topic
    and corrupt active_topic/suggested_actions with it, on a turn where no
    entity had been resolved yet (the common case -- see
    BUILD-29D2-REPORT.md Sec 15). `display_topic` must stay `None` for any
    phrasing built from the fixed drug-attribute vocabulary this backend
    already asks about elsewhere (suggested_actions.py::_DRUG_LABELS,
    conversation_state.py::_typed_aliases), so no state write is ever
    attempted from it -- the caller must fall back to `None`, never to the
    ascii-folded `semantic.topic` retrieval string (see the route's own
    docstring for why that fallback is unsafe too)."""
    for message in (
        "Công dụng của thuốc Long Huyết P/H là gì",
        "Tác dụng phụ của Vitamin C là gì",
        "Liều dùng của thuốc này là gì",
        "Cách dùng thuốc Panadol là gì",
    ):
        semantic = normalize_semantic_medical_query(message)
        assert semantic.display_topic is None, (message, semantic.display_topic)
        assert (
            _authoritative_topic_for_turn(
                ConversationState.empty("conversation-a"),
                selected_action=None,
                semantic_topic=semantic.display_topic,
                is_general_medical_turn=True,
                resolved_entity=None,
            )
            is None
        )

    # A genuine disease/topic question is unaffected by the guard.
    assert normalize_semantic_medical_query("bệnh sỏi thận là gì").display_topic == "sỏi thận"
