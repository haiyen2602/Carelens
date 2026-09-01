"""BUILD-1/3 tests: authorization, bounded execution, and terminal guardrails."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.agents.v2.authorization import require_agent_patient_access
from backend.agents.v2.model_gateway import ModelPlan, ModelSynthesis, ModelUsage, StaticModelGateway, ToolCall
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus, SafetyContext
from backend.agents.v2.tools import ToolGateway, ToolResult
from backend.api.security import CurrentUser


def _limits(**changes) -> AgentRunLimits:
    values = {
        "token_budget": 100,
        "max_steps": 5,
        "max_model_calls": 2,
        "max_tool_calls": 3,
        "max_retries": 1,
        "model_timeout_seconds": 10.0,
        "run_timeout_seconds": 20.0,
    }
    values.update(changes)
    return AgentRunLimits(**values)


class _Gateway(ToolGateway):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append(name)
        if name != "search_drug":
            raise ValueError("TOOL_NOT_ALLOWED")
        return ToolResult(name=name, data={"items": []})


def test_runtime_executes_only_allowlisted_read_tool():
    # A tool call needs a planning step, a tool-execution step, and a
    # synthesis step (BUILD-19B): max_steps=3 is the tight budget for one
    # tool call end to end.
    runtime = ReadOnlyAgentRuntime(
        StaticModelGateway(
            ModelPlan((ToolCall("search_drug", {"query": "para"}),), "done"),
            ModelSynthesis(free_prose="Day la thong tin thuoc ban can."),
        ),
        limits=_limits(max_steps=3),
    )
    tools = _Gateway()
    result = runtime.run(message="tim thuoc", actor_role="patient", tools=tools)
    assert result.status == RunStatus.COMPLETED
    # The final reply must be the post-tool synthesis text, never the
    # pre-tool planning turn's own output_text (the BUILD-19 defect).
    assert result.response == "Day la thong tin thuoc ban can."
    assert tools.calls == ["search_drug"]
    assert (result.metrics.steps, result.metrics.model_calls, result.metrics.tool_calls) == (3, 2, 1)


def test_runtime_fails_closed_for_unapproved_tool():
    runtime = ReadOnlyAgentRuntime(
        StaticModelGateway(ModelPlan((ToolCall("mark_dose_taken", {}),), "ignored")), limits=_limits(max_steps=2)
    )
    result = runtime.run(message="da uong", actor_role="patient", tools=_Gateway())
    assert result.status == RunStatus.FAILED


def test_runtime_enforces_tool_budget_before_execution():
    runtime = ReadOnlyAgentRuntime(
        StaticModelGateway(ModelPlan((ToolCall("search_drug", {}), ToolCall("search_drug", {"query": "para"})), "ignored")),
        limits=_limits(max_tool_calls=1),
    )
    tools = _Gateway()
    result = runtime.run(message="x", actor_role="patient", tools=tools)
    assert result.status == RunStatus.BUDGET_EXCEEDED
    assert tools.calls == []


def test_token_budget_stops_before_any_tool_execution():
    plan = ModelPlan(response="ignored", usage=ModelUsage(input_tokens=60, output_tokens=50))
    result = ReadOnlyAgentRuntime(StaticModelGateway(plan), limits=_limits(token_budget=100)).run(
        message="x", actor_role="patient", tools=_Gateway()
    )
    assert result.status == RunStatus.BUDGET_EXCEEDED
    assert result.metrics.token_total == 110


def test_unresolved_safety_becomes_safety_blocked_when_token_budget_is_exceeded():
    plan = ModelPlan(response="ignored", usage=ModelUsage(input_tokens=60, output_tokens=50))
    result = ReadOnlyAgentRuntime(StaticModelGateway(plan), limits=_limits(token_budget=100)).run(
        message="x", actor_role="patient", tools=_Gateway(), safety_context=SafetyContext.UNRESOLVED
    )
    assert result.status == RunStatus.SAFETY_BLOCKED


def test_step_and_model_call_limits_stop_before_provider_or_tool_overrun():
    tool_plan = ModelPlan((ToolCall("search_drug", {}),), "ignored")
    step_result = ReadOnlyAgentRuntime(StaticModelGateway(tool_plan), limits=_limits(max_steps=1)).run(
        message="x", actor_role="patient", tools=_Gateway()
    )
    model_result = ReadOnlyAgentRuntime(StaticModelGateway(tool_plan), limits=_limits(max_model_calls=0)).run(
        message="x", actor_role="patient", tools=_Gateway()
    )
    assert step_result.status == model_result.status == RunStatus.BUDGET_EXCEEDED


class _FlakyModelGateway:
    def __init__(self, failures: int, plan: ModelPlan | None = None) -> None:
        self.failures = failures
        self.calls = 0
        self.plan = plan or ModelPlan(response="ok")

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("provider failure")
        return self.plan


def test_model_retry_is_bounded_and_counts_every_model_call():
    gateway = _FlakyModelGateway(1)
    # BUILD-20: a no-op sleep keeps this test's real-time cost at zero while
    # still exercising the retry-with-backoff code path (see ``_backoff``).
    result = ReadOnlyAgentRuntime(
        gateway, limits=_limits(max_model_calls=2, max_retries=1), sleep=lambda _seconds: None
    ).run(message="x", actor_role="patient", tools=_Gateway())
    assert result.status == RunStatus.COMPLETED
    assert (gateway.calls, result.metrics.model_calls, result.metrics.retries) == (2, 2, 1)


def test_model_failure_after_retry_budget_is_non_sensitive_terminal_failure():
    gateway = _FlakyModelGateway(2)
    result = ReadOnlyAgentRuntime(
        gateway, limits=_limits(max_model_calls=2, max_retries=1), sleep=lambda _seconds: None
    ).run(message="x", actor_role="patient", tools=_Gateway())
    assert result.status == RunStatus.FAILED
    assert result.response == "Agent tạm thời không sẵn sàng."


def test_model_retry_backs_off_before_retrying_a_transient_failure():
    # BUILD-20 hardening: a failed model call must not be retried immediately
    # -- a small bounded pause gives a transient provider error (rate limit,
    # 5xx) a chance to clear instead of being hammered again right away.
    gateway = _FlakyModelGateway(1)
    sleeps: list[float] = []
    result = ReadOnlyAgentRuntime(
        gateway, limits=_limits(max_model_calls=2, max_retries=1), sleep=sleeps.append
    ).run(message="x", actor_role="patient", tools=_Gateway())
    assert result.status == RunStatus.COMPLETED
    assert sleeps == [0.2]  # exactly one retry -> exactly one backoff pause


def test_model_retry_backoff_is_clamped_to_the_remaining_run_timeout_budget():
    # A run with very little time budget left must not let its own backoff
    # pause exceed what remains -- the pause is clamped down, never the full
    # (larger) default backoff.
    gateway = _FlakyModelGateway(1)
    sleeps: list[float] = []
    result = ReadOnlyAgentRuntime(
        gateway,
        limits=_limits(max_model_calls=2, max_retries=1, run_timeout_seconds=0.05),
        clock=lambda: 0.0,  # elapsed time never advances -> "remaining" stays exactly the budget
        sleep=sleeps.append,
    ).run(message="x", actor_role="patient", tools=_Gateway())
    assert result.status == RunStatus.COMPLETED  # the flaky gateway still recovers on retry
    assert sleeps == [0.05]  # clamped down from the 0.2s default, not eliminated


class _SlowModelGateway:
    def __init__(self, now: list[float]) -> None:
        self.now = now

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        self.now[0] += 11
        return ModelPlan(response="late")


def test_model_timeout_and_unresolved_safety_fail_closed():
    now = [0.0]
    timeout = ReadOnlyAgentRuntime(
        _SlowModelGateway(now), limits=_limits(model_timeout_seconds=5), clock=lambda: now[0]
    ).run(message="x", actor_role="patient", tools=_Gateway())
    now[0] = 0.0
    safety_blocked = ReadOnlyAgentRuntime(
        _SlowModelGateway(now), limits=_limits(model_timeout_seconds=5), clock=lambda: now[0]
    ).run(message="x", actor_role="patient", tools=_Gateway(), safety_context=SafetyContext.UNRESOLVED)
    assert timeout.status == RunStatus.TIMEOUT
    assert safety_blocked.status == RunStatus.SAFETY_BLOCKED


def test_safety_blocked_message_distinguishes_not_yet_due_from_domain_outage():
    # BUILD-20 (BUILD-19's P2): the fixed-string message must vary with the
    # domain's reason_code -- "too early to ask" reads differently from
    # "something is broken" -- while both still terminate SAFETY_BLOCKED.
    from backend.agents.v2.safety import SafetyDecision, SafetyOutcome

    not_yet_due = ReadOnlyAgentRuntime(StaticModelGateway(ModelPlan(response="never reached")), limits=_limits()).run(
        message="x",
        actor_role="patient",
        tools=_Gateway(),
        safety_decision=SafetyDecision(
            outcome=SafetyOutcome.SAFETY_BLOCKED, reason_code="DOSE_NOT_YET_ASSESSABLE", provenance="safety-domain:not-yet-due"
        ),
    )
    outage = ReadOnlyAgentRuntime(StaticModelGateway(ModelPlan(response="never reached")), limits=_limits()).run(
        message="x",
        actor_role="patient",
        tools=_Gateway(),
        safety_decision=SafetyDecision(
            outcome=SafetyOutcome.SAFETY_BLOCKED, reason_code="SAFETY_DOMAIN_UNAVAILABLE", provenance="safety-domain:unavailable"
        ),
    )
    assert not_yet_due.status == outage.status == RunStatus.SAFETY_BLOCKED
    assert not_yet_due.response != outage.response
    assert not_yet_due.response and outage.response  # neither is ever empty


def test_confusable_cyrillic_in_the_final_reply_is_normalized_to_latin():
    # BUILD-20 (BUILD-19's P2): reproduces the exact live defect -- "Các
    # **тип** chính:" (Cyrillic т/и/п) instead of the intended Latin "tip".
    plan = ModelPlan(response="Các **тип** chính: Тіps để uống thuốc đúng giờ.")
    result = ReadOnlyAgentRuntime(StaticModelGateway(plan), limits=_limits()).run(
        message="x", actor_role="patient", tools=_Gateway()
    )
    assert result.status == RunStatus.COMPLETED
    assert result.response == "Các **tip** chính: Tips để uống thuốc đúng giờ."
    assert not any("а" <= ch <= "я" or "А" <= ch <= "Я" for ch in result.response)  # no stray Cyrillic remains


def test_loop_is_detected_before_duplicate_tool_execution():
    plan = ModelPlan((ToolCall("search_drug", {"query": "para"}), ToolCall("search_drug", {"query": "para"})), "ignored")
    tools = _Gateway()
    result = ReadOnlyAgentRuntime(StaticModelGateway(plan), limits=_limits()).run(
        message="x", actor_role="patient", tools=tools
    )
    assert result.status == RunStatus.BUDGET_EXCEEDED
    assert tools.calls == []


# ---------------------------------------------------------------------------
# TASK-V2.5-004: renderer_enabled wiring. Default (renderer_enabled=False,
# every test above) must stay byte-identical -- only a runtime explicitly
# constructed with renderer_enabled=True exercises assemble_reply/RENDERER.
# ---------------------------------------------------------------------------


class _DrugNameGateway:
    """Tool-loop gateway whose search_drug result maps into RenderableFactSlots
    (drug_name). synthesize_read_only's own policy/fact_slots args are
    ignored here -- this double asserts the RUNTIME builds and applies them
    via assemble_reply, not that the gateway itself receives them correctly
    (that is already covered by tests/test_agent_v2_model_gateway.py)."""

    def __init__(self, free_prose: str) -> None:
        self._free_prose = free_prose
        self.received_policy = "unset"
        self.received_fact_slots = "unset"

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return ModelPlan((ToolCall("search_drug", {"query": "para"}),), "ignored")

    def synthesize_read_only(self, *, message, actor_role, evidence, policy=None, fact_slots=None):
        self.received_policy = policy
        self.received_fact_slots = fact_slots
        return ModelSynthesis(free_prose=self._free_prose)


class _DrugNameTools:
    """Real search_drug output shape (backend/agents/v2/tools.py::
    SearchDrugOutput) -- a single, server-confirmed unique match."""

    def execute(self, name, arguments):
        return ToolResult(
            name=name,
            data={
                "items": [{"legacy_drug_id": "drug-1", "name": "Paracetamol", "dosage_form": "vien nen", "route": "uong"}],
                "unique_match_legacy_drug_id": "drug-1",
            },
            provenance="canonical-drug-v2",
        )


def test_renderer_disabled_by_default_leaves_gateway_policy_args_none():
    gateway = _DrugNameGateway("Day la thong tin ban can.")
    result = ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=3)).run(
        message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools()
    )
    assert result.status == RunStatus.COMPLETED
    assert result.response == "Day la thong tin ban can."
    assert gateway.received_policy is None
    assert gateway.received_fact_slots is None


def test_renderer_enabled_passes_policy_and_fact_slots_to_gateway():
    gateway = _DrugNameGateway("Day la thong tin ban can.")
    ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=3), renderer_enabled=True).run(
        message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools()
    )
    assert gateway.received_policy is not None
    assert gateway.received_fact_slots is not None
    assert gateway.received_fact_slots.drug_name == "Paracetamol"


def test_renderer_enabled_assembles_free_prose_with_protected_fact_verbatim():
    gateway = _DrugNameGateway("Day la thong tin ban can biet ve thuoc nay.")
    result = ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=3), renderer_enabled=True).run(
        message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools()
    )
    assert result.status == RunStatus.COMPLETED
    assert "Day la thong tin ban can biet ve thuoc nay." in result.response
    assert "Paracetamol" in result.response


def test_renderer_disabled_never_appends_a_fact_line_even_when_evidence_has_one():
    """Non-regression: with the flag off, today's exact behavior -- the
    model's own full text, verbatim, nothing appended -- must be preserved,
    even though the SAME evidence would populate a fact slot if the flag
    were on."""
    gateway = _DrugNameGateway("Day la thong tin ban can.")
    result = ReadOnlyAgentRuntime(gateway, limits=_limits(max_steps=3)).run(
        message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools()
    )
    assert result.response == "Day la thong tin ban can."


# ---------------------------------------------------------------------------
# TASK-V2.5-004 CP1 contract mục 5: fallback/EmptySynthesisError test plan,
# specifically at ModelRole.RENDERER (renderer_enabled=True). Same fail-
# closed mechanism as MAIN (unchanged) -- these tests exist to prove that
# holds for the renderer path too, and that a FAILED/timed-out renderer turn
# never leaks a protected fact through assemble_reply by some other path.
# ---------------------------------------------------------------------------


class _RendererTimeoutGateway:
    """search_drug succeeds; the renderer synthesis turn always times out."""

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return ModelPlan((ToolCall("search_drug", {"query": "para"}),), "ignored")

    def synthesize_read_only(self, *, message, actor_role, evidence, policy=None, fact_slots=None):
        import openai

        raise openai.APITimeoutError(request=SimpleNamespace())


def test_renderer_role_timeout_fails_closed_same_path_as_main_never_leaks_a_fact():
    """Test-plan item 1 (mục 5): a simulated timeout at ModelRole.RENDERER
    must exhaust the existing bounded-retry path and end FAILED with the
    fixed fallback text -- never an empty free_prose slipping through
    assemble_reply, and never the tool result's drug name leaking through
    some other path."""
    result = ReadOnlyAgentRuntime(
        _RendererTimeoutGateway(), limits=_limits(max_steps=3, max_retries=0), renderer_enabled=True
    ).run(message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools())
    assert result.status == RunStatus.FAILED
    assert result.response == "Agent tạm thời không sẵn sàng."
    assert "Paracetamol" not in result.response


class _RendererEmptyFreeProseGateway:
    """search_drug succeeds; the renderer synthesis turn always raises
    EmptySynthesisError (mirrors OpenAIModelGateway's own real behavior for
    an empty/whitespace-only free_prose -- see test_agent_v2_model_gateway.py
    ::test_synthesize_read_only_renderer_path_fails_closed_on_empty_free_prose)."""

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return ModelPlan((ToolCall("search_drug", {"query": "para"}),), "ignored")

    def synthesize_read_only(self, *, message, actor_role, evidence, policy=None, fact_slots=None):
        from backend.agents.v2.model_gateway import EmptySynthesisError

        raise EmptySynthesisError("MODEL_SYNTHESIS_EMPTY")


def test_renderer_role_empty_free_prose_fails_closed_same_path_as_main_never_leaks_a_fact():
    """Test-plan item 2 (mục 5): empty free_prose at ModelRole.RENDERER goes
    through the exact same EmptySynthesisError -> ERROR_CODE_EMPTY_REPLY ->
    RunStatus.FAILED path as MAIN's own empty-output_text case."""
    result = ReadOnlyAgentRuntime(
        _RendererEmptyFreeProseGateway(), limits=_limits(max_steps=3, max_retries=0), renderer_enabled=True
    ).run(message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools())
    assert result.status == RunStatus.FAILED
    assert result.error_code == "EMPTY_REPLY"
    assert result.response == "Agent tạm thời không sẵn sàng."
    assert "Paracetamol" not in result.response


