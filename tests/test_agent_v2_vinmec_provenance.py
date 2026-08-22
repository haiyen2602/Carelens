"""BUILD-24B/24D: Vinmec provenance honesty.

Found live during BUILD-24's 5% canary (report 32-build-24): a message
containing "Vinmec" would get an answer synthesized from an unrelated
internal tool (search_drug, provenance "canonical-drug-v2:catalog") while
the model's own reply text still claimed the content came "from Vinmec" --
reproduced twice, traced to exact log lines. The structured ``citations``
array stayed correctly empty both times (no fabricated citation *object*),
but the free-text claim was still false.

Three independent layers close this, tested here:
  1. ``_NO_VINMEC_EVIDENCE_NOTE`` -- makes the negative result explicit to
     the model *before* it answers, whenever VINMEC_WEB_INFORMATION intent
     gathered zero real Vinmec evidence.
  2. The general provenance rule added to
     ``OpenAIModelGateway.synthesize_read_only``'s prompt (not
     independently testable without a real OpenAI call; covered by
     inspection, see model_gateway.py).
  3. ``_enforce_vinmec_provenance`` -- a deterministic, code-level backstop
     that is the actual enforced guarantee: if the model's final reply
     text mentions "vinmec" but no real ``source == "vinmec-web"`` citation
     exists for this run, the false claim is corrected. This is what makes
     the property "tuyet doi" (absolute) rather than merely "the prompt
     asked nicely."

BUILD-24D (report 35, section 4.1): BUILD-24B's layer 3 above was found
*over*-triggering in the 101-query golden set -- it replaced the *entire*
reply with a "no Vinmec result" message even for the 12 queries below that
never mentioned Vinmec at all (a bare drug name like "vizicin", a storage
question, a schedule question), discarding a real, correctly-sourced
internal/RAG answer for a confusing non-sequitur. The fix makes the
correction strategy intent-aware via ``vinmec_required`` (true only for
``OrchestrationIntent.VINMEC_WEB_INFORMATION``, i.e. ``decision.
use_vinmec_web``):
  - ``vinmec_required=True`` (the user did ask for Vinmec): full-reply
    replacement, unchanged from BUILD-24B.
  - ``vinmec_required=False`` (the user never asked for Vinmec): word-level
    correction only -- the false "Vinmec" mention is replaced with
    source-neutral wording, the rest of the factual answer is preserved,
    and the full "no Vinmec result" fallback is never shown.
"""

from __future__ import annotations

import pytest

from backend.agents.v2.model_gateway import ModelPlan, ModelSynthesis, ToolCall
from backend.agents.v2.orchestrator import (
    Citation,
    OrchestrationIntent,
    _enforce_vinmec_provenance,
    _strip_false_vinmec_claim,
    _NO_VINMEC_EVIDENCE_REPLY,
)
from backend.agents.v2.retrieval import RetrievalConfig, RetrievalGateway
from backend.agents.v2.runtime import RunMetrics, RunResult, RunStatus
from backend.agents.v2.vinmec_web import VinmecWebConfig, VinmecWebSearchGateway

from tests.test_agent_v2_orchestrator import (
    _DomainTools,
    _RetrievalDomain,
    _SpyModelGateway,
    _VinmecDomain,
    _orchestrator,
    _request,
    _tools,
)
from backend.services.agent_retrieval import DomainRetrievalResult, RetrievedKnowledgeDocument
from backend.services.vinmec_web_search import VinmecSourceDocument

_NO_CITATIONS: tuple[Citation, ...] = ()
_REAL_VINMEC_CITATION = (Citation(title="Benh tieu duong", source="vinmec-web", url="https://vinmec.example/x"),)
_RAG_CITATION = (Citation(title="drug-1", source="cong_dung — Paracetamol", url=None),)


def _result(response: str, status: RunStatus = RunStatus.COMPLETED) -> RunResult:
    return RunResult(status, response, (), RunMetrics())


# ---------------------------------------------------------------------------
# Unit tests: _enforce_vinmec_provenance (the actual enforced guarantee)
# ---------------------------------------------------------------------------


