"""BUILD-30: unit tests for backend/services/agent_activity.py --
build_activity_timeline() is a pure function of a real OrchestrationResult,
so every required scenario (A-H) can be verified deterministically here
without any live model/tool/DB call. Real end-to-end coverage (actual
/api/chat + the new activity endpoint) lives in
tests/test_api/test_agent_activity_routes.py and the local E2E script used
for BUILD-30's own production verification.
"""

from __future__ import annotations

from backend.agents.v2.conversation_state import SuggestedAction
from backend.agents.v2.handoff import AgentHandoffResult
from backend.agents.v2.orchestrator import Citation, OrchestrationIntent, OrchestrationResult
from backend.agents.v2.runtime import RunMetrics, RunStatus
from backend.agents.v2.safety import SafetyDecision, SafetyOutcome
from backend.agents.v2.tools import ToolResult
from backend.services.agent_activity import build_activity_timeline

_METRICS_NO_MODEL_CALLS = RunMetrics(steps=1, model_calls=0, tool_calls=1)
_METRICS_WITH_MODEL_CALLS = RunMetrics(steps=2, model_calls=1, tool_calls=1)


def _result(
    *,
    intent: OrchestrationIntent,
    status: RunStatus = RunStatus.COMPLETED,
    tool_results: tuple = (),
    citations: tuple = (),
    safety_decision: SafetyDecision | None = None,
    handoff_result: AgentHandoffResult | None = None,
    metrics: RunMetrics = _METRICS_WITH_MODEL_CALLS,
) -> OrchestrationResult:
    return OrchestrationResult(
        trace_id="trace-1", agent_run_id="run-1", intent=intent, status=status, response="reply",
        tool_results=tool_results, citations=citations, safety_decision=safety_decision,
        handoff_result=handoff_result, metrics=metrics,
    )


def _labels(activities: list[dict]) -> list[str]:
    return [a["label"] for a in activities]


def _tool(name: str) -> ToolResult:
    return ToolResult(name=name, data={}, provenance=f"tool:{name}")


# ---------------------------------------------------------------------------
# A. Drug info
# ---------------------------------------------------------------------------


def test_a_drug_information_shows_router_and_drug_tool_and_completion():
    result = _result(
        intent=OrchestrationIntent.DRUG_INFORMATION,
        tool_results=(_tool("search_drug"),),
    )
    activities = build_activity_timeline(result)
    assert _labels(activities) == ["Đã xác định yêu cầu", "Đã tra thông tin thuốc", "Đã hoàn thành câu trả lời"]
    assert all(a["status"] == "completed" for a in activities)


def test_a_drug_info_dedupes_search_drug_and_get_drug_info_into_one_step():
    result = _result(
        intent=OrchestrationIntent.DRUG_INFORMATION,
        tool_results=(_tool("search_drug"), _tool("get_drug_info")),
    )
    activities = build_activity_timeline(result)
    assert _labels(activities).count("Đã tra thông tin thuốc") == 1


def test_dynamic_action_events_are_user_safe_and_never_expose_ids():
    action = SuggestedAction(
        action_id="internal-action-id",
        type="drug_followup",
        label="Công dụng của Long Huyết",
        value="drug_uses",
        entity_id="internal-drug-id",
    )
    activities = build_activity_timeline(
        _result(intent=OrchestrationIntent.DRUG_INFORMATION),
        selected_action=action,
        suggested_actions=(action,),
    )

    assert 'Bạn chọn "Công dụng của Long Huyết"' in _labels(activities)
    assert "Đã tạo gợi ý cho câu hỏi tiếp theo" in _labels(activities)
    assert "internal-action-id" not in str(activities)
    assert "internal-drug-id" not in str(activities)


# ---------------------------------------------------------------------------
# B. General medical (retrieval)
# ---------------------------------------------------------------------------


def test_b_general_medical_shows_retrieval_with_real_source_count():
    citations = (
        Citation(title="Gan nhiễm mỡ", source="cong_dung", url=None),
        Citation(title="Gan nhiễm mỡ 2", source="cong_dung", url=None),
    )
    result = _result(intent=OrchestrationIntent.GENERAL_MEDICAL_INFORMATION, citations=citations)
    activities = build_activity_timeline(result)
    assert _labels(activities) == ["Đã xác định yêu cầu", "Đã tìm nguồn thông tin liên quan", "Đã hoàn thành câu trả lời"]
    retrieval_step = next(a for a in activities if a["type"] == "retrieval")
    assert retrieval_step["source_count"] == 2


def test_b_general_medical_with_zero_results_still_shows_the_real_attempt():
    result = _result(intent=OrchestrationIntent.GENERAL_MEDICAL_INFORMATION, citations=())
    activities = build_activity_timeline(result)
    retrieval_step = next(a for a in activities if a["type"] == "retrieval")
    assert retrieval_step["source_count"] == 0


def test_retrieval_step_never_appears_for_an_intent_that_never_uses_it():
    result = _result(intent=OrchestrationIntent.DRUG_INFORMATION, citations=(Citation("x", "cong_dung", None),))
    activities = build_activity_timeline(result)
    assert "Đã tìm nguồn thông tin liên quan" not in _labels(activities)


