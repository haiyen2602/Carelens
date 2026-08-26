"""BUILD-43: Conversation State / Follow-up Resolution -- required test
matrix (spec SS20 A-P), orchestrator-level scenarios.

Root cause this build fixes (see the report for the full audit): the old
``_follow_up_category``/``resolve_conversation_context`` mechanism used
``len(message.strip()) <= 35`` as its deciding signal and re-derived "the
current topic" from raw short-term MEMORY TEXT via regex -- entirely
independent of the canonical, durable ``ConversationState.active_topic``/
``active_entity`` fields. This module tests the new deterministic
TRUE_FOLLOWUP/STANDALONE_QUESTION/TOPIC_SWITCH/AMBIGUOUS_FRAGMENT taxonomy
(``backend/agents/v2/follow_up.py``) end to end through the real
orchestrator -- routes.py-level scenarios (state persistence/clearing,
answerability-attempt reset on topic switch) live in
``test_agent_v2_build43_conversation_state.py``.
"""

from __future__ import annotations

from backend.agents.v2.answerability import MAX_CLARIFICATION_ATTEMPTS
from backend.agents.v2.follow_up import FollowUpCategory
from backend.agents.v2.model_gateway import ModelPlan, ModelSynthesis, ToolCall
from backend.agents.v2.orchestrator import OrchestrationIntent, RunStatus
from tests.test_agent_v2_orchestrator import NOW, _DomainTools, _orchestrator, _request, _SpyModelGateway, _tools

# ---------------------------------------------------------------------------
# A/B. Short/long standalone question != follow-up, even WITH unrelated
# prior context present (SHORT != FOLLOW_UP is the headline invariant).
# ---------------------------------------------------------------------------


def test_a_short_standalone_disease_question_ignores_unrelated_prior_drug():
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="grounded")))
    result = orchestrator.run(
        _request("Viêm gan B là gì?", prior_active_entity_id="drug-1", prior_active_entity_name="Amoxicillin"),
        tools=_tools(),
    )
    assert result.follow_up_decision.category is FollowUpCategory.TOPIC_SWITCH
    assert result.follow_up_decision.inherited_entity is False
    assert "amoxicillin" not in gateway.calls[-1]["message"].casefold()


def test_b_long_standalone_question_ignores_unrelated_prior_drug():
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="grounded")))
    message = "Bệnh tiểu đường type 2 có những triệu chứng nào cần chú ý theo dõi lâu dài?"
    result = orchestrator.run(
        _request(message, prior_active_entity_id="drug-1", prior_active_entity_name="Amoxicillin"), tools=_tools()
    )
    assert result.follow_up_decision.category is not FollowUpCategory.TRUE_FOLLOWUP
    assert "amoxicillin" not in gateway.calls[-1]["message"].casefold()


# ---------------------------------------------------------------------------
# C. Explicit drug-aspect follow-up -- inherits the entity, binds the SAME
# deterministic tool-lookup shortcut a clicked suggestion button would have
# used (no model re-search of an ambiguous drug name).
# ---------------------------------------------------------------------------


def test_c_explicit_aspect_follow_up_binds_inherited_entity_deterministically():
    domain = _DomainTools()
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="Có thể gây buồn nôn.")))
    result = orchestrator.run(
        _request("Tác dụng phụ thì sao?", prior_active_entity_id="drug-1", prior_active_entity_name="Paracetamol"),
        tools=_tools(domain),
    )
    assert result.follow_up_decision.category is FollowUpCategory.TRUE_FOLLOWUP
    assert result.follow_up_decision.inherited_entity is True
    assert result.status is RunStatus.COMPLETED
    # The deterministic bound-lookup shortcut fired -- get_drug_info called
    # directly with the INHERITED id, search_drug never called at all (no
    # ambiguous re-search of a name the model was never given).
    assert ("get_drug_info", "drug-1") in domain.calls
    assert not any(call[0] == "search_drug" for call in domain.calls)


# ---------------------------------------------------------------------------
# D. Pronoun/deictic follow-up ("Thuốc này...").
# ---------------------------------------------------------------------------


