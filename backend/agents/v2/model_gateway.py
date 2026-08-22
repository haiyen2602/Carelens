"""Config-driven, provider-neutral model boundary for the isolated Agent V2 path.

BUILD-2 keeps this boundary backend-only.  It has no database access and its
only callable functions are the six read-only tools already approved by
BUILD-1.  ``AGENT_RUNTIME_ENABLED`` remains the route-level exposure gate.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import openai


class ModelRole(StrEnum):
    ROUTER = "router"
    MAIN = "main"
    FALLBACK = "fallback"
    EMBEDDING = "embedding"
    JUDGE = "judge"


@dataclass(frozen=True)
class ModelWorkload:
    role: ModelRole
    model: str
    api_key: str
    credential_source: str
    preferred_credential_env: str


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ModelSmokeResult:
    role: ModelRole
    model: str
    passed: bool
    latency_ms: float
    usage: ModelUsage
    request_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class EmbeddingResult:
    """Typed vector result for Agent V2 retrieval; never includes credentials."""

    model: str
    vector: tuple[float, ...]
    usage: ModelUsage = ModelUsage()
    request_id: str | None = None


class MissingModelCredentialError(RuntimeError):
    """Raised before a request when an explicitly named backend env var is absent."""


def _setting(settings: Any, name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def build_model_workloads(settings: Any) -> dict[ModelRole, ModelWorkload]:
    """Resolve workload models and credential references without logging secrets.

    A workload-specific key wins.  The pre-existing backend-only
    ``OPENAI_API_KEY`` is an intentional local-development fallback from the
    approved plan, not a client-side configuration mechanism.
    """

    global_key = _setting(settings, "openai_api_key")
    definitions = (
        (ModelRole.ROUTER, "agent_router_model", "openai_router_api_key", "OPENAI_ROUTER_API_KEY"),
        (ModelRole.MAIN, "agent_main_model", "openai_main_api_key", "OPENAI_MAIN_API_KEY"),
        (ModelRole.FALLBACK, "agent_fallback_model", "openai_fallback_api_key", "OPENAI_FALLBACK_API_KEY"),
        (ModelRole.EMBEDDING, "agent_embedding_model", "openai_embedding_api_key", "OPENAI_EMBEDDING_API_KEY"),
        (ModelRole.JUDGE, "rag_judge_model", "openai_judge_api_key", "OPENAI_JUDGE_API_KEY"),
    )
    workloads: dict[ModelRole, ModelWorkload] = {}
    for role, model_setting, key_setting, preferred_env in definitions:
        workload_key = _setting(settings, key_setting)
        workloads[role] = ModelWorkload(
            role=role,
            model=_setting(settings, model_setting),
            api_key=workload_key or global_key,
            credential_source=preferred_env if workload_key else "OPENAI_API_KEY",
            preferred_credential_env=preferred_env,
        )
    return workloads


def missing_model_credentials(workloads: dict[ModelRole, ModelWorkload]) -> tuple[str, ...]:
    """Return only env-var names; values are intentionally never returned."""

    return tuple(workload.preferred_credential_env for workload in workloads.values() if not workload.api_key)


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _usage(response: Any) -> ModelUsage:
    usage = _value(response, "usage")
    details = _value(usage, "input_tokens_details", {})
    return ModelUsage(
        input_tokens=_value(usage, "input_tokens") or _value(usage, "prompt_tokens"),
        cached_input_tokens=_value(details, "cached_tokens"),
        output_tokens=_value(usage, "output_tokens"),
    )


def _request_id(response: Any) -> str | None:
    request_id = _value(response, "_request_id") or _value(response, "request_id")
    return str(request_id) if request_id else None


def _safe_error(error: Exception) -> str:
    """Keep smoke telemetry useful without leaking messages, prompts, or keys."""

    status = getattr(error, "status_code", None)
    return f"{type(error).__name__}{f' (HTTP {status})' if status else ''}"


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelPlan:
    tool_calls: tuple[ToolCall, ...] = ()
    response: str = ""
    usage: ModelUsage = ModelUsage()
    request_id: str | None = None


@dataclass(frozen=True)
class SynthesisEvidence:
    """One already-executed, already-verified tool result for the synthesis turn.

    Deliberately independent of ``backend.agents.v2.tools.ToolResult`` so this
    module keeps its existing zero-dependency-on-tools.py layering; the
    runtime converts a ``ToolResult`` into this shape before calling
    ``synthesize_read_only``.
    """

    tool_name: str
    provenance: str
    data: dict


@dataclass(frozen=True)
class ModelSynthesis:
    """Final-reply turn produced strictly from verified tool evidence."""

    response: str = ""
    usage: ModelUsage = ModelUsage()
    request_id: str | None = None


class ModelGateway(Protocol):
    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan: ...

    def synthesize_read_only(
        self, *, message: str, actor_role: str, evidence: tuple[SynthesisEvidence, ...]
    ) -> ModelSynthesis: ...


class EmbeddingGateway(Protocol):
    def embed_query(self, *, text: str) -> EmbeddingResult: ...


class DisabledModelGateway:
    """Safe production default until BUILD-2 model smoke tests are approved."""

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return ModelPlan(response="Agent V2 dang chua duoc kich hoat de tra loi.")

    def synthesize_read_only(
        self, *, message: str, actor_role: str, evidence: tuple[SynthesisEvidence, ...]
    ) -> ModelSynthesis:
        return ModelSynthesis(response="Agent V2 dang chua duoc kich hoat de tra loi.")


class StaticModelGateway:
    """Deterministic test double; it never calls an external model."""

    def __init__(self, plan: ModelPlan, synthesis: ModelSynthesis | None = None) -> None:
        self.plan = plan
        # Deliberately not derived from ``plan.response``: defaulting a
        # tool-calling synthesis reply to the pre-tool planning text is
        # exactly the BUILD-19 defect this double must not reintroduce by
        # accident. Tests that care about the synthesized text pass it.
        self.synthesis = synthesis if synthesis is not None else ModelSynthesis(response="synthesized-reply")

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        return self.plan

    def synthesize_read_only(
        self, *, message: str, actor_role: str, evidence: tuple[SynthesisEvidence, ...]
    ) -> ModelSynthesis:
        return self.synthesis


_ROUTER_SCHEMA = {
    "type": "object",
    "properties": {"intent": {"type": "string"}},
    "required": ["intent"],
    "additionalProperties": False,
}

_READ_ONLY_TOOL_SCHEMAS = (
    {
        "type": "function",
        "name": "search_drug",
        "description": "Search the canonical drug catalog by a short query.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_drug_info",
        "description": "Read approved canonical details for one resolved legacy drug id.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"legacy_drug_id": {"type": "string"}, "query": {"type": "string"}},
            "required": ["legacy_drug_id", "query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_active_prescriptions",
        "description": "Read the authorized patient's active prescriptions.",
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_today_doses",
        "description": "Read the authorized patient's doses scheduled today.",
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_upcoming_doses",
        "description": "Read the authorized patient's upcoming doses.",
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_dose_status",
        "description": "Read the status of one authorized dose group.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"dose_id": {"type": "string"}},
            "required": ["dose_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_doses_for_range",
        # BUILD-27B: no date/range parameters here on purpose -- the server
        # (not the model) has already resolved the exact date or range this
        # specific request means (e.g. "hôm qua", "ngày kia", "20/08") from
        # the message before this tool is ever offered; calling it always
        # reads that pre-resolved range. Use this instead of
        # get_today_doses/get_upcoming_doses whenever the request names a
        # specific past date, a specific future date beyond tomorrow, or a
        # week ("tuần trước"/"tuần tới") -- those two tools only ever cover
        # exactly today or a short rolling forward window.
        "description": (
            "Read the authorized patient's doses for the specific past or future "
            "date/date-range the server has already resolved for this request. "
            "Takes no arguments -- the range is fixed server-side, not chosen here."
        ),
        "strict": True,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
)


class OpenAIModelGateway:
    """OpenAI implementation selected by settings, with no frontend key surface."""

    def __init__(
        self,
        workloads: dict[ModelRole, ModelWorkload],
        *,
        client_factory: Callable[..., Any] = openai.OpenAI,
        request_timeout_seconds: float = 15.0,
    ) -> None:
        self._workloads = workloads
        self._client_factory = client_factory
        self._request_timeout_seconds = request_timeout_seconds

    @classmethod
    def from_settings(cls, settings: Any) -> "OpenAIModelGateway":
        return cls(
            build_model_workloads(settings),
            request_timeout_seconds=float(getattr(settings, "agent_model_timeout_seconds", 15.0)),
        )

    def _client_for(self, role: ModelRole) -> Any:
        workload = self._workloads[role]
        if not workload.api_key:
            raise MissingModelCredentialError(
                f"{workload.preferred_credential_env} (or OPENAI_API_KEY for local development) is required"
            )
        # SDK retries are disabled so the runtime owns the exact retry/model
        # call budget. The SDK-level timeout bounds each outbound request.
        return self._client_factory(
            api_key=workload.api_key,
            max_retries=0,
            timeout=self._request_timeout_seconds,
        )

    def route_read_only(self, *, message: str, actor_role: str) -> str:
        """Return a typed router intent; this is not yet wired into runtime flow."""

        workload = self._workloads[ModelRole.ROUTER]
        response = self._client_for(ModelRole.ROUTER).responses.create(
            model=workload.model,
            input=(
                "Classify this authorized Agent V2 read-only request. Return a concise intent only. "
                f"Actor role: {actor_role}. Request: {message}"
            ),
            text={"format": {"type": "json_schema", "name": "agent_router", "strict": True, "schema": _ROUTER_SCHEMA}},
        )
        parsed = json.loads(str(_value(response, "output_text", "{}")))
        return str(parsed["intent"])

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        """Ask only the Main workload for calls from the six-read-tool allowlist.

        The flag-gated endpoint remains disabled by default.  This first turn
        never has write capability.  ``response`` here is the pre-tool
        planning text only -- the runtime does not use it as the final reply
        once ``tool_calls`` is non-empty; see ``synthesize_read_only`` below
        and ``ReadOnlyAgentRuntime`` (BUILD-19B), which runs it as the
        required second turn after tool execution.
        """

        workload = self._workloads[ModelRole.MAIN]
        response = self._client_for(ModelRole.MAIN).responses.create(
            model=workload.model,
            input=(
                "You are an Agent V2 read-only planner. Use only supplied read tools when data is needed. "
                # BUILD-24L (found in Phase 2's real golden retest, report 44, golden
                # query_id 5): search_drug only returns name/dosage_form/route/
                # strength -- it has no indication/side-effect/usage/storage field at
                # all. Answering an indication/side-effect/usage/storage question from
                # search_drug's result alone (or from outside knowledge) is exactly the
                # kind of partially-ungrounded claim BUILD-24F's grounding backstop
                # cannot catch (it only checks whether *any* tool evidence exists, not
                # whether *this specific claim* is backed by it).
                "For questions about a specific drug's indication/purpose (cong dung), "
                "side effects (tac dung phu), usage instructions (cach dung), or storage "
                "(bao quan), calling search_drug alone is not enough -- it only returns "
                "name/dosage_form/route/strength. You must also call get_drug_info with "
                "the resolved legacy_drug_id to get that specific field's data before "
                "answering; if get_drug_info does not return that field either, say so "
                "honestly instead of answering from outside knowledge. "
                # BUILD-24L (golden query_id 8): the model previously picked one SKU
                # silently when search_drug returned more than one plausible match for
                # an ambiguous short name (e.g. "vitamin b1").
                "If search_drug returns more than one plausible match for an ambiguous "
                "drug name, do not pick one automatically -- list the candidates for the "
                "user and ask which one they mean. "
                # BUILD-27B: get_doses_for_range answers a specific resolved
                # past/future date or week; get_today_doses/get_upcoming_doses
                # only ever cover exactly today or a short rolling forward
                # window and must not be used for a named date beyond that.
                "For a question naming a specific past date, a future date beyond "
                "tomorrow, or a week ('tuần trước'/'tuần tới'), call get_doses_for_range, "
                "not get_today_doses or get_upcoming_doses -- the server has already fixed "
                "the exact date/range for this request before you see it. Never state or "
                "compute your own date/range for that call; it takes no arguments. If the "
                "request is about a FUTURE date/range, never phrase the reply as though the "
                "dose has already happened -- say what is scheduled, not what was taken. "
                "Never propose prescription changes, dose-state writes, or clinical advice. "
                f"Authorized actor role: {actor_role}. Request: {message}"
            ),
            tools=list(_READ_ONLY_TOOL_SCHEMAS),
        )
        calls: list[ToolCall] = []
        for item in _value(response, "output", ()):
            if _value(item, "type") != "function_call":
                continue
            arguments = json.loads(str(_value(item, "arguments", "{}")))
            if not isinstance(arguments, dict):
                raise ValueError("MODEL_TOOL_ARGUMENTS_INVALID")
            calls.append(ToolCall(name=str(_value(item, "name", "")), arguments=arguments))
        return ModelPlan(
            tool_calls=tuple(calls),
            response=str(_value(response, "output_text", "")),
            usage=_usage(response),
            request_id=_request_id(response),
        )

    def synthesize_read_only(
        self, *, message: str, actor_role: str, evidence: tuple[SynthesisEvidence, ...]
    ) -> ModelSynthesis:
        """Turn already-executed, already-verified tool evidence into final reply text.

        This is the second turn of the tool-calling loop
        (User -> Model -> Tool Call -> Tool Result -> Model Synthesis -> Final
        Reply). It is intentionally called with no ``tools=`` schema at all,
        so the model structurally cannot call another tool or otherwise act
        here -- it can only phrase the evidence the runtime already fetched
        and verified into a reply. The prompt additionally instructs the
        model never to contradict or override Safety/Doctor/Operational DB
        provenance; the runtime never sends unresolved-safety evidence to
        this turn in the first place (see ``ReadOnlyAgentRuntime``).
        """

        workload = self._workloads[ModelRole.MAIN]
        serialized_evidence = json.dumps(
            [{"tool": item.tool_name, "provenance": item.provenance, "data": item.data} for item in evidence],
            ensure_ascii=False,
        )
        response = self._client_for(ModelRole.MAIN).responses.create(
            model=workload.model,
            input=(
                "You are an Agent V2 read-only assistant. The tool calls you requested have "
                "already run; the results below are verified and authoritative. Treat them as "
                "ground truth and never contradict, override, or second-guess a Safety, Doctor, "
                "or Operational DB provenance entry. Do not invent facts beyond this evidence. "
                # BUILD-24L (found in Phase 2's real golden retest, report 44, golden
                # query_id 45): a reply opened "Minh da ghi nhan: ban da uong thuoc..."
                # ("I've recorded: you took...") for the patient's own unverified claim
                # in their message -- Agent V2 is read-only and never persists any
                # input at all, so this implies a write action that never happened.
                "NEVER say the patient's own message/claim has been recorded, logged, "
                "noted, or saved anywhere -- this agent is read-only and does not "
                "persist any input. Only describe something as 'recorded'/'on file' if "
                "it is actually present in the verified tool evidence above; a "
                "patient's own statement in their message is not itself a recorded fact "
                "just because you are responding to it. "
                "PROVENANCE RULE (BUILD-24B): only describe information as coming from Vinmec if "
                "the evidence below actually carries Vinmec Web provenance -- the user's own "
                "wording mentioning Vinmec is never sufficient grounds by itself. Internal/"
                "canonical drug catalog data (e.g. provenance starting with 'canonical-drug-v2') "
                "and internal RAG retrieval data must always be described as internal or "
                "verified system data, never as Vinmec. If nothing here is genuinely Vinmec-"
                "sourced and the request specifically asked about Vinmec, say honestly that no "
                "Vinmec result was found rather than substituting another source under that name. "
                # BUILD-27B: this turn only ever sees FUTURE-dated schedule
                # evidence for a dose-schedule question (past-dated
                # medication-history queries are answered deterministically
                # in code, before this turn is ever reached -- see
                # AgentOrchestrator._medication_history_reply), so "already
                # taken" phrasing here would always be describing something
                # that has not happened yet.
                "If the verified evidence is about doses scheduled for today or a future "
                "date, describe them as scheduled/upcoming -- never say or imply the patient "
                "has already taken a dose that has not occurred yet. "
                "Write the final natural-language reply for the authorized actor in Vietnamese. "
                f"Authorized actor role: {actor_role}. Original request: {message}. "
                f"Verified tool evidence (JSON): {serialized_evidence}"
            ),
        )
        text = str(_value(response, "output_text", "")).strip()
        if not text:
            # Fail closed through the same bounded-retry path as plan_read_only
            # rather than silently returning empty text again.
            raise ValueError("MODEL_SYNTHESIS_EMPTY")
        return ModelSynthesis(response=text, usage=_usage(response), request_id=_request_id(response))

    def embed_query(self, *, text: str) -> EmbeddingResult:
        """Embed one retrieval query through the configured EMBEDDING workload."""
        workload = self._workloads[ModelRole.EMBEDDING]
        response = self._client_for(ModelRole.EMBEDDING).embeddings.create(model=workload.model, input=[text])
        data = _value(response, "data", ())
        vector = _value(data[0], "embedding") if data else None
        if not isinstance(vector, (list, tuple)) or not vector:
            raise ValueError("EMBEDDING_EMPTY")
        try:
            normalized = tuple(float(value) for value in vector)
        except (TypeError, ValueError) as exc:
            raise ValueError("EMBEDDING_INVALID") from exc
        return EmbeddingResult(workload.model, normalized, _usage(response), _request_id(response))

    def smoke_all(self) -> tuple[ModelSmokeResult, ...]:
        """Run minimal live endpoint checks after all credentials pass preflight."""

        missing = missing_model_credentials(self._workloads)
        if missing:
            raise MissingModelCredentialError(", ".join(missing) + " (or OPENAI_API_KEY for local development) is required")
        return tuple(self._smoke(role) for role in ModelRole)

    def _smoke(self, role: ModelRole) -> ModelSmokeResult:
        workload = self._workloads[role]
        started = time.perf_counter()
        try:
            client = self._client_for(role)
            if role is ModelRole.ROUTER:
                response = client.responses.create(
                    model=workload.model,
                    input="Return a smoke-test intent.",
                    text={"format": {"type": "json_schema", "name": "build2_router", "strict": True, "schema": _ROUTER_SCHEMA}},
                )
                parsed = json.loads(str(_value(response, "output_text", "{}")))
                if not isinstance(parsed.get("intent"), str):
                    raise ValueError("ROUTER_STRUCTURED_OUTPUT_INVALID")
            elif role is ModelRole.MAIN:
                response = client.responses.create(
                    model=workload.model,
                    input="Use the supplied search_drug tool for the query para.",
                    tools=[_READ_ONLY_TOOL_SCHEMAS[0]],
                    tool_choice={"type": "function", "name": "search_drug"},
                )
                if not any(_value(item, "type") == "function_call" and _value(item, "name") == "search_drug" for item in _value(response, "output", ())):
                    raise ValueError("MAIN_TOOL_CALL_NOT_RETURNED")
            elif role is ModelRole.EMBEDDING:
                response = client.embeddings.create(model=workload.model, input=["BUILD-2 smoke test"])
                if not _value(response, "data"):
                    raise ValueError("EMBEDDING_EMPTY")
            else:
                response = client.responses.create(model=workload.model, input="Reply with the single word OK.")
                if not str(_value(response, "output_text", "")).strip():
                    raise ValueError("TEXT_OUTPUT_EMPTY")
            return ModelSmokeResult(role, workload.model, True, (time.perf_counter() - started) * 1000, _usage(response), _request_id(response))
        except Exception as error:
            return ModelSmokeResult(
                role,
                workload.model,
                False,
                (time.perf_counter() - started) * 1000,
                ModelUsage(),
                error=_safe_error(error),
            )
