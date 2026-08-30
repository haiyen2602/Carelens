"""BUILD-48: conversation context must survive an ordinary follow-up turn.

Every case below was taken from a REAL user session, not invented: BUILD-47's
durable ``agent_run.follow_up_category`` column recorded the misclassification
live (e.g. 17:13:46 → ``TOPIC_SWITCH`` / ``NAMED_SUBJECT_DIFFERS_FROM_PRIOR``
for the harmless message "cho mình thông tin thuốc"), and the route then
wiped ``active_topic``/``active_entity`` — so the next turn genuinely had no
idea which drug was being discussed.

Two independent defects are locked here.

Defect 1 -- ``_strip_evidence_markers`` leaves polite-request filler ("cho
mình", "giúp mình") and the GENERIC category noun "thuốc"/"bệnh" in the
remainder. ``classify_follow_up`` then reads that residue as "this message
names its own subject", concludes the subject differs from the prior one, and
returns TOPIC_SWITCH. The worst instance is the textbook follow-up "tác dụng
phụ của thuốc là gì", whose remainder is the single word "thuoc".

Defect 2 -- Case 1 (the ``_explicit_topic`` branch) compares the extracted
topic ONLY against ``prior_topic``, never against ``prior_entity_name``,
while Case 2 checks both. So naming the very drug already under discussion in
an explicit-topic-shaped question ("An Cung Ngưu Hoàng có nguy hiểm không?")
is read as switching away from it.

The negative cases matter as much as the positive ones: a fix that made the
classifier simply stop switching topics would be worse than the bug. Each
"must still switch" case names a genuinely different drug/disease.
"""

from __future__ import annotations

import pytest

from backend.agents.v2.conversation_state import (
    ActiveEntity,
    ConversationState,
    SuggestedAction,
    is_allowed_action,
    is_drug_candidate_action,
    resolve_state_input,
    transition_state,
)
from backend.agents.v2.follow_up import FollowUpCategory, classify_follow_up
from backend.agents.v2.orchestrator import OrchestrationIntent, SemanticMedicalQuery
from backend.agents.v2.runtime import RunStatus
from backend.agents.v2.suggested_actions import build_suggested_actions
from backend.agents.v2.tools import ToolResult
from backend.api.agent_v2_routes import _picked_candidate_entity

_PRIOR_DRUG = "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v"


# ---------------------------------------------------------------------------
# Defect 1 -- polite filler / generic noun must not read as a new subject
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "cho mình thông tin thuốc",  # the exact real-session message, 17:13:46
        "tác dụng phụ của thuốc là gì",  # remainder was the bare word "thuoc"
        "công dụng của thuốc",
        "liều dùng của thuốc",
        "cho tôi tác dụng của thuốc",
        "cho tôi xem",
        "giúp mình với",
        "bạn cho mình biết",
        "mình muốn xem",
        "cho hỏi",
        "cho mình xin thông tin",
    ],
)
def test_polite_or_generic_phrasing_keeps_the_prior_drug(message: str):
    decision = classify_follow_up(message, prior_topic=None, prior_entity_name=_PRIOR_DRUG)
    assert decision.category is FollowUpCategory.TRUE_FOLLOWUP, (
        f"{message!r} names no subject of its own and must not discard the prior drug"
    )
    assert decision.inherited_entity is True


@pytest.mark.parametrize(
    "message",
    [
        "cho mình thông tin thuốc",
        "tác dụng phụ của thuốc là gì",
        "cho tôi xem",
    ],
)
def test_polite_or_generic_phrasing_is_ambiguous_without_prior_context(message: str):
    """Naming no subject is only *resolvable* when there is context to inherit.

    With nothing to inherit these must ask for clarification, never silently
    answer about an unspecified drug -- the same asymmetry BUILD-43 already
    encodes for deictic fragments.
    """
    decision = classify_follow_up(message, prior_topic=None, prior_entity_name=None)
    assert decision.category is FollowUpCategory.AMBIGUOUS_FRAGMENT


# ---------------------------------------------------------------------------
# Defect 1 -- a real new subject must STILL switch (anti-overfit)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Paracetamol là gì",
        "Viêm gan B là gì",
        "thuốc Amoxicillin dùng thế nào",
        "cho tôi thông tin thuốc Paracetamol",  # polite filler AND a real drug name
        "tiểu đường có nguy hiểm không",
        "bị chó cắn phải làm sao",  # "chó" folds to "cho" -- must not be eaten
    ],
)
def test_a_genuinely_new_subject_still_switches_topic(message: str):
    decision = classify_follow_up(message, prior_topic=None, prior_entity_name=_PRIOR_DRUG)
    assert decision.category is FollowUpCategory.TOPIC_SWITCH, (
        f"{message!r} names a real, different subject and must still clear stale context"
    )


# ---------------------------------------------------------------------------
# Defect 2 -- Case 1 must compare against the prior ENTITY, not only the topic
# ---------------------------------------------------------------------------


