"""BUILD-33: provider-agnostic Judge model call + structured-output validation.

Uses only the already-installed ``openai`` package for BOTH supported
providers:

  - ``openai``: the real OpenAI Chat Completions API.
  - ``google``: Gemini via Google's own OpenAI-compatible endpoint
    (``https://generativelanguage.googleapis.com/v1beta/openai/``) -- no new
    SDK dependency. Verified real 2026-08-25: ``gemini-3.7-flash`` is a
    generally-available model ID on this endpoint, and its ``reasoning_effort``
    request parameter maps to Gemini's own ``thinkingLevel`` (low/medium/high)
    -- see BUILD-33 report §2 for the primary sources. The exact same
    base_url is already a proven, working preset in this repo's OWN
    ``backend/vlm_demthuoc/providers.py`` (a separate, standalone VLM tool) --
    this module intentionally does not import that one (different pipeline,
    different config surface, see that module's own docstring), but reuses
    the identical, already-verified endpoint.

Structured output uses ``response_format={"type": "json_object"}`` (a plain
JSON-mode request) plus explicit Pydantic validation of the parsed body --
deliberately NOT OpenAI's strict ``json_schema`` mode
(``chat.completions.parse`` with a Pydantic model, the mechanism
``backend/agents/v2/deepeval_judge.py``'s ``TrackingGPT4oJudge`` uses): the
``dimensions`` field here is an open, rubric-dependent ``dict[str, float]``,
which OpenAI's *strict* schema mode cannot represent (it requires a fixed,
enumerated property set, not ``additionalProperties``) -- and Google's
OpenAI-compat layer's strict-mode coverage for arbitrary Pydantic schemas is
unverified in this build (no live credential, see BUILD-33 report §2). Plain
JSON mode is far more broadly supported across both providers and every
model, at the cost of needing our own validation step below -- which is
exactly what turns a malformed response into ``JUDGE_FAILED`` (§7) instead of
a silent ``score=0.0``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import openai
from pydantic import BaseModel, Field, ValidationError, field_validator

_GOOGLE_OPENAI_COMPAT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class JudgeOutputSchema(BaseModel):
    """The ONLY shape a Judge call is allowed to succeed with (BUILD-33 §7)."""

    overall_score: float
    dimensions: dict[str, float]
    flags: list[str] = Field(default_factory=list)
    confidence: float

    @field_validator("overall_score", "confidence")
    @classmethod
    def _in_unit_range(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("score/confidence must be within [0.0, 1.0]")
        return value

    @field_validator("dimensions")
    @classmethod
    def _dimensions_in_unit_range(cls, value: dict[str, float]) -> dict[str, float]:
        for key, score in value.items():
            if not (0.0 <= score <= 1.0):
                raise ValueError(f"dimension {key!r} score must be within [0.0, 1.0]")
        return value


@dataclass(frozen=True)
class JudgeCallResult:
    status: str  # "SCORED" | "JUDGE_FAILED"
    overall_score: float | None = None
    dimension_scores: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    confidence: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    failure_reason: str | None = None


def resolve_credential(*, provider: str, openai_judge_api_key: str, openai_api_key: str, google_api_key: str) -> str:
    if provider == "google":
        return google_api_key
    # provider == "openai": the SAME credential backend/agents/v2/
    # deepeval_judge.py already uses for its own (offline) judge, falling
    # back to the shared global OPENAI_API_KEY exactly like every other
    # Agent V2 workload credential (backend.agents.v2.model_gateway.
    # build_model_workloads) -- deliberately NOT a third distinct OpenAI
    # secret for the same logical "Judge" purpose.
    return openai_judge_api_key or openai_api_key


def resolve_base_url(*, provider: str, configured_base_url: str) -> str | None:
    if configured_base_url:
        return configured_base_url
    if provider == "google":
        return _GOOGLE_OPENAI_COMPAT_BASE_URL
    return None  # OpenAI SDK's own default endpoint


def _failure_status(error: Exception) -> str:
    """Mirror deepeval_judge.py's own exception classification -- both
    providers go through the same `openai` SDK exception hierarchy, so one
    classifier covers both without any provider-specific branching."""

    root: BaseException = error
    while root.__cause__ is not None:
        root = root.__cause__
    if isinstance(root, openai.APITimeoutError):
        return "FAILED_TIMEOUT"
    if isinstance(root, openai.AuthenticationError):
        return "FAILED_AUTHENTICATION"
    if isinstance(root, openai.APIConnectionError):
        return "FAILED_CONNECTION"
    if isinstance(root, openai.RateLimitError):
        return "FAILED_RATE_LIMIT"
    if isinstance(root, openai.APIStatusError):
        return f"FAILED_API_STATUS_{getattr(root, 'status_code', 'UNKNOWN')}"
    if isinstance(root, OSError):
        return "FAILED_TRANSPORT_OSERROR"
    return f"FAILED_{type(root).__name__.upper()}"


def call_judge(
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None,
    reasoning_effort: str,
    timeout_seconds: float,
    prompt: str,
) -> JudgeCallResult:
    """One real (or real-provider-shaped) Judge call. Never raises -- every
    failure mode (missing credential, timeout, connection error, malformed
    output, out-of-range score) returns ``JUDGE_FAILED`` with a specific
    ``failure_reason`` instead."""

    if not api_key:
        return JudgeCallResult(status="JUDGE_FAILED", failure_reason="CREDENTIAL_NOT_CONFIGURED")
    if not model:
        return JudgeCallResult(status="JUDGE_FAILED", failure_reason="MODEL_NOT_CONFIGURED")

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    # Only Google's endpoint documents/accepts `reasoning_effort` mapped to
    # its `thinkingLevel` (BUILD-33 report §2) -- sending it to a plain
    # OpenAI model risks an unexpected 400 on a model that does not support
    # reasoning effort at all.
    if provider == "google" and reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort

    # `with` (not a bare `openai.OpenAI(...)` + scattered `client.close()`
    # calls) guarantees the underlying httpx connection pool is released on
    # every exit path -- including one this function's own exception
    # handling below does not explicitly anticipate.
    with openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=0) as client:
        # 2-rung ladder, same resilience idiom as this repo's own
        # backend/vlm_demthuoc/providers.py::OpenAICompatBackend (schema/
        # object/off) -- json_object first (broadly supported, guarantees
        # valid JSON syntax); if the endpoint rejects `response_format`
        # entirely, fall back to plain prompting + best-effort JSON-
        # substring extraction rather than failing every call on a provider
        # that simply does not support the parameter.
        attempts = [{**kwargs, "response_format": {"type": "json_object"}}, kwargs]
        completion = None
        for index, attempt_kwargs in enumerate(attempts):
            is_last_attempt = index == len(attempts) - 1
            try:
                completion = client.chat.completions.create(**attempt_kwargs)
                break
            except openai.BadRequestError as error:
                message = str(getattr(error, "message", "") or error).lower()
                unsupported = "response_format" in message or "not supported" in message
                if not is_last_attempt and unsupported:
                    continue
                return JudgeCallResult(status="JUDGE_FAILED", failure_reason=_failure_status(error))
            except Exception as error:  # noqa: BLE001 -- every provider failure must degrade to JUDGE_FAILED, never raise
                return JudgeCallResult(status="JUDGE_FAILED", failure_reason=_failure_status(error))
        assert completion is not None  # every loop exit above either returns or sets completion

    usage = completion.usage
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    choice = completion.choices[0] if completion.choices else None
    content = getattr(getattr(choice, "message", None), "content", None) if choice is not None else None

    if not content:
        return JudgeCallResult(
            status="JUDGE_FAILED", failure_reason="EMPTY_OUTPUT", input_tokens=input_tokens, output_tokens=output_tokens
        )

    parsed = _parse_judge_output(content)
    if parsed is None:
        return JudgeCallResult(
            status="JUDGE_FAILED",
            failure_reason="MALFORMED_OUTPUT",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    return JudgeCallResult(
        status="SCORED",
        overall_score=parsed.overall_score,
        dimension_scores=dict(parsed.dimensions),
        flags=list(parsed.flags),
        confidence=parsed.confidence,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_judge_output(content: str) -> JudgeOutputSchema | None:
    """Validate raw model text against ``JudgeOutputSchema``. Returns
    ``None`` (never raises, never fabricates a score) on any parse/schema/
    range failure -- the caller turns that into ``JUDGE_FAILED``."""

    candidates = [content]
    match = _JSON_OBJECT_RE.search(content)
    if match and match.group(0) != content:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            raw = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        try:
            return JudgeOutputSchema.model_validate(raw)
        except ValidationError:
            continue
    return None


__all__ = [
    "JudgeCallResult",
    "JudgeOutputSchema",
    "call_judge",
    "resolve_base_url",
    "resolve_credential",
]