def test_no_vinmec_mention_passes_through_untouched():
    original = _result("Paracetamol dung de ha sot, giam dau.")
    assert _enforce_vinmec_provenance(original, _NO_CITATIONS, vinmec_required=True) is original
    assert _enforce_vinmec_provenance(original, _NO_CITATIONS, vinmec_required=False) is original


def test_required_vinmec_mention_without_a_real_citation_is_fully_replaced():
    # vinmec_required=True: the user did ask for Vinmec -- an honest "not
    # found" for the whole reply is correct and expected (BUILD-24B, unchanged).
    original = _result("Theo Vinmec, thuoc nay la Paracetamol dang vien nen 500mg.")
    corrected = _enforce_vinmec_provenance(original, _NO_CITATIONS, vinmec_required=True)
    assert corrected.response == _NO_VINMEC_EVIDENCE_REPLY
    assert corrected.status == original.status  # status untouched, only text corrected


def test_required_vinmec_mention_without_a_real_citation_is_replaced_even_with_unrelated_rag_citations():
    # Having SOME citation isn't enough -- it must specifically be vinmec-web.
    original = _result("Theo Vinmec, day la thong tin ve thuoc.")
    corrected = _enforce_vinmec_provenance(original, _RAG_CITATION, vinmec_required=True)
    assert corrected.response == _NO_VINMEC_EVIDENCE_REPLY


def test_vinmec_mention_with_a_real_vinmec_citation_is_left_alone_regardless_of_requirement():
    original = _result("Theo Vinmec, benh tieu duong la benh roi loan chuyen hoa.")
    assert _enforce_vinmec_provenance(original, _REAL_VINMEC_CITATION, vinmec_required=True) is original
    assert _enforce_vinmec_provenance(original, _REAL_VINMEC_CITATION, vinmec_required=False) is original


@pytest.mark.parametrize("word", ["Vinmec", "VINMEC", "vinmec", "Vinmec.vn", "vinmec's"])
def test_case_insensitive_and_matches_as_a_substring_when_required(word):
    original = _result(f"Nguon: {word}")
    corrected = _enforce_vinmec_provenance(original, _NO_CITATIONS, vinmec_required=True)
    assert corrected.response == _NO_VINMEC_EVIDENCE_REPLY


def test_fixed_terminal_messages_never_contain_a_vinmec_mention_so_are_never_touched():
    # Sanity check on the messages runtime.py actually uses for these statuses.
    for status, text in (
        (RunStatus.HANDOFF_REQUIRED, "Yeu cau can duoc bac si xem xet."),
        (RunStatus.HANDOFF_CREATED, "Yeu cau da duoc ghi nhan de bac si xem xet."),
        (RunStatus.CANCELLED, "Agent run da bi huy."),
    ):
        original = _result(text, status=status)
        assert _enforce_vinmec_provenance(original, _NO_CITATIONS, vinmec_required=True) is original
        assert _enforce_vinmec_provenance(original, _NO_CITATIONS, vinmec_required=False) is original


# ---------------------------------------------------------------------------
# BUILD-24D: vinmec_required=False -- word-level correction, not full
# replacement. This is the fix for report 35 section 4.1's over-triggering
# defect (12 golden-set cases: query_id 6, 7, 8, 11, 16, 18, 19, 22, 30, 33,
# 66, 91 -- none of those queries ever mentioned Vinmec).
# ---------------------------------------------------------------------------


def test_not_required_false_claim_is_corrected_in_place_not_replaced():
    original = _result("Theo Vinmec, thuoc nay la Paracetamol dang vien nen 500mg.")
    corrected = _enforce_vinmec_provenance(original, _NO_CITATIONS, vinmec_required=False)
    assert corrected.response != _NO_VINMEC_EVIDENCE_REPLY
    assert "vinmec" not in corrected.response.lower()
    # The rest of the factual answer survives untouched.
    assert "Paracetamol" in corrected.response
    assert "500mg" in corrected.response
    assert corrected.status == original.status


