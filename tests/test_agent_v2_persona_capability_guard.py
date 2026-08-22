"""BUILD-24H (V2 RC hardening, Phase 1 item 4): persona/capability/domain guard.

Found in BUILD-24C's golden set (report 35, section 4):

- query_id 75 ("bạn có thể giúp tôi đặt lịch khám bác sĩ không" -- can you
  help me book a doctor's appointment): the model said "Yes, I can help you
  plan/book an appointment" and listed steps -- a false capability claim.
  Agent V2 has no booking tool at all; this is structurally impossible.
- query_id 76 ("bạn tên gì, ai tạo ra bạn" -- what's your name, who made
  you): the model answered "Mình là ChatGPT, một trợ lý AI do OpenAI tạo
  ra" -- a vendor/persona leak, unprompted disclosure of the underlying
  provider.
- query_id 78 ("kể cho tôi nghe 1 câu chuyện cười đi" -- tell me a joke) and
  query_id 79 ("1+1 bằng mấy" -- what's 1+1): both explicitly out-of-scope
  requests, answered directly instead of declined.

Fix: a new ``OrchestrationIntent.OUT_OF_SCOPE_REQUEST``, detected by
``_detect_out_of_scope_category`` (three categories: IDENTITY,
CAPABILITY_BOOKING, GENERAL_OFF_TOPIC), short-circuited in
``AgentOrchestrator.run()`` to a fixed, honest reply *before* Safety,
retrieval, Vinmec Web, or the Main Model are ever reached -- the same
"guarantee the outcome deterministically" principle as acute-danger/
doctor-review (BUILD-24E), chosen because a false capability claim or a
vendor leak needs to never happen, not just be corrected after the fact.

A second, independent layer -- ``_enforce_no_vendor_disclosure`` -- is a
defense-in-depth post-model backstop (same architecture as the Vinmec-
provenance backstop) that replaces any reply mentioning "ChatGPT"/"OpenAI"/
"GPT" with the same fixed identity text, in case some other, differently
worded message reaches the Main Model and it discloses the vendor anyway.
"""

from __future__ import annotations

import pytest

from backend.agents.v2.model_gateway import ModelPlan
from backend.agents.v2.orchestrator import (
    OrchestrationIntent,
    _OUT_OF_SCOPE_REPLIES,
    _detect_out_of_scope_category,
    _enforce_no_vendor_disclosure,
    classify_intent,
)
from backend.agents.v2.runtime import RunMetrics, RunResult, RunStatus

from tests.test_agent_v2_orchestrator import _SpyModelGateway, _orchestrator, _request, _tools

_GOLDEN_CASES = [
    (75, "bạn có thể giúp tôi đặt lịch khám bác sĩ không", "CAPABILITY_BOOKING"),
    (76, "bạn tên gì, ai tạo ra bạn", "IDENTITY"),
    (78, "kể cho tôi nghe 1 câu chuyện cười đi", "GENERAL_OFF_TOPIC"),
    (79, "1+1 bằng mấy", "GENERAL_OFF_TOPIC"),
]


# ---------------------------------------------------------------------------
# 1. Unit: _detect_out_of_scope_category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query_id,query,expected_category", _GOLDEN_CASES, ids=[str(c[0]) for c in _GOLDEN_CASES])
def test_golden_out_of_scope_queries_are_detected_with_the_right_category(query_id, query, expected_category):
    assert _detect_out_of_scope_category(query) == expected_category


@pytest.mark.parametrize(
    "query",
    [
        "Paracetamol la thuoc gi",
        "Toi quen uong thuoc sang nay",
        "Hom nay toi can uong thuoc gi",
        "vizicin",
        "xin chao",
        "Vitamin C uống bao nhiêu viên 1 ngày",
    ],
)
def test_ordinary_medical_queries_are_not_out_of_scope(query):
    assert _detect_out_of_scope_category(query) is None


@pytest.mark.parametrize("query", ["2+2 bằng mấy", "3 x 4 = ?", "5-2 bằng bao nhiêu"])
def test_arithmetic_variants_are_detected(query):
    assert _detect_out_of_scope_category(query) == "GENERAL_OFF_TOPIC"


def test_who_are_you_english_variant_is_detected():
    assert _detect_out_of_scope_category("who are you") == "IDENTITY"
    assert _detect_out_of_scope_category("who made you") == "IDENTITY"


