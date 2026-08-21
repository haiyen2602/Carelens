"""BUILD-19B regression tests for the tool-calling synthesis loop.

Fixes the P1 ``reply=""`` defect BUILD-19 found on every Agent V2 turn that
called a tool: the runtime now completes the full loop --

    User -> Model -> Tool Call -> Tool Result -> Model Synthesis -> Final Reply

-- instead of returning the pre-tool planning turn's own (frequently empty)
``output_text`` as the final reply. See ``backend/agents/v2/runtime.py``
(``ReadOnlyAgentRuntime._synthesize_with_limits``) and
``backend/agents/v2/model_gateway.py`` (``synthesize_read_only``).

Ten scenarios required by the BUILD-19B report:
  1. drug information + tool -> non-empty reply
  2. today doses -> non-empty reply
  3. Safety SAFE -> non-empty reply
  4. prescription -> non-empty reply
  5. multiple tools -> one final synthesized reply
  6. SAFETY_BLOCKED -> no synthesis call
  7. HANDOFF_CREATED -> no synthesis call
  8. synthesis timeout/error -> fail-closed (never fabricates a reply)
  9. budget exceeded -> synthesis is budget-gated like planning, not exempt
 10. checkpoint resume does not replay the tool call or the synthesis call
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.handoff import AgentHandoffResult
from backend.agents.v2.model_gateway import ModelPlan, ModelSynthesis, ToolCall
from backend.agents.v2.orchestrator import OrchestrationIntent
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyDecision, SafetyOutcome
from backend.agents.v2.tools import ToolResult
from backend.db.models import AgentRun, AgentRunCheckpoint
from backend.services.agent_checkpoint import CheckpointTerminalError
from tests.test_agent_v2_orchestrator import (
    _DomainTools,
    _SafetyDomain,
    _SpyModelGateway,
    _orchestrator,
    _request,
    _safety_decision,
    _tools,
)

# ---------------------------------------------------------------------------
# Runtime-level fakes (no orchestrator, no DB) for the pure guardrail tests
# ---------------------------------------------------------------------------


def _runtime_limits(**overrides) -> AgentRunLimits:
    values = dict(
        token_budget=1000, max_steps=6, max_model_calls=3, max_tool_calls=4,
        max_retries=1, model_timeout_seconds=5.0, run_timeout_seconds=20.0,
    )
    values.update(overrides)
    return AgentRunLimits(**values)


class _CountingGateway:
    """Records plan/synthesis call counts; can be made to fail synthesis N times."""

    def __init__(self, plan: ModelPlan, synthesis: ModelSynthesis | None = None, *, fail_synthesis_times: int = 0) -> None:
        self.plan = plan
        self.synthesis = synthesis or ModelSynthesis(response="synthesized-reply")
        self.plan_calls = 0
        self.synthesis_calls = 0
        self._fail_synthesis_times = fail_synthesis_times

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        self.plan_calls += 1
        return self.plan

    def synthesize_read_only(self, *, message: str, actor_role: str, evidence) -> ModelSynthesis:
        self.synthesis_calls += 1
        if self._fail_synthesis_times > 0:
            self._fail_synthesis_times -= 1
            raise ValueError("MODEL_SYNTHESIS_EMPTY")
        return self.synthesis


class _RuntimeTools:
    """Bare ToolGateway-shaped fake: no DB, no authorization -- just a recorder."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append(name)
        return ToolResult(name=name, data={"ok": True}, provenance=f"tool:{name}")


# ---------------------------------------------------------------------------
# 1-4. Non-empty reply for each scenario the BUILD-19 UAT found reply=""
# ---------------------------------------------------------------------------


