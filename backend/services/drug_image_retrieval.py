"""Offline visual embedding and exact retrieval for validated drug images.

This module is deliberately independent from FastAPI, Agent V2, and the text
RAG embedding client.  B-04 returns ranked candidates only; it never assigns a
drug identity, confidence band, or unknown-drug decision.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DrugImage, DrugImageEmbedding
from backend.services.drug_images import VALIDATION_STATUS, FileSystemStorageBackend

OPENCLIP_MODEL = "ViT-B-32"
OPENCLIP_PRETRAINED = "laion2b_s34b_b79k"
OPENCLIP_PACKAGE_VERSION = "2.26.1"
EMBEDDING_DIMENSION = 512
PREPROCESSING_VERSION = "openclip-rgb-exif-transpose-center-crop-224-v1"
EMBEDDING_COUNTERS = ("TOTAL", "EMBEDDED", "RESUMED", "FAILED", "SKIPPED")


class DrugImageEmbeddingError(ValueError):
    """Raised when a visual embedding cannot be safely generated or searched."""


class ImageEmbedder(Protocol):
    """Model boundary which keeps the persistence and search layers testable."""

    embedding_model: str
    embedding_version: str
    embedding_dimension: int
    preprocessing_version: str

    def embed_paths(self, paths: Sequence[Path]) -> list[tuple[float, ...]]: ...

    def embed_image(self, image: Image.Image) -> tuple[float, ...]: ...


class OpenClipImageEmbedder:
    """CPU-safe OpenCLIP ViT-B/32 baseline with deterministic preprocessing."""

    embedding_model = f"open_clip/{OPENCLIP_MODEL}"
    embedding_version = f"open_clip_torch-{OPENCLIP_PACKAGE_VERSION}:{OPENCLIP_PRETRAINED}"
    embedding_dimension = EMBEDDING_DIMENSION
    preprocessing_version = PREPROCESSING_VERSION

    def __init__(self, *, device: str = "cpu") -> None:
        try:
            import open_clip
            import torch
        except ImportError as error:  # pragma: no cover - exercised by the CLI environment, not core test env
            raise DrugImageEmbeddingError(
                "OpenCLIP is not installed; use requirements-drug-image-vision.txt in an isolated Python 3.11 environment"
            ) from error
        self._torch = torch
        self._device = torch.device(device)
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            OPENCLIP_MODEL,
            pretrained=OPENCLIP_PRETRAINED,
            device=self._device,
        )
        self._model.eval()
        dimension = int(getattr(self._model.visual, "output_dim", 0))
        if dimension != self.embedding_dimension:
            raise DrugImageEmbeddingError(f"unexpected OpenCLIP embedding dimension: {dimension}")

    def embed_paths(self, paths: Sequence[Path]) -> list[tuple[float, ...]]:
        images: list[Image.Image] = []
        try:
            for path in paths:
                with Image.open(path) as image:
                    images.append(ImageOps.exif_transpose(image).convert("RGB"))
            return self._embed_images(images)
        finally:
            for image in images:
                image.close()

    def embed_image(self, image: Image.Image) -> tuple[float, ...]:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        try:
            return self._embed_images([normalized])[0]
        finally:
            normalized.close()

    def _embed_images(self, images: Sequence[Image.Image]) -> list[tuple[float, ...]]:
        if not images:
            return []
        tensors = self._torch.stack([self._preprocess(image) for image in images]).to(self._device)
        with self._torch.inference_mode():
            features = self._model.encode_image(tensors)
            features = features / features.norm(dim=-1, keepdim=True)
        return [tuple(float(value) for value in vector.tolist()) for vector in features.cpu()]


@dataclass(frozen=True)
class EmbeddingFailure:
    drug_image_id: str
    storage_key: str
    reason: str


@dataclass
class EmbeddingRun:
    counters: Counter[str] = field(default_factory=lambda: Counter({key: 0 for key in EMBEDDING_COUNTERS}))
    failures: list[EmbeddingFailure] = field(default_factory=list)


@dataclass(frozen=True)
class DrugImageSearchResult:
    rank: int
    drug_image_id: str
    drug_product_id: str
    similarity_score: float
    embedding_model: str
    embedding_version: str


def generate_drug_image_embeddings(
    session: Session,
    storage: FileSystemStorageBackend,
    embedder: ImageEmbedder,
    *,
    batch_size: int = 16,
    dry_run: bool = False,
) -> EmbeddingRun:
    """Embed eligible images in committed batches so interrupted jobs resume safely."""

    if batch_size <= 0:
        raise DrugImageEmbeddingError("batch_size must be positive")
    _validate_embedder(embedder)
    run = EmbeddingRun()
    images = session.scalars(select(DrugImage).order_by(DrugImage.id)).all()
    existing_ids = set(
        session.scalars(
            select(DrugImageEmbedding.drug_image_id).where(
                DrugImageEmbedding.embedding_model == embedder.embedding_model,
                DrugImageEmbedding.embedding_version == embedder.embedding_version,
            )
        ).all()
    )
    pending: list[tuple[DrugImage, Path]] = []
    for image in images:
        run.counters["TOTAL"] += 1
        if image.validation_status != VALIDATION_STATUS:
            run.counters["SKIPPED"] += 1
            continue
        if image.id in existing_ids:
            run.counters["RESUMED"] += 1
            continue
        path = storage.path_for(image.storage_key)
        if not path.is_file():
            _record_failure(run, image, "IMAGE_FILE_MISSING")
            continue
        pending.append((image, path))
        if len(pending) >= batch_size:
            _embed_batch(session, pending, embedder, run, dry_run=dry_run)
            pending = []
    if pending:
        _embed_batch(session, pending, embedder, run, dry_run=dry_run)
    return run


def search_similar_drug_images(
    session: Session,
    query_embedding: Sequence[float],
    *,
    embedding_model: str,
    embedding_version: str,
    top_k: int,
) -> list[DrugImageSearchResult]:
    """Return exact cosine-ranked product candidates for one visual query.

    The B-04 corpus is only ~3.5k rows, so scanning all persisted vectors is
    intentional and avoids premature ANN recall trade-offs.  Results are
    deduplicated at canonical product level to support future multi-view data.
    """

    if top_k <= 0:
        raise DrugImageEmbeddingError("top_k must be positive")
    normalized_query = _normalize(query_embedding)
    filters = (
        DrugImage.validation_status == VALIDATION_STATUS,
        DrugImageEmbedding.embedding_model == embedding_model,
        DrugImageEmbedding.embedding_version == embedding_version,
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        distance = DrugImageEmbedding.embedding.cosine_distance(list(normalized_query))
        rows = session.execute(
            select(
                DrugImageEmbedding.drug_image_id,
                DrugImage.drug_product_id,
                (1 - distance).label("similarity"),
            )
            .join(DrugImage, DrugImage.id == DrugImageEmbedding.drug_image_id)
            .where(*filters)
            .order_by(distance, DrugImage.drug_product_id, DrugImageEmbedding.drug_image_id)
        ).all()
        ranked = [(float(row.similarity), row.drug_image_id, row.drug_product_id) for row in rows]
    else:
        rows = session.execute(
            select(DrugImageEmbedding, DrugImage).join(DrugImage, DrugImage.id == DrugImageEmbedding.drug_image_id).where(*filters)
        ).all()
        ranked = sorted(
            (
                (
                    _cosine_similarity(normalized_query, embedding.embedding),
                    image.id,
                    image.drug_product_id,
                )
                for embedding, image in rows
            ),
            key=lambda row: (-row[0], row[2], row[1]),
        )
    results: list[DrugImageSearchResult] = []
    seen_products: set[str] = set()
    for score, image_id, product_id in ranked:
        if product_id in seen_products:
            continue
        seen_products.add(product_id)
        results.append(
            DrugImageSearchResult(
                rank=len(results) + 1,
                drug_image_id=image_id,
                drug_product_id=product_id,
                similarity_score=score,
                embedding_model=embedding_model,
                embedding_version=embedding_version,
            )
        )
        if len(results) == top_k:
            break
    return results


def _embed_batch(
    session: Session,
    pending: Sequence[tuple[DrugImage, Path]],
    embedder: ImageEmbedder,
    run: EmbeddingRun,
    *,
    dry_run: bool,
) -> None:
    try:
        vectors = embedder.embed_paths([path for _, path in pending])
        _persist_vectors(session, pending, vectors, embedder, run, dry_run=dry_run)
    except Exception:
        # A corrupt reference must not discard an otherwise valid batch.  Retry
        # individually so the failure queue identifies the exact record.
        session.rollback()
        for image, path in pending:
            try:
                _persist_vectors(session, [(image, path)], embedder.embed_paths([path]), embedder, run, dry_run=dry_run)
            except Exception as error:  # noqa: BLE001 - external model/decoder failures become durable evidence
                _record_failure(run, image, type(error).__name__)


def _persist_vectors(
    session: Session,
    pending: Sequence[tuple[DrugImage, Path]],
    vectors: Sequence[Sequence[float]],
    embedder: ImageEmbedder,
    run: EmbeddingRun,
    *,
    dry_run: bool,
) -> None:
    if len(vectors) != len(pending):
        raise DrugImageEmbeddingError("encoder returned an unexpected vector count")
    prepared = [_normalize(vector) for vector in vectors]
    if any(len(vector) != embedder.embedding_dimension for vector in prepared):
        raise DrugImageEmbeddingError("encoder returned an unexpected vector dimension")
    if dry_run:
        run.counters["EMBEDDED"] += len(prepared)
        return
    for (image, _), vector in zip(pending, prepared, strict=True):
        session.add(
            DrugImageEmbedding(
                drug_image_id=image.id,
                embedding_model=embedder.embedding_model,
                embedding_version=embedder.embedding_version,
                embedding_dimension=embedder.embedding_dimension,
                embedding=list(vector),
                preprocessing_version=embedder.preprocessing_version,
            )
        )
    session.commit()
    run.counters["EMBEDDED"] += len(prepared)


def _record_failure(run: EmbeddingRun, image: DrugImage, reason: str) -> None:
    run.counters["FAILED"] += 1
    run.failures.append(EmbeddingFailure(image.id, image.storage_key, reason))


def _validate_embedder(embedder: ImageEmbedder) -> None:
    if embedder.embedding_dimension != EMBEDDING_DIMENSION:
        raise DrugImageEmbeddingError(f"B-04 requires {EMBEDDING_DIMENSION}-dimension embeddings")
    if not embedder.embedding_model or not embedder.embedding_version or not embedder.preprocessing_version:
        raise DrugImageEmbeddingError("embedder identity and preprocessing version are required")


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    try:
        values = tuple(float(value) for value in vector)
    except (TypeError, ValueError) as error:
        raise DrugImageEmbeddingError("embedding must contain numeric values") from error
    norm = math.sqrt(sum(value * value for value in values))
    if not values or norm == 0.0 or not math.isfinite(norm):
        raise DrugImageEmbeddingError("embedding must be a non-zero finite vector")
    return tuple(value / norm for value in values)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    normalized_right = _normalize(right)
    if len(left) != len(normalized_right):
        raise DrugImageEmbeddingError("query and stored embedding dimensions do not match")
    return sum(a * b for a, b in zip(left, normalized_right, strict=True))
