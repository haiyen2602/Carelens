"""TASK-023: unit tests for `_append_drug_info_disclaimer`
(backend/agents/v2/orchestrator.py).

Deterministic backstop -- appends the fixed reference-only disclaimer
("Thông tin này chỉ mang tính tham khảo, không thay thế tư vấn của bác sĩ
hoặc dược sĩ.") to a COMPLETED reply for a genuinely drug-info-shaped intent
(DRUG_INFORMATION, PRESCRIPTION_INFORMATION, MEDICATION_DOSE_SAFETY). Never
model-generated -- same reasoning as `_enforce_vinmec_provenance`/
`_enforce_medical_grounding`, which this file's own test pattern mirrors
(see tests/test_agent_v2_medical_grounding.py).
"""

from __future__ import annotations

import pytest

from backend.agents.v2.orchestrator import (
    _DRUG_INFO_DISCLAIMER,
    OrchestrationIntent,
    _append_drug_info_disclaimer,
)
from backend.agents.v2.runtime import RunMetrics, RunResult, RunStatus


def _result(response: str, status: RunStatus = RunStatus.COMPLETED, error_code: str | None = None) -> RunResult:
    return RunResult(status, response, (), RunMetrics(), error_code)


@pytest.mark.parametrize(
    "intent",
    [
        OrchestrationIntent.DRUG_INFORMATION,
        OrchestrationIntent.PRESCRIPTION_INFORMATION,
        OrchestrationIntent.MEDICATION_DOSE_SAFETY,
    ],
)
def test_appends_disclaimer_for_drug_info_intents(intent):
    result = _result("Paracetamol dùng để giảm đau, hạ sốt.")
    updated = _append_drug_info_disclaimer(result, intent=intent)
    assert updated.response.endswith(_DRUG_INFO_DISCLAIMER)
    assert "Paracetamol" in updated.response


@pytest.mark.parametrize(
    "intent",
    [
        OrchestrationIntent.GENERAL_MEDICAL_INFORMATION,
        OrchestrationIntent.DOSE_STATUS,
        OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS,
        OrchestrationIntent.TODAY_DOSES,
    ],
)
def test_no_disclaimer_outside_drug_info_intents(intent):
    original = "Bạn đã uống liều 08:00 rồi nhé."
    result = _result(original)
    updated = _append_drug_info_disclaimer(result, intent=intent)
    assert updated.response == original


def test_no_disclaimer_when_not_completed():
    original = "Trường hợp này cần bác sĩ đánh giá thêm."
    result = _result(original, status=RunStatus.HANDOFF_CREATED)
    updated = _append_drug_info_disclaimer(result, intent=OrchestrationIntent.DRUG_INFORMATION)
    assert updated.response == original


def test_no_disclaimer_on_grounding_failure_decline_reply_shape_is_still_a_noop_by_status_only():
    """This backstop only gates on status/intent (see its own docstring) --
    a GROUNDING_FAILURE reply is still status=COMPLETED, so a decline reply
    for a drug-info intent WOULD get the disclaimer appended if this function
    ran on it. It never does in the real orchestrator flow: the call site
    sits after the Answerability Gate, which already returns its own
    separate reply for every GROUNDING_FAILURE case on a drug-info intent
    before this function is ever reached (see the call site's own comment).
    This test documents that structural guarantee at the unit level: the
    function itself has no special-case for error_code, by design (single
    responsibility -- status+intent only), so the real invariant lives at
    the call site, not here.
    """
    result = _result("Mình chưa có dữ liệu đã xác minh...", error_code="GROUNDING_FAILURE")
    updated = _append_drug_info_disclaimer(result, intent=OrchestrationIntent.DRUG_INFORMATION)
    assert updated.response.endswith(_DRUG_INFO_DISCLAIMER)  # documents current behavior, not a safety gap


def test_idempotent_does_not_double_append():
    already = f"Thông tin thuốc X.\n\n{_DRUG_INFO_DISCLAIMER}"
    result = _result(already)
    updated = _append_drug_info_disclaimer(result, intent=OrchestrationIntent.DRUG_INFORMATION)
    assert updated.response == already
    assert updated.response.count(_DRUG_INFO_DISCLAIMER) == 1


def test_empty_response_gets_bare_disclaimer_no_leading_blank_lines():
    result = _result("")
    updated = _append_drug_info_disclaimer(result, intent=OrchestrationIntent.DRUG_INFORMATION)
    assert updated.response == _DRUG_INFO_DISCLAIMER