def test_explicit_topic_shape_naming_the_prior_drug_keeps_it():
    decision = classify_follow_up(
        "An Cung Ngưu Hoàng có nguy hiểm không", prior_topic=None, prior_entity_name="An Cung Ngưu Hoàng"
    )
    assert decision.category is not FollowUpCategory.TOPIC_SWITCH
    assert decision.inherited_entity is True


def test_explicit_topic_shape_naming_a_different_drug_still_switches():
    """The BUILD-43 stale-entity lock, restated so the fix cannot over-reach."""
    decision = classify_follow_up(
        "Cảm cúm có nguy hiểm không?", prior_topic=None, prior_entity_name="Ibuprofen"
    )
    assert decision.category is FollowUpCategory.TOPIC_SWITCH
    assert decision.inherited_entity is False


# ---------------------------------------------------------------------------
# Defects 3 & 4 -- remembering an ambiguous search's candidates, and the one
# the user picks.
#
# `search_catalog_unique_match` needs exactly one catalog item scoring >= 0.90
# against the QUERY STRING, so an ambiguous -- or merely mistyped -- drug
# question produces no unique match and nothing was ever remembered. Real
# session: the turn that correctly described "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ
# 3v" ran only `search_drug` (trace: tool_calls=1), and the next turn reported
# NAMED_SUBJECT_NO_PRIOR_CONTEXT. Picking a product afterwards ("loại 400
# Stella") then re-searched the whole catalog and returned unrelated products.
# ---------------------------------------------------------------------------

_CANDIDATES = [
    {"legacy_drug_id": "an-cung-nguu-hoang-hop-go-3v", "name": "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v"},
    {"legacy_drug_id": "an-cung-nguu-hoang-hongjitang", "name": "AN CUNG NGƯU Hoàng Hoàn Hongjitang 1 VIÊN X 3g"},
]


def _build(tool_results, *, entity=None, topic=None, intent=OrchestrationIntent.DRUG_INFORMATION):
    return build_suggested_actions(
        reply="Mình tìm thấy một số sản phẩm.",
        status=RunStatus.COMPLETED,
        intent=intent,
        semantic_query=SemanticMedicalQuery("an cung nguu", "an cung nguu"),
        topic=topic,
        entity=entity,
        selected_action=None,
        tool_results=tool_results,
        safety_event=False,
    )


def test_ambiguous_search_offers_each_candidate_as_a_pickable_action():
    build = _build((ToolResult(name="search_drug", data={"items": _CANDIDATES, "unique_match_legacy_drug_id": None}),))

    assert [action.entity_id for action in build.actions] == [c["legacy_drug_id"] for c in _CANDIDATES]
    assert [action.label for action in build.actions] == [c["name"] for c in _CANDIDATES]
    assert all(is_drug_candidate_action(action) for action in build.actions)
    # Must survive the same allowlist `transition_state` filters through,
    # otherwise the offer shown would silently not persist to the next turn.
    assert all(is_allowed_action(action) for action in build.actions)
    assert "Bạn muốn xem loại nào?" in build.reply


def test_candidate_offer_is_skipped_when_an_entity_was_already_resolved():
    """The pre-existing aspect-button flow must be unreachable from the new
    branch -- a resolved entity still gets aspect follow-ups, not a re-offer
    of the search results."""
    entity = ActiveEntity("drug", "drug-1", "Paracetamol")
    build = _build(
        (
            ToolResult(name="search_drug", data={"items": _CANDIDATES, "unique_match_legacy_drug_id": None}),
            ToolResult(name="get_drug_info", data={"legacy_drug_id": "drug-1", "results": [{"field": "cong_dung"}]}),
        ),
        entity=entity,
    )
    assert all(not is_drug_candidate_action(action) for action in build.actions)
    assert "Bạn muốn xem loại nào?" not in build.reply


def test_a_long_candidate_list_still_offers_the_top_four():
    """Found in real local E2E, not by review: a first cut of this branch
    required ``len(items) <= 4`` and so offered NOTHING for the commonest
    ambiguous query there is -- the live catalog returns 5 items for
    "paracetamol" (7 at limit=10). Offering none is the exact failure this
    build exists to remove, so a longer list is truncated to the 4 actions
    `transition_state` persists rather than discarded.
    """
    many = [{"legacy_drug_id": f"drug-{i}", "name": f"Paracetamol {i}"} for i in range(7)]
    build = _build((ToolResult(name="search_drug", data={"items": many, "unique_match_legacy_drug_id": None}),))

    assert len(build.actions) == 4
    assert [action.entity_id for action in build.actions] == [f"drug-{i}" for i in range(4)]
    assert all(is_drug_candidate_action(action) for action in build.actions)


def test_no_candidates_offered_when_search_payload_is_unusable():
    assert _build((ToolResult(name="search_drug", data={"items": []}),)).actions == ()
    assert _build((ToolResult(name="search_drug", data={"items": [{"name": "no id"}]}),)).actions == ()
    assert _build(()).actions == ()


def test_picking_a_candidate_resolves_without_a_prior_entity():
    """Defect 4: this used to fall through to the raw message, so "loại 400
    Stella" was re-searched across the whole catalog."""
    action = SuggestedAction(
        "drug-candidate-1", "drug_followup", "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v", "drug_uses", entity_id="an-cung-3v"
    )
    state = ConversationState(conversation_id="c1", offered_actions=(action,))

    resolution = resolve_state_input(state, message="AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v", selected_action=action)

    assert resolution.used is True
    assert resolution.selected_action == action
    assert "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v" in resolution.query


