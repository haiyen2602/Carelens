"""BUILD-29D.2 response-consistent suggested actions.

The module has no model or database authority. It chooses from a fixed,
user-safe semantic allowlist only after the real answer, intent, and
authoritative topic/entity are available. It appends the same choices to the
reply, so the UI cannot offer a direction the assistant did not offer.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from backend.agents.v2.conversation_state import (
    DRUG_CANDIDATE_ACTION_PREFIX,
    ActiveEntity,
    SuggestedAction,
)
from backend.agents.v2.orchestrator import OrchestrationIntent, SemanticMedicalQuery
from backend.agents.v2.runtime import RunStatus

# BUILD-48: mirrors the cap `transition_state` applies to `offered_actions`,
# so the list shown is exactly the list that survives into the next turn.
_MAX_CANDIDATE_ACTIONS = 4


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

    # BUILD-48: the turn listed several candidate products and resolved NO
    # single entity. `search_catalog_unique_match` requires exactly one
    # catalog item scoring >= 0.90 against the QUERY STRING, so an ambiguous
    # -- or merely mistyped -- drug question yields no unique match and
    # nothing was ever remembered. Picking one afterwards ("loại 400
    # Stella") then re-searched the whole catalog and returned unrelated
    # products. Offering the candidates makes the choice explicit and, once
    # picked, server-verifiable. Deliberately NOT an automatic top-1 bind:
    # in a medical app, silently attaching the wrong product would answer
    # dosage and contraindication questions about a drug the patient never
    # asked about.
    #
    # Placed LAST (round 2, after a real disease turn was hijacked): a
    # question about an illness whose drug search happened to return one
    # unrelated product was offered as "Bạn muốn xem loại nào? - Ceelin
    # United 60ml", and because this branch used to sit above the topic
    # branch it also SUPPRESSED that turn's real disease follow-ups. A
    # resolved topic now always wins.
    if entity is None:
        candidates = _search_drug_candidates(tool_results)
        if candidates:
            actions = tuple(
                SuggestedAction(
                    f"{DRUG_CANDIDATE_ACTION_PREFIX}{uuid4()}",
                    "drug_followup",
                    name,
                    "drug_uses",
                    entity_id=legacy_drug_id,
                )
                for legacy_drug_id, name in candidates
            )
            offer = "\n\nBạn muốn xem loại nào?\n" + "\n".join(f"- {action.label}" for action in actions)
            return SuggestedActionBuild(reply=f"{reply.rstrip()}{offer}", actions=actions)

    return SuggestedActionBuild(reply=reply, actions=())


def _search_drug_candidates(tool_results: tuple[object, ...]) -> tuple[tuple[str, str], ...]:
    """Return (legacy_drug_id, product name) for a single search's candidates.

    Empty unless EXACTLY ONE ``search_drug`` ran this turn -- two distinct
    searches in one turn is itself a form of ambiguity, and guessing which
    one "counts" is the kind of inference this module deliberately avoids
    (the same reasoning `_resolved_drug_entity` already applies).

    TRUNCATED to the 4 actions ``transition_state`` persists, never
    discarded for being too long: an earlier cut of this function required
    ``len(items) <= 4`` and therefore offered nothing at all for the
    commonest ambiguous query there is -- the live catalog returns 5 items
    for "paracetamol" -- which is precisely the "nothing was remembered"
    failure this build exists to remove. The list is already relevance-
    ranked, and the reply text still names every match, so the buttons are a
    shortcut for the likeliest picks rather than the only way to choose.

    Defensive about shape for the same reason as ``_has_drug_evidence``: a
    malformed tool payload must yield no buttons, never an exception.
    """
    searches = [result for result in tool_results if getattr(result, "name", None) == "search_drug"]
    if len(searches) != 1:
        return ()
    data = getattr(searches[0], "data", None)
    if not isinstance(data, dict):
        return ()
    items = data.get("items")
    # At least TWO, because a candidate list exists to DISAMBIGUATE. A lone
    # hit is not a disambiguation: had it been a confident match,
    # `unique_match_legacy_drug_id` would already have promoted it via
    # `_resolved_drug_entity` and this branch would never be reached -- so a
    # single hit arriving here is by definition a weak one. Offering it as
    # "did you mean this?" is how a disease question ("bệnh gan nhiễm mỡ")
    # ended up being answered with an unrelated syrup (real session, 21:17).
    if not isinstance(items, list) or len(items) < 2:
        return ()
    candidates: list[tuple[str, str]] = []
    for item in items[:_MAX_CANDIDATE_ACTIONS]:
        if not isinstance(item, dict):
            return ()
        legacy_drug_id, name = item.get("legacy_drug_id"), item.get("name")
        if not legacy_drug_id or not name:
            return ()
        candidates.append((str(legacy_drug_id), str(name)))
    return tuple(candidates)


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
