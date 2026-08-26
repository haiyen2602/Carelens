"""BUILD-42: Answerability Gate & Doctor Handoff -- required test matrix
(spec SS20/SS21/SS22).

Root cause / design this build addresses (see the audit in the report):
the pre-existing pipeline had exactly one way to fail an unanswerable
question -- either a fixed honest decline (Cluster B, BUILD-38, still
COMPLETED, no handoff) or an unbounded "ask the same clarification forever"
loop (PERSONAL_SYMPTOM/MEDICATION_DOSE_SAFETY). Neither could escalate to a
human. This module tests the new, deterministic three-way decision
(ANSWERABLE / NEED_MORE_INFO / NEED_DOCTOR) added on top of that -- no
model call, no confidence score, every decision derived from structured
evidence already computed by the existing pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.agents.v2.answerability import (
    MAX_CLARIFICATION_ATTEMPTS,
    AnswerabilityOutcome,
    AnswerabilityReasonCode,
    HandoffType,
    evaluate_clinical_clarification_answerability,
    evaluate_grounding_answerability,
    handoff_type_for,
    is_explicit_doctor_request,
)
from backend.agents.v2.handoff import HandoffCreateCommand
from backend.agents.v2.model_gateway import ModelPlan, ModelSynthesis, ToolCall
from backend.agents.v2.orchestrator import (
    _EXPLICIT_DOCTOR_REQUEST_REPLY,
    _NEED_DOCTOR_REPLY,
    OrchestrationIntent,
    RunStatus,
)
from backend.api.security import CurrentUser
from backend.db.models import Account, CaregiverLink, DoctorReviewRequest, DoctorWatch, Patient
from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter
from tests.test_agent_v2_orchestrator import _orchestrator, _request, _SpyModelGateway, _tools

# ---------------------------------------------------------------------------
# is_explicit_doctor_request -- deterministic keyword detection (SS10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Cho tôi nói chuyện với bác sĩ.",
        "Chuyển tôi cho bác sĩ.",
        "Tôi muốn nói chuyện với bác sĩ.",
        "cho toi noi chuyen voi bac si",
        "Tôi muốn gặp bác sĩ",
        "Bạn có thể kết nối tôi với bác sĩ không?",
    ],
)
def test_is_explicit_doctor_request_positive(message):
    assert is_explicit_doctor_request(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "Paracetamol dùng để làm gì?",
        "Bác sĩ của tôi tên là gì?",
        "Tôi bị đau đầu",
        "Viêm phổi là bệnh gì?",
        "Bác sĩ có nói gì về thuốc này không?",
        "Bạn là ai?",
        "Xin chào",
    ],
)
def test_is_explicit_doctor_request_negative(message):
    assert is_explicit_doctor_request(message) is False


# ---------------------------------------------------------------------------
# evaluate_grounding_answerability / evaluate_clinical_clarification_answerability
# -- pure decision logic, SS8/SS9/SS23
# ---------------------------------------------------------------------------


def test_grounding_answerability_first_attempt_is_need_more_info():
    decision = evaluate_grounding_answerability(
        attempt_count=0, provenance="test", has_ambiguous_candidates=False
    )
    assert decision.outcome is AnswerabilityOutcome.NEED_MORE_INFO
    assert decision.reason_code is AnswerabilityReasonCode.MISSING_REQUIRED_CONTEXT
    assert decision.attempt_count == 1


def test_grounding_answerability_ambiguous_candidates_uses_unresolved_entity():
    decision = evaluate_grounding_answerability(attempt_count=0, provenance="test", has_ambiguous_candidates=True)
    assert decision.reason_code is AnswerabilityReasonCode.UNRESOLVED_ENTITY


def test_grounding_answerability_exhausted_attempts_escalates_to_doctor():
    decision = evaluate_grounding_answerability(
        attempt_count=MAX_CLARIFICATION_ATTEMPTS, provenance="test", has_ambiguous_candidates=False
    )
    assert decision.outcome is AnswerabilityOutcome.NEED_DOCTOR
    assert decision.reason_code is AnswerabilityReasonCode.MAX_ATTEMPTS_REACHED


def test_grounding_answerability_beyond_threshold_uses_repeated_clarification():
    decision = evaluate_grounding_answerability(
        attempt_count=MAX_CLARIFICATION_ATTEMPTS + 1, provenance="test", has_ambiguous_candidates=False
    )
    assert decision.reason_code is AnswerabilityReasonCode.REPEATED_CLARIFICATION


def test_clinical_clarification_answerability_bounded_the_same_way():
    first = evaluate_clinical_clarification_answerability(attempt_count=0, provenance="test")
    assert first.outcome is AnswerabilityOutcome.NEED_MORE_INFO
    exhausted = evaluate_clinical_clarification_answerability(attempt_count=MAX_CLARIFICATION_ATTEMPTS, provenance="test")
    assert exhausted.outcome is AnswerabilityOutcome.NEED_DOCTOR
    assert exhausted.reason_code is AnswerabilityReasonCode.REPEATED_CLARIFICATION


def test_handoff_type_for_derivation():
    assert handoff_type_for(reason_code="ACUTE_DANGER_DETECTED", risk_disposition="HANDOFF_REQUIRED") is HandoffType.SAFETY
    assert handoff_type_for(reason_code="DOCTOR_REVIEW_REQUESTED", risk_disposition="HANDOFF_REQUIRED") is HandoffType.SAFETY
    assert (
        handoff_type_for(reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF")
        is HandoffType.USER_REQUEST
    )
    assert (
        handoff_type_for(reason_code="MAX_ATTEMPTS_REACHED", risk_disposition="UNCERTAINTY_HANDOFF")
        is HandoffType.UNCERTAINTY
    )


# ---------------------------------------------------------------------------
# Full orchestrator integration -- required test matrix (SS20)
# ---------------------------------------------------------------------------


def test_a_answerable_general_medical_no_handoff():
    """A. Answerable general medical -> ANSWERABLE, no handoff."""
    from backend.agents.v2.retrieval import RetrievalConfig, RetrievalGateway
    from backend.services.agent_retrieval import DomainRetrievalResult
    from tests.test_agent_v2_orchestrator import _RetrievalDomain, _retrieved_document

    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(ModelPlan(response="Viêm phổi là tình trạng nhiễm trùng phổi.")),
        retrieval_gateway=RetrievalGateway(
            _SpyModelGateway(),
            _RetrievalDomain(DomainRetrievalResult((_retrieved_document(),), no_source_found=False)),
            config=RetrievalConfig(embedding_model="text-embedding-3-small", top_k=5, token_budget=2000),
        ),
    )
    result = orchestrator.run(_request("Viêm phổi là bệnh gì?"), tools=_tools())
    assert result.status is RunStatus.COMPLETED
    assert result.handoff_result is None
    assert result.answerability_decision is None


def test_b_answerable_drug_lookup_no_handoff():
    """B. Answerable drug lookup -> ANSWERABLE."""
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "paracetamol", "limit": 3}),), response="")
    synthesis = ModelSynthesis(response="Paracetamol dùng để hạ sốt, giảm đau.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))
    result = orchestrator.run(_request("Paracetamol dùng để làm gì?"), tools=_tools())
    assert result.status is RunStatus.COMPLETED
    assert result.handoff_result is None
    assert result.answerability_decision is None


def test_c_missing_drug_strength_need_more_info():
    """C. Missing drug info/strength (ungrounded DRUG_INFORMATION) -> NEED_MORE_INFO."""
    plan = ModelPlan(response="Thuốc này thường uống 1 viên mỗi lần.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan))
    result = orchestrator.run(_request("thuoc omeprazole uong truoc hay sau an"), tools=_tools())
    assert result.status is RunStatus.COMPLETED
    assert result.answerability_decision.outcome is AnswerabilityOutcome.NEED_MORE_INFO
    assert result.handoff_result is None


def test_d_clarification_resolves_to_answerable():
    """D. Clarification resolves the issue -> ANSWERABLE (a real search_drug
    tool call this time -- the SAME query shape as C but with real evidence
    now present, exactly what a resolved follow-up looks like)."""
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "omeprazole", "limit": 3}),), response="")
    synthesis = ModelSynthesis(response="Omeprazole nên uống trước ăn 30-60 phút.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))
    result = orchestrator.run(
        _request("thuoc omeprazole uong truoc hay sau an", answerability_attempt_count=1), tools=_tools()
    )
    assert result.status is RunStatus.COMPLETED
    assert result.answerability_decision is None  # grounded -- gate never engages
    assert result.handoff_result is None


def test_e_repeated_clarification_unresolved_escalates_to_doctor():
    """E. Repeated clarification remains unresolved -> NEED_DOCTOR (personal
    symptom triage clarification, exhausted -- SS21's own multi-turn shape,
    "Tôi không biết." after bounded attempts)."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway())
    result = orchestrator.run(
        _request("tôi bị đau đầu", answerability_attempt_count=MAX_CLARIFICATION_ATTEMPTS), tools=_tools()
    )
    assert result.intent is OrchestrationIntent.PERSONAL_SYMPTOM
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.response == _NEED_DOCTOR_REPLY
    assert result.handoff_result is not None
    assert result.answerability_decision.reason_code is AnswerabilityReasonCode.REPEATED_CLARIFICATION
    assert result.safety_decision is None


