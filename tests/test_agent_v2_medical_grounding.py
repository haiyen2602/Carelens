"""BUILD-24F (V2 RC hardening, Phase 1 item 2): medical-grounding enforcement.

Found in BUILD-24C's golden set (report 35, section 4, query_id 21):
"thuốc omeprazole uống trước hay sau ăn" (does omeprazole get taken before
or after food) was answered confidently and plausibly -- but from the
model's own general training knowledge (`tools_used: []`, `citations: []`,
no `search_drug` call at all) rather than checked against this system's own
corpus and declined if absent, as the query's own expected criteria
("Nếu thuốc/hoạt chất không có trong corpus -> từ chối rõ, không đoán")
requires.

Fix: ``_enforce_medical_grounding`` in backend/agents/v2/orchestrator.py --
a deterministic backstop, applied after the Vinmec-provenance backstop,
that replaces the final reply with a fixed, honest decline whenever a
grounding-required intent (DRUG_INFORMATION, PRESCRIPTION_INFORMATION,
DOSE_STATUS, GENERAL_MEDICAL_INFORMATION, UNKNOWN_OR_AMBIGUOUS) produced
zero tool calls AND zero retrieval/Vinmec citations. Structurally the same
philosophy as the Vinmec backstop: a fact the orchestrator itself already
knows (how much evidence was actually gathered) is a more reliable signal
than trusting the model's free text.

BUILD-28: TODAY_DOSES/UPCOMING_DOSES/MEDICATION_HISTORY are no longer in
the grounding-required set -- all three now bypass the Main Model entirely
(see ``AgentOrchestrator._schedule_reply``), so an "ungrounded schedule
answer from the model" is no longer a possible failure mode for them at
all, not merely one caught after the fact by this backstop.
"""

from __future__ import annotations

import pytest

from backend.agents.v2.answerability import AnswerabilityOutcome, AnswerabilityReasonCode
from backend.agents.v2.model_gateway import ModelPlan, ModelSynthesis, ToolCall
from backend.agents.v2.orchestrator import (
    _NEED_DOCTOR_REPLY,
    _NEED_MORE_INFO_REPLIES,
    _UNGROUNDED_ANSWER_DECLINE_REPLY,
    _UNGROUNDED_GENERAL_MEDICAL_DECLINE_REPLY,
    Citation,
    OrchestrationIntent,
    _enforce_medical_grounding,
)
from backend.agents.v2.retrieval import RetrievalConfig, RetrievalGateway
from backend.agents.v2.runtime import RunMetrics, RunResult, RunStatus
from backend.services.agent_retrieval import DomainRetrievalResult, RetrievedKnowledgeDocument
from tests.test_agent_v2_orchestrator import (
    _orchestrator,
    _request,
    _RetrievalDomain,
    _SpyModelGateway,
    _tools,
)

_NO_CITATIONS: tuple[Citation, ...] = ()
_ONE_CITATION = (Citation(title="drug-1", source="cong_dung — Paracetamol", url=None),)


def _result(response: str, status: RunStatus = RunStatus.COMPLETED, tool_results: tuple = ()) -> RunResult:
    return RunResult(status, response, tool_results, RunMetrics())


# ---------------------------------------------------------------------------
# 1. Unit tests: _enforce_medical_grounding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent",
    [
        OrchestrationIntent.DRUG_INFORMATION,
        OrchestrationIntent.PRESCRIPTION_INFORMATION,
        OrchestrationIntent.DOSE_STATUS,
    ],
)
def test_grounding_required_drug_shaped_intent_with_zero_evidence_is_declined(intent):
    original = _result("Thuoc nay uong truoc an, tot nhat truoc bua an 30-60 phut.")
    corrected = _enforce_medical_grounding(original, intent=intent, citations=_NO_CITATIONS)
    assert corrected.response == _UNGROUNDED_ANSWER_DECLINE_REPLY
    assert corrected.status == original.status  # status untouched, only text corrected


@pytest.mark.parametrize(
    "intent",
    [OrchestrationIntent.GENERAL_MEDICAL_INFORMATION, OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS],
)
def test_grounding_required_general_medical_intent_with_zero_evidence_is_declined(intent):
    """BUILD-38 Cluster B: a non-drug-shaped grounding-required intent gets
    its own decline text -- not the drug-specific one, which asks for a
    'specific drug name' that doesn't make sense for e.g. a disease/symptom
    question. Confirmed as a real production Judge V2 quality defect
    (low `relevance`, flags `irrelevant_clarification_request`/
    `misaligned_followup_prompt`) before this fix -- see BUILD-38 report."""

    original = _result("Thuoc nay uong truoc an, tot nhat truoc bua an 30-60 phut.")
    corrected = _enforce_medical_grounding(original, intent=intent, citations=_NO_CITATIONS)
    assert corrected.response == _UNGROUNDED_GENERAL_MEDICAL_DECLINE_REPLY
    assert corrected.status == original.status
    # the drug-specific clarification ask must not leak into the general-
    # medical decline -- this is the exact mismatch the fix addresses.
    assert "tên thuốc" not in corrected.response


