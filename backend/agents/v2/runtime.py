"""Bounded, fail-closed execution for the isolated read-only Agent V2 path."""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import openai

from backend.agents.v2.handoff import AgentHandoffResult
from backend.agents.v2.model_gateway import (
    EmptySynthesisError,
    ModelGateway,
    ModelPlan,
    ModelRole,
    ModelSynthesis,
    SynthesisEvidence,
)
from backend.agents.v2.observability import AgentTelemetry, TraceComponent, TraceContext
from backend.agents.v2.safety import SafetyDecision, SafetyOutcome
from backend.agents.v2.tools import ToolGateway, ToolResult

# BUILD-32: canonical run-level error taxonomy (BUILD-32-TO-36-MASTER-PLAN.md
# §9, plus REQUEST_TIMEOUT per §7's separate timeout sub-taxonomy -- the plan
# calls its §9 list a floor, "chuẩn hóa tối thiểu"). `None` on a `RunResult`
# means the run was not an error/timeout state (COMPLETED, CANCELLED,
# SAFETY_BLOCKED, HANDOFF_REQUIRED, HANDOFF_CREATED -- none of those are
# failures of the agent itself). `TOOL_TIMEOUT`/`RETRIEVAL_TIMEOUT` are part
# of the taxonomy but never emitted by this runtime: there is no real
# per-tool/per-retrieval deadline distinct from the overall run timeout today
# (see backend.agents.v2.tools.ToolGateway), so inventing that distinction
# here would be a fabricated metric.
ERROR_CODE_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
ERROR_CODE_MODEL_ERROR = "MODEL_ERROR"
ERROR_CODE_MODEL_TIMEOUT = "MODEL_TIMEOUT"
ERROR_CODE_REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
ERROR_CODE_TOOL_ERROR = "TOOL_ERROR"
ERROR_CODE_EMPTY_REPLY = "EMPTY_REPLY"

# BUILD-20 (BUILD-19's P2): the Main Model occasionally emits a visually-
# confusable Cyrillic character where it plainly means the Latin lookalike
# (observed live: "Các **тип** chính:" instead of "Các **tip** chính:" --
# Cyrillic т/и/п, not Latin t/i/p). Vietnamese medical replies never contain
# genuine Cyrillic content, so replacing only this small, deliberately narrow
# set of confusable code points is safe and cannot corrupt legitimate text.
# This is a display/encoding cleanup, not a safety mechanism -- it runs on
# the final synthesized reply only, never on tool/retrieval evidence or
# anything Safety Domain-authored.
#
# BUILD-24I (V2 RC hardening, Phase 1 item 5) added "к"/"в" (BUILD-24C golden
# query_id 46/101: "thuốc đang aкtiвe"/"aкtiв" -- lowercase Cyrillic к/в for
# Latin k/v -- the table had uppercase К/В but not their lowercase forms).
# Kept deliberately narrow and evidence-based, same as every entry above: add
# only what has actually been observed live, not a theoretical full
# Cyrillic-Latin confusable table.
_CYRILLIC_HOMOGLYPHS: dict[str, str] = {
    # Live-observed defect (BUILD-19): "тип" for "tip" -- т/и/п -> t/i/p.
    "т": "t", "и": "i", "п": "p",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ѕ": "s", "ј": "j", "ԁ": "d", "ѡ": "w",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "Ѕ": "S", "І": "I", "Ј": "J",
    # BUILD-24I: lowercase forms live-observed but missing before this build.
    "к": "k", "в": "v",
}
_CYRILLIC_HOMOGLYPH_TABLE = str.maketrans(_CYRILLIC_HOMOGLYPHS)


def _normalize_confusable_cyrillic(text: str) -> str:
    return text.translate(_CYRILLIC_HOMOGLYPH_TABLE)


# BUILD-24I: unlike a Cyrillic homoglyph (a single character that visually
# substitutes for a Latin lookalike, fixed by direct character replacement
# above), the Main Model has also been observed inserting an entire foreign-
# script *word* mid-sentence with no Latin equivalent to substitute -- BUILD-
# 24C golden query_id 76: "do OpenAI உருவ/ tạo ra" (Tamil, meaning roughly
# "form/create"); query_id 92: "toa thuốc đang सक्रिय" (Devanagari, meaning
# "active") *and*, in the same reply, "đọc dữ liệu בלבד" (Hebrew, meaning
# "only") -- confirmed by decoding the raw golden-set JSON code point by code
# point, not just the report's own narrative summary. This app's output is
# always Vietnamese/English in Latin script; none of these scripts has ever
# been genuine, expected content here, so the only sound fix is to remove
# the foreign-script run outright (there is no single correct Latin word to
# substitute for a whole leaked foreign word) and tidy up the
# whitespace/punctuation left behind.
_DISALLOWED_SCRIPT_RANGES: tuple[tuple[int, int], ...] = (
    (0x0590, 0x05FF),  # Hebrew (query_id 92)
    (0x0900, 0x097F),  # Devanagari (query_id 92)
    (0x0B80, 0x0BFF),  # Tamil (query_id 76)
)


