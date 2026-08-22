"""Canonical, durable-friendly conversation state for Agent V2.

This module deliberately contains no ORM access.  The state is a small,
validated contract that can be stored in the existing AgentRun checkpoint
metadata and resolved before ordinary routing.  It is never an authority for
patient access, safety, dose data, or drug facts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

ActionType = Literal["drug_attribute", "topic_attribute"]


@dataclass(frozen=True)
class ActiveTopic:
    type: str
    canonical_name: str


@dataclass(frozen=True)
class ActiveEntity:
    type: str
    id: str
    canonical_name: str


@dataclass(frozen=True)
class SuggestedAction:
    action_id: str
    type: ActionType
    label: str
    value: str
    entity_id: str | None = None
    topic: str | None = None

    def as_dict(self) -> dict[str, str]:
        value = {
            "action_id": self.action_id,
            "type": self.type,
            "label": self.label,
            "value": self.value,
        }
        if self.entity_id:
            value["entity_id"] = self.entity_id
        if self.topic:
            value["topic"] = self.topic
        return value


@dataclass(frozen=True)
class ConversationState:
    conversation_id: str
    active_topic: ActiveTopic | None = None
    active_entity: ActiveEntity | None = None
    last_intent: str | None = None
    requested_attribute: str | None = None
    offered_actions: tuple[SuggestedAction, ...] = ()
    pending_selection: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def empty(cls, conversation_id: str) -> ConversationState:
        return cls(conversation_id=conversation_id)

    def as_dict(self, *, actor_id: str, patient_id: str) -> dict[str, object]:
        return {
            "version": 1,
            "actor_id": actor_id,
            "patient_id": patient_id,
            "conversation_id": self.conversation_id,
            "active_topic": None
            if self.active_topic is None
            else {"type": self.active_topic.type, "canonical_name": self.active_topic.canonical_name},
            "active_entity": None
            if self.active_entity is None
            else {
                "type": self.active_entity.type,
                "id": self.active_entity.id,
                "canonical_name": self.active_entity.canonical_name,
            },
            "last_intent": self.last_intent,
            "requested_attribute": self.requested_attribute,
            "offered_actions": [action.as_dict() for action in self.offered_actions],
            "pending_selection": self.pending_selection,
            "updated_at": (self.updated_at or datetime.now(UTC)).isoformat(),
        }

    @classmethod
    def from_dict(cls, value: object, *, actor_id: str, patient_id: str, conversation_id: str) -> ConversationState | None:
        if not isinstance(value, dict):
            return None
        if value.get("actor_id") != actor_id or value.get("patient_id") != patient_id or value.get("conversation_id") != conversation_id:
            return None
        try:
            topic = value.get("active_topic")
            entity = value.get("active_entity")
            actions = tuple(
                SuggestedAction(
                    action_id=str(item["action_id"]), type=item["type"], label=str(item["label"]), value=str(item["value"]),
                    entity_id=item.get("entity_id"), topic=item.get("topic"),
                )
                for item in value.get("offered_actions", [])
                if isinstance(item, dict) and item.get("type") in {"drug_attribute", "topic_attribute"}
            )
            return cls(
                conversation_id=conversation_id,
                active_topic=ActiveTopic(str(topic["type"]), str(topic["canonical_name"])) if isinstance(topic, dict) else None,
                active_entity=ActiveEntity(str(entity["type"]), str(entity["id"]), str(entity["canonical_name"])) if isinstance(entity, dict) else None,
                last_intent=str(value["last_intent"]) if value.get("last_intent") else None,
                requested_attribute=str(value["requested_attribute"]) if value.get("requested_attribute") else None,
                offered_actions=actions,
                pending_selection=str(value["pending_selection"]) if value.get("pending_selection") else None,
                updated_at=datetime.fromisoformat(value["updated_at"]) if value.get("updated_at") else None,
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class StateInputResolution:
    query: str
    selected_action: SuggestedAction | None = None
    used: bool = False


_TOPIC_ATTRIBUTES = (
    ("causes", "Nguyên nhân"),
    ("symptoms", "Triệu chứng"),
    ("danger", "Có nguy hiểm không?"),
    ("prevention", "Phòng ngừa"),
    ("urgent_care", "Khi nào cần đi khám?"),
)
_DRUG_ATTRIBUTES = (
    ("uses", "Công dụng"),
    ("dosage", "Cách dùng - liều dùng"),
    ("side_effects", "Tác dụng phụ"),
    ("contraindications", "Chống chỉ định"),
)


def resolve_state_input(
    state: ConversationState,
    *,
    message: str,
    selected_action: SuggestedAction | None,
) -> StateInputResolution:
    """Resolve a validated UI action, numeric choice, or concise typed label."""
    action = selected_action or _typed_action(state, message)
    if action is None:
        return StateInputResolution(query=message)
    if action.type == "topic_attribute" and action.topic:
        return StateInputResolution(query=_topic_query(action.topic, action.value), selected_action=action, used=True)
    if action.type == "drug_attribute" and state.active_entity and action.entity_id == state.active_entity.id:
        return StateInputResolution(
            query=f"{action.label} của thuốc {state.active_entity.canonical_name}", selected_action=action, used=True
        )
    return StateInputResolution(query=message)


def validate_selected_action(state: ConversationState, candidate: SuggestedAction | None) -> SuggestedAction | None:
    """Return only the exact latest server-issued action; client values are hints."""
    if candidate is None:
        return None
    for action in state.offered_actions:
        if action == candidate:
            return action
    return None


def transition_state(
    state: ConversationState,
    *,
    intent: str,
    topic: str | None = None,
    entity: ActiveEntity | None = None,
    selected_action: SuggestedAction | None = None,
    safety_event: bool = False,
) -> ConversationState:
    """Apply one explicit state transition after an authoritative run result."""
    if safety_event:
        return replace(state, last_intent=intent, offered_actions=(), pending_selection=None, updated_at=datetime.now(UTC))

    next_topic = ActiveTopic("medical_topic", topic) if topic else state.active_topic
    next_entity = entity or state.active_entity
    if topic:
        # A distinct explicit topic is a conversational boundary; old actions
        # cannot be selected against it.
        next_entity = None
    if entity:
        next_topic = None

    actions: tuple[SuggestedAction, ...] = ()
    if next_entity is not None:
        actions = tuple(
            SuggestedAction(str(uuid4()), "drug_attribute", label, value, entity_id=next_entity.id)
            for value, label in _DRUG_ATTRIBUTES
        )
    elif next_topic is not None:
        actions = tuple(
            SuggestedAction(str(uuid4()), "topic_attribute", label, value, topic=next_topic.canonical_name)
            for value, label in _TOPIC_ATTRIBUTES
        )

    return ConversationState(
        conversation_id=state.conversation_id,
        active_topic=next_topic,
        active_entity=next_entity,
        last_intent=intent,
        requested_attribute=selected_action.value if selected_action else None,
        offered_actions=actions,
        pending_selection=None,
        updated_at=datetime.now(UTC),
    )


def _typed_action(state: ConversationState, message: str) -> SuggestedAction | None:
    normalized = " ".join(message.casefold().strip(" ?!.,;:").split())
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(state.offered_actions):
            return state.offered_actions[index]
    for action in state.offered_actions:
        if normalized in {action.label.casefold(), action.value.casefold()}:
            return action
        if normalized.startswith("còn ") and normalized[4:] == action.label.casefold():
            return action
    return None


def _topic_query(topic: str, value: str) -> str:
    templates = {
        "causes": f"Nguyên nhân của {topic} là gì?",
        "symptoms": f"Triệu chứng của {topic} là gì?",
        "danger": f"{topic} có nguy hiểm không?",
        "prevention": f"Cách phòng ngừa {topic} là gì?",
        "urgent_care": f"Khi nào {topic} cần đi khám ngay?",
    }
    return templates.get(value, topic)