@pytest.mark.parametrize(
    "intent",
    [
        OrchestrationIntent.GENERAL_CONVERSATION,
        OrchestrationIntent.VINMEC_WEB_INFORMATION,
        OrchestrationIntent.DOCTOR_REVIEW,
        OrchestrationIntent.ACUTE_DANGER_ESCALATION,
        OrchestrationIntent.MISSED_DOSE,
        OrchestrationIntent.DELAYED_DOSE,
        # BUILD-28: these three never reach this backstop at all any more
        # (see AgentOrchestrator._schedule_reply) -- kept here as a direct,
        # permanent check that the unit-level function itself also leaves
        # them untouched, not just that ``run()`` happens to bypass it.
        OrchestrationIntent.TODAY_DOSES,
        OrchestrationIntent.UPCOMING_DOSES,
        OrchestrationIntent.MEDICATION_HISTORY,
    ],
)
def test_non_grounding_required_intent_is_never_touched_even_with_zero_evidence(intent):
    original = _result("Bat ky noi dung nao, khong co bang chung.")
    assert _enforce_medical_grounding(original, intent=intent, citations=_NO_CITATIONS) is original


def test_a_real_tool_call_is_sufficient_evidence():
    from backend.agents.v2.tools import ToolResult

    original = _result(
        "Paracetamol dung de ha sot.",
        tool_results=(ToolResult(name="search_drug", data={"items": []}),),
    )
    assert _enforce_medical_grounding(original, intent=OrchestrationIntent.DRUG_INFORMATION, citations=_NO_CITATIONS) is original


def test_a_real_citation_is_sufficient_evidence():
    original = _result("Tac dung phu thuong gap la buon non.")
    assert _enforce_medical_grounding(original, intent=OrchestrationIntent.GENERAL_MEDICAL_INFORMATION, citations=_ONE_CITATION) is original


@pytest.mark.parametrize(
    "status",
    [
        RunStatus.SAFETY_BLOCKED,
        RunStatus.HANDOFF_REQUIRED,
        RunStatus.HANDOFF_CREATED,
        RunStatus.FAILED,
        RunStatus.TIMEOUT,
        RunStatus.BUDGET_EXCEEDED,
        RunStatus.CANCELLED,
    ],
)
def test_non_completed_status_is_never_touched(status):
    original = _result("Fixed terminal text.", status=status)
    assert _enforce_medical_grounding(original, intent=OrchestrationIntent.DRUG_INFORMATION, citations=_NO_CITATIONS) is original


# ---------------------------------------------------------------------------
# 2. Full orchestrator integration -- exact reproduction of golden query_id 21
# ---------------------------------------------------------------------------