def test_assemble_reply_is_never_invoked_when_the_renderer_turn_fails(monkeypatch):
    """Test-plan item 3 (mục 5), proven directly rather than only inferred
    from the fixed fallback text above: assemble_reply (the one place a
    protected fact is inserted) must not even be CALLED on a FAILED/timed-out
    renderer turn -- a protected fact must never reach the composition step
    at all when the model call itself did not succeed."""
    import backend.agents.v2.runtime as runtime_module

    def _poisoned_assemble_reply(*_args, **_kwargs):
        raise AssertionError("assemble_reply must not be called when the renderer turn failed")

    monkeypatch.setattr(runtime_module, "assemble_reply", _poisoned_assemble_reply)

    result = ReadOnlyAgentRuntime(
        _RendererTimeoutGateway(), limits=_limits(max_steps=3, max_retries=0), renderer_enabled=True
    ).run(message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools())
    assert result.status == RunStatus.FAILED  # got here without the poisoned assemble_reply raising


def test_renderer_role_does_not_increase_model_call_budget_on_retry():
    """Test-plan item 4 (mục 5): AGENT_MAX_MODEL_CALLS is unchanged (still 2,
    backend/config.py:435) -- the renderer replaces the existing synthesis
    call within this budget, it never adds a new call slot to "save" an
    empty free_prose."""
    from backend.config import Settings

    assert Settings.model_fields["agent_max_model_calls"].default == 2

    result = ReadOnlyAgentRuntime(
        _RendererTimeoutGateway(), limits=_limits(max_steps=3, max_model_calls=2, max_retries=5), renderer_enabled=True
    ).run(message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools())
    assert result.status == RunStatus.FAILED
    assert result.metrics.model_calls == 2  # plan_read_only (1) + exactly one synthesis attempt (1), budget enforced