def test_not_required_false_claim_correction_is_never_the_full_vinmec_fallback_text():
    # The absolute guarantee from requirement 2: a query that never asked
    # for Vinmec must never see the "khong tim thay ket qua tra cuu Vinmec"
    # non-sequitur, no matter what the model said.
    for text in (
        "Vinmec cho biet thuoc nay dung de ha sot.",
        "Theo trang Vinmec, ban nen bao quan noi kho thoang.",
        "Nguon: Vinmec.vn",
    ):
        corrected = _enforce_vinmec_provenance(_result(text), _NO_CITATIONS, vinmec_required=False)
        assert corrected.response != _NO_VINMEC_EVIDENCE_REPLY
        assert "vinmec" not in corrected.response.lower()


def test_not_required_rag_evidence_answer_is_preserved():
    original = _result("Theo Vinmec, tac dung phu thuong gap la buon non va dau dau.")
    corrected = _enforce_vinmec_provenance(original, _RAG_CITATION, vinmec_required=False)
    assert corrected.response != _NO_VINMEC_EVIDENCE_REPLY
    assert "buon non" in corrected.response and "dau dau" in corrected.response
    assert corrected.status == original.status


def test_strip_false_vinmec_claim_preserves_surrounding_text_and_capitalizes_sentence_starts():
    # BUILD-24K: the neutral phrase now carries its own correct Vietnamese
    # diacritics (found jarring/mixed-script otherwise in Phase 2's real
    # golden retest, report 43) -- "Dữ liệu nội bộ đã xác minh", not the
    # bare-ASCII "Du lieu noi bo da xac minh" BUILD-24D originally shipped.
    assert _strip_false_vinmec_claim("Vinmec cho biet day la thuoc giam dau.").startswith("Dữ liệu nội bộ đã xác minh")
    mid = _strip_false_vinmec_claim("Thuoc nay, theo Vinmec, dung de ha sot.")
    assert "vinmec" not in mid.lower()
    assert "Thuoc nay, theo" in mid and "dung de ha sot." in mid
    assert "dữ liệu nội bộ đã xác minh" in mid


# ---------------------------------------------------------------------------
# Regression scenario 1: Vinmec query + real Vinmec evidence -> may claim
# Vinmec + citation. (Already covered by
# test_agent_v2_orchestrator.py::test_vinmec_web_query_preserves_provenance_and_citation;
# re-asserted here from this file's own angle for completeness.)
# ---------------------------------------------------------------------------


def test_scenario_1_real_vinmec_evidence_allows_the_vinmec_claim():
    source = VinmecSourceDocument(
        title="Benh tieu duong la gi", url="https://www.vinmec.com/vie/bai-viet/benh-tieu-duong",
        excerpt="Thong tin cong khai.", content="Noi dung chi tiet.",
    )
    vinmec_gateway = VinmecWebSearchGateway(
        _VinmecDomain((source,)), config=VinmecWebConfig(enabled=True, max_calls=2, max_results=3, timeout_seconds=2.0, token_budget=2000)
    )
    plan = ModelPlan(response="Theo Vinmec, benh tieu duong la benh roi loan chuyen hoa.")
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(plan), vinmec_gateway=vinmec_gateway)

    result = orchestrator.run(_request("Tim tren Vinmec thong tin ve benh tieu duong"), tools=_tools())

    assert result.status is RunStatus.COMPLETED
    assert "vinmec" in result.response.lower()
    assert result.citations[0].source == "vinmec-web"


# ---------------------------------------------------------------------------
# Regression scenario 2: Vinmec query + only canonical drug evidence ->
# must NOT claim Vinmec, even when the model (here, simulated via a spy that
# always returns the same misbehaving text) tries to.
# ---------------------------------------------------------------------------