def test_f_explicit_doctor_request_need_doctor():
    """F. Explicit doctor request -> NEED_DOCTOR, no model call at all."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result = orchestrator.run(_request("Tôi muốn nói chuyện với bác sĩ."), tools=_tools())
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.response == _EXPLICIT_DOCTOR_REQUEST_REPLY
    assert result.answerability_decision.reason_code is AnswerabilityReasonCode.EXPLICIT_DOCTOR_REQUEST
    assert len(gateway.calls) == 0  # SS10: "no need to force user through clarification"
    assert result.safety_decision is None


def test_g_general_grounding_failure_does_not_auto_handoff():
    """G. General grounding failure (GENERAL_MEDICAL_INFORMATION) -> honest
    decline stays, NO automatic handoff -- BUILD-38 Cluster B's existing
    behavior is untouched by this build (SS23's own explicit carve-out)."""
    from backend.agents.v2.orchestrator import _UNGROUNDED_GENERAL_MEDICAL_DECLINE_REPLY

    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="Bệnh này rất hiếm gặp.")))
    result = orchestrator.run(
        _request("Rối loạn chuyển hóa hiếm gặp XYZ là gì?", answerability_attempt_count=5), tools=_tools()
    )
    assert result.status is RunStatus.COMPLETED
    assert result.response == _UNGROUNDED_GENERAL_MEDICAL_DECLINE_REPLY
    assert result.handoff_result is None
    assert result.answerability_decision is None