# ---------------------------------------------------------------------------
# C. Schedule deterministic (BUILD-28: zero Main Model calls)
# ---------------------------------------------------------------------------


def test_c_schedule_deterministic_shows_time_query_and_schedule_tool_no_fake_ai_step():
    result = _result(
        intent=OrchestrationIntent.UPCOMING_DOSES,
        tool_results=(_tool("get_doses_for_range"),),
        metrics=_METRICS_NO_MODEL_CALLS,
    )
    activities = build_activity_timeline(result)
    assert _labels(activities) == [
        "Đã xác định yêu cầu", "Đã xác định thời gian", "Đã kiểm tra lịch dùng thuốc", "Đã hoàn thành câu trả lời",
    ]
    # The one thing BUILD-30 §6 explicitly forbids: no "thinking"/"called
    # Main Model" step, verified directly against the real model_calls=0
    # metric this run actually has.
    assert result.metrics.model_calls == 0
    forbidden = {"Đang dùng AI suy nghĩ", "Đã gọi Main Model"}
    assert forbidden.isdisjoint(_labels(activities))


def test_today_doses_and_upcoming_doses_also_get_the_time_query_step():
    for intent in (OrchestrationIntent.TODAY_DOSES, OrchestrationIntent.UPCOMING_DOSES, OrchestrationIntent.MEDICATION_HISTORY):
        activities = build_activity_timeline(_result(intent=intent, metrics=_METRICS_NO_MODEL_CALLS))
        assert "Đã xác định thời gian" in _labels(activities)


def test_time_query_step_never_appears_for_a_non_schedule_intent():
    activities = build_activity_timeline(_result(intent=OrchestrationIntent.DRUG_INFORMATION))
    assert "Đã xác định thời gian" not in _labels(activities)


# ---------------------------------------------------------------------------
# D. Past history
# ---------------------------------------------------------------------------


def test_d_past_history_is_deterministic_like_c():
    result = _result(
        intent=OrchestrationIntent.MEDICATION_HISTORY,
        tool_results=(_tool("get_doses_for_range"),),
        metrics=_METRICS_NO_MODEL_CALLS,
    )
    activities = build_activity_timeline(result)
    assert _labels(activities) == [
        "Đã xác định yêu cầu", "Đã xác định thời gian", "Đã kiểm tra lịch dùng thuốc", "Đã hoàn thành câu trả lời",
    ]


# ---------------------------------------------------------------------------
# E. Vinmec web path
# ---------------------------------------------------------------------------


def test_e_vinmec_web_shows_the_real_attempt_and_source_count():
    citations = (Citation(title="Vinmec bài viết", source="vinmec-web", url="https://vinmec.com/x"),)
    result = _result(intent=OrchestrationIntent.VINMEC_WEB_INFORMATION, citations=citations)
    activities = build_activity_timeline(result)
    assert _labels(activities) == ["Đã xác định yêu cầu", "Đã tra cứu nguồn Vinmec", "Đã hoàn thành câu trả lời"]
    vinmec_step = next(a for a in activities if a["type"] == "vinmec_web")
    assert vinmec_step["source_count"] == 1


def test_vinmec_citations_never_get_double_counted_as_retrieval():
    citations = (Citation(title="Vinmec", source="vinmec-web", url=None),)
    result = _result(intent=OrchestrationIntent.VINMEC_WEB_INFORMATION, citations=citations)
    activities = build_activity_timeline(result)
    assert "Đã tìm nguồn thông tin liên quan" not in _labels(activities)


# ---------------------------------------------------------------------------
# F. Safety (acute danger)
# ---------------------------------------------------------------------------


def test_f_acute_danger_shows_detection_then_safety_then_handoff_no_completion_step():
    safety_decision = SafetyDecision(outcome=SafetyOutcome.HANDOFF_REQUIRED, reason_code="ACUTE_DANGER_DETECTED", provenance="agent-orchestrator:acute-danger")
    handoff = AgentHandoffResult(request_id="handoff-1", status="PENDING", assigned_doctor_id=None, created=True)
    result = _result(
        intent=OrchestrationIntent.ACUTE_DANGER_ESCALATION,
        status=RunStatus.HANDOFF_CREATED,
        safety_decision=safety_decision,
        handoff_result=handoff,
    )
    activities = build_activity_timeline(result)
    assert _labels(activities) == [
        "Đã xác định yêu cầu",
        "Phát hiện nội dung cần kiểm tra an toàn",
        "Đã kiểm tra an toàn",
        "Đã chuyển yêu cầu để bác sĩ xem xét",
    ]
    # No internal reason_code/outcome value ever leaks into a label/status.
    for item in activities:
        assert "ACUTE_DANGER_DETECTED" not in str(item)
        assert "HANDOFF_REQUIRED" not in str(item)
    # No duplicate "hoàn thành" step -- the handoff step above IS the real
    # terminal event for this path.
    assert "Đã hoàn thành câu trả lời" not in _labels(activities)