def _is_disallowed_script_char(ch: str) -> bool:
    code_point = ord(ch)
    return any(lo <= code_point <= hi for lo, hi in _DISALLOWED_SCRIPT_RANGES)


def _strip_disallowed_scripts(text: str) -> str:
    if not any(_is_disallowed_script_char(ch) for ch in text):
        return text
    cleaned = "".join(ch for ch in text if not _is_disallowed_script_char(ch))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)  # collapse a run of spaces the removal left behind
    cleaned = re.sub(r"[ \t]+([.,;:!?)\]])", r"\1", cleaned)  # "word ." -> "word."
    cleaned = re.sub(r"([/(\[])[ \t]+", r"\1", cleaned)  # "( word" -> "(word"
    return cleaned.strip()


# BUILD-24I (golden query_id 46; also observed in 57/58, now moot -- both are
# ACUTE_DANGER_ESCALATION messages since BUILD-24E and never reach the Main
# Model any more): the Main Model occasionally regenerates its own answer a
# second time within the same completion, back-to-back, often with no
# separator at all -- the reply's own first sentence reappears verbatim
# later in the text, sometimes run directly into the prior sentence's
# closing period with no space ("...thay đổi.Tôi không thể..."). BUILD-24C's
# own analysis: this happens *inside* a single model completion, not from
# any orchestration-level concatenation (`plan.response` is never
# concatenated with `synthesis.response`) -- a generation-quality issue this
# codebase cannot prevent at the source, only detect and clean up after the
# fact. Detected by finding the reply's own first sentence again later in
# the text; when found, the reply is truncated to its first occurrence, since
# the second occurrence is by definition already contained in what preceded
# it.
_FIRST_SENTENCE_RE = re.compile(r"^(.{8,200}?[.!?])(?:\s|$)")


def _dedupe_self_repeated_reply(text: str) -> str:
    match = _FIRST_SENTENCE_RE.match(text)
    if match is None:
        return text
    first_sentence = match.group(1)
    repeat_at = text.find(first_sentence, match.end())
    if repeat_at == -1:
        return text
    return text[:repeat_at].rstrip()


def _clean_final_reply_text(text: str) -> str:
    """The single BUILD-16..24I output-quality cleanup pipeline, applied to
    every terminal reply text (see ``ReadOnlyAgentRuntime._result``) --
    self-repetition dedup, then confusable-Cyrillic normalization, then
    disallowed-foreign-script stripping. Purely a display/generation-quality
    cleanup, never a safety mechanism: never runs on tool/retrieval evidence
    or anything Safety Domain-authored, and every step here is a no-op on
    ordinary text that doesn't exhibit the specific live-observed defect it
    targets.
    """
    text = _dedupe_self_repeated_reply(text)
    text = _normalize_confusable_cyrillic(text)
    text = _strip_disallowed_scripts(text)
    return text


class RunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    TIMEOUT = "TIMEOUT"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    HANDOFF_REQUIRED = "HANDOFF_REQUIRED"
    HANDOFF_CREATED = "HANDOFF_CREATED"
    CANCELLED = "CANCELLED"


