"""BUILD-9: Safety Domain is the only authority for Agent V2 safety routing."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.agents.v2.context import ContextAuthority, ContextBudget, ContextBuildStatus, ContextManager, MemoryKind
from backend.agents.v2.model_gateway import ModelPlan
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import (
    SafetyAssessmentNotYetDueError,
    SafetyDomainDecision,
    SafetyGateway,
    SafetyOutcome,
    SafetyRequest,
    SafetyTrigger,
)
from backend.agents.v2.tools import ToolResult
from backend.services.agent_safety import SafetyDomainAdapter


def _decision(**changes: object) -> SafetyDomainDecision:
    values: dict[str, object] = {
        "assessment_id": "assessment-1",
        "risk_level": "LOW",
        "recommended_action": "LOG_ONLY",
        "reason_code": "POLICY_DRUG_PRODUCT_MATCH",
        "policy_source_type": "CLINICAL_POLICY",
        "policy_review_status": "REVIEWED",
        "evaluated_at": datetime(2026, 8, 18, tzinfo=UTC),
    }
    values.update(changes)
    return SafetyDomainDecision(**values)  # type: ignore[arg-type]


class _Domain:
    def __init__(self, result: SafetyDomainDecision | Exception, *, now: list[float] | None = None) -> None:
        self.result = result
        self.calls: list[str] = []
        self.now = now

    def assess(self, *, occurrence_id: str, evaluated_at: datetime) -> SafetyDomainDecision:
        self.calls.append(occurrence_id)
        if self.now is not None:
            self.now[0] += 6
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _gateway(domain: _Domain, **changes: object) -> SafetyGateway:
    values: dict[str, object] = {"timeout_seconds": 5.0}
    values.update(changes)
    return SafetyGateway(domain, **values)  # type: ignore[arg-type]


def test_only_trusted_server_triggers_require_safety_and_safe_decision_is_provenanced():
    domain = _Domain(_decision())
    gateway = _gateway(domain)

    assert gateway.requires_safety(SafetyTrigger.MISSED_DOSE) is True
    assert gateway.requires_safety(SafetyTrigger.DELAYED_DOSE) is True
    assert gateway.requires_safety(SafetyTrigger.GENERAL_INFORMATION) is False
    result = gateway.evaluate(SafetyRequest(SafetyTrigger.MISSED_DOSE, "dose-1"))

    assert result.outcome is SafetyOutcome.SAFE
    assert result.provenance == "safety-domain:assessment-1"
    assert result.reason_code == "POLICY_DRUG_PRODUCT_MATCH"
    assert domain.calls == ["dose-1"]


@pytest.mark.parametrize(
    "changes",
    [
        {"recommended_action": "REQUIRE_MEDICAL_REVIEW"},
        {"policy_review_status": "LEGACY_UNREVIEWED"},
        {"risk_level": "UNKNOWN", "policy_review_status": "REVIEW_REQUIRED"},
    ],
)
def test_unreviewed_or_unresolved_domain_decisions_require_handoff(changes):
    result = _gateway(_Domain(_decision(**changes))).evaluate(SafetyRequest(SafetyTrigger.DELAYED_DOSE, "dose-1"))
    assert result.outcome is SafetyOutcome.HANDOFF_REQUIRED


def test_domain_failure_and_timeout_are_safety_blocked_without_sensitive_error():
    failed = _gateway(_Domain(RuntimeError("db credentials must not leak"))).evaluate(
        SafetyRequest(SafetyTrigger.MISSED_DOSE, "dose-1")
    )
    now = [0.0]
    timed_out = _gateway(_Domain(_decision(), now=now), clock=lambda: now[0]).evaluate(
        SafetyRequest(SafetyTrigger.MISSED_DOSE, "dose-1")
    )
    assert (failed.outcome, failed.reason_code) == (SafetyOutcome.SAFETY_BLOCKED, "SAFETY_DOMAIN_UNAVAILABLE")
    assert (timed_out.outcome, timed_out.reason_code) == (SafetyOutcome.SAFETY_BLOCKED, "SAFETY_DOMAIN_TIMEOUT")


def test_dose_not_yet_due_is_distinguished_from_a_real_domain_outage():
    # BUILD-20 (BUILD-19's P2): "too early to assess" must not collapse into
    # the same generic reason_code as "the safety domain is unavailable" --
    # both still fail closed to SAFETY_BLOCKED, but a specific typed
    # exception keeps the reason_code (and therefore the user-facing
    # message, see runtime.py::_safety_blocked_message) distinguishable.
    not_yet_due = _gateway(_Domain(SafetyAssessmentNotYetDueError("chua den han"))).evaluate(
        SafetyRequest(SafetyTrigger.MISSED_DOSE, "dose-1")
    )
    outage = _gateway(_Domain(RuntimeError("db credentials must not leak"))).evaluate(
        SafetyRequest(SafetyTrigger.MISSED_DOSE, "dose-1")
    )
    assert (not_yet_due.outcome, not_yet_due.reason_code) == (SafetyOutcome.SAFETY_BLOCKED, "DOSE_NOT_YET_ASSESSABLE")
    assert (outage.outcome, outage.reason_code) == (SafetyOutcome.SAFETY_BLOCKED, "SAFETY_DOMAIN_UNAVAILABLE")
    assert not_yet_due.reason_code != outage.reason_code


def test_required_trigger_rejects_missing_occurrence_and_non_required_trigger_skips_domain():
    with pytest.raises(ValueError, match="SAFETY_OCCURRENCE_REQUIRED"):
        SafetyRequest(SafetyTrigger.MISSED_DOSE)
    domain = _Domain(_decision())
    result = _gateway(domain).evaluate(SafetyRequest(SafetyTrigger.GENERAL_INFORMATION))
    assert result.outcome is SafetyOutcome.SAFE
    assert result.reason_code == "SAFETY_NOT_REQUIRED"
    assert domain.calls == []


def test_safety_timeout_is_read_from_server_settings():
    gateway = SafetyGateway.from_settings(_Domain(_decision()), SimpleNamespace(agent_safety_timeout_seconds=3.0))
    assert gateway._timeout_seconds == 3.0


def test_safety_context_is_protected_from_retrieval_or_web_content():
    decision = _gateway(_Domain(_decision())).evaluate(SafetyRequest(SafetyTrigger.MISSED_DOSE, "dose-1"))
    context = decision.to_context_item()
    assert context.authority is ContextAuthority.SAFETY_DOMAIN
    assert context.protected is True
    result = ContextManager(
        ContextBudget(
            input_token_budget=1,
            output_token_reserve=1,
            total_run_token_budget=2,
            memory_fractions={kind: 0.0 for kind in MemoryKind},
        )
    ).build([context])
    assert result.status is ContextBuildStatus.OVERFLOW
    assert result.included[0].rendered_content == context.content


class _NoCallModel:
    def __init__(self) -> None:
        self.calls = 0

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        self.calls += 1
        return ModelPlan(response="unsafe model output")


class _Tools:
    def execute(self, name: str, arguments: dict) -> ToolResult:
        raise AssertionError("Safety terminal result must prevent tool execution")


def _limits() -> AgentRunLimits:
    return AgentRunLimits(100, 4, 2, 2, 0, 5.0, 10.0)


@pytest.mark.parametrize(
    ("domain_decision", "expected"),
    [
        (_decision(recommended_action="REQUIRE_MEDICAL_REVIEW"), RunStatus.HANDOFF_REQUIRED),
        (RuntimeError("safety unavailable"), RunStatus.SAFETY_BLOCKED),
    ],
)
def test_runtime_cannot_bypass_or_rewrite_block_or_handoff(domain_decision, expected):
    model = _NoCallModel()
    safety = _gateway(_Domain(domain_decision)).evaluate(SafetyRequest(SafetyTrigger.MISSED_DOSE, "dose-1"))
    result = ReadOnlyAgentRuntime(model, limits=_limits()).run(
        message="please give a clinical answer",
        actor_role="patient",
        tools=_Tools(),
        safety_decision=safety,
    )
    assert result.status is expected
    assert result.response != "unsafe model output"
    assert model.calls == 0


def test_domain_adapter_projects_existing_db4h_service_without_escalation(monkeypatch):
    class _Assessment:
        id = "assessment-2"
        risk_level = "LOW"
        recommended_action = "LOG_ONLY"
        reason_code = "POLICY_DRUG_PRODUCT_MATCH"
        policy_source_type = "CLINICAL_POLICY"
        policy_review_status = "REVIEWED"
        evaluated_at = datetime(2026, 8, 18, tzinfo=UTC)

    class _Result:
        assessment = _Assessment()

    observed: dict[str, object] = {}

    def fake_assess(db, *, occurrence_id, evaluated_at):
        observed.update({"db": db, "occurrence_id": occurrence_id, "evaluated_at": evaluated_at})
        return _Result()

    monkeypatch.setattr("backend.services.agent_safety.assess_dose_safety", fake_assess)
    db = object()
    result = SafetyDomainAdapter(db).assess(occurrence_id="dose-2", evaluated_at=datetime(2026, 8, 18, tzinfo=UTC))
    assert result.assessment_id == "assessment-2"
    assert observed["db"] is db
    assert observed["occurrence_id"] == "dose-2"


def test_domain_adapter_translates_the_real_not_yet_due_db_error(monkeypatch):
    # backend/agents/v2/safety.py must never import the DB-touching
    # DoseSafetyStateError itself (agents/v2 stays DB-free) -- this adapter
    # is the one place that translates it into the agent-layer's own typed
    # SafetyAssessmentNotYetDueError, using the REAL exception class real
    # code raises, not a stand-in.
    from backend.services.safety_policy_domain.errors import DoseSafetyStateError

    def fake_assess(db, *, occurrence_id, evaluated_at):
        raise DoseSafetyStateError("Chỉ liều MISSED hoặc DELAYED mới được đánh giá safety.", occurrence_id=occurrence_id)

    monkeypatch.setattr("backend.services.agent_safety.assess_dose_safety", fake_assess)
    with pytest.raises(SafetyAssessmentNotYetDueError):
        SafetyDomainAdapter(object()).assess(occurrence_id="dose-3", evaluated_at=datetime(2026, 8, 18, tzinfo=UTC))