def test_golden_query_21_omeprazole_ungrounded_answer_is_now_declined():
    # Exactly the live-observed defect: the model answers a real, plausible
    # drug-timing fact from its own general knowledge, calling no tool at
    # all (plan.response alone becomes the final reply per BUILD-19B, since
    # there are no tool_calls to synthesize from).
    #
    # BUILD-42: through the FULL orchestrator.run() pipeline (unlike the
    # _enforce_medical_grounding unit tests below, which call that function
    # directly and are unaffected -- it is unchanged), a DRUG_INFORMATION-
    # shaped grounding failure's FIRST occurrence in a conversation is no
    # longer this fixed decline -- it is now a NEED_MORE_INFO clarification
    # ask via the Answerability Gate (see answerability.py). The fixed
    # decline text (_UNGROUNDED_ANSWER_DECLINE_REPLY) itself still exists
    # and is still what _enforce_medical_grounding computes internally, but
    # the orchestrator now overrides it for this specific intent group --
    # see test_golden_query_21_second_grounding_failure_escalates_to_doctor
    # below for what happens once the clarification attempt is exhausted.
    plan = ModelPlan(response="Omeprazole thuong uong truoc an, tot nhat truoc bua an 30-60 phut.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan))

    result = orchestrator.run(_request("thuoc omeprazole uong truoc hay sau an"), tools=_tools())

    assert result.intent is OrchestrationIntent.DRUG_INFORMATION
    assert result.status is RunStatus.COMPLETED  # still answers -- just not with the fabricated fact
    assert result.response == _NEED_MORE_INFO_REPLIES[AnswerabilityReasonCode.MISSING_REQUIRED_CONTEXT]
    assert result.citations == ()
    assert result.tool_results == ()
    assert result.answerability_decision is not None
    assert result.answerability_decision.outcome is AnswerabilityOutcome.NEED_MORE_INFO
    assert result.answerability_decision.attempt_count == 1


def test_golden_query_21_second_grounding_failure_escalates_to_doctor():
    """BUILD-42: the SAME unresolved drug-information grounding failure, now
    on a THIRD turn (``answerability_attempt_count=2``, as the API boundary
    would thread in from durable ConversationState after two prior
    NEED_MORE_INFO turns -- spec's own SS8 example: "turn1 -> NEED_MORE_INFO
    attempt=1, turn2 -> NEED_MORE_INFO attempt=2, turn3 -> NEED_DOCTOR")
    exhausts the bounded clarification budget
    (answerability.MAX_CLARIFICATION_ATTEMPTS=2) and hands off instead of
    asking a third time."""
    plan = ModelPlan(response="Omeprazole thuong uong truoc an, tot nhat truoc bua an 30-60 phut.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan))

    result = orchestrator.run(
        _request("thuoc omeprazole uong truoc hay sau an", answerability_attempt_count=2), tools=_tools()
    )

    assert result.intent is OrchestrationIntent.DRUG_INFORMATION
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.response == _NEED_DOCTOR_REPLY
    assert result.handoff_result is not None
    assert result.answerability_decision is not None
    assert result.answerability_decision.outcome is AnswerabilityOutcome.NEED_DOCTOR
    assert result.answerability_decision.reason_code is AnswerabilityReasonCode.MAX_ATTEMPTS_REACHED
    assert result.safety_decision is None  # never routed through the Safety Domain -- see SS17


def test_grounded_drug_information_query_is_unaffected():
    plan = ModelPlan(
        tool_calls=(ToolCall(name="search_drug", arguments={"query": "paracetamol", "limit": 5}),),
        response="planning",
    )
    synthesis = ModelSynthesis(response="Paracetamol la thuoc giam dau, ha sot dang vien nen 500mg.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))

    result = orchestrator.run(_request("Paracetamol la thuoc gi"), tools=_tools())

    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response  # untouched -- a real tool call backs this
    assert [t.name for t in result.tool_results] == ["search_drug"]


def test_grounded_rag_query_is_unaffected():
    retrieval_gateway = RetrievalGateway(
        _EmbeddingStub(),
        _RetrievalDomain(
            DomainRetrievalResult(
                documents=(
                    RetrievedKnowledgeDocument(
                        source_id="chunk-1", drug_id="drug-1", drug_name="Paracetamol", field_group="cong_dung",
                        content="Ha sot, giam dau.", source="cong_dung", vector_score=0.9, lexical_score=0.5, relevance=0.8, rank=1,
                    ),
                ),
                no_source_found=False,
            )
        ),
        config=RetrievalConfig(embedding_model="text-embedding-3-small", top_k=5, token_budget=2000),
    )
    plan = ModelPlan(response="Paracetamol dung de ha sot, theo [retrieval evidence]1.")
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(plan), retrieval_gateway=retrieval_gateway)

    result = orchestrator.run(_request("Tac dung cua thuoc giam dau la gi"), tools=_tools())

    assert result.intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION
    assert result.status is RunStatus.COMPLETED
    assert result.response == plan.response  # untouched -- RAG evidence backs this
    assert len(result.citations) == 1


def test_today_doses_never_reaches_the_model_so_an_ungrounded_narration_is_impossible():
    # BUILD-28: a schedule claim narrated from thin air (BUILD-24F's original
    # concern for this intent) is no longer merely caught after the fact --
    # TODAY_DOSES bypasses the Main Model entirely (see
    # AgentOrchestrator._schedule_reply), so this configured plan is never
    # even consulted; the composer's own real tool evidence is what answers.
    plan = ModelPlan(response="Hom nay ban co 2 lieu can uong: 8h sang va 8h toi.")
    gateway = _SpyModelGateway(plan)
    orchestrator, _ = _orchestrator(model_gateway=gateway)

    result = orchestrator.run(_request("Hom nay toi can uong thuoc gi"), tools=_tools())

    assert result.intent is OrchestrationIntent.TODAY_DOSES
    assert result.status is RunStatus.COMPLETED
    assert result.response != _UNGROUNDED_ANSWER_DECLINE_REPLY
    assert gateway.calls == [] and gateway.synthesis_calls == []
    assert [t.name for t in result.tool_results] == ["get_doses_for_range"]


def test_general_conversation_is_unaffected_by_grounding_enforcement():
    plan = ModelPlan(response="Chao ban! Minh co the giup gi cho ban hom nay?")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan))

    result = orchestrator.run(_request("xin chao"), tools=_tools())

    assert result.intent is OrchestrationIntent.GENERAL_CONVERSATION
    assert result.status is RunStatus.COMPLETED
    assert result.response == plan.response  # small talk never requires grounding


class _EmbeddingStub:
    def embed_query(self, *, text: str):
        from backend.agents.v2.model_gateway import EmbeddingResult

        return EmbeddingResult(model="text-embedding-3-small", vector=(0.1, 0.2))