class _RendererProhibitedClaimLeakGateway:
    """search_drug succeeds; the renderer synthesis turn always leaks a
    prohibited claim (mirrors OpenAIModelGateway's own real fail-closed
    behavior -- see test_agent_v2_model_gateway.py::
    test_synthesize_read_only_renderer_path_fails_closed_when_model_
    hallucinates_a_prohibited_claim)."""

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return ModelPlan((ToolCall("search_drug", {"query": "para"}),), "ignored")

    def synthesize_read_only(self, *, message, actor_role, evidence, policy=None, fact_slots=None):
        from backend.agents.v2.model_gateway import ProhibitedClaimLeakError

        raise ProhibitedClaimLeakError("PROHIBITED_CLAIM_LEAK:dose_time")


def test_default_response_policy_prohibits_all_four_protected_claim_categories():
    """ResponsePolicy is a real enforced input (owner requirement): the
    generic tool-loop call site's own default must actually list every
    category free_prose should never need -- an empty
    prohibited_claim_categories would make validate_free_prose a no-op."""
    policy = ReadOnlyAgentRuntime._default_response_policy()
    assert set(policy.prohibited_claim_categories) == {"dose_time", "dose_status", "medication_identity", "handoff_state"}


def test_renderer_role_prohibited_claim_leak_fails_closed_same_path_as_main_never_leaks_a_fact():
    """Test-plan item 5 (owner-required adversarial invariant): a model that
    hallucinates a prohibited claim from nothing must fail closed through
    the same bounded-retry-then-FAILED path, with its own distinct error
    code (not conflated with EMPTY_REPLY -- this is a different failure
    mode: the model said something, just something unauthorized)."""
    result = ReadOnlyAgentRuntime(
        _RendererProhibitedClaimLeakGateway(), limits=_limits(max_steps=3, max_retries=0), renderer_enabled=True
    ).run(message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools())
    assert result.status == RunStatus.FAILED
    assert result.error_code == "PROHIBITED_CLAIM_LEAK"
    assert result.response == "Agent tạm thời không sẵn sàng."
    assert "Paracetamol" not in result.response