def test_scenario_2_canonical_only_evidence_never_lets_the_vinmec_claim_through():
    vinmec_gateway = VinmecWebSearchGateway(
        _VinmecDomain(()), config=VinmecWebConfig(enabled=True, max_calls=2, max_results=3, timeout_seconds=2.0, token_budget=2000)
    )
    # Simulates exactly the live-observed misbehavior: the model calls the
    # internal catalog tool but still narrates the answer as "from Vinmec".
    plan = ModelPlan(
        tool_calls=(ToolCall(name="search_drug", arguments={"query": "paracetamol", "limit": 5}),),
        response="planning",
    )
    synthesis = ModelSynthesis(response="Theo Vinmec, thuoc nay la Paracetamol dang vien nen 500mg.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis), vinmec_gateway=vinmec_gateway)

    result = orchestrator.run(_request("Vinmec co thong tin gi ve thuoc paracetamol khong"), tools=_tools())

    assert result.status is RunStatus.COMPLETED
    assert result.response == _NO_VINMEC_EVIDENCE_REPLY
    assert "vinmec" not in result.response.lower() or result.response == _NO_VINMEC_EVIDENCE_REPLY
    assert result.citations == ()  # no fabricated citation object either
    # The model was told explicitly, before it answered, that there was no
    # real Vinmec evidence -- proves layer 1 (the proactive note) fired.
    assert "không tìm thấy kết quả tra cứu Vinmec Web" in gateway.synthesis_calls[-1]["message"] or any(
        "không tìm thấy kết quả tra cứu Vinmec Web" in c["message"] for c in gateway.calls
    )


# ---------------------------------------------------------------------------
# Regression scenario 3: Vinmec query + zero evidence of any kind -> honest
# no-Vinmec-evidence response.
# ---------------------------------------------------------------------------


def test_scenario_3_zero_evidence_gets_the_honest_fallback():
    vinmec_gateway = VinmecWebSearchGateway(
        _VinmecDomain(()), config=VinmecWebConfig(enabled=True, max_calls=2, max_results=3, timeout_seconds=2.0, token_budget=2000)
    )
    # No tool calls at all this time -- the model just free-associates from
    # the user's own wording (the worst case: nothing grounding it).
    plan = ModelPlan(response="planning")
    synthesis = ModelSynthesis(response="Xin loi, minh khong the tim thong tin tu Vinmec luc nay.")
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis), vinmec_gateway=vinmec_gateway)

    result = orchestrator.run(_request("Vinmec noi gi ve thuoc nay"), tools=_tools())

    assert result.status is RunStatus.COMPLETED
    assert result.citations == ()
    # Either the model's own honest text passes through unmodified (it
    # already said the right thing), or the backstop's fixed text does --
    # both are an honest "no Vinmec evidence" outcome, never a claim.
    lowered = result.response.lower()
    assert "vinmec" not in lowered or "khong" in lowered or "khong the" in lowered


# ---------------------------------------------------------------------------
# Regression scenario 4: normal search_drug (unrelated to Vinmec) -> correct
# canonical provenance, completely unaffected by this build's change.
# ---------------------------------------------------------------------------


def test_scenario_4_normal_drug_information_query_is_unaffected():
    plan = ModelPlan(
        tool_calls=(ToolCall(name="search_drug", arguments={"query": "paracetamol", "limit": 5}),),
        response="planning",
    )
    synthesis = ModelSynthesis(response="Paracetamol la thuoc giam dau, ha sot dang vien nen 500mg.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))

    result = orchestrator.run(_request("Paracetamol la thuoc gi"), tools=_tools())

    assert result.intent is OrchestrationIntent.DRUG_INFORMATION
    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response  # untouched -- no "vinmec" mention, guard is a no-op
    assert result.citations == ()


# ---------------------------------------------------------------------------
# Regression scenario 5: RAG evidence must not be mislabeled as Vinmec
# either -- the backstop still catches this regardless of intent, but
# (BUILD-24D) since GENERAL_MEDICAL_INFORMATION never required Vinmec, the
# correction now preserves the real RAG-sourced answer instead of discarding
# it for the full "no Vinmec result" fallback -- see report 35, section 4.1.
# ---------------------------------------------------------------------------


def test_scenario_5_rag_evidence_mislabeled_as_vinmec_is_corrected_not_discarded():
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
    # RAG evidence is embedded directly into the augmented message text (see
    # _compose_message) -- no tool call is needed for the model to see it, so
    # (per BUILD-19B) an empty ``tool_calls`` plan response IS the final
    # reply; synthesize_read_only is never reached. Simulated misbehavior:
    # the model mislabels that evidence as Vinmec right here.
    plan = ModelPlan(response="Theo Vinmec, paracetamol dung de ha sot.")
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(plan), retrieval_gateway=retrieval_gateway)

    result = orchestrator.run(_request("Tac dung phu cua thuoc giam dau la gi"), tools=_tools())

    assert result.intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION
    assert result.status is RunStatus.COMPLETED
    # BUILD-24D: never required Vinmec (not VINMEC_WEB_INFORMATION intent) --
    # the false claim is corrected, the real RAG-sourced answer is kept.
    assert result.response != _NO_VINMEC_EVIDENCE_REPLY
    assert "vinmec" not in result.response.lower()
    assert "paracetamol" in result.response.lower()
    assert "ha sot" in result.response.lower()
    assert all(c.source != "vinmec-web" for c in result.citations)