def test_i_acute_danger_safety_wins_over_uncertainty():
    """I. Acute danger -> Safety handoff wins, never routed as an
    Answerability-Gate uncertainty handoff."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result = orchestrator.run(_request("Tôi vừa nôn ra máu"), tools=_tools())
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.safety_decision is not None
    assert result.safety_decision.reason_code == "ACUTE_DANGER_DETECTED"
    assert result.answerability_decision is None


def test_j_possible_overdose_safety_wins_over_uncertainty():
    """J. Possible overdose -> Safety handoff wins."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result = orchestrator.run(_request("Tôi vừa uống nhầm 20 viên thuốc rồi"), tools=_tools())
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.safety_decision is not None
    assert result.safety_decision.reason_code == "POSSIBLE_OVERDOSE_REPORTED"
    assert result.answerability_decision is None


def test_explicit_doctor_request_does_not_override_active_overdose_safety():
    """A message that is BOTH an overdose report AND happens to mention a
    doctor is still Safety's -- the explicit-request check is guarded by
    `not needs_handoff` in run() precisely for this case."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result = orchestrator.run(
        _request("Tôi vừa uống nhầm 20 viên thuốc rồi, cho tôi gặp bác sĩ"), tools=_tools()
    )
    assert result.safety_decision is not None
    assert result.safety_decision.reason_code == "POSSIBLE_OVERDOSE_REPORTED"
    assert result.answerability_decision is None


def test_k_out_of_scope_no_doctor_handoff():
    """K. Out-of-scope -> no doctor handoff."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result = orchestrator.run(_request("Bạn là ai?"), tools=_tools())
    assert result.handoff_result is None
    assert result.answerability_decision is None


