"""Pure evaluation hooks for deterministic retrieval relevance datasets."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import log2


@dataclass(frozen=True)
class RetrievalMetrics:
    hit_at_10: float
    mrr_at_10: float
    ndcg_at_10: float
    precision_at_k: float
    map_at_10: float


def hit_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], *, k: int) -> float:
    return float(any(item_id in relevant_ids for item_id in retrieved_ids[:k]))


def mrr_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], *, k: int) -> float:
    for rank, item_id in enumerate(retrieved_ids[:k], start=1):
        if item_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], *, k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    return sum(item_id in relevant_ids for item_id in retrieved_ids[:k]) / k


def average_precision_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], *, k: int) -> float:
    if not relevant_ids:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for rank, item_id in enumerate(retrieved_ids[:k], start=1):
        if item_id in relevant_ids:
            hits += 1
            precision_sum += hits / rank
    return precision_sum / min(len(relevant_ids), k)


def ndcg_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], *, k: int) -> float:
    dcg = sum(1.0 / log2(rank + 1) for rank, item_id in enumerate(retrieved_ids[:k], start=1) if item_id in relevant_ids)
    ideal_count = min(len(relevant_ids), k)
    if not ideal_count:
        return 0.0
    ideal_dcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal_dcg


def evaluate_retrieval(
    cases: Iterable[tuple[Sequence[str], set[str]]],
    *,
    precision_k: int = 5,
) -> RetrievalMetrics:
    evaluated = tuple(cases)
    if not evaluated:
        raise ValueError("at least one retrieval evaluation case is required")
    count = len(evaluated)
    return RetrievalMetrics(
        hit_at_10=sum(hit_at_k(ids, relevant, k=10) for ids, relevant in evaluated) / count,
        mrr_at_10=sum(mrr_at_k(ids, relevant, k=10) for ids, relevant in evaluated) / count,
        ndcg_at_10=sum(ndcg_at_k(ids, relevant, k=10) for ids, relevant in evaluated) / count,
        precision_at_k=sum(precision_at_k(ids, relevant, k=precision_k) for ids, relevant in evaluated) / count,
        map_at_10=sum(average_precision_at_k(ids, relevant, k=10) for ids, relevant in evaluated) / count,
    )