def test_drug_information_with_tool_call_produces_non_empty_synthesized_reply():
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "paracetamol", "limit": 3}),), response="")
    synthesis = ModelSynthesis(response="Paracetamol la thuoc ha sot, giam dau thong dung.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))

    result = orchestrator.run(_request("Cho toi biet thong tin ve thuoc paracetamol"), tools=_tools())

    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response
    assert result.response != ""  # the exact BUILD-19 P1 defect: no longer reproducible
    assert len(gateway.calls) == 1
    assert len(gateway.synthesis_calls) == 1


def test_today_doses_with_tool_call_produces_non_empty_synthesized_reply():
    domain_tools = _DomainTools()
    plan = ModelPlan(tool_calls=(ToolCall("get_today_doses", {}),), response="")
    synthesis = ModelSynthesis(response="Hom nay ban co 1 lieu thuoc can uong luc 8 gio sang.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))

    result = orchestrator.run(_request("Hom nay toi can uong thuoc gi"), tools=_tools(domain_tools))

    assert result.intent is OrchestrationIntent.TODAY_DOSES
    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response
    assert result.response
    assert [t.name for t in result.tool_results] == ["get_today_doses"]
    assert len(gateway.synthesis_calls) == 1


def test_safety_safe_disposition_with_tool_call_produces_non_empty_synthesized_reply():
    # BUILD-19's UAT explicitly flagged this exact scenario: a resolved SAFE
    # disposition whose Main Model turn calls a tool must not come back with
    # an empty reply.
    domain_tools = _DomainTools(dose_status_by_id={"dose-1": ["occ-1"]})
    plan = ModelPlan(tool_calls=(ToolCall("get_dose_status", {"dose_id": "dose-1"}),), response="")
    synthesis = ModelSynthesis(response="Ban da bo lo mot lieu sang nay; muc do an toan thap, khong can lo lang.")
    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(plan, synthesis),
        safety_domain=_SafetyDomain(_safety_decision()),
    )

    result = orchestrator.run(_request("Toi quen uong thuoc sang nay", dose_id="dose-1"), tools=_tools(domain_tools))

    assert result.intent is OrchestrationIntent.MISSED_DOSE
    assert result.safety_decision is not None
    assert result.safety_decision.outcome is SafetyOutcome.SAFE
    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response
    assert result.response
    assert len(gateway.calls) == 1
    assert len(gateway.synthesis_calls) == 1


def test_prescription_query_with_tool_call_produces_non_empty_synthesized_reply():
    plan = ModelPlan(tool_calls=(ToolCall("get_active_prescriptions", {}),), response="")
    synthesis = ModelSynthesis(response="Ban dang co 1 don thuoc dang hoat dong.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))

    result = orchestrator.run(_request("Don thuoc hien tai cua toi co gi"), tools=_tools())

    assert result.intent is OrchestrationIntent.PRESCRIPTION_INFORMATION
    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response
    assert result.response
    assert len(gateway.synthesis_calls) == 1


# ---------------------------------------------------------------------------
# 5. Multiple tool calls -> exactly one final synthesized reply
# ---------------------------------------------------------------------------


def test_multiple_tool_calls_produce_exactly_one_final_synthesized_reply():
    plan = ModelPlan(
        tool_calls=(
            ToolCall("search_drug", {"query": "para", "limit": 3}),
            ToolCall("get_today_doses", {}),
        ),
        response="",
    )
    synthesis = ModelSynthesis(response="Day la thong tin thuoc va lieu hom nay cua ban.")
    gateway = _CountingGateway(plan, synthesis)
    tools = _RuntimeTools()
    runtime = ReadOnlyAgentRuntime(gateway, limits=_runtime_limits(max_tool_calls=3, max_steps=6))

    result = runtime.run(message="tim thuoc va lieu hom nay", actor_role="patient", tools=tools)

    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response
    assert tools.calls == ["search_drug", "get_today_doses"]
    assert gateway.plan_calls == 1
    assert gateway.synthesis_calls == 1  # one synthesis call covering both tool results
    assert len(result.tool_results) == 2


def test_three_tool_prescription_flow_completes_within_the_real_production_default_budget():
    # BUILD-20 hardening: the exact scenario BUILD-19B's live staging UAT
    # found broken under the OLD code default (agent_max_steps=4, sized for
    # the pre-synthesis single-model-turn design) -- get_active_prescriptions
    # + get_today_doses + get_upcoming_doses is 3 tool calls, so 1 planning
    # step + 3 tool steps already exhausted that old default before synthesis
    # could ever run. This uses ``AgentRunLimits.from_settings`` against the
    # REAL ``Settings()`` object (not a hand-tuned test-local limit), so it
    # fails if the shipped default regresses back to being too tight -- not
    # hard-coded just to pass.
    from backend.config import get_settings

    limits = AgentRunLimits.from_settings(get_settings())
    plan = ModelPlan(
        tool_calls=(
            ToolCall("get_active_prescriptions", {}),
            ToolCall("get_today_doses", {}),
            ToolCall("get_upcoming_doses", {}),
        ),
        response="",
    )
    synthesis = ModelSynthesis(response="Ban dang co 1 don thuoc, kem lieu hom nay va sap toi.")
    gateway = _CountingGateway(plan, synthesis)
    tools = _RuntimeTools()
    runtime = ReadOnlyAgentRuntime(gateway, limits=limits)

    result = runtime.run(message="don thuoc va lieu cua toi the nao", actor_role="patient", tools=tools)

    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response
    assert tools.calls == ["get_active_prescriptions", "get_today_doses", "get_upcoming_doses"]
    assert gateway.synthesis_calls == 1
    assert len(result.tool_results) == 3


def test_three_tool_prescription_flow_still_fails_closed_under_the_old_tight_budget():
    # The historical regression, kept as a permanent negative-side proof: the
    # pre-BUILD-20 default (max_steps=4) genuinely could not fit 3 tool calls
    # plus synthesis. It must still fail *closed* (BUDGET_EXCEEDED, a fixed
    # safe message, tools already run are preserved) rather than crash or
    # fabricate a reply -- this is what actually happened live in BUILD-19B
    # before the default was raised, not a hypothetical.
    old_default_limits = AgentRunLimits(
        token_budget=4096, max_steps=4, max_model_calls=2, max_tool_calls=6,
        max_retries=1, model_timeout_seconds=15.0, run_timeout_seconds=30.0,
    )
    plan = ModelPlan(
        tool_calls=(
            ToolCall("get_active_prescriptions", {}),
            ToolCall("get_today_doses", {}),
            ToolCall("get_upcoming_doses", {}),
        ),
        response="",
    )
    gateway = _CountingGateway(plan)
    tools = _RuntimeTools()
    runtime = ReadOnlyAgentRuntime(gateway, limits=old_default_limits)

    result = runtime.run(message="don thuoc va lieu cua toi the nao", actor_role="patient", tools=tools)

    assert result.status is RunStatus.BUDGET_EXCEEDED
    assert result.response  # safe, non-empty guardrail message, never fabricated content
    assert tools.calls == ["get_active_prescriptions", "get_today_doses", "get_upcoming_doses"]  # tools still ran
    assert gateway.synthesis_calls == 0  # but never got a budget slot to synthesize


# ---------------------------------------------------------------------------
# 6. SAFETY_BLOCKED -> no synthesis call (and no planning/tool call either)
# ---------------------------------------------------------------------------


def test_safety_blocked_short_circuits_before_any_model_or_synthesis_call():
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "x", "limit": 1}),), response="should never be produced")
    gateway = _CountingGateway(plan)
    tools = _RuntimeTools()
    runtime = ReadOnlyAgentRuntime(gateway, limits=_runtime_limits())
    safety_decision = SafetyDecision(
        outcome=SafetyOutcome.SAFETY_BLOCKED, reason_code="SAFETY_DOMAIN_UNAVAILABLE", provenance="safety-domain:outage"
    )

    result = runtime.run(message="x", actor_role="patient", tools=tools, safety_decision=safety_decision)

    assert result.status is RunStatus.SAFETY_BLOCKED
    assert result.response  # safe, non-empty fallback message
    assert gateway.plan_calls == 0
    assert gateway.synthesis_calls == 0
    assert tools.calls == []