def test_picking_a_candidate_by_typing_its_number_also_resolves():
    action = SuggestedAction("drug-candidate-2", "drug_followup", "Paracetamol 500mg", "drug_uses", entity_id="para-500")
    state = ConversationState(conversation_id="c1", offered_actions=(action,))

    resolution = resolve_state_input(state, message="1", selected_action=None)

    assert resolution.used is True
    assert resolution.selected_action == action


def test_picked_candidate_is_promoted_into_state():
    action = SuggestedAction(
        "drug-candidate-3", "drug_followup", "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v", "drug_uses", entity_id="an-cung-3v"
    )
    entity = _picked_candidate_entity(action)

    assert entity is not None
    assert entity.id == "an-cung-3v"
    assert entity.canonical_name == "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v"

    # And it must actually survive the real state transition.
    next_state = transition_state(
        ConversationState(conversation_id="c1"), intent="DRUG_INFORMATION", entity=entity, selected_action=action
    )
    assert next_state.active_entity is not None
    assert next_state.active_entity.canonical_name == "AN CUNG NGƯU Hoàng HOÀN HỘP GỖ 3v"


def test_an_aspect_button_is_never_mistaken_for_a_candidate_pick():
    """The dangerous confusion this design exists to prevent: an aspect
    action's label is templated, so promoting it as an entity would store
    "Tác dụng phụ của Paracetamol" as the drug's own name."""
    aspect = SuggestedAction(
        "aspect-1", "drug_followup", "Tác dụng phụ của Paracetamol", "side_effects", entity_id="para-500"
    )
    assert is_drug_candidate_action(aspect) is False
    assert _picked_candidate_entity(aspect) is None


# ---------------------------------------------------------------------------
# Round 2 -- three more failures found in a real "gan nhiễm mỡ" session, after
# the first round shipped. Telemetry pinpointed the break at 21:20:24.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "cách né tránh",  # 21:20:24 -- "tránh" is stripped, bare "né" survived
        "cách phòng tránh",
        "né tránh thế nào",
    ],
)
def test_avoidance_phrasing_is_an_aspect_not_a_new_topic(message: str):
    decision = classify_follow_up(message, prior_topic="gan nhiễm mỡ", prior_entity_name=None)
    assert decision.category is FollowUpCategory.TRUE_FOLLOWUP
    assert decision.inherited_topic is True


@pytest.mark.parametrize(
    "message",
    [
        "bệnh mà mình vừa nói với bạn ý",  # 21:21:28
        "thuốc mình vừa đưa cho bạn",
        "cái mình vừa hỏi lúc nãy",
        "bệnh lúc nãy",
    ],
)
def test_back_reference_to_an_earlier_turn_is_a_follow_up(message: str):
    """An explicit back-reference is anaphora: it points AT the prior subject,
    so it can never be a new one. These were read as new named subjects purely
    because words like "vừa"/"nãy" survived stripping."""
    decision = classify_follow_up(message, prior_topic="gan nhiễm mỡ", prior_entity_name=None)
    assert decision.category is FollowUpCategory.TRUE_FOLLOWUP


def test_back_reference_without_prior_context_asks_instead_of_guessing():
    decision = classify_follow_up("bệnh mà mình vừa nói với bạn ý", prior_topic=None, prior_entity_name=None)
    assert decision.category is FollowUpCategory.AMBIGUOUS_FRAGMENT


def test_a_single_weak_search_hit_is_not_offered_as_a_candidate():
    """Regression from round 1, seen live: a DISEASE question ("bệnh gan
    nhiễm mỡ") whose drug search returned one unrelated product was offered
    as "Bạn muốn xem loại nào? - Ceelin United 60ml".

    A candidate list exists to DISAMBIGUATE between plausible products. One
    hit is not a disambiguation: had it been a confident match,
    `unique_match_legacy_drug_id` would already have promoted it without ever
    reaching this branch, so a lone hit arriving here is by definition a weak
    one and must not be presented as the thing the user meant.
    """
    single = [{"legacy_drug_id": "ceelin-united-60ml", "name": "Ceelin United 60ml"}]
    build = _build((ToolResult(name="search_drug", data={"items": single, "unique_match_legacy_drug_id": None}),))
    assert build.actions == ()
    assert "Bạn muốn xem loại nào?" not in build.reply


def test_topic_follow_ups_win_over_drug_candidates_on_a_disease_turn():
    """A disease answer must keep offering disease follow-ups even when the
    model also happened to run a drug search."""
    build = _build(
        (ToolResult(name="search_drug", data={"items": _CANDIDATES, "unique_match_legacy_drug_id": None}),),
        topic="gan nhiễm mỡ",
        intent=OrchestrationIntent.GENERAL_MEDICAL_INFORMATION,
    )
    assert build.actions
    assert all(action.type == "topic_followup" for action in build.actions)