class SafetyContext(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class AgentRunLimits:
    token_budget: int
    max_steps: int
    max_model_calls: int
    max_tool_calls: int
    max_retries: int
    model_timeout_seconds: float
    run_timeout_seconds: float

    @classmethod
    def from_settings(cls, settings: Any) -> "AgentRunLimits":
        return cls(
            token_budget=int(settings.agent_token_budget),
            max_steps=int(settings.agent_max_steps),
            max_model_calls=int(settings.agent_max_model_calls),
            max_tool_calls=int(settings.agent_max_tool_calls),
            max_retries=int(settings.agent_max_retries),
            model_timeout_seconds=float(settings.agent_model_timeout_seconds),
            run_timeout_seconds=float(settings.agent_run_timeout_seconds),
        )


@dataclass(frozen=True)
class RunMetrics:
    steps: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: float = 0.0

    @property
    def token_total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    response: str
    tool_results: tuple[ToolResult, ...]
    metrics: RunMetrics = RunMetrics()
    # BUILD-32: canonical error taxonomy code (see the ERROR_CODE_* constants
    # above), `None` for every non-error terminal status.
    error_code: str | None = None


class ReadOnlyAgentRuntime:
    """Enforce every BUILD-3 guardrail before continuing an Agent V2 run.

    BUILD-3 tools are synchronous and read-only. They cannot safely be force-
    cancelled from a separate thread while sharing a DB session, so the runtime
    checks its deadline before and immediately after a tool call. The Model
    Gateway passes the configured SDK timeout to each outbound model call.
    """

    def __init__(
        self,
        model_gateway: ModelGateway,
        *,
        limits: AgentRunLimits,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        telemetry: AgentTelemetry | None = None,
        model_name: str | None = None,
    ) -> None:
        self._model_gateway = model_gateway
        self._limits = limits
        self._clock = clock
        self._sleep = sleep
        self._telemetry = telemetry
        self._model_name = model_name or "unknown"

    def run(
        self,
        *,
        message: str,
        actor_role: str,
        tools: ToolGateway,
        safety_context: SafetyContext = SafetyContext.NOT_APPLICABLE,
        safety_decision: SafetyDecision | None = None,
        handoff_result: AgentHandoffResult | None = None,
        handoff_required: bool = False,
        is_cancelled: Callable[[], bool] | None = None,
        trace: TraceContext | None = None,
    ) -> RunResult:
        """Run with optional privacy-minimized telemetry around Agent V2 only."""
        telemetry = self._telemetry
        if telemetry is None:
            return self._run(
                message=message,
                actor_role=actor_role,
                tools=tools,
                safety_context=safety_context,
                safety_decision=safety_decision,
                handoff_result=handoff_result,
                handoff_required=handoff_required,
                is_cancelled=is_cancelled,
                trace=None,
            )
        active_trace = trace or telemetry.start_run()
        started = self._clock()
        with telemetry.span(active_trace, TraceComponent.RUNTIME, operation="read_only_run"):
            result = self._run(
                message=message,
                actor_role=actor_role,
                tools=tools,
                safety_context=safety_context,
                safety_decision=safety_decision,
                handoff_result=handoff_result,
                handoff_required=handoff_required,
                is_cancelled=is_cancelled,
                trace=active_trace,
            )
        telemetry.record_terminal(
            active_trace,
            status=result.status.value,
            latency_ms=max(0.0, (self._clock() - started) * 1000),
            steps=result.metrics.steps,
            tool_calls=result.metrics.tool_calls,
            retries=result.metrics.retries,
            safety_disposition=safety_decision.outcome.value if safety_decision else None,
            handoff_outcome="CREATED" if handoff_result else None,
        )
        if result.status in {RunStatus.BUDGET_EXCEEDED, RunStatus.TIMEOUT}:
            telemetry.event(active_trace, TraceComponent.GUARDRAIL, "agent_guardrail.terminal", error_code=result.status.value)
        return result

    def _run(
        self,
        *,
        message: str,
        actor_role: str,
        tools: ToolGateway,
        safety_context: SafetyContext,
        safety_decision: SafetyDecision | None,
        handoff_result: AgentHandoffResult | None,
        handoff_required: bool,
        is_cancelled: Callable[[], bool] | None,
        trace: TraceContext | None,
    ) -> RunResult:
        started = self._clock()
        metrics = RunMetrics()
        results: list[ToolResult] = []

        if handoff_result is not None:
            reason_code = safety_decision.reason_code if safety_decision is not None else None
            return self._result(
                RunStatus.HANDOFF_CREATED,
                self._handoff_created_message(reason_code),
                results,
                metrics,
                started,
            )
        # This is before cancellation/model/tool handling by design: no model
        # output may reinterpret a Safety Domain decision or leak a partial
        # answer when safety could not be resolved.
        if safety_decision is not None:
            if safety_decision.outcome is SafetyOutcome.SAFETY_BLOCKED:
                return self._result(
                    RunStatus.SAFETY_BLOCKED,
                    self._safety_blocked_message(safety_decision.reason_code),
                    results,
                    metrics,
                    started,
                )
            if safety_decision.outcome is SafetyOutcome.HANDOFF_REQUIRED:
                return self._result(
                    RunStatus.HANDOFF_REQUIRED,
                    self._handoff_required_message(safety_decision.reason_code),
                    results,
                    metrics,
                    started,
                )
            safety_context = SafetyContext.RESOLVED
        if handoff_required:
            return self._result(RunStatus.HANDOFF_REQUIRED, "Cần chuyển yêu cầu đến bác sĩ.", results, metrics, started)
        if self._cancelled(is_cancelled):
            return self._result(RunStatus.CANCELLED, "Agent run đã bị hủy.", results, metrics, started)

        model_started = self._clock()
        if self._telemetry is not None and trace is not None:
            with self._telemetry.span(trace, TraceComponent.MODEL, operation="plan_read_only", attributes={"model_role": ModelRole.MAIN.value, "model": self._model_name}):
                plan, model_result, metrics = self._plan_with_limits(
                    message=message,
                    actor_role=actor_role,
                    safety_context=safety_context,
                    metrics=metrics,
                    started=started,
                    is_cancelled=is_cancelled,
                    trace=trace,
                )
        else:
            plan, model_result, metrics = self._plan_with_limits(
                message=message,
                actor_role=actor_role,
                safety_context=safety_context,
                metrics=metrics,
                started=started,
                is_cancelled=is_cancelled,
                trace=None,
            )
        if model_result is not None:
            return model_result
        assert plan is not None
        if self._telemetry is not None and trace is not None:
            self._telemetry.record_model(
                trace,
                role=ModelRole.MAIN,
                model=self._model_name,
                usage=plan.usage,
                latency_ms=max(0.0, (self._clock() - model_started) * 1000),
                request_id=plan.request_id,
            )
        metrics = self._add_usage(metrics, plan)

        if metrics.token_total > self._limits.token_budget:
            self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.budget", error_code="TOKEN_BUDGET_EXCEEDED")
            return self._guardrail_result("token", safety_context, results, metrics, started)
        if len(plan.tool_calls) > self._limits.max_tool_calls:
            self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.budget", error_code="TOOL_BUDGET_EXCEEDED")
            return self._guardrail_result("tool", safety_context, results, metrics, started)

        signatures = {
            (call.name, json.dumps(call.arguments, sort_keys=True, separators=(",", ":"), default=str))
            for call in plan.tool_calls
        }
        if len(signatures) != len(plan.tool_calls):
            self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.loop", error_code="LOOP_DETECTED")
            return self._guardrail_result("loop", safety_context, results, metrics, started)
        for call in plan.tool_calls:
            if self._cancelled(is_cancelled):
                return self._result(RunStatus.CANCELLED, "Agent run đã bị hủy.", results, metrics, started)
            if self._timed_out(started):
                self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.timeout", error_code="RUN_TIMEOUT")
                return self._timeout_result(safety_context, results, metrics, started)
            if metrics.steps + 1 > self._limits.max_steps:
                self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.budget", error_code="STEP_BUDGET_EXCEEDED")
                return self._guardrail_result("step", safety_context, results, metrics, started)
            try:
                if self._telemetry is not None and trace is not None:
                    with self._telemetry.span(trace, TraceComponent.TOOL, operation="execute", attributes={"tool_name": call.name}):
                        result = tools.execute(call.name, call.arguments)
                    self._telemetry.event(trace, TraceComponent.TOOL, "agent_tool.completed", tool_name=call.name, provenance=result.provenance)
                    results.append(result)
                else:
                    results.append(tools.execute(call.name, call.arguments))
            except ValueError:
                return self._result(
                    RunStatus.FAILED,
                    "Agent không thể thực hiện yêu cầu này.",
                    results,
                    metrics,
                    started,
                    error_code=ERROR_CODE_TOOL_ERROR,
                )
            metrics = self._with(metrics, steps=metrics.steps + 1, tool_calls=metrics.tool_calls + 1)
            if self._timed_out(started):
                self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.timeout", error_code="RUN_TIMEOUT")
                return self._timeout_result(safety_context, results, metrics, started)

        if not plan.tool_calls:
            # No tool was called: the planning turn's own output_text already
            # is the (only) model turn's real answer, so it is the final
            # reply as-is. This is not the BUILD-19 defect path.
            return self._result(RunStatus.COMPLETED, plan.response, results, metrics, started)

        # Tool-calling loop, step 2: User -> Model -> Tool Call -> Tool Result
        # -> Model Synthesis -> Final Reply. ``plan.response`` is deliberately
        # never used as the final reply here -- with tools in play it is the
        # pre-tool planning turn's text (frequently empty), not a synthesis of
        # the verified tool results. Safety/Handoff terminal states above this
        # point already returned before any model call ran, so synthesis only
        # ever sees a run that is not blocked or pending handoff.
        synth_started = self._clock()
        if self._telemetry is not None and trace is not None:
            with self._telemetry.span(
                trace,
                TraceComponent.MODEL,
                operation="synthesize_read_only",
                attributes={"model_role": ModelRole.MAIN.value, "model": self._model_name},
            ):
                synthesis, synth_result, metrics = self._synthesize_with_limits(
                    message=message,
                    actor_role=actor_role,
                    tool_results=results,
                    safety_context=safety_context,
                    metrics=metrics,
                    started=started,
                    is_cancelled=is_cancelled,
                    trace=trace,
                )
        else:
            synthesis, synth_result, metrics = self._synthesize_with_limits(
                message=message,
                actor_role=actor_role,
                tool_results=results,
                safety_context=safety_context,
                metrics=metrics,
                started=started,
                is_cancelled=is_cancelled,
                trace=None,
            )
        if synth_result is not None:
            return synth_result
        assert synthesis is not None
        if self._telemetry is not None and trace is not None:
            self._telemetry.record_model(
                trace,
                role=ModelRole.MAIN,
                model=self._model_name,
                usage=synthesis.usage,
                latency_ms=max(0.0, (self._clock() - synth_started) * 1000),
                request_id=synthesis.request_id,
            )
        metrics = self._add_usage(metrics, synthesis)
        if metrics.token_total > self._limits.token_budget:
            self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.budget", error_code="TOKEN_BUDGET_EXCEEDED")
            return self._guardrail_result("token", safety_context, results, metrics, started)

        return self._result(RunStatus.COMPLETED, synthesis.response, results, metrics, started)

    def _plan_with_limits(
        self,
        *,
        message: str,
        actor_role: str,
        safety_context: SafetyContext,
        metrics: RunMetrics,
        started: float,
        is_cancelled: Callable[[], bool] | None,
        trace: TraceContext | None,
    ) -> tuple[ModelPlan | None, RunResult | None, RunMetrics]:
        current = metrics
        while True:
            if self._cancelled(is_cancelled):
                return None, self._result(RunStatus.CANCELLED, "Agent run đã bị hủy.", (), current, started), current
            if self._timed_out(started):
                self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.timeout", error_code="RUN_TIMEOUT")
                return None, self._timeout_result(safety_context, (), current, started), current
            if current.model_calls >= self._limits.max_model_calls or current.steps + 1 > self._limits.max_steps:
                self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.budget", error_code="MODEL_OR_STEP_BUDGET_EXCEEDED")
                return None, self._guardrail_result("model/step", safety_context, (), current, started), current
            before_call = self._clock()
            try:
                plan = self._model_gateway.plan_read_only(message=message, actor_role=actor_role)
            except Exception as exc:
                current = self._with(current, model_calls=current.model_calls + 1, steps=current.steps + 1)
                if self._timed_out(started) or self._clock() - before_call > self._limits.model_timeout_seconds:
                    timeout_code = self._classify_timeout(started, self._clock(), self._limits.run_timeout_seconds)
                    return None, self._timeout_result(safety_context, (), current, started, error_code=timeout_code), current
                if current.retries >= self._limits.max_retries or current.model_calls >= self._limits.max_model_calls:
                    # BUILD-32: same terminal decision as before this build --
                    # only the error_code label is new, from the caught
                    # exception's real type, never from re-inferring solely off
                    # elapsed time.
                    exhausted_code = ERROR_CODE_MODEL_TIMEOUT if isinstance(exc, openai.APITimeoutError) else ERROR_CODE_MODEL_ERROR
                    return None, self._result(
                        RunStatus.FAILED, "Agent tạm thời không sẵn sàng.", (), current, started, error_code=exhausted_code
                    ), current
                current = self._with(current, retries=current.retries + 1)
                self._telemetry_event(trace, TraceComponent.MODEL, "agent_model.retry", error_code="MODEL_CALL_RETRY", retries=current.retries)
                self._backoff(current.retries, started)
                continue
            current = self._with(current, model_calls=current.model_calls + 1, steps=current.steps + 1)
            if self._timed_out(started) or self._clock() - before_call > self._limits.model_timeout_seconds:
                timeout_code = self._classify_timeout(started, self._clock(), self._limits.run_timeout_seconds)
                return None, self._timeout_result(safety_context, (), current, started, error_code=timeout_code), current
            return plan, None, current

    def _synthesize_with_limits(
        self,
        *,
        message: str,
        actor_role: str,
        tool_results: tuple[ToolResult, ...] | list[ToolResult],
        safety_context: SafetyContext,
        metrics: RunMetrics,
        started: float,
        is_cancelled: Callable[[], bool] | None,
        trace: TraceContext | None,
    ) -> tuple[ModelSynthesis | None, RunResult | None, RunMetrics]:
        """Second model turn: phrase already-verified tool results into a reply.

        Structurally mirrors ``_plan_with_limits`` (same cancellation/timeout/
        budget checks, same bounded-retry-then-fail-closed pattern on
        exception) so a synthesis failure -- including the model gateway
        raising on an empty ``output_text`` -- degrades exactly like a
        planning failure: ``RunStatus.FAILED`` with a fixed safe message,
        never a fabricated reply. Already-fetched tool results are kept in
        the returned ``RunResult`` even on failure, for audit transparency.
        """

        evidence = tuple(
            SynthesisEvidence(tool_name=result.name, provenance=result.provenance, data=result.data)
            for result in tool_results
        )
        current = metrics
        while True:
            if self._cancelled(is_cancelled):
                return None, self._result(RunStatus.CANCELLED, "Agent run đã bị hủy.", tool_results, current, started), current
            if self._timed_out(started):
                self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.timeout", error_code="RUN_TIMEOUT")
                return None, self._timeout_result(safety_context, tool_results, current, started), current
            if current.model_calls >= self._limits.max_model_calls or current.steps + 1 > self._limits.max_steps:
                self._telemetry_event(trace, TraceComponent.GUARDRAIL, "agent_guardrail.budget", error_code="MODEL_OR_STEP_BUDGET_EXCEEDED")
                return None, self._guardrail_result("model/step", safety_context, tool_results, current, started), current
            before_call = self._clock()
            try:
                synthesis = self._model_gateway.synthesize_read_only(message=message, actor_role=actor_role, evidence=evidence)
            except Exception as exc:
                current = self._with(current, model_calls=current.model_calls + 1, steps=current.steps + 1)
                if self._timed_out(started) or self._clock() - before_call > self._limits.model_timeout_seconds:
                    timeout_code = self._classify_timeout(started, self._clock(), self._limits.run_timeout_seconds)
                    return None, self._timeout_result(safety_context, tool_results, current, started, error_code=timeout_code), current
                if current.retries >= self._limits.max_retries or current.model_calls >= self._limits.max_model_calls:
                    # BUILD-32: same terminal decision as before this build --
                    # only the error_code label is new. EmptySynthesisError
                    # (model returned no usable text) is distinguished from a
                    # real timeout/other model error so Admin can tell "the
                    # model answered nothing" apart from "the model call
                    # itself failed/timed out".
                    if isinstance(exc, EmptySynthesisError):
                        exhausted_code = ERROR_CODE_EMPTY_REPLY
                    elif isinstance(exc, openai.APITimeoutError):
                        exhausted_code = ERROR_CODE_MODEL_TIMEOUT
                    else:
                        exhausted_code = ERROR_CODE_MODEL_ERROR
                    return None, self._result(
                        RunStatus.FAILED, "Agent tạm thời không sẵn sàng.", tool_results, current, started, error_code=exhausted_code
                    ), current
                current = self._with(current, retries=current.retries + 1)
                self._telemetry_event(trace, TraceComponent.MODEL, "agent_model.retry", error_code="SYNTHESIS_CALL_RETRY", retries=current.retries)
                self._backoff(current.retries, started)
                continue
            current = self._with(current, model_calls=current.model_calls + 1, steps=current.steps + 1)
            if self._timed_out(started) or self._clock() - before_call > self._limits.model_timeout_seconds:
                timeout_code = self._classify_timeout(started, self._clock(), self._limits.run_timeout_seconds)
                return None, self._timeout_result(safety_context, tool_results, current, started, error_code=timeout_code), current
            return synthesis, None, current

    def _guardrail_result(
        self,
        kind: str,
        safety_context: SafetyContext,
        results: tuple[ToolResult, ...] | list[ToolResult],
        metrics: RunMetrics,
        started: float,
    ) -> RunResult:
        if safety_context is SafetyContext.UNRESOLVED:
            return self._result(
                RunStatus.SAFETY_BLOCKED,
                "Không thể tiếp tục khi đánh giá an toàn chưa được giải quyết.",
                results,
                metrics,
                started,
            )
        return self._result(
            RunStatus.BUDGET_EXCEEDED,
            f"Agent run vượt giới hạn {kind}.",
            results,
            metrics,
            started,
            error_code=ERROR_CODE_BUDGET_EXCEEDED,
        )

    def _timeout_result(
        self,
        safety_context: SafetyContext,
        results: tuple[ToolResult, ...] | list[ToolResult],
        metrics: RunMetrics,
        started: float,
        *,
        error_code: str = ERROR_CODE_REQUEST_TIMEOUT,
    ) -> RunResult:
        if safety_context is SafetyContext.UNRESOLVED:
            return self._result(
                RunStatus.SAFETY_BLOCKED,
                "Không thể tiếp tục khi đánh giá an toàn chưa được giải quyết.",
                results,
                metrics,
                started,
            )
        return self._result(
            RunStatus.TIMEOUT, "Agent run đã quá thời gian cho phép.", results, metrics, started, error_code=error_code
        )

    # BUILD-20: BUILD-19's P2 finding -- the fixed SAFETY_BLOCKED message did
    # not distinguish "this dose isn't due/missed yet, so it can't be
    # assessed" from "the safety domain itself is unavailable/erroring".
    # Both still fail closed to the same terminal status (never a fabricated
    # SAFE/HANDOFF disposition); only the user-facing wording differs, keyed
    # off the domain-supplied ``reason_code`` (see
    # ``SafetyAssessmentNotYetDueError`` in backend/agents/v2/safety.py).
    @staticmethod
    def _safety_blocked_message(reason_code: str) -> str:
        if reason_code == "DOSE_NOT_YET_ASSESSABLE":
            return "Liều này chưa đến hạn hoặc chưa quá hạn nên chưa thể đánh giá an toàn lúc này. Vui lòng thử lại sau khi qua giờ uống theo lịch hẹn."
        return "Không thể trả lời khi đánh giá an toàn chưa được xác nhận."

    # BUILD-24E: an acute-danger report (overdose, poisoning, self-harm
    # ideation, severe reaction -- see orchestrator.py's ACUTE_DANGER_
    # ESCALATION) deserves a real emergency response, not the generic "a
    # doctor will review this" text -- that text implies a delay this
    # situation cannot afford. Fixed, deterministic, no dosing numbers of any
    # kind: the Main Model is never called on this path (see the early
    # returns above), so this is the only text such a message can ever
    # produce, keyed off the same reason_code convention as
    # ``_safety_blocked_message``.
    @staticmethod
    def _handoff_required_message(reason_code: str) -> str:
        if reason_code == "ACUTE_DANGER_DETECTED":
            return (
                "Hệ thống nhận thấy tin nhắn của bạn có dấu hiệu nguy hiểm cấp tính và đang "
                "chuyển ngay đến bác sĩ để được ưu tiên xem xét. NẾU đây là tình huống khẩn "
                "cấp ngay bây giờ, hãy gọi cấp cứu 115 (Việt Nam) hoặc số khẩn cấp tại nơi bạn "
                "đang ở -- đừng chờ phản hồi từ hệ thống này. Không tự ý uống thêm thuốc. Nếu "
                "có thể, hãy ở gần một người bạn tin cậy ngay lúc này."
            )
        if reason_code == "POSSIBLE_OVERDOSE_REPORTED":
            return (
                "Bạn cho biết có thể đã dùng nhiều thuốc hơn dự định. Để bảo đảm an toàn, hệ thống đang "
                "chuyển yêu cầu đến bác sĩ. Hãy liên hệ ngay cơ sở y tế, Trung tâm Chống độc hoặc gọi 115 "
                "(Việt Nam) nếu bạn có bất kỳ triệu chứng bất thường nào; không tự uống thêm thuốc để xử lý."
            )
        return "Yêu cầu cần được bác sĩ xem xét."

    @staticmethod
    def _handoff_created_message(reason_code: str | None) -> str:
        if reason_code == "ACUTE_DANGER_DETECTED":
            return (
                "Hệ thống đã ghi nhận đây là tình huống nguy hiểm cấp tính và đã chuyển đến "
                "bác sĩ để được ưu tiên xem xét. NẾU đây là tình huống khẩn cấp ngay bây giờ, "
                "hãy gọi cấp cứu 115 (Việt Nam) hoặc số khẩn cấp tại nơi bạn đang ở -- đừng chờ "
                "bác sĩ phản hồi. Không tự ý uống thêm thuốc. Nếu có thể, hãy ở gần một người "
                "bạn tin cậy ngay lúc này."
            )
        if reason_code == "POSSIBLE_OVERDOSE_REPORTED":
            return (
                "Hệ thống đã chuyển yêu cầu để bác sĩ ưu tiên xem xét vì bạn có thể đã dùng nhiều thuốc "
                "hơn dự định. Hãy liên hệ ngay cơ sở y tế, Trung tâm Chống độc hoặc gọi 115 (Việt Nam) nếu "
                "có triệu chứng bất thường; không tự uống thêm thuốc để xử lý."
            )
        return "Yêu cầu đã được ghi nhận để bác sĩ xem xét."

    def _timed_out(self, started: float) -> bool:
        return self._clock() - started > self._limits.run_timeout_seconds

    # BUILD-20 hardening: a bounded exponential backoff before every model-call
    # retry (planning or synthesis), so a transient provider error (rate limit,
    # 5xx) is not immediately hammered again. Capped low (0.2s..1.6s) because
    # ``agent_max_retries`` is itself small (default 1) -- this is a courtesy
    # pause, not a full backoff policy -- and clamped to whatever run-timeout
    # budget remains so a retry's own backoff can never blow the run's overall
    # deadline; a run that has no budget left to spare simply does not sleep
    # and lets the next loop iteration's own timeout check fail closed.
    _BACKOFF_BASE_SECONDS = 0.2
    _BACKOFF_CAP_SECONDS = 1.6

    def _backoff(self, retries: int, started: float) -> None:
        remaining = self._limits.run_timeout_seconds - (self._clock() - started)
        if remaining <= 0:
            return
        delay = min(self._BACKOFF_BASE_SECONDS * (2 ** max(0, retries - 1)), self._BACKOFF_CAP_SECONDS, remaining)
        if delay > 0:
            self._sleep(delay)

    def _telemetry_event(
        self, trace: TraceContext | None, component: TraceComponent, name: str, **attributes: object
    ) -> None:
        if self._telemetry is not None and trace is not None:
            self._telemetry.event(trace, component, name, **attributes)

    @staticmethod
    def _cancelled(is_cancelled: Callable[[], bool] | None) -> bool:
        return bool(is_cancelled and is_cancelled())

    @staticmethod
    def _with(metrics: RunMetrics, **changes: int | float) -> RunMetrics:
        return RunMetrics(
            steps=int(changes.get("steps", metrics.steps)),
            model_calls=int(changes.get("model_calls", metrics.model_calls)),
            tool_calls=int(changes.get("tool_calls", metrics.tool_calls)),
            retries=int(changes.get("retries", metrics.retries)),
            input_tokens=int(changes.get("input_tokens", metrics.input_tokens)),
            cached_input_tokens=int(changes.get("cached_input_tokens", metrics.cached_input_tokens)),
            output_tokens=int(changes.get("output_tokens", metrics.output_tokens)),
            elapsed_ms=float(changes.get("elapsed_ms", metrics.elapsed_ms)),
        )

    def _add_usage(self, metrics: RunMetrics, plan: ModelPlan | ModelSynthesis) -> RunMetrics:
        usage = plan.usage
        return self._with(
            metrics,
            input_tokens=metrics.input_tokens + (usage.input_tokens or 0),
            cached_input_tokens=metrics.cached_input_tokens + (usage.cached_input_tokens or 0),
            output_tokens=metrics.output_tokens + (usage.output_tokens or 0),
        )

    def _result(
        self,
        status: RunStatus,
        response: str,
        results: tuple[ToolResult, ...] | list[ToolResult],
        metrics: RunMetrics,
        started: float,
        *,
        error_code: str | None = None,
    ) -> RunResult:
        elapsed_ms = max(0.0, (self._clock() - started) * 1000)
        return RunResult(
            status,
            _clean_final_reply_text(response),
            tuple(results),
            self._with(metrics, elapsed_ms=elapsed_ms),
            error_code,
        )

    @staticmethod
    def _classify_timeout(started: float, clock_now: float, run_timeout_seconds: float) -> str:
        """BUILD-32: REQUEST_TIMEOUT when the overall run budget is what
        tripped, MODEL_TIMEOUT when only the per-call model budget did --
        same elapsed-time evidence the caller already checked, just labeled."""
        return ERROR_CODE_REQUEST_TIMEOUT if (clock_now - started) > run_timeout_seconds else ERROR_CODE_MODEL_TIMEOUT