def test_assemble_reply_is_never_invoked_when_the_renderer_turn_leaks_a_prohibited_claim(monkeypatch):
    import backend.agents.v2.runtime as runtime_module

    def _poisoned_assemble_reply(*_args, **_kwargs):
        raise AssertionError("assemble_reply must not be called when the renderer turn leaked a prohibited claim")

    monkeypatch.setattr(runtime_module, "assemble_reply", _poisoned_assemble_reply)

    result = ReadOnlyAgentRuntime(
        _RendererProhibitedClaimLeakGateway(), limits=_limits(max_steps=3, max_retries=0), renderer_enabled=True
    ).run(message="thuoc nay la gi", actor_role="patient", tools=_DrugNameTools())
    assert result.status == RunStatus.FAILED  # got here without the poisoned assemble_reply raising


def test_cancel_and_handoff_required_are_terminal_without_a_write_action():
    runtime = ReadOnlyAgentRuntime(StaticModelGateway(ModelPlan(response="ignored")), limits=_limits())
    cancelled = runtime.run(message="x", actor_role="patient", tools=_Gateway(), is_cancelled=lambda: True)
    handoff = runtime.run(message="x", actor_role="patient", tools=_Gateway(), handoff_required=True)
    assert cancelled.status == RunStatus.CANCELLED
    assert handoff.status == RunStatus.HANDOFF_REQUIRED


