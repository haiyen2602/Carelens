"""Validated, durable conversation state for Agent V2.

State is intentionally a record of server-issued context, not the place that
decides which suggestions to show. BUILD-29D.2 keeps action generation in
``suggested_actions.py`` because it needs the actual answer and evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Literal

ActionType = Literal["topic_followup", "drug_followup", "schedule_followup"]


def _parse_schedule_range(value: object) -> tuple[date, date] | None:
    """Parse the two-element ISO-date list `as_dict` writes for
    `active_schedule_range`. Any other shape (absent, None, malformed --
    including a pre-version-6 row that never had this key at all) reads back
    as None, never a fabricated or partially-parsed range."""
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        return (date.fromisoformat(str(value[0])), date.fromisoformat(str(value[1])))
    except ValueError:
        return None

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
    display_name: str | None = None
    normalized_key: str | None = None

    def __post_init__(self) -> None:
        """Keep a human-safe canonical/display value separate from lookup text."""
        display_name = self.display_name or self.canonical_name
        object.__setattr__(self, "canonical_name", display_name)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "normalized_key", self.normalized_key or _normalized_key(display_name))


@dataclass(frozen=True)
class ActiveEntity:
    type: str
    id: str
    canonical_name: str
    display_name: str | None = None
    normalized_key: str | None = None
    # B-07 keeps the canonical V2 product ID in ``id``. Agent V2's existing
    # Drug Tool still uses a legacy lookup key during the V1/V2 transition, so
    # the server-owned mapping is carried separately and is never client input.
    legacy_drug_id: str | None = None

    def __post_init__(self) -> None:
        """Never replace a canonical drug name with its normalized lookup key."""
        display_name = self.display_name or self.canonical_name
        object.__setattr__(self, "canonical_name", display_name)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "normalized_key", self.normalized_key or _normalized_key(display_name))


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


# BUILD-48: marks a `drug_followup` that offers ONE CANDIDATE PRODUCT to pick
# from an ambiguous search, rather than an ASPECT of an already-resolved drug.
# Both share the `drug_followup` type and can both carry `value="drug_uses"`,
# so `value` cannot tell them apart -- and confusing them would be harmful:
# an aspect action's label is templated ("Tác dụng phụ của X"), so promoting
# it as an entity would store that whole phrase as the drug's name. The
# action_id is server-issued and re-validated against `offered_actions` on
# every turn, so it is a safe discriminator; raw client input can never forge
# one that was not offered.
DRUG_CANDIDATE_ACTION_PREFIX = "drug-candidate-"


def is_drug_candidate_action(action: SuggestedAction | None) -> bool:
    return (
        action is not None
        and action.type == "drug_followup"
        and bool(action.entity_id)
        and action.action_id.startswith(DRUG_CANDIDATE_ACTION_PREFIX)
    )


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
    # BUILD-42: bounded clarification-attempt tracking for the Answerability
    # Gate (see backend/agents/v2/answerability.py). Reset to 0 by
    # ``transition_state`` on every turn the Answerability Gate did not
    # itself decide NEED_MORE_INFO for -- see that function's own docstring.
    # No equivalent counter existed anywhere in this module before this
    # build (confirmed by audit before adding it, per the build's own
    # instruction not to duplicate existing state).
    answerability_attempt_count: int = 0
    last_answerability_reason: str | None = None
    # TASK-V2.5-002: the (start_date, end_date) of the most recent multi-day
    # schedule query, valid for AT MOST one following turn -- see
    # transition_state's own docstring. Unlike active_topic/active_entity,
    # this never carries forward implicitly: transition_state persists
    # exactly what its `schedule_range` argument says this turn, defaulting
    # to None, never `state.active_schedule_range`.
    active_schedule_range: tuple[date, date] | None = None

    @property
    def requested_aspect(self) -> str | None:
        """Semantic follow-up aspect; ``requested_attribute`` is the legacy name."""
        return self.requested_attribute

    @classmethod
    def empty(cls, conversation_id: str) -> ConversationState:
        return cls(conversation_id=conversation_id)

    def as_dict(self, *, actor_id: str, patient_id: str) -> dict[str, object]:
        return {
            # TASK-V2.5-002: version 6 adds active_schedule_range. No
            # migration needed -- this dict is stored inside the existing
            # AgentRun.metadata_json JSON column, not a typed table (see
            # backend/services/agent_conversation_state.py).
            "version": 6,
            "actor_id": actor_id,
            "patient_id": patient_id,
            "conversation_id": self.conversation_id,
            "active_topic": None
            if self.active_topic is None
            else {
                "type": self.active_topic.type,
                "canonical_name": self.active_topic.canonical_name,
                "display_name": self.active_topic.display_name,
                "normalized_key": self.active_topic.normalized_key,
            },
            "active_entity": None
            if self.active_entity is None
            else {
                "type": self.active_entity.type,
                "id": self.active_entity.id,
                "canonical_name": self.active_entity.canonical_name,
                "display_name": self.active_entity.display_name,
                "normalized_key": self.active_entity.normalized_key,
                "legacy_drug_id": self.active_entity.legacy_drug_id,
            },
            "last_intent": self.last_intent,
            "requested_attribute": self.requested_attribute,
            "requested_aspect": self.requested_aspect,
            "offered_actions": [action.as_dict() for action in self.offered_actions],
            "pending_selection": self.pending_selection,
            "updated_at": (self.updated_at or datetime.now(UTC)).isoformat(),
            "answerability_attempt_count": self.answerability_attempt_count,
            "last_answerability_reason": self.last_answerability_reason,
            "active_schedule_range": None
            if self.active_schedule_range is None
            else [self.active_schedule_range[0].isoformat(), self.active_schedule_range[1].isoformat()],
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
                active_topic=ActiveTopic(
                    str(topic["type"]),
                    str(topic["canonical_name"]),
                    str(topic["display_name"]) if topic.get("display_name") else None,
                    str(topic["normalized_key"]) if topic.get("normalized_key") else None,
                )
                if isinstance(topic, dict)
                else None,
                active_entity=ActiveEntity(
                    str(entity["type"]),
                    str(entity["id"]),
                    str(entity["canonical_name"]),
                    str(entity["display_name"]) if entity.get("display_name") else None,
                    str(entity["normalized_key"]) if entity.get("normalized_key") else None,
                    str(entity["legacy_drug_id"]) if entity.get("legacy_drug_id") else None,
                )
                if isinstance(entity, dict)
                else None,
                last_intent=str(value["last_intent"]) if value.get("last_intent") else None,
                requested_attribute=str(value.get("requested_aspect") or value.get("requested_attribute"))
                if value.get("requested_aspect") or value.get("requested_attribute")
                else None,
                offered_actions=actions,
                pending_selection=str(value["pending_selection"]) if value.get("pending_selection") else None,
                updated_at=datetime.fromisoformat(value["updated_at"]) if value.get("updated_at") else None,
                # BUILD-42: absent on any state persisted before this build
                # (older ``version: 3`` rows) -- default 0/None reads back
                # exactly as a fresh conversation, never a fabricated count.
                answerability_attempt_count=int(value.get("answerability_attempt_count") or 0),
                last_answerability_reason=str(value["last_answerability_reason"])
                if value.get("last_answerability_reason")
                else None,
                # TASK-V2.5-002: absent on any state persisted before version
                # 6 (older `version: 5` and earlier rows) -- default None
                # reads back exactly as no stored range, never a fabricated
                # one, same convention as answerability_attempt_count above.
                active_schedule_range=_parse_schedule_range(value.get("active_schedule_range")),
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
    if action.type == "topic_followup" and state.active_topic:
        # The client echo's topic was checked only for exact equality with a
        # server-issued action. The current state remains authoritative: a
        # retrieval query must never be allowed to rename the topic.
        return StateInputResolution(
            query=build_followup_query(state.active_topic, action.value), selected_action=action, used=True
        )
    if action.type == "topic_followup" and action.topic:
        # A valid server-issued action can restore a missing legacy state,
        # but its topic is still not taken directly from arbitrary client input.
        return StateInputResolution(query=build_followup_query(action.topic, action.value), selected_action=action, used=True)
    if action.type == "drug_followup" and state.active_entity and action.entity_id == state.active_entity.id:
        return StateInputResolution(
            query=f"{action.label} của thuốc {state.active_entity.canonical_name}", selected_action=action, used=True
        )
    if is_drug_candidate_action(action):
        # BUILD-48: picking one product out of an ambiguous search result.
        # Checked AFTER the aspect branch above so the existing flow (an
        # action bound to the CURRENT entity) is untouched. `active_entity`
        # is normally None here -- that ambiguity is precisely why a list was
        # offered. The label is the server-issued product name, so phrasing
        # it this way keeps the router classifying this as a drug-information
        # question rather than an unrecognized fragment.
        return StateInputResolution(
            query=f"Công dụng của thuốc {action.label}", selected_action=action, used=True
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
    answerability_attempt_count: int = 0,
    last_answerability_reason: str | None = None,
    schedule_range: tuple[date, date] | None = None,
) -> ConversationState:
    """Persist a server-authoritative state transition without fallback templates.

    BUILD-42: ``answerability_attempt_count`` defaults to 0 -- the caller
    (agent_v2_routes.py) only passes a nonzero value when this exact turn's
    ``OrchestrationResult.answerability_decision`` was NEED_MORE_INFO, so
    every other turn (an answered question, a topic switch, a genuinely new
    question) resets the bounded-clarification counter rather than letting
    it silently accumulate across unrelated turns.

    TASK-V2.5-002: ``schedule_range`` follows the OPPOSITE carry-forward rule
    from ``topic``/``entity`` above. Those two fall back to the PRIOR
    state's value when omitted (an ordinary turn keeps the existing topic).
    ``schedule_range`` never does -- it is always exactly what the caller
    passes for *this* turn, defaulting to ``None``. This is what makes it
    valid for at most one following turn: the caller only passes a value the
    one turn a new multi-day schedule query resolves; every other turn
    (the remainder-follow-up turn that consumes it, a topic switch, a
    safety/handoff event, or any unrelated intent) passes nothing and the
    field is gone for the turn after that -- no separate "clear" branch
    needed for each of those cases.
    """
    if safety_event:
        return replace(
            state,
            last_intent=intent,
            offered_actions=(),
            pending_selection=None,
            updated_at=datetime.now(UTC),
            answerability_attempt_count=0,
            last_answerability_reason=None,
            active_schedule_range=None,
        )

    # `topic` and `entity` are mutually exclusive by contract (a turn is
    # either about a general medical topic or about one specific drug, never
    # both -- see the caller in agent_v2_routes.py, which never sets both on
    # the same call). Branched with elif rather than two independent `if`s:
    # the earlier form set `next_entity = None` when `topic` was truthy and
    # `next_topic = None` when `entity` was truthy, so a call that (against
    # the contract) passed both truthy at once silently nulled out *both* --
    # discarding a real resolved entity instead of keeping it. `entity` wins
    # if that contract is ever violated, since a resolved entity is a
    # stronger, more specific signal than a topic string.
    if entity:
        next_entity = entity
        next_topic = None
    elif topic:
        next_entity = None
        next_topic = ActiveTopic("medical_topic", topic)
    else:
        next_entity = state.active_entity
        next_topic = state.active_topic

    return ConversationState(
        conversation_id=state.conversation_id,
        active_topic=next_topic,
        active_entity=next_entity,
        last_intent=intent,
        requested_attribute=selected_action.value if selected_action else None,
        offered_actions=tuple(action for action in offered_actions if is_allowed_action(action))[:4],
        pending_selection=None,
        updated_at=datetime.now(UTC),
        answerability_attempt_count=answerability_attempt_count,
        last_answerability_reason=last_answerability_reason,
        active_schedule_range=schedule_range,
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
    # A short semantic follow-up may be useful after its corresponding button
    # was no longer among the latest 2-4 suggestions. This is constructed on
    # the server from the current canonical state and the allowlist only; it
    # is never a client-supplied action and cannot introduce a new topic.
    if state.active_topic:
        follow_up = normalized[4:] if normalized.startswith("con ") else normalized
        for value in TOPIC_ACTION_VALUES:
            candidate = SuggestedAction(
                action_id=f"typed-topic-{value}",
                type="topic_followup",
                label=message.strip(),
                value=value,
                topic=state.active_topic.canonical_name,
            )
            if follow_up in _typed_aliases(candidate):
                return candidate
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
    return " ".join(folded.replace("đ", "d").strip(" ?!.,;:").split())


def _normalized_key(value: str) -> str:
    return _normalize(value)


def build_followup_query(active_topic: ActiveTopic | str, requested_aspect: str) -> str:
    """Build an ephemeral retrieval/model query for a canonical topic.

    The caller must treat this output as request-local input only. It is not
    a topic resolver and must never be persisted into ``active_topic``.
    """
    topic = active_topic.canonical_name if isinstance(active_topic, ActiveTopic) else active_topic
    templates = {
        "definition": f"{topic} là gì?",
        "causes": f"nguyên nhân gây {topic}",
        "symptoms": f"triệu chứng của {topic}",
        "treatment": f"điều trị {topic}",
        "prevention": f"cách phòng ngừa {topic}",
        "danger": f"{topic} có nguy hiểm không?",
        "urgent_signs": f"dấu hiệu nguy hiểm của {topic} cần đi khám ngay",
        "diagnosis": f"{topic} được chẩn đoán như thế nào?",
        "monitoring": f"cần theo dõi gì khi bị {topic}",
    }
    return templates.get(requested_aspect, topic)


# Compatibility for callers that imported the private BUILD-29D.2 helper.
_topic_query = build_followup_query