def test_d_pronoun_follow_up_inherits_entity():
    domain = _DomainTools()
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="Uống trước ăn 30 phút.")))
    result = orchestrator.run(
        _request(
            "Thuốc này uống trước hay sau ăn?", prior_active_entity_id="drug-1", prior_active_entity_name="Amoxicillin"
        ),
        tools=_tools(domain),
    )
    assert result.follow_up_decision.category is FollowUpCategory.TRUE_FOLLOWUP
    assert result.follow_up_decision.inherited_entity is True
    assert ("get_drug_info", "drug-1") in domain.calls


# ---------------------------------------------------------------------------
# G. Schedule follow-up -- deterministic Time Query Engine untouched by this
# build (BUILD-27B), never reaches the follow-up classifier at all.
# ---------------------------------------------------------------------------


def test_g_schedule_follow_up_bypasses_the_classifier_entirely():
    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(ModelPlan(response="should not be used")), now=lambda: NOW
    )
    result = orchestrator.run(
        _request("Còn ngày mai?", prior_active_topic="viêm phổi"), tools=_tools(_DomainTools())
    )
    assert result.intent is OrchestrationIntent.UPCOMING_DOSES
    assert result.follow_up_decision is None
    assert len(gateway.calls) == 0


# ---------------------------------------------------------------------------
# H/I. Ambiguous fragment -- resolved vs unresolved.
# ---------------------------------------------------------------------------


def test_h_ambiguous_fragment_resolves_to_true_followup_with_context():
    domain = _DomainTools()
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="500mg co san.")))
    result = orchestrator.run(
        _request("còn loại 500mg?", prior_active_entity_id="drug-1", prior_active_entity_name="Paracetamol"),
        tools=_tools(domain),
    )
    assert result.follow_up_decision.category is FollowUpCategory.TRUE_FOLLOWUP
    assert result.status is RunStatus.COMPLETED


def test_i_ambiguous_fragment_unresolved_asks_clarification_bounded():
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="should not be used")))
    result = orchestrator.run(_request("còn loại 500mg?"), tools=_tools())
    assert result.intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS
    assert result.status is RunStatus.COMPLETED
    assert "chủ đề nào" in result.response
    assert len(gateway.calls) == 0
    # BUILD-43: this path is now bounded (BUILD-42's own Answerability Gate
    # mechanism, previously never wired to this specific reply builder) --
    # a real answerability_decision is attached, not silently absent.
    assert result.answerability_decision is not None
    assert result.answerability_decision.outcome.value == "NEED_MORE_INFO"