# ---------------------------------------------------------------------------
# 7. HANDOFF_CREATED -> no synthesis call
# ---------------------------------------------------------------------------


def test_handoff_created_short_circuits_before_any_model_or_synthesis_call():
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "x", "limit": 1}),), response="should never be produced")
    gateway = _CountingGateway(plan)
    tools = _RuntimeTools()
    runtime = ReadOnlyAgentRuntime(gateway, limits=_runtime_limits())
    handoff_result = AgentHandoffResult(request_id="handoff-1", status="PENDING", assigned_doctor_id=None, created=True)

    result = runtime.run(message="x", actor_role="patient", tools=tools, handoff_result=handoff_result)

    assert result.status is RunStatus.HANDOFF_CREATED
    assert result.response
    assert gateway.plan_calls == 0
    assert gateway.synthesis_calls == 0
    assert tools.calls == []


# ---------------------------------------------------------------------------
# 8. Synthesis timeout/error -> fail-closed, never fabricates a reply
# ---------------------------------------------------------------------------


def test_synthesis_failure_fails_closed_and_never_fabricates_a_reply():
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "para", "limit": 1}),), response="")
    gateway = _CountingGateway(plan, fail_synthesis_times=99)  # always fails
    tools = _RuntimeTools()
    # A no-op sleep keeps this test's real-time cost at zero while still
    # exercising the retry-with-backoff code path (BUILD-20 ``_backoff``).
    runtime = ReadOnlyAgentRuntime(
        gateway, limits=_runtime_limits(max_model_calls=3, max_retries=1), sleep=lambda _seconds: None
    )

    result = runtime.run(message="tim thuoc", actor_role="patient", tools=tools)

    assert result.status is RunStatus.FAILED
    assert result.response == "Agent tam thoi khong san sang."
    # The already-executed, already-verified tool read is preserved for
    # audit even though synthesis could not turn it into a reply.
    assert [t.name for t in result.tool_results] == ["search_drug"]
    assert gateway.plan_calls == 1
    assert gateway.synthesis_calls >= 1


