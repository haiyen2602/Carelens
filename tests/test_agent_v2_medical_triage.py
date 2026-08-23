"""BUILD-29F: deterministic triage and medication-dose-safety coverage."""

from __future__ import annotations

import pytest

from backend.agents.v2.evaluation_v2 import EvaluationPath, MetricStatus, dispatch_evaluation
from backend.agents.v2.orchestrator import OrchestrationIntent, classify_intent
from backend.agents.v2.runtime import RunStatus
from backend.services.agent_activity import build_activity_timeline
from tests.test_agent_v2_orchestrator import _IdempotentHandoffDomain, _orchestrator, _request, _SpyModelGateway, _tools


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Tôi đau đầu", OrchestrationIntent.PERSONAL_SYMPTOM),
        ("Đầu tôi đau quá", OrchestrationIntent.PERSONAL_SYMPTOM),
        ("Tự nhiên tôi chóng mặt", OrchestrationIntent.PERSONAL_SYMPTOM),
        ("Mấy hôm nay tôi đau bụng", OrchestrationIntent.PERSONAL_SYMPTOM),
        ("Tôi bị buồn nôn", OrchestrationIntent.PERSONAL_SYMPTOM),
        ("Tôi có thể uống 10 viên vitamin C không?", OrchestrationIntent.MEDICATION_DOSE_SAFETY),
        ("Uống gấp đôi liều được không?", OrchestrationIntent.MEDICATION_DOSE_SAFETY),
        ("Tôi uống thêm 3 viên được không?", OrchestrationIntent.MEDICATION_DOSE_SAFETY),
        ("Tôi vừa uống 10 viên vitamin C", OrchestrationIntent.POSSIBLE_OVERDOSE),
        ("Tôi lỡ uống quá nhiều thuốc", OrchestrationIntent.POSSIBLE_OVERDOSE),
    ],
)
def test_triage_and_dose_taxonomy_covers_personal_vietnamese_paraphrases(message, intent):
    assert classify_intent(message).intent is intent


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Đau đầu là gì?", OrchestrationIntent.GENERAL_MEDICAL_INFORMATION),
        ("Vitamin C là gì?", OrchestrationIntent.DRUG_INFORMATION),
        ("Thuốc ngủ có tác dụng gì?", OrchestrationIntent.DRUG_INFORMATION),
        ("Tôi không uống 10 viên thuốc ngủ", OrchestrationIntent.DRUG_INFORMATION),
    ],
)
def test_triage_and_dose_negative_controls_remain_non_acute(message, intent):
    assert classify_intent(message).intent is intent


@pytest.mark.parametrize(
    "message",
    [
        "Tôi đau đầu đột ngột dữ dội",
        "Tôi đau đầu và yếu một bên người",
        "Tôi khó thở",
        "Tôi muốn uống 10 viên thuốc ngủ",
        "Tôi vừa uống rất nhiều thuốc ngủ",
    ],
)
def test_red_flags_and_high_risk_ingestion_win_over_triage_and_dose_paths(message):
    assert classify_intent(message).intent is OrchestrationIntent.ACUTE_DANGER_ESCALATION


def test_personal_symptom_is_a_deterministic_non_diagnostic_triage_response():
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway())

    result = orchestrator.run(_request("Tôi cảm thấy đau đầu"), tools=_tools())

    assert result.intent is OrchestrationIntent.PERSONAL_SYMPTOM
    assert result.status is RunStatus.COMPLETED
    assert "không thể chẩn đoán qua chat" in result.response
    assert "tên thuốc" not in result.response
    assert result.tool_results == () and result.citations == ()
    assert gateway.calls == [] and gateway.synthesis_calls == []


def test_dose_safety_requests_strength_without_inventing_a_dose_and_keeps_server_entity_context():
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway())

    result = orchestrator.run(
        _request(
            "Tôi uống 10 viên được không?",
            active_entity_id="canonical-vitamin-c",
            active_entity_name="Vitamin C",
        ),
        tools=_tools(),
    )

    assert result.intent is OrchestrationIntent.MEDICATION_DOSE_SAFETY
    assert result.status is RunStatus.COMPLETED
    assert "Vitamin C" in result.response
    assert "mỗi viên bao nhiêu mg" in result.response
    assert "Không nên tự tăng hoặc gấp đôi liều" in result.response
    assert result.tool_results == () and result.citations == ()
    assert gateway.calls == [] and gateway.synthesis_calls == []


def test_possible_overdose_escalates_safely_without_running_the_model():
    handoff_domain = _IdempotentHandoffDomain()
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(), handoff_domain=handoff_domain)

    result = orchestrator.run(_request("Tôi vừa uống 10 viên vitamin C"), tools=_tools())

    assert result.intent is OrchestrationIntent.POSSIBLE_OVERDOSE
    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.safety_decision is not None
    assert result.safety_decision.reason_code == "POSSIBLE_OVERDOSE_REPORTED"
    assert len(handoff_domain.commands) == 1
    assert gateway.calls == [] and gateway.synthesis_calls == []


def test_triage_dose_and_safety_evaluation_paths_keep_rag_metrics_not_applicable():
    class Result:
        def __init__(self, intent, safety=None):
            self.intent = intent
            self.status = RunStatus.COMPLETED
            self.tool_results = ()
            self.citations = ()
            self.safety_decision = safety
            self.handoff_result = None

    triage = dispatch_evaluation(result=Result(OrchestrationIntent.PERSONAL_SYMPTOM))
    dose = dispatch_evaluation(result=Result(OrchestrationIntent.MEDICATION_DOSE_SAFETY))
    overdose = dispatch_evaluation(result=Result(OrchestrationIntent.POSSIBLE_OVERDOSE, safety=object()))

    assert triage.path is EvaluationPath.TRIAGE
    assert dose.path is EvaluationPath.MEDICATION_DOSE_SAFETY
    assert overdose.path is EvaluationPath.SAFETY
    for evaluation in (triage, dose, overdose):
        assert evaluation.metrics["hit_rate_at_10"].status is MetricStatus.NOT_APPLICABLE
        assert evaluation.metrics["mrr_at_10"].status is MetricStatus.NOT_APPLICABLE
        assert evaluation.metrics["ndcg_at_10"].status is MetricStatus.NOT_APPLICABLE


def test_clinical_activity_timeline_is_sanitized_and_describes_real_deterministic_steps():
    orchestrator, _ = _orchestrator(model_gateway=_SpyModelGateway())
    result = orchestrator.run(_request("Tôi đang chóng mặt"), tools=_tools())

    labels = [item["label"] for item in build_activity_timeline(result)]

    assert labels == [
        "Đã xác định yêu cầu",
        "Đã nhận diện triệu chứng",
        "Đã kiểm tra dấu hiệu cần lưu ý",
        "Đã chuẩn bị câu hỏi làm rõ",
        "Đã hoàn thành câu trả lời",
    ]
    assert "PERSONAL_SYMPTOM" not in str(labels)