def test_i2_ambiguous_fragment_repeated_escalates_to_need_doctor():
    """The same previously-unbounded loop (SS9/SS21) now escalates after
    MAX_CLARIFICATION_ATTEMPTS, matching _clinical_clarification_reply's
    own already-bounded shape exactly."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway())
    result = orchestrator.run(
        _request("còn loại 500mg?", answerability_attempt_count=MAX_CLARIFICATION_ATTEMPTS), tools=_tools()
    )
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.handoff_result is not None
    assert result.answerability_decision.reason_code.value == "REPEATED_CLARIFICATION"
    assert len(gateway.calls) == 0


# ---------------------------------------------------------------------------
# J. Stale entity not inherited on an explicit new topic.
# ---------------------------------------------------------------------------


def test_j_stale_entity_not_inherited_on_explicit_new_topic():
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="grounded")))
    result = orchestrator.run(
        _request("Cảm cúm có nguy hiểm không?", prior_active_entity_id="drug-1", prior_active_entity_name="Ibuprofen"),
        tools=_tools(),
    )
    assert result.follow_up_decision.category is FollowUpCategory.TOPIC_SWITCH
    assert result.follow_up_decision.inherited_entity is False
    assert "ibuprofen" not in gateway.calls[-1]["message"].casefold()


# ---------------------------------------------------------------------------
# K. retrieval_query never overwrites canonical state -- structural
# invariant: classify_follow_up's own signature never accepts a retrieval
# query at all (see follow_up.py), so this is enforced by construction, not
# by a runtime check. This test documents/locks that contract.
# ---------------------------------------------------------------------------


def test_k_classify_follow_up_signature_has_no_retrieval_query_input():
    import inspect

    from backend.agents.v2.follow_up import classify_follow_up

    params = set(inspect.signature(classify_follow_up).parameters)
    assert params == {"message", "prior_topic", "prior_entity_name"}


# ---------------------------------------------------------------------------
# PR #130 review: _DRUG_ASPECT_KEYWORDS (detection) and _DRUG_ASPECT_LABELS
# (display text) are two separately-maintained dicts that must stay
# key-for-key in sync -- a real maintenance risk (not a live bug today,
# both currently define the exact same 7 keys) since a future edit could
# add a keyword group with no matching label and KeyError deep inside a
# live run. Locked by both a module-load-time assertion (orchestrator.py)
# and a defensive membership check inside _detect_drug_aspect itself.
# ---------------------------------------------------------------------------


def test_drug_aspect_keywords_and_labels_stay_in_sync():
    from backend.agents.v2.orchestrator import _DRUG_ASPECT_KEYWORDS, _DRUG_ASPECT_LABELS

    assert set(_DRUG_ASPECT_KEYWORDS) == set(_DRUG_ASPECT_LABELS)


def test_detect_drug_aspect_never_returns_a_key_missing_from_labels(monkeypatch):
    """Simulates the exact drift the review warned about: a keyword group
    added to _DRUG_ASPECT_KEYWORDS with no matching _DRUG_ASPECT_LABELS
    entry. _detect_drug_aspect must degrade to None (safe), never surface
    a key that would KeyError at the real call site."""
    import backend.agents.v2.orchestrator as orchestrator_module

    drifted_keywords = dict(orchestrator_module._DRUG_ASPECT_KEYWORDS)
    drifted_keywords["storage"] = ("bảo quản", "bao quan")
    monkeypatch.setattr(orchestrator_module, "_DRUG_ASPECT_KEYWORDS", drifted_keywords)

    assert orchestrator_module._detect_drug_aspect("Bảo quản thuốc này thế nào?") is None


# ---------------------------------------------------------------------------
# N. Safety precedence -- Safety still runs first, follow-up resolution
# never overrides ACUTE_DANGER/POSSIBLE_OVERDOSE/MEDICATION_DOSE_SAFETY.
# ---------------------------------------------------------------------------


def test_n_safety_precedence_over_true_followup_shaped_message():
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="should never run")))
    result = orchestrator.run(
        _request("Tôi vừa uống nhầm 20 viên thuốc rồi", prior_active_entity_id="drug-1", prior_active_entity_name="Paracetamol"),
        tools=_tools(),
    )
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.safety_decision is not None
    assert len(gateway.calls) == 0


# ---------------------------------------------------------------------------
# O. Router regression -- BUILD-40's own fix (disease/symptom no longer
# defaults to DRUG_INFORMATION) must survive this build untouched.
# ---------------------------------------------------------------------------


def test_o_router_regression_disease_question_not_forced_to_drug_information():
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="grounded")))
    result = orchestrator.run(_request("huyết áp cao có dấu hiệu nào"), tools=_tools())
    assert result.intent is not OrchestrationIntent.DRUG_INFORMATION


# ---------------------------------------------------------------------------
# D2/F. Explicit topic switch, disease -> drug direction.
# ---------------------------------------------------------------------------


def test_topic_switch_disease_to_drug_direction():
    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(
            ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "amoxicillin", "limit": 3}),), response=""),
            ModelSynthesis(response="Uống 3 lần/ngày."),
        )
    )
    result = orchestrator.run(
        _request("Amoxicillin dùng thế nào?", prior_active_topic="viêm phổi"), tools=_tools()
    )
    assert result.follow_up_decision.category is FollowUpCategory.TOPIC_SWITCH
    assert "viêm phổi" not in gateway.calls[-1]["message"].casefold() and "viem phoi" not in gateway.calls[-1]["message"].casefold()
