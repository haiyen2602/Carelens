"""Deterministic synthetic-query transforms and retrieval metric helpers for B-04."""

from __future__ import annotations

import io
import random
import statistics
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from backend.services.drug_image_retrieval import DrugImageSearchResult

SYNTHETIC_TRANSFORMATIONS = (
    "jpeg_resize",
    "brightness",
    "rotation",
    "crop_padding",
    "mild_blur",
)


@dataclass(frozen=True)
class EvaluatedQuery:
    expected_drug_product_ids: frozenset[str]
    results: Sequence[DrugImageSearchResult]
    latency_ms: float


def synthetic_query_from_reference(image: Image.Image, *, transformation_type: str, seed: int) -> Image.Image:
    """Create a documented, deterministic non-identical synthetic query image."""

    if transformation_type not in SYNTHETIC_TRANSFORMATIONS:
        raise ValueError(f"unsupported synthetic transformation: {transformation_type}")
    randomizer = random.Random(seed)
    source = ImageOps.exif_transpose(image).convert("RGB")
    try:
        if transformation_type == "jpeg_resize":
            scale = randomizer.choice((0.55, 0.65, 0.75))
            resized = source.resize(
                (max(16, int(source.width * scale)), max(16, int(source.height * scale))), Image.Resampling.LANCZOS
            )
            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=randomizer.choice((55, 65, 75)), optimize=False)
            with Image.open(io.BytesIO(buffer.getvalue())) as decoded:
                return decoded.convert("RGB")
        if transformation_type == "brightness":
            return ImageEnhance.Brightness(source).enhance(randomizer.choice((0.78, 0.86, 1.14, 1.22)))
        if transformation_type == "rotation":
            return source.rotate(randomizer.choice((-5, -3, 3, 5)), resample=Image.Resampling.BICUBIC, fillcolor="white")
        if transformation_type == "crop_padding":
            margin = max(1, int(min(source.size) * randomizer.choice((0.04, 0.06, 0.08))))
            cropped = source.crop((margin, margin, source.width - margin, source.height - margin))
            canvas = Image.new("RGB", source.size, "white")
            fitted = ImageOps.contain(cropped, (int(source.width * 0.9), int(source.height * 0.9)), Image.Resampling.LANCZOS)
            canvas.paste(fitted, ((source.width - fitted.width) // 2, (source.height - fitted.height) // 2))
            return canvas
        return source.filter(ImageFilter.GaussianBlur(radius=randomizer.choice((0.4, 0.6, 0.8))))
    finally:
        source.close()


def evaluate_rankings(queries: Iterable[EvaluatedQuery]) -> dict[str, float | int | None]:
    """Compute product-level retrieval metrics without inventing score thresholds."""

    rows = list(queries)
    if not rows:
        return {"queries": 0, "top1_accuracy": None, "recall_at_3": None, "recall_at_5": None, "recall_at_10": None, "mrr": None}
    correct_ranks: list[int | None] = []
    for query in rows:
        rank = next(
            (result.rank for result in query.results if result.drug_product_id in query.expected_drug_product_ids),
            None,
        )
        correct_ranks.append(rank)
    return {
        "queries": len(rows),
        "top1_accuracy": _rate(rank == 1 for rank in correct_ranks),
        "recall_at_3": _rate(rank is not None and rank <= 3 for rank in correct_ranks),
        "recall_at_5": _rate(rank is not None and rank <= 5 for rank in correct_ranks),
        "recall_at_10": _rate(rank is not None and rank <= 10 for rank in correct_ranks),
        "mrr": sum(1.0 / rank if rank is not None else 0.0 for rank in correct_ranks) / len(correct_ranks),
        "median_correct_rank": statistics.median(rank for rank in correct_ranks if rank is not None)
        if any(rank is not None for rank in correct_ranks)
        else None,
        "retrieval_latency_p50_ms": _percentile([query.latency_ms for query in rows], 50),
        "retrieval_latency_p95_ms": _percentile([query.latency_ms for query in rows], 95),
    }


def measure_query(callable_query) -> tuple[list[DrugImageSearchResult], float]:
    """Execute one query and return wall-clock latency in milliseconds."""

    started = time.perf_counter()
    results = callable_query()
    return results, (time.perf_counter() - started) * 1000


def _rate(values: Iterable[bool]) -> float:
    checked = list(values)
    return sum(checked) / len(checked)


def _percentile(values: Sequence[float], percentile: int) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math_ceil((percentile / 100) * len(ordered)) - 1))
    return ordered[index]


def math_ceil(value: float) -> int:
    return int(value) if value.is_integer() else int(value) + 1