def test_missed_dose_and_delayed_dose_also_get_the_detection_step():
    for intent in (OrchestrationIntent.MISSED_DOSE, OrchestrationIntent.DELAYED_DOSE):
        safety_decision = SafetyDecision(outcome=SafetyOutcome.SAFE, reason_code="POLICY_MATCH", provenance="p")
        activities = build_activity_timeline(_result(intent=intent, safety_decision=safety_decision))
        assert "Phát hiện nội dung cần kiểm tra an toàn" in _labels(activities)


def test_safety_blocked_status_shows_an_honest_blocked_terminal_step():
    safety_decision = SafetyDecision(outcome=SafetyOutcome.SAFETY_BLOCKED, reason_code="DOSE_NOT_YET_ASSESSABLE", provenance="p")
    result = _result(intent=OrchestrationIntent.MISSED_DOSE, status=RunStatus.SAFETY_BLOCKED, safety_decision=safety_decision)
    activities = build_activity_timeline(result)
    blocked = [a for a in activities if a["status"] == "blocked"]
    assert len(blocked) == 1
    assert "Đã hoàn thành câu trả lời" not in _labels(activities)


# ---------------------------------------------------------------------------
# G. Doctor Handoff (non-acute, e.g. dosage change request)
# ---------------------------------------------------------------------------


def test_g_doctor_review_handoff_created():
    safety_decision = SafetyDecision(outcome=SafetyOutcome.HANDOFF_REQUIRED, reason_code="DOCTOR_REVIEW_REQUESTED", provenance="p")
    handoff = AgentHandoffResult(request_id="handoff-2", status="PENDING", assigned_doctor_id=None, created=True)
    result = _result(
        intent=OrchestrationIntent.DOCTOR_REVIEW, status=RunStatus.HANDOFF_CREATED,
        safety_decision=safety_decision, handoff_result=handoff,
    )
    activities = build_activity_timeline(result)
    assert _labels(activities) == [
        "Đã xác định yêu cầu",
        "Phát hiện nội dung cần kiểm tra an toàn",
        "Đã kiểm tra an toàn",
        "Đã chuyển yêu cầu để bác sĩ xem xét",
    ]


# ---------------------------------------------------------------------------
# H. Out-of-scope
# ---------------------------------------------------------------------------


def test_h_out_of_scope_shows_only_router_and_completion():
    result = _result(intent=OrchestrationIntent.OUT_OF_SCOPE_REQUEST, metrics=RunMetrics())
    activities = build_activity_timeline(result)
    assert _labels(activities) == ["Đã xác định yêu cầu", "Đã hoàn thành câu trả lời"]


# ---------------------------------------------------------------------------
# Cross-cutting: no leaks, no fake steps, honest terminal states
# ---------------------------------------------------------------------------


def test_no_activity_ever_carries_raw_tool_arguments_or_data():
    tool = ToolResult(name="search_drug", data={"secret_internal_field": "should never appear"}, provenance="tool:search_drug")
    result = _result(intent=OrchestrationIntent.DRUG_INFORMATION, tool_results=(tool,))
    activities = build_activity_timeline(result)
    assert "secret_internal_field" not in str(activities)
    assert "should never appear" not in str(activities)


def test_no_activity_ever_carries_pii_or_ids():
    result = _result(intent=OrchestrationIntent.DRUG_INFORMATION)
    activities = build_activity_timeline(result)
    serialized = str(activities)
    assert "trace-1" not in serialized
    assert "run-1" not in serialized


def test_every_activity_item_is_json_serializable_and_has_only_documented_keys():
    import json

    result = _result(
        intent=OrchestrationIntent.GENERAL_MEDICAL_INFORMATION,
        citations=(Citation("x", "cong_dung", None),),
    )
    activities = build_activity_timeline(result)
    json.dumps(activities)  # raises if not serializable
    allowed_keys = {"type", "label", "status", "duration_ms", "source_count"}
    for item in activities:
        assert set(item.keys()) <= allowed_keys


def test_unmapped_tool_names_are_silently_skipped_not_shown_raw():
    tool = ToolResult(name="some_future_unmapped_tool", data={}, provenance="tool:x")
    result = _result(intent=OrchestrationIntent.DRUG_INFORMATION, tool_results=(tool,))
    activities = build_activity_timeline(result)
    assert "some_future_unmapped_tool" not in str(activities)


def test_failed_status_shows_an_honest_error_step_not_a_fake_completion():
    result = _result(intent=OrchestrationIntent.DRUG_INFORMATION, status=RunStatus.FAILED)
    activities = build_activity_timeline(result)
    assert activities[-1]["status"] == "failed"
    assert "Đã hoàn thành câu trả lời" not in _labels(activities)


def test_budget_exceeded_and_timeout_and_cancelled_all_show_the_same_honest_error_step():
    for status in (RunStatus.BUDGET_EXCEEDED, RunStatus.TIMEOUT, RunStatus.CANCELLED):
        activities = build_activity_timeline(_result(intent=OrchestrationIntent.DRUG_INFORMATION, status=status))
        assert activities[-1]["status"] == "failed"
        assert "Đã hoàn thành câu trả lời" not in _labels(activities)
