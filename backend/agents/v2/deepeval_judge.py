"""Offline-only DeepEval Judge boundary for versioned public RAG cases.

Nothing in this module is imported by Agent runtime/Safety code.  Its inputs
are intentionally limited to public drug-corpus text and versioned golden
queries; patient, conversation and operational identifiers are rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import openai
from deepeval.models.llms.openai_model import GPTModel
from pydantic import BaseModel


class JudgeMetricName(StrEnum):
    CONTEXTUAL_RELEVANCY = "contextual_relevancy"
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"


@dataclass(frozen=True)
class PublicContextReference:
    chunk_id: str
    drug_id: str
    field_group: str


@dataclass(frozen=True)
class JudgeEvaluationInput:
    case_id: str
    query: str
    answer: str
    context_references: tuple[PublicContextReference, ...]
    contexts: tuple[str, ...]
    expected_no_result: bool

    def __post_init__(self) -> None:
        if not self.case_id or not self.query or not self.answer:
            raise ValueError("judge evaluation requires case_id, query, and answer")
        if len(self.context_references) != len(self.contexts):
            raise ValueError("each context must retain exactly one provenance reference")
        for value in (self.case_id, self.query, self.answer, *self.contexts):
            assert_public_evaluation_text(value)


@dataclass(frozen=True)
class JudgeMetricScore:
    metric: JudgeMetricName
    score: float | None
    evaluation_cost_usd: float | None
    status: str


class JudgeMetric(Protocol):
    score: float
    evaluation_cost: float | None

    def measure(self, test_case: object) -> None: ...


@dataclass(frozen=True)
class JudgeUsage:
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class TrackingGPT4oJudge(GPTModel):
    """DeepEval adapter using only the backend Judge credential.

    It retains aggregate usage in memory for the offline report. Prompts,
    model output and credentials are never logged or persisted here.
    """

    INPUT_USD_PER_MILLION = 2.50
    OUTPUT_USD_PER_MILLION = 10.00

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        if not api_key or not model:
            raise ValueError("JUDGE_CREDENTIAL_OR_MODEL_MISSING")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client: openai.OpenAI | None = None
        self.usages: list[JudgeUsage] = []
        super().__init__(model=model, _openai_api_key=api_key, temperature=0)

    def load_model(self, async_mode: bool = False) -> openai.OpenAI:
        if async_mode:
            raise RuntimeError("BUILD-15 uses synchronous deterministic DeepEval metrics only")
        # A Judge round makes one DeepEval call per applicable metric. Reuse a
        # single SDK/httpx transport instead of opening a short-lived client
        # for every call. Retries intentionally remain disabled: an exhausted
        # provider failure must still surface as a failed metric.
        if self._client is None:
            self._client = openai.OpenAI(api_key=self._api_key, max_retries=0, timeout=self._timeout_seconds)
        return self._client

    def close(self) -> None:
        """Release the offline Judge transport after a completed evaluation."""

        if self._client is not None:
            self._client.close()
            self._client = None

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):  # type: ignore[override]
        client = self.load_model()
        if schema is not None:
            completion = client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format=schema,
                temperature=0,
            )
            result = completion.choices[0].message.parsed
        else:
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            result = completion.choices[0].message.content or ""
        usage = completion.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = (input_tokens * self.INPUT_USD_PER_MILLION + output_tokens * self.OUTPUT_USD_PER_MILLION) / 1_000_000
        self.usages.append(JudgeUsage(input_tokens, output_tokens, cost))
        return result, cost

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):  # type: ignore[override]
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return str(self.model_name)


_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE = re.compile(r"(?<!\d)\+?\d[\d .-]{7,}\d(?!\d)")
_PATIENT_MARKER = re.compile(r"\b(patient_id|actor_id|conversation_id|email|phone)\b", re.IGNORECASE)


def assert_public_evaluation_text(value: str) -> None:
    """Block obvious PII and operational identifiers before a Judge call."""

    if _EMAIL.search(value) or _PHONE.search(value) or _PATIENT_MARKER.search(value):
        raise ValueError("JUDGE_PII_PHI_INPUT_REJECTED")


def _failure_status(error: Exception) -> str:
    """Return an actionable but non-sensitive evaluation error code."""

    root: BaseException = error
    while root.__cause__ is not None:
        root = root.__cause__
    if isinstance(root, openai.APITimeoutError):
        return "FAILED_OPENAI_TIMEOUT"
    if isinstance(root, openai.APIConnectionError):
        return "FAILED_OPENAI_CONNECTION"
    if isinstance(root, OSError):
        return "FAILED_TRANSPORT_OSERROR"
    return f"FAILED_{type(root).__name__.upper()}"


def score_metrics(
    evaluation_input: JudgeEvaluationInput,
    *,
    test_case: object,
    metrics: dict[JudgeMetricName, JudgeMetric],
) -> tuple[JudgeMetricScore, ...]:
    """Run required DeepEval metrics; missing context is explicit, never PASS."""

    required = set(JudgeMetricName)
    if set(metrics) != required:
        raise ValueError("JUDGE_METRICS_INCOMPLETE")
    if not evaluation_input.contexts:
        status = "NOT_APPLICABLE_NO_EVIDENCE" if evaluation_input.expected_no_result else "FAILED_MISSING_CONTEXT"
        return tuple(JudgeMetricScore(metric, None, None, status) for metric in JudgeMetricName)

    scores: list[JudgeMetricScore] = []
    for name in JudgeMetricName:
        metric = metrics[name]
        try:
            metric.measure(test_case)
            value = float(metric.score)
            if not 0.0 <= value <= 1.0:
                raise ValueError("JUDGE_SCORE_OUT_OF_RANGE")
            cost = getattr(metric, "evaluation_cost", None)
            scores.append(JudgeMetricScore(name, value, float(cost) if cost is not None else None, "SCORED"))
        except Exception as error:
            scores.append(JudgeMetricScore(name, None, None, _failure_status(error)))
    return tuple(scores)
