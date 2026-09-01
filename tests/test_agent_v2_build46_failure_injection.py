"""BUILD-46 section 12: failure-boundary injection tests at the runtime
level (not just the Tool Gateway unit-test level already covered by
test_agent_v2_tools.py). Confirms the invariant the spec requires for
every injected failure: a safe TERMINAL status (never stuck), no
fabricated success, a correct durable error_code, and a fixed, safe
user-facing message -- never a raw exception/stack trace.
"""

from __future__ import annotations

from backend.agents.v2.model_gateway import ModelPlan, ModelSynthesis, StaticModelGateway, ToolCall
from backend.agents.v2.runtime import ERROR_CODE_TOOL_ERROR, AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.tools import ToolExecutionError, ToolGateway, ToolResult


def _limits(**changes) -> AgentRunLimits:
    values = {
        "token_budget": 1000,
        "max_steps": 5,
        "max_model_calls": 2,
        "max_tool_calls": 3,
        "max_retries": 1,
        "model_timeout_seconds": 10.0,
        "run_timeout_seconds": 20.0,
    }
    values.update(changes)
    return AgentRunLimits(**values)


class _RaisingGateway(ToolGateway):
    """Simulates a real ToolGateway.execute() failure -- the exact
    exception class the real gateway raises, not a bare ValueError."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls: list[str] = []

    def execute(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append(name)
        raise self._exc


# ---------------------------------------------------------------------------
# Malformed model tool arguments (the exact class Fix A closed for
# search_drug) -- confirmed safe at the runtime level, not just the gateway
# unit-test level.
# ---------------------------------------------------------------------------


def test_invalid_tool_arguments_from_the_model_is_a_safe_terminal_failure_never_stuck():
    runtime = ReadOnlyAgentRuntime(
        StaticModelGateway(
            ModelPlan((ToolCall("search_drug", {"query": "para", "limit": 999}),), "ignored"),
            ModelSynthesis(free_prose="unreachable"),
        ),
        limits=_limits(),
    )
    tools = _RaisingGateway(ToolExecutionError("INVALID_TOOL_ARGUMENTS"))
    result = runtime.run(message="tim thuoc", actor_role="patient", tools=tools)

    assert result.status == RunStatus.FAILED, "must be a real terminal status, never left non-terminal"
    assert result.error_code == ERROR_CODE_TOOL_ERROR
    assert result.response == "Agent không thể thực hiện yêu cầu này."
    # No raw exception text/stack trace ever reaches the user-facing reply.
    assert "INVALID_TOOL_ARGUMENTS" not in result.response
    assert "Traceback" not in result.response


# ---------------------------------------------------------------------------
# A genuine domain/infrastructure failure inside a tool call (simulates a
# DB error, network error, or unexpected exception a tool's own domain
# adapter raises) -- the ToolGateway itself already converts this to
# TOOL_UNAVAILABLE (test_agent_v2_tools.py::
# test_domain_failure_and_malformed_output_are_sanitized); this confirms
# the runtime layer ABOVE the gateway degrades the same safe way too.
# ---------------------------------------------------------------------------


def test_tool_unavailable_from_a_domain_failure_is_a_safe_terminal_failure_never_stuck():
    runtime = ReadOnlyAgentRuntime(
        StaticModelGateway(
            ModelPlan((ToolCall("get_today_doses", {}),), "ignored"),
            ModelSynthesis(free_prose="unreachable"),
        ),
        limits=_limits(),
    )
    tools = _RaisingGateway(ToolExecutionError("TOOL_UNAVAILABLE"))
    result = runtime.run(message="thuoc hom nay", actor_role="patient", tools=tools)

    assert result.status == RunStatus.FAILED
    assert result.error_code == ERROR_CODE_TOOL_ERROR
    assert result.response == "Agent không thể thực hiện yêu cầu này."


# ---------------------------------------------------------------------------
# The run's own metrics/tool_calls must reflect the attempted-but-failed
# call was never silently double-counted or left in an ambiguous state.
# ---------------------------------------------------------------------------


def test_failed_tool_call_does_not_leave_ambiguous_or_partial_metrics():
    runtime = ReadOnlyAgentRuntime(
        StaticModelGateway(
            ModelPlan((ToolCall("search_drug", {"query": "para", "limit": 5}),), "ignored"),
            ModelSynthesis(free_prose="unreachable"),
        ),
        limits=_limits(),
    )
    tools = _RaisingGateway(ToolExecutionError("INVALID_TOOL_ARGUMENTS"))
    result = runtime.run(message="tim thuoc", actor_role="patient", tools=tools)

    # Exactly one attempted call, no synthesis step reached (never a
    # fabricated "completed" reply layered on top of a failed tool call).
    assert tools.calls == ["search_drug"]
    assert result.metrics.tool_calls == 0, "a FAILED call must not be counted as a successful tool_call"
