"""Validated, durable conversation state for Agent V2.

State is intentionally a record of server-issued context, not the place that
decides which suggestions to show. BUILD-29D.2 keeps action generation in
``suggested_actions.py`` because it needs the actual answer and evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

ActionType = Literal["topic_followup", "drug_followup", "schedule_followup"]

TOPIC_ACTION_VALUES = frozenset(
    {"definition", "causes", "symptoms", "treatment", "prevention", "danger", "urgent_signs", "diagnosis", "monitoring"}
)
DRUG_ACTION_VALUES = frozenset(
    {"drug_uses", "dosage", "administration", "side_effects", "contraindications", "warnings", "interactions"}
)
SCHEDULE_ACTION_VALUES = frozenset({"today_schedule", "next_dose", "upcoming_schedule", "adherence_history"})


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
        value = {"action_id": self.action_id, "type": self.type, "label": self.label, "value": self.value}
        if self.entity_id:
            value["entity_id"] = self.entity_id
        if self.topic:
            value["topic"] = self.topic
        return value


def is_allowed_action(action: SuggestedAction) -> bool:
    """Validate the user-safe action vocabulary independently of client input."""
    if action.type == "topic_followup":
        return action.value in TOPIC_ACTION_VALUES and bool(action.topic) and action.entity_id is None
    if action.type == "drug_followup":
        return action.value in DRUG_ACTION_VALUES and bool(action.entity_id) and action.topic is None
    if action.type == "schedule_followup":
        return action.value in SCHEDULE_ACTION_VALUES and action.entity_id is None and action.topic is None
    return False


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
            "version": 2,
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
    def from_dict(
        cls, value: object, *, actor_id: str, patient_id: str, conversation_id: str
    ) -> ConversationState | None:
        if not isinstance(value, dict):
            return None
        if (
            value.get("actor_id") != actor_id
            or value.get("patient_id") != patient_id
            or value.get("conversation_id") != conversation_id
        ):
            return None
        try:
            topic = value.get("active_topic")
            entity = value.get("active_entity")
            actions = tuple(
                action
                for item in value.get("offered_actions", [])
                if isinstance(item, dict)
                for action in (
                    SuggestedAction(
                        str(item["action_id"]),
                        item["type"],
                        str(item["label"]),
                        str(item["value"]),
                        item.get("entity_id"),
                        item.get("topic"),
                    ),
                )
                if is_allowed_action(action)
            )
            return cls(
                conversation_id=conversation_id,
                active_topic=ActiveTopic(str(topic["type"]), str(topic["canonical_name"]))
                if isinstance(topic, dict)
                else None,
                active_entity=ActiveEntity(str(entity["type"]), str(entity["id"]), str(entity["canonical_name"]))
                if isinstance(entity, dict)
                else None,
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


def resolve_state_input(
    state: ConversationState, *, message: str, selected_action: SuggestedAction | None
) -> StateInputResolution:
    """Resolve only a validated current action, numeric choice, or typed alias."""
    action = selected_action or _typed_action(state, message)
    if action is None:
        return StateInputResolution(query=message)
    if action.type == "topic_followup" and action.topic:
        return StateInputResolution(query=_topic_query(action.topic, action.value), selected_action=action, used=True)
    if action.type == "drug_followup" and state.active_entity and action.entity_id == state.active_entity.id:
        return StateInputResolution(
            query=f"{action.label} của thuốc {state.active_entity.canonical_name}", selected_action=action, used=True
        )
    return StateInputResolution(query=message)


def validate_selected_action(state: ConversationState, candidate: SuggestedAction | None) -> SuggestedAction | None:
    """Return only an exact, latest, allowlisted action issued by this server."""
    if candidate is None or not is_allowed_action(candidate):
        return None
    return next((action for action in state.offered_actions if action == candidate), None)


def transition_state(
    state: ConversationState,
    *,
    intent: str,
    topic: str | None = None,
    entity: ActiveEntity | None = None,
    selected_action: SuggestedAction | None = None,
    offered_actions: tuple[SuggestedAction, ...] = (),
    safety_event: bool = False,
) -> ConversationState:
    """Persist a server-authoritative state transition without fallback templates."""
    if safety_event:
        return replace(
            state, last_intent=intent, offered_actions=(), pending_selection=None, updated_at=datetime.now(UTC)
        )

    next_topic = ActiveTopic("medical_topic", topic) if topic else state.active_topic
    next_entity = entity or state.active_entity
    if topic:
        next_entity = None
    if entity:
        next_topic = None

    return ConversationState(
        conversation_id=state.conversation_id,
        active_topic=next_topic,
        active_entity=next_entity,
        last_intent=intent,
        requested_attribute=selected_action.value if selected_action else None,
        offered_actions=tuple(action for action in offered_actions if is_allowed_action(action))[:4],
        pending_selection=None,
        updated_at=datetime.now(UTC),
    )


def _typed_action(state: ConversationState, message: str) -> SuggestedAction | None:
    normalized = _normalize(message)
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(state.offered_actions):
            return state.offered_actions[index]
    for action in state.offered_actions:
        if normalized in {_normalize(action.label), _normalize(action.value)}:
            return action
        follow_up = normalized[4:] if normalized.startswith("con ") else normalized
        if follow_up == _normalize(action.label) or follow_up in _typed_aliases(action):
            return action
    return None


def _typed_aliases(action: SuggestedAction) -> frozenset[str]:
    aliases = {
        "definition": {"la gi", "dinh nghia"},
        "causes": {"nguyen nhan", "do dau", "tai sao"},
        "symptoms": {"trieu chung", "dau hieu"},
        "treatment": {"co chua duoc khong", "dieu tri"},
        "prevention": {"phong ngua", "phong tranh"},
        "danger": {"co nguy hiem khong", "nguy hiem"},
        "urgent_signs": {"dau hieu can di kham ngay", "khi nao can di kham"},
        "diagnosis": {"chan doan"},
        "monitoring": {"theo doi"},
        "drug_uses": {"cong dung", "chi dinh"},
        "dosage": {"lieu dung"},
        "administration": {"cach dung"},
        "side_effects": {"tac dung phu"},
        "contraindications": {"chong chi dinh"},
        "warnings": {"luu y", "canh bao"},
        "interactions": {"tuong tac"},
    }
    return frozenset(aliases.get(action.value, set()))


def _normalize(value: str) -> str:
    import unicodedata

    folded = "".join(
        char for char in unicodedata.normalize("NFD", value.casefold()) if unicodedata.category(char) != "Mn"
    )
    return " ".join(folded.strip(" ?!.,;:").split())


def _topic_query(topic: str, value: str) -> str:
    templates = {
        "definition": f"{topic} là gì?",
        "causes": f"Nguyên nhân gây {topic} là gì?",
        "symptoms": f"Triệu chứng của {topic} là gì?",
        "treatment": f"{topic} có chữa được không?",
        "prevention": f"Cách phòng ngừa {topic} là gì?",
        "danger": f"{topic} có nguy hiểm không?",
        "urgent_signs": f"Dấu hiệu nào của {topic} cần đi khám ngay?",
        "diagnosis": f"{topic} được chẩn đoán như thế nào?",
        "monitoring": f"Cần theo dõi gì khi bị {topic}?",
    }
    return templates.get(value, topic)
