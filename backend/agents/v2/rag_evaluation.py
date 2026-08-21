"""Deterministic, versioned evaluation primitives for the Agent V2 RAG path.

This module deliberately has no model client and no database dependency.  A
runner supplies ranked drug identifiers and deterministic response text, which
makes the metric calculation suitable for CI and prevents an evaluation from
spending embedding/model budget implicitly.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import exp, log2, sqrt

from backend.agents.v2.retrieval_eval import RetrievalMetrics, evaluate_retrieval


class RagEvaluationGroup(StrEnum):
    EXACT_DRUG = "exact_drug"
    NATURAL_LANGUAGE = "natural_language"
    INDICATION = "indication"
    USAGE = "usage"
    SIDE_EFFECT = "side_effect"
    DIFFICULT = "difficult"
    NO_RESULT = "no_result"


@dataclass(frozen=True)
class GoldenRagCase:
    case_id: str
    group: RagEvaluationGroup
    query: str
    relevant_drug_ids: tuple[str, ...]
    expected_generation: str
    expect_no_result: bool = False

    def __post_init__(self) -> None:
        if not self.case_id or not self.query or not self.expected_generation:
            raise ValueError("golden RAG cases require id, query, and expected generation")
        if self.expect_no_result == bool(self.relevant_drug_ids):
            raise ValueError("a case must declare either relevant IDs or an expected no-result")


@dataclass(frozen=True)
class RagEvaluationVersions:
    corpus_version: str
    corpus_manifest_hash: str
    chunking_version: str
    embedding_model: str
    embedding_dimensions: int
    index_version: str
    retrieval_version: str
    generation_version: str
    prompt_version: str


@dataclass(frozen=True)
class GenerationMetrics:
    exact_match: float
    rouge_l_f1: float
    bleu_4: float


@dataclass(frozen=True)
class EmbeddingDrift:
    passed: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseGate:
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class LatencyDistribution:
    sample_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    median_ms: float
    mean_ms: float
    variance_ms2: float
    min_ms: float
    max_ms: float

    @property
    def spread_ms(self) -> float:
        return self.max_ms - self.min_ms

    @property
    def standard_deviation_ms(self) -> float:
        return sqrt(self.variance_ms2)


@dataclass(frozen=True)
class EvaluationCaseResult:
    case_id: str
    group: RagEvaluationGroup
    retrieved_drug_ids: tuple[str, ...]
    expected_drug_ids: tuple[str, ...]
    expect_no_result: bool
    no_result_passed: bool
    generated_text: str
    expected_generation: str
    latency_ms: float


@dataclass(frozen=True)
class RagEvaluationSummary:
    retrieval: RetrievalMetrics
    generation: GenerationMetrics
    no_result_accuracy: float
    p50_latency_ms: float
    p95_latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    versions: RagEvaluationVersions
    results: tuple[EvaluationCaseResult, ...]


def evaluate_golden_rag(
    cases: Sequence[GoldenRagCase],
    *,
    retrieve: Callable[[GoldenRagCase], Sequence[str]],
    generate: Callable[[GoldenRagCase, Sequence[str]], str],
    latency_ms: Callable[[GoldenRagCase], float] | None = None,
    versions: RagEvaluationVersions,
    precision_k: int = 5,
) -> RagEvaluationSummary:
    """Evaluate a versioned corpus without invoking an LLM or embedding API.

    No-result cases are validated as a separate safety/recall contract, not
    included in ranking metrics where conventional IR metrics are undefined.
    """

    if not cases:
        raise ValueError("at least one golden RAG case is required")
    results: list[EvaluationCaseResult] = []
    ranking_cases: list[tuple[Sequence[str], set[str]]] = []
    generated: list[tuple[str, str]] = []
    for case in cases:
        retrieved = tuple(dict.fromkeys(str(item) for item in retrieve(case)))
        text = generate(case, retrieved)
        elapsed = float(latency_ms(case)) if latency_ms else 0.0
        if elapsed < 0:
            raise ValueError("latency cannot be negative")
        no_result_passed = (not retrieved) if case.expect_no_result else bool(retrieved)
        results.append(
            EvaluationCaseResult(
                case_id=case.case_id,
                group=case.group,
                retrieved_drug_ids=retrieved,
                expected_drug_ids=case.relevant_drug_ids,
                expect_no_result=case.expect_no_result,
                no_result_passed=no_result_passed,
                generated_text=text,
                expected_generation=case.expected_generation,
                latency_ms=elapsed,
            )
        )
        generated.append((text, case.expected_generation))
        if not case.expect_no_result:
            ranking_cases.append((retrieved, set(case.relevant_drug_ids)))

    return RagEvaluationSummary(
        retrieval=evaluate_retrieval(ranking_cases, precision_k=precision_k),
        generation=evaluate_generation(generated),
        no_result_accuracy=sum(result.no_result_passed for result in results) / len(results),
        p50_latency_ms=_percentile([result.latency_ms for result in results], 50),
        p95_latency_ms=_percentile([result.latency_ms for result in results], 95),
        # BUILD-14 has no model, embedding, or judge request.  Keep these
        # explicit rather than reporting an inferred zero-priced model call.
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0.0,
        versions=versions,
        results=tuple(results),
    )


def evaluate_generation(outputs: Sequence[tuple[str, str]]) -> GenerationMetrics:
    if not outputs:
        raise ValueError("at least one generation pair is required")
    return GenerationMetrics(
        exact_match=sum(_normalise(actual) == _normalise(expected) for actual, expected in outputs) / len(outputs),
        rouge_l_f1=sum(rouge_l_f1(actual, expected) for actual, expected in outputs) / len(outputs),
        bleu_4=sum(bleu_4(actual, expected) for actual, expected in outputs) / len(outputs),
    )


def evaluate_embedding_drift(
    baseline: RagEvaluationVersions, observed: RagEvaluationVersions
) -> EmbeddingDrift:
    """Detect identity drift without re-embedding or sampling provider output.

    A semantic-vector drift check needs a separately approved vector sample.
    BUILD-14 therefore fails closed on the reproducibility identity that is
    available locally: corpus/chunk manifest, embedding model/dimension and
    index version.
    """

    fields = (
        ("CORPUS_VERSION_DRIFT", baseline.corpus_version, observed.corpus_version),
        ("CHUNK_MANIFEST_DRIFT", baseline.corpus_manifest_hash, observed.corpus_manifest_hash),
        ("EMBEDDING_MODEL_DRIFT", baseline.embedding_model, observed.embedding_model),
        ("EMBEDDING_DIMENSION_DRIFT", baseline.embedding_dimensions, observed.embedding_dimensions),
        ("INDEX_VERSION_DRIFT", baseline.index_version, observed.index_version),
    )
    return EmbeddingDrift(False, tuple(code for code, expected, actual in fields if expected != actual)) if any(
        expected != actual for _code, expected, actual in fields
    ) else EmbeddingDrift(True, ())


def evaluate_release_gate(baseline: RagEvaluationSummary, observed: RagEvaluationSummary) -> ReleaseGate:
    """Use a measured baseline as the release threshold; no invented target."""

    checks = (
        ("HIT_AT_10_REGRESSION", observed.retrieval.hit_at_10 >= baseline.retrieval.hit_at_10),
        ("MRR_AT_10_REGRESSION", observed.retrieval.mrr_at_10 >= baseline.retrieval.mrr_at_10),
        ("NDCG_AT_10_REGRESSION", observed.retrieval.ndcg_at_10 >= baseline.retrieval.ndcg_at_10),
        ("PRECISION_AT_K_REGRESSION", observed.retrieval.precision_at_k >= baseline.retrieval.precision_at_k),
        ("MAP_AT_10_REGRESSION", observed.retrieval.map_at_10 >= baseline.retrieval.map_at_10),
        ("EXACT_MATCH_REGRESSION", observed.generation.exact_match >= baseline.generation.exact_match),
        ("ROUGE_L_REGRESSION", observed.generation.rouge_l_f1 >= baseline.generation.rouge_l_f1),
        ("BLEU_4_REGRESSION", observed.generation.bleu_4 >= baseline.generation.bleu_4),
        ("NO_RESULT_REGRESSION", observed.no_result_accuracy >= baseline.no_result_accuracy),
        ("P95_LATENCY_REGRESSION", observed.p95_latency_ms <= baseline.p95_latency_ms),
        ("INPUT_TOKEN_REGRESSION", observed.input_tokens <= baseline.input_tokens),
        ("OUTPUT_TOKEN_REGRESSION", observed.output_tokens <= baseline.output_tokens),
        ("COST_REGRESSION", observed.estimated_cost_usd <= baseline.estimated_cost_usd),
    )
    failures = tuple(code for code, passed in checks if not passed)
    return ReleaseGate(not failures, failures)


def describe_latency(values: Sequence[float]) -> LatencyDistribution:
    """Describe measured samples only; no synthetic latency tolerance is added."""

    if not values:
        raise ValueError("at least one latency sample is required")
    if any(value < 0 for value in values):
        raise ValueError("latency cannot be negative")
    mean = sum(values) / len(values)
    return LatencyDistribution(
        sample_count=len(values),
        p50_ms=_percentile(values, 50),
        p95_ms=_percentile(values, 95),
        p99_ms=_percentile(values, 99),
        median_ms=_percentile(values, 50),
        mean_ms=mean,
        variance_ms2=sum((value - mean) ** 2 for value in values) / len(values),
        min_ms=min(values),
        max_ms=max(values),
    )


def empirical_performance_gate(
    *,
    stored_baseline_p95_ms: float,
    baseline_run_p95_ms: Sequence[float],
    candidate_run_p95_ms: Sequence[float],
) -> ReleaseGate:
    """Use the measured P95 envelope and cohort overlap, never a guessed margin.

    Both independent cohorts must overlap and the immutable stored baseline and
    candidate median must lie inside the pooled observed envelope.  This is a
    stability check, not a quality-tuning mechanism.
    """

    baseline = describe_latency(baseline_run_p95_ms)
    candidate = describe_latency(candidate_run_p95_ms)
    pooled = describe_latency((*baseline_run_p95_ms, *candidate_run_p95_ms))
    candidate_median = candidate.median_ms
    overlap = max(baseline.min_ms, candidate.min_ms) <= min(baseline.max_ms, candidate.max_ms)
    within_envelope = (
        pooled.min_ms <= stored_baseline_p95_ms <= pooled.max_ms
        and pooled.min_ms <= candidate_median <= pooled.max_ms
    )
    failures = tuple(
        code
        for code, passed in (
            ("P95_COHORT_NO_OVERLAP", overlap),
            ("STORED_BASELINE_OUTSIDE_MEASURED_ENVELOPE", within_envelope),
        )
        if not passed
    )
    return ReleaseGate(not failures, failures)


def rouge_l_f1(actual: str, expected: str) -> float:
    actual_tokens, expected_tokens = _tokens(actual), _tokens(expected)
    if not actual_tokens or not expected_tokens:
        return float(actual_tokens == expected_tokens)
    lcs = _lcs_length(actual_tokens, expected_tokens)
    precision = lcs / len(actual_tokens)
    recall = lcs / len(expected_tokens)
    return 0.0 if not precision + recall else 2 * precision * recall / (precision + recall)


def bleu_4(actual: str, expected: str) -> float:
    """Small dependency-free BLEU-4 with add-one smoothing and brevity penalty."""

    candidate, reference = _tokens(actual), _tokens(expected)
    if not candidate or not reference:
        return float(candidate == reference)
    log_precision = 0.0
    for size in range(1, 5):
        candidate_ngrams = _ngrams(candidate, size)
        reference_ngrams = _ngrams(reference, size)
        overlap = sum(min(count, reference_ngrams.get(gram, 0)) for gram, count in candidate_ngrams.items())
        log_precision += log2((overlap + 1) / (sum(candidate_ngrams.values()) + 1))
    brevity = 1.0 if len(candidate) > len(reference) else exp(1 - len(reference) / len(candidate))
    return brevity * 2 ** (log_precision / 4)


def _normalise(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))


def _ngrams(tokens: Sequence[str], size: int) -> dict[tuple[str, ...], int]:
    grams: dict[tuple[str, ...], int] = {}
    for index in range(max(0, len(tokens) - size + 1)):
        gram = tuple(tokens[index : index + size])
        grams[gram] = grams.get(gram, 0) + 1
    return grams


def _lcs_length(left: Sequence[str], right: Sequence[str]) -> int:
    previous = [0] * (len(right) + 1)
    for item in left:
        current = [0]
        for index, other in enumerate(right, start=1):
            current.append(previous[index - 1] + 1 if item == other else max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def _percentile(values: Sequence[float], percentile: int) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]