# ---------------------------------------------------------------------------
# 9. Budget exceeded -> synthesis is budget-gated, not exempt from limits
# ---------------------------------------------------------------------------


def test_synthesis_is_budget_gated_when_no_model_calls_remain_after_planning():
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "para", "limit": 1}),), response="")
    gateway = _CountingGateway(plan)
    tools = _RuntimeTools()
    # Exactly enough model-call budget for the planning call, none left for
    # the synthesis call: BUILD-19B's synthesis turn must be bound by the
    # same budgets as planning, not exempt from them.
    runtime = ReadOnlyAgentRuntime(gateway, limits=_runtime_limits(max_model_calls=1, max_steps=6))

    result = runtime.run(message="tim thuoc", actor_role="patient", tools=tools)

    assert result.status is RunStatus.BUDGET_EXCEEDED
    assert tools.calls == ["search_drug"]  # the tool itself did run
    assert gateway.synthesis_calls == 0  # synthesis never got a budget slot
    assert result.response  # still a safe, non-empty guardrail message


# ---------------------------------------------------------------------------
# 10. Checkpoint resume must not replay the tool call or the synthesis call
# ---------------------------------------------------------------------------

TABLES = (AgentRun.__table__, AgentRunCheckpoint.__table__)


@pytest.fixture
def checkpoint_db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_checkpoint_resume_after_completion_does_not_replay_tool_or_synthesis_calls(checkpoint_db):
    agent_run_id = "run-synthesis-resume-1"
    plan = ModelPlan(tool_calls=(ToolCall("search_drug", {"query": "para", "limit": 3}),), response="")
    synthesis = ModelSynthesis(response="Paracetamol la thuoc ha sot pho bien.")
    orchestrator, gateway = _orchestrator(model_gateway=_SpyModelGateway(plan, synthesis))
    tools = _tools()
    request = _request("Cho toi biet thong tin ve thuoc paracetamol", agent_run_id=agent_run_id)

    result = orchestrator.run(request, tools=tools, checkpoint_db=checkpoint_db)

    assert result.status is RunStatus.COMPLETED
    assert result.response == synthesis.response
    assert len(gateway.calls) == 1
    assert len(gateway.synthesis_calls) == 1

    # A retried/duplicated request for the same agent_run_id (e.g. a client
    # timeout-and-retry after the server had actually finished) must not be
    # allowed to replay the tool call or the synthesis call: the checkpoint
    # is already terminal, so the resume attempt is rejected before the
    # runtime -- and therefore the tools and the model -- are ever re-entered.
    with pytest.raises(CheckpointTerminalError):
        orchestrator.run(request, tools=tools, checkpoint_db=checkpoint_db)

    assert len(gateway.calls) == 1  # still exactly one -- no replay
    assert len(gateway.synthesis_calls) == 1  # still exactly one -- no replay