def test_terminal_state_contract_is_exact_and_reserves_handoff_created_for_a_later_domain():
    assert {status.value for status in RunStatus} == {
        "COMPLETED",
        "FAILED",
        "BUDGET_EXCEEDED",
        "TIMEOUT",
        "SAFETY_BLOCKED",
        "HANDOFF_REQUIRED",
        "HANDOFF_CREATED",
        "CANCELLED",
    }


def test_limits_are_read_from_settings_not_runtime_constants():
    settings = SimpleNamespace(
        agent_token_budget=17,
        agent_max_steps=3,
        agent_max_model_calls=2,
        agent_max_tool_calls=1,
        agent_max_retries=0,
        agent_model_timeout_seconds=4.0,
        agent_run_timeout_seconds=9.0,
    )
    assert AgentRunLimits.from_settings(settings) == _limits(
        token_budget=17,
        max_steps=3,
        max_model_calls=2,
        max_tool_calls=1,
        max_retries=0,
        model_timeout_seconds=4.0,
        run_timeout_seconds=9.0,
    )


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _AuthDb:
    def __init__(self, *, patient=True, relation=None):
        self.patient = patient
        self.relation = relation

    def get(self, _model, _patient_id):
        return object() if self.patient else None

    def execute(self, _query):
        return _Scalar(self.relation)


def test_patient_is_limited_to_jwt_patient():
    actor = CurrentUser(id="account", role="patient", patient_id="p-1", doctor_id=None)
    assert require_agent_patient_access(_AuthDb(), actor, "p-1") == "p-1"
    with pytest.raises(HTTPException) as exc:
        require_agent_patient_access(_AuthDb(), actor, "p-2")
    assert exc.value.status_code == 403


def test_caregiver_and_doctor_require_an_approved_relationship():
    caregiver = CurrentUser(id="caregiver", role="caregiver", patient_id=None, doctor_id=None)
    doctor = CurrentUser(id="doctor-account", role="doctor", patient_id=None, doctor_id="doctor-1")
    with pytest.raises(HTTPException) as caregiver_denied:
        require_agent_patient_access(_AuthDb(relation=None), caregiver, "p-1")
    with pytest.raises(HTTPException) as doctor_denied:
        require_agent_patient_access(_AuthDb(relation=None), doctor, "p-1")
    assert caregiver_denied.value.status_code == doctor_denied.value.status_code == 403
    assert require_agent_patient_access(_AuthDb(relation="link"), caregiver, "p-1") == "p-1"
    assert require_agent_patient_access(_AuthDb(relation="watch"), doctor, "p-1") == "p-1"