# ---------------------------------------------------------------------------
# Regression scenario 6 (BUILD-24D, report 35 section 4.1): the exact golden-
# set failure shape -- a bare drug-name query (no "vinmec" anywhere in the
# user's own message, e.g. golden query_id 7 "vizicin") where the model
# calls the internal canonical catalog tool but still mislabels the answer
# as Vinmec-sourced. Must keep the real catalog answer, never the fallback.
# ---------------------------------------------------------------------------


def test_scenario_6_bare_drug_name_query_keeps_canonical_answer_not_the_vinmec_fallback():
    plan = ModelPlan(
        tool_calls=(ToolCall(name="search_drug", arguments={"query": "vizicin", "limit": 5}),),
        response="planning",
    )
    synthesis = ModelSynthesis(response="Theo Vinmec, vizicin la thuoc dang vien nen, ham luong 500mg.")
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))

    result = orchestrator.run(_request("vizicin"), tools=_tools())

    assert result.intent is OrchestrationIntent.DRUG_INFORMATION
    assert result.status is RunStatus.COMPLETED
    assert result.response != _NO_VINMEC_EVIDENCE_REPLY
    assert "vinmec" not in result.response.lower()
    assert "vizicin" in result.response.lower()
    assert "500mg" in result.response
    assert result.citations == ()  # no fabricated citation object


def test_scenario_6b_today_schedule_query_keeps_operational_db_answer():
    # Mirrors golden query_id 30/33/66: a schedule question, TODAY/UPCOMING-
    # style intent, no "vinmec" in the user's own message.
    #
    # BUILD-28: TODAY_DOSES now bypasses the Main Model entirely (see
    # AgentOrchestrator._schedule_reply) -- a false "Theo Vinmec" claim for
    # this intent is no longer merely scrubbed by this backstop after the
    # fact, it is structurally impossible (there is no model turn to
    # fabricate one). The configured plan/synthesis below prove exactly
    # that: they are never consulted, and the real operational-DB answer
    # (with no vinmec mention) comes from the deterministic composer instead.
    plan = ModelPlan(
        tool_calls=(ToolCall(name="get_today_doses", arguments={}),),
        response="planning",
    )
    synthesis = ModelSynthesis(response="Theo Vinmec, hom nay ban da uong lieu 8h sang.")
    gateway = _SpyModelGateway(plan, synthesis)
    orchestrator, _ = _orchestrator(model_gateway=gateway)

    result = orchestrator.run(_request("toi da uong thuoc sang nay chua nhi"), tools=_tools())

    assert result.status is RunStatus.COMPLETED
    assert result.response != _NO_VINMEC_EVIDENCE_REPLY
    assert "vinmec" not in result.response.lower()
    assert gateway.calls == [] and gateway.synthesis_calls == []


class _EmbeddingStub:
    def embed_query(self, *, text: str):
        from backend.agents.v2.model_gateway import EmbeddingResult

        return EmbeddingResult(model="text-embedding-3-small", vector=(0.1, 0.2))