def test_l_greeting_no_doctor_handoff():
    """L. Greeting -> no doctor handoff."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result = orchestrator.run(_request("Xin chào"), tools=_tools())
    assert result.handoff_result is None
    assert result.answerability_decision is None


def test_no_new_synchronous_model_calls_for_answerability_paths():
    """SS27: 0 new synchronous model calls -- explicit request and exhausted
    clarification never reach the Main Model at all."""
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result = orchestrator.run(_request("Tôi muốn nói chuyện với bác sĩ."), tools=_tools())
    assert len(gateway.calls) == 0

    orchestrator2, gateway2 = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="ignored")))
    result2 = orchestrator2.run(
        _request("tôi bị đau đầu", answerability_attempt_count=MAX_CLARIFICATION_ATTEMPTS), tools=_tools()
    )
    assert len(gateway2.calls) == 0
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result2.status is RunStatus.HANDOFF_CREATED


# ---------------------------------------------------------------------------
# M/N. Duplicate handoff prevention / existing active handoff reuse (SS12)
# O/P. Authorization / cross-patient forbidden (SS28)
# ---------------------------------------------------------------------------

NOW = datetime(2026, 8, 26, tzinfo=UTC)
TABLES = (Patient.__table__, Account.__table__, CaregiverLink.__table__, DoctorWatch.__table__, DoctorReviewRequest.__table__)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _sqlite_btrim(connection, _record) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip() if value else value, deterministic=True)

    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patient(db: Session, *, patient_id="patient-1", doctor_id="doctor-1") -> None:
    db.add(Patient(id=patient_id, full_name="Patient", doctor_id=doctor_id))
    db.commit()


def _patient_actor(patient_id="patient-1") -> CurrentUser:
    return CurrentUser(id=f"account-{patient_id}", role="patient", patient_id=patient_id, doctor_id=None)


def _uncertainty_command(patient_id="patient-1", actor_id=None, idempotency_key="key-1") -> HandoffCreateCommand:
    return HandoffCreateCommand(
        patient_id=patient_id,
        actor_id=actor_id or f"account-{patient_id}",
        patient_question="Tôi muốn nói chuyện với bác sĩ.",
        reason_code=AnswerabilityReasonCode.EXPLICIT_DOCTOR_REQUEST.value,
        risk_disposition="UNCERTAINTY_HANDOFF",
        idempotency_key=idempotency_key,
        verified_context_refs=(),
    )


def test_gateway_create_for_uncertainty_end_to_end_with_real_context_ref(db: Session):
    """Regression test for a real bug found only by local E2E (never by the
    orchestrator-level tests above, which use a pure in-memory stub domain,
    or by the adapter-level tests below, which pass an EMPTY
    verified_context_refs): ``DoctorHandoffGateway.create_for_uncertainty``
    always attaches a real ``HandoffContextRef(HandoffContextSource.
    ANSWERABILITY_GATE, ...)`` (see handoff.py), which
    ``AuthorizedDoctorHandoffAdapter.create`` converts into a
    ``VerifiedContextSource`` (doctor_handoff.py) -- a SEPARATE, parallel
    enum that did not originally have a matching ``ANSWERABILITY_GATE``
    value, so this exact conversion raised a raw ``ValueError``. Goes
    through the REAL gateway + REAL adapter + REAL DB, unlike every other
    test in this module, specifically to keep this class of bug caught by
    the fast test suite from now on rather than only by a slow, manual
    local E2E run."""
    from backend.agents.v2.handoff import DoctorHandoffGateway, DoctorHandoffRequest

    _patient(db)
    gateway = DoctorHandoffGateway(AuthorizedDoctorHandoffAdapter(db, _patient_actor()))
    result = gateway.create_for_uncertainty(
        request=DoctorHandoffRequest(
            patient_id="patient-1",
            actor_id="account-patient-1",
            patient_question="Tôi muốn nói chuyện với bác sĩ.",
            idempotency_key="agent-run:real-e2e-key:handoff",
        ),
        reason_code=AnswerabilityReasonCode.EXPLICIT_DOCTOR_REQUEST.value,
        provenance="agent-orchestrator:answerability-gate",
    )
    assert result.created is True
    row = db.get(DoctorReviewRequest, result.request_id)
    assert row.risk_disposition == "UNCERTAINTY_HANDOFF"
    assert row.verified_context_refs  # a real ref was persisted, not silently dropped


def test_m_repeated_request_does_not_duplicate_handoff(db: Session):
    _patient(db)
    adapter = AuthorizedDoctorHandoffAdapter(db, _patient_actor())
    first = adapter.create(_uncertainty_command(idempotency_key="key-1"), created_at=NOW)
    assert first.created is True
    second = adapter.create(_uncertainty_command(idempotency_key="key-2"), created_at=NOW)
    assert second.created is False
    assert second.request_id == first.request_id
    assert db.query(DoctorReviewRequest).count() == 1


def test_n_existing_active_handoff_is_reused_and_status_returned(db: Session):
    _patient(db)
    adapter = AuthorizedDoctorHandoffAdapter(db, _patient_actor())
    first = adapter.create(_uncertainty_command(idempotency_key="key-1"), created_at=NOW)
    row = db.get(DoctorReviewRequest, first.request_id)
    row.status = "ASSIGNED"
    row.assigned_doctor_id = "doctor-1"
    db.commit()
    reused = adapter.create(_uncertainty_command(idempotency_key="key-2"), created_at=NOW)
    assert reused.created is False
    assert reused.status == "ASSIGNED"
    assert reused.assigned_doctor_id == "doctor-1"


def test_dedup_does_not_reuse_a_resolved_prior_handoff(db: Session):
    """A CANCELLED/ANSWERED prior request is not "active" -- a genuinely new
    uncertainty handoff must still be created."""
    _patient(db)
    adapter = AuthorizedDoctorHandoffAdapter(db, _patient_actor())
    first = adapter.create(_uncertainty_command(idempotency_key="key-1"), created_at=NOW)
    row = db.get(DoctorReviewRequest, first.request_id)
    row.status = "ANSWERED"
    db.commit()
    second = adapter.create(_uncertainty_command(idempotency_key="key-2"), created_at=NOW)
    assert second.created is True
    assert second.request_id != first.request_id
    assert db.query(DoctorReviewRequest).count() == 2


def test_dedup_is_scoped_to_uncertainty_handoffs_only_not_safety(db: Session):
    """The new cross-run dedup must never change Safety-sourced handoff
    creation -- confirmed by using risk_disposition=HANDOFF_REQUIRED
    (the Safety shape) instead of UNCERTAINTY_HANDOFF."""
    _patient(db)
    adapter = AuthorizedDoctorHandoffAdapter(db, _patient_actor())
    safety_command_1 = HandoffCreateCommand(
        patient_id="patient-1",
        actor_id="account-patient-1",
        patient_question="Tôi vừa nôn ra máu",
        reason_code="ACUTE_DANGER_DETECTED",
        risk_disposition="HANDOFF_REQUIRED",
        idempotency_key="safety-key-1",
        verified_context_refs=(),
    )
    safety_command_2 = HandoffCreateCommand(
        patient_id="patient-1",
        actor_id="account-patient-1",
        patient_question="Tôi vừa uống nhầm 20 viên thuốc rồi",
        reason_code="POSSIBLE_OVERDOSE_REPORTED",
        risk_disposition="HANDOFF_REQUIRED",
        idempotency_key="safety-key-2",
        verified_context_refs=(),
    )
    first = adapter.create(safety_command_1, created_at=NOW)
    second = adapter.create(safety_command_2, created_at=NOW)
    assert first.created is True
    assert second.created is True  # NOT deduped -- unchanged pre-existing Safety behavior
    assert first.request_id != second.request_id
    assert db.query(DoctorReviewRequest).count() == 2


def test_o_patient_authorization_allows_own_handoff(db: Session):
    _patient(db)
    adapter = AuthorizedDoctorHandoffAdapter(db, _patient_actor())
    result = adapter.create(_uncertainty_command(), created_at=NOW)
    assert result.created is True


def test_p_cross_patient_uncertainty_handoff_is_forbidden(db: Session):
    from fastapi import HTTPException

    _patient(db, patient_id="patient-1")
    _patient(db, patient_id="patient-2")
    # An actor authenticated as patient-1 cannot create an uncertainty
    # handoff naming patient-2 -- same require_agent_patient_access boundary
    # every other Agent V2 tool read already goes through (fails closed,
    # 403), not a BUILD-42-specific check.
    adapter = AuthorizedDoctorHandoffAdapter(db, _patient_actor("patient-1"))
    with pytest.raises(HTTPException) as exc_info:
        adapter.create(_uncertainty_command(patient_id="patient-2", actor_id="account-patient-1"), created_at=NOW)
    assert exc_info.value.status_code == 403
