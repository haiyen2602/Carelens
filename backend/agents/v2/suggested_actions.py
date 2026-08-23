"""BUILD-29D.2 response-consistent suggested actions.

The module has no model or database authority. It chooses from a fixed,
user-safe semantic allowlist only after the real answer, intent, and
authoritative topic/entity are available. It appends the same choices to the
reply, so the UI cannot offer a direction the assistant did not offer.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from backend.agents.v2.conversation_state import ActiveEntity, SuggestedAction
from backend.agents.v2.orchestrator import OrchestrationIntent, SemanticMedicalQuery
from backend.agents.v2.runtime import RunStatus


@dataclass(frozen=True)
class SuggestedActionBuild:
    reply: str
    actions: tuple[SuggestedAction, ...]


_TOPIC_LABELS = {
    "causes": "Nguyên nhân gây {topic}",
    "symptoms": "Triệu chứng của {topic}",
    "treatment": "{topic} có chữa được không?",
    "prevention": "Cách phòng ngừa {topic}",
    "danger": "{topic} có nguy hiểm không?",
    "urgent_signs": "Dấu hiệu cần đi khám ngay",
    "diagnosis": "{topic} được chẩn đoán thế nào?",
    "monitoring": "Cần theo dõi gì?",
}
_DRUG_LABELS = {
    "drug_uses": "Công dụng của {entity}",
    "dosage": "Liều dùng {entity}",
    "administration": "Cách dùng {entity}",
    "side_effects": "Tác dụng phụ của {entity}",
    "contraindications": "Chống chỉ định của {entity}",
    "warnings": "Lưu ý khi dùng {entity}",
    "interactions": "Tương tác thuốc của {entity}",
}
_TOPIC_FOLLOWUP_ORDER = {
    "definition": ("causes", "treatment", "urgent_signs"),
    "causes": ("treatment", "symptoms", "urgent_signs"),
    "symptoms": ("treatment", "danger", "urgent_signs"),
    "treatment": ("monitoring", "prevention", "urgent_signs"),
    "prevention": ("symptoms", "treatment", "urgent_signs"),
    "danger": ("symptoms", "treatment", "urgent_signs"),
    "urgent_signs": ("diagnosis", "treatment", "monitoring"),
    "diagnosis": ("treatment", "monitoring", "urgent_signs"),
    "monitoring": ("treatment", "prevention", "urgent_signs"),
}
_DRUG_FOLLOWUP_ORDER = {
    "drug_uses": ("side_effects", "warnings", "administration"),
    "dosage": ("administration", "warnings", "interactions"),
    "administration": ("side_effects", "warnings", "interactions"),
    "side_effects": ("warnings", "interactions", "drug_uses"),
    "contraindications": ("warnings", "interactions", "drug_uses"),
    "warnings": ("side_effects", "interactions", "drug_uses"),
    "interactions": ("warnings", "side_effects", "drug_uses"),
}


def build_suggested_actions(
    *,
    reply: str,
    status: RunStatus,
    intent: OrchestrationIntent,
    semantic_query: SemanticMedicalQuery,
    topic: str | None,
    entity: ActiveEntity | None,
    selected_action: SuggestedAction | None,
    tool_results: tuple[object, ...],
    safety_event: bool,
) -> SuggestedActionBuild:
    """Return 0-3 allowlisted actions and a reply that explicitly offers them.

    Failed, safety, unsupported, ambiguous, or evidence-free runs get no
    action. The requested semantic direction selects useful *next*
    capabilities; server-resolved topic/entity makes every action unambiguous.
    """
    if safety_event or status is not RunStatus.COMPLETED or not reply.strip():
        return SuggestedActionBuild(reply=reply, actions=())

    current_value = selected_action.value if selected_action else _semantic_value(semantic_query.family)

    # BUILD-29D.2 fix (found via real local E2E, 2026-08-23): checked before
    # the topic branch, and independent of the router's own intent label --
    # a resolved canonical drug entity backed by real tool evidence is
    # authoritative regardless of intent (the keyword router can mislabel a
    # drug-specific question, e.g. "Cong dung cua thuoc X la gi", as
    # GENERAL_MEDICAL_INFORMATION while the orchestrator still answered from
    # that drug's evidence). Trusting the label alone here previously offered
    # topic_followup actions with no entity binding for an answer that was
    # actually about one specific drug.
    if entity and _has_drug_evidence(tool_results):
        values = _DRUG_FOLLOWUP_ORDER.get(current_value or "drug_uses", _DRUG_FOLLOWUP_ORDER["drug_uses"])
        actions = tuple(
            SuggestedAction(
                str(uuid4()),
                "drug_followup",
                _DRUG_LABELS[value].format(entity=entity.canonical_name),
                value,
                entity_id=entity.id,
            )
            for value in values
        )
        return _with_reply_offer(reply, actions)

    if intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION and topic:
        values = _TOPIC_FOLLOWUP_ORDER.get(current_value or "definition", _TOPIC_FOLLOWUP_ORDER["definition"])
        actions = tuple(
            SuggestedAction(
                str(uuid4()), "topic_followup", _TOPIC_LABELS[value].format(topic=topic), value, topic=topic
            )
            for value in values
        )
        return _with_reply_offer(reply, actions)

    return SuggestedActionBuild(reply=reply, actions=())


def _has_drug_evidence(tool_results: tuple[object, ...]) -> bool:
    # Deliberately defensive against a malformed/unexpected tool_results
    # entry, not just a missing get_drug_info call: `getattr(..., None)`
    # never raises for an object without a `name` attribute, and the
    # `isinstance(..., dict)` check short-circuits the chained `and` (Python
    # never evaluates the trailing `.get("results")` unless `data` was
    # already confirmed to be a dict), so a non-dict `.data` cannot raise
    # AttributeError here.
    return any(
        getattr(result, "name", None) == "get_drug_info"
        and isinstance(getattr(result, "data", {}), dict)
        and bool(getattr(result, "data", {}).get("results"))
        for result in tool_results
    )


def _semantic_value(family: str | None) -> str | None:
    return {"cause": "causes", "urgent_care": "urgent_signs"}.get(family or "", family)


def _with_reply_offer(reply: str, actions: tuple[SuggestedAction, ...]) -> SuggestedActionBuild:
    offer = "\n\nBạn có thể hỏi thêm:\n" + "\n".join(f"- {action.label}" for action in actions)
    return SuggestedActionBuild(reply=f"{reply.rstrip()}{offer}", actions=actions)