# ---------------------------------------------------------------------------
# 2. classify_intent routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query_id,query,expected_category", _GOLDEN_CASES, ids=[str(c[0]) for c in _GOLDEN_CASES])
def test_classify_intent_routes_to_out_of_scope_request(query_id, query, expected_category):
    decision = classify_intent(query)
    assert decision.intent is OrchestrationIntent.OUT_OF_SCOPE_REQUEST
    assert decision.safety_trigger is None
    assert decision.bypass_to_handoff is False
    assert decision.use_retrieval is False
    assert decision.use_vinmec_web is False


def test_acute_danger_wins_over_out_of_scope_in_the_same_message():
    # Extremely unlikely real phrasing, but the priority order must hold:
    # acute danger is checked far earlier than out-of-scope.
    decision = classify_intent("tôi vừa uống một lúc 15 viên panadol, bạn tên gì")
    assert decision.intent is OrchestrationIntent.ACUTE_DANGER_ESCALATION


# ---------------------------------------------------------------------------
# 3. Full orchestrator integration -- exact golden-query reproductions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query_id,query,expected_category", _GOLDEN_CASES, ids=[str(c[0]) for c in _GOLDEN_CASES])
def test_golden_queries_get_the_fixed_reply_and_never_reach_the_main_model(query_id, query, expected_category):
    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(ModelPlan(response="should never be produced")),
    )
    result = orchestrator.run(_request(query), tools=_tools())

    assert result.intent is OrchestrationIntent.OUT_OF_SCOPE_REQUEST
    assert result.status is RunStatus.COMPLETED
    assert result.response == _OUT_OF_SCOPE_REPLIES[expected_category]
    assert result.safety_decision is None
    assert result.handoff_result is None
    assert result.citations == ()
    assert result.tool_results == ()
    assert gateway.calls == []  # Main Model never reached
    assert gateway.synthesis_calls == []


def test_identity_reply_never_names_the_vendor():
    reply = _OUT_OF_SCOPE_REPLIES["IDENTITY"]
    lowered = reply.lower()
    assert "chatgpt" not in lowered
    assert "openai" not in lowered
    assert "gpt" not in lowered


def test_capability_booking_reply_is_honest_about_the_missing_tool():
    reply = _OUT_OF_SCOPE_REPLIES["CAPABILITY_BOOKING"]
    lowered = reply.lower()
    assert "khong the dat lich" in lowered or "không thể đặt lịch" in reply


# ---------------------------------------------------------------------------
# 4. Defense-in-depth: _enforce_no_vendor_disclosure
# ---------------------------------------------------------------------------


def _result(response: str, status: RunStatus = RunStatus.COMPLETED) -> RunResult:
    return RunResult(status, response, (), RunMetrics())


@pytest.mark.parametrize("phrase", ["Mình là ChatGPT", "do OpenAI tạo ra", "I'm a GPT model", "gpt-4"])
def test_vendor_mention_is_replaced(phrase):
    original = _result(f"Some preamble. {phrase}. Some trailer.")
    corrected = _enforce_no_vendor_disclosure(original)
    assert corrected.response == _OUT_OF_SCOPE_REPLIES["IDENTITY"]
    assert corrected.status == original.status


def test_no_vendor_mention_passes_through_untouched():
    original = _result("Paracetamol dung de ha sot, giam dau.")
    assert _enforce_no_vendor_disclosure(original) is original


def test_non_completed_status_is_never_touched():
    original = _result("Yeu cau can duoc bac si xem xet.", status=RunStatus.HANDOFF_REQUIRED)
    assert _enforce_no_vendor_disclosure(original) is original


def test_vendor_backstop_reached_via_full_orchestrator_for_a_normal_intent():
    # Simulates a message that doesn't match the out-of-scope detector at
    # all but where the model still discloses the vendor mid-answer. A real
    # tool call is included so BUILD-24F's grounding backstop is a no-op
    # here and this isolates the vendor-leak backstop specifically.
    from backend.agents.v2.model_gateway import ModelSynthesis, ToolCall

    plan = ModelPlan(tool_calls=(ToolCall(name="search_drug", arguments={"query": "paracetamol", "limit": 5}),), response="planning")
    synthesis = ModelSynthesis(response="Theo ChatGPT cua OpenAI, paracetamol dung de ha sot.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))

    result = orchestrator.run(_request("Paracetamol la thuoc gi"), tools=_tools())

    assert result.intent is OrchestrationIntent.DRUG_INFORMATION
    assert result.status is RunStatus.COMPLETED
    assert result.response == _OUT_OF_SCOPE_REPLIES["IDENTITY"]
    assert "chatgpt" not in result.response.lower()
    assert "openai" not in result.response.lower()
