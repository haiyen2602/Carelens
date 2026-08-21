"""BUILD-24L (found during Phase 2's real golden retest, report 44): four
small, non-critical FAIL_DEFECT fixes, none touching Safety/Auth/Handoff/
Vinmec/checkpoint code.

- golden query_id 74 ("hôm nay thời tiết thế nào" -- what's the weather
  today): misrouted to TODAY_DOSES by the bare "hôm nay" keyword. Fixed by
  checking `_detect_out_of_scope_category` *before* `_TODAY_KEYWORDS` in
  `classify_intent`, and adding a few unambiguous non-medical topic markers
  (weather/sports/news) to `_GENERAL_OFF_TOPIC_KEYWORDS`.
- golden query_id 5 (Vitamin B1 indication) and query_id 8 ("vitamin b1",
  ambiguous): the Main Model answered an indication question from outside
  knowledge instead of calling `get_drug_info` (which has real `cong_dung`
  RAG data for this exact drug -- confirmed by querying the corpus
  directly), and picked one SKU silently instead of asking for
  clarification when `search_drug` returned more than one plausible match.
  Fixed with two new instructions in `plan_read_only`'s prompt
  (`backend/agents/v2/model_gateway.py`). Unlike the router fix above,
  this is a prompt-level guidance fix, not a hard deterministic guarantee
  -- consistent with BUILD-24B's own established distinction between
  prompt instructions (layer 1/2) and deterministic backstops (layer 3);
  a partially-ungrounded claim riding alongside genuinely grounded tool
  fields has no clean deterministic signal to backstop against the way a
  literal "vinmec" mention does. Re-verified against the real model
  (report 44's follow-up) rather than left as a unit-test-only claim.
- golden query_id 45 ("tôi uống thuốc huyết áp rồi..."): reply opened
  "Mình đã ghi nhận..." ("I've recorded...") for the patient's own
  unverified claim -- Agent V2 is read-only and never persists any input.
  Fixed with a new instruction in `synthesize_read_only`'s prompt. Same
  prompt-level-guidance caveat as above.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.agents.v2.model_gateway import OpenAIModelGateway, SynthesisEvidence, build_model_workloads
from backend.agents.v2.orchestrator import OrchestrationIntent, classify_intent


def _settings(**overrides):
    values = {
        "openai_api_key": "backend-only-test-key",
        "openai_router_api_key": "",
        "openai_main_api_key": "",
        "openai_fallback_api_key": "",
        "openai_embedding_api_key": "",
        "openai_judge_api_key": "",
        "agent_router_model": "gpt-5.4-nano",
        "agent_main_model": "gpt-5.4-mini",
        "agent_fallback_model": "gpt-5.4",
        "agent_embedding_model": "text-embedding-3-small",
        "rag_judge_model": "gpt-4o",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Responses:
    def __init__(self, response: dict):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _Client:
    def __init__(self, response: dict):
        self.responses = _Responses(response)


# ---------------------------------------------------------------------------
# 1. Router: golden query_id 74 -- "hôm nay thời tiết thế nào"
# ---------------------------------------------------------------------------


def test_golden_query_74_weather_question_is_no_longer_misrouted():
    decision = classify_intent("hôm nay thời tiết thế nào")
    assert decision.intent is OrchestrationIntent.OUT_OF_SCOPE_REQUEST
    assert decision.intent is not OrchestrationIntent.TODAY_DOSES


def test_new_off_topic_markers_detected():
    for query in ("thời tiết hôm nay thế nào", "kết quả bóng đá tối qua", "có tin tức gì mới không"):
        assert classify_intent(query).intent is OrchestrationIntent.OUT_OF_SCOPE_REQUEST


def test_genuine_today_doses_queries_still_route_correctly_after_reordering():
    # Regression: moving the out-of-scope check earlier must not touch any
    # legitimate schedule query (already covered in depth by
    # test_agent_v2_router_remediation.py; re-asserted here as a direct
    # sanity check on the specific reordering this build made).
    for query in ("hôm nay tôi uống thuốc gì", "buổi sáng tôi cần uống thuốc gì", "buổi tối nay uống gì"):
        assert classify_intent(query).intent is OrchestrationIntent.TODAY_DOSES


def test_acute_danger_and_doctor_review_still_win_over_out_of_scope_ordering():
    # Priority order sanity: acute-danger/doctor-review/missed/delayed-dose
    # checks all still run before the (now earlier) out-of-scope check.
    from backend.agents.v2.orchestrator import OrchestrationIntent as OI

    assert classify_intent("tôi vừa uống một lúc 15 viên panadol").intent is OI.ACUTE_DANGER_ESCALATION
    assert classify_intent("Toi muon doi lieu thuoc sang 2 vien").intent is OI.DOCTOR_REVIEW


# ---------------------------------------------------------------------------
# 2. plan_read_only prompt: get_drug_info-for-indication + disambiguation
# ---------------------------------------------------------------------------


def test_plan_prompt_instructs_get_drug_info_for_indication_side_effect_usage_storage():
    client = _Client({"output_text": "planning", "usage": {"input_tokens": 1, "output_tokens": 1}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)

    gateway.plan_read_only(message="vitamin b1 dùng để điều trị bệnh gì", actor_role="patient")

    prompt = client.responses.calls[0]["input"]
    assert "get_drug_info" in prompt
    assert "indication" in prompt.lower() or "cong dung" in prompt.lower()


def test_plan_prompt_instructs_asking_for_clarification_on_ambiguous_matches():
    client = _Client({"output_text": "planning", "usage": {"input_tokens": 1, "output_tokens": 1}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)

    gateway.plan_read_only(message="vitamin b1", actor_role="patient")

    prompt = client.responses.calls[0]["input"]
    assert "ask" in prompt.lower() and "candidate" in prompt.lower()


# ---------------------------------------------------------------------------
# 3. synthesize_read_only prompt: never imply the patient's claim was recorded
# ---------------------------------------------------------------------------


def test_synthesis_prompt_forbids_implying_the_patients_claim_was_recorded():
    client = _Client(
        {"output_text": "Da ghi nhan.", "usage": {"input_tokens": 1, "output_tokens": 1}, "_request_id": "req_1"}
    )
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    evidence = (SynthesisEvidence(tool_name="get_active_prescriptions", provenance="tool:get_active_prescriptions", data={"items": []}),)

    gateway.synthesize_read_only(message="toi uong thuoc huyet ap roi", actor_role="patient", evidence=evidence)

    prompt = client.responses.calls[0]["input"]
    assert "recorded" in prompt.lower() or "logged" in prompt.lower()
    assert "read-only" in prompt.lower()
