"""B-04 visual embedding persistence and exact retrieval coverage."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ["INTERNAL_AUTH_SECRET"] = "b04-local-test-secret"
os.environ["JWT_SECRET"] = "b04-local-test-jwt"

from backend.db.models import DrugImage, DrugImageEmbedding, DrugProduct
from backend.services.drug_image_evaluation import EvaluatedQuery, evaluate_rankings, synthetic_query_from_reference
from backend.services.drug_image_retrieval import (
    EMBEDDING_DIMENSION,
    PREPROCESSING_VERSION,
    DrugImageSearchResult,
    generate_drug_image_embeddings,
    search_similar_drug_images,
)
from backend.services.drug_images import FileSystemStorageBackend


class FakeImageEmbedder:
    embedding_model = "test/image"
    embedding_version = "test-v1"
    embedding_dimension = EMBEDDING_DIMENSION
    preprocessing_version = PREPROCESSING_VERSION

    def embed_paths(self, paths: list[Path]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for path in paths:
            payload = path.read_bytes()
            if payload == b"corrupt":
                raise OSError("corrupt image")
            vectors.append(self._unit(payload[0]))
        return vectors

    def embed_image(self, image: Image.Image) -> tuple[float, ...]:
        return self._unit(image.convert("RGB").getpixel((0, 0))[0])

    @staticmethod
    def _unit(index: int) -> tuple[float, ...]:
        return tuple(1.0 if position == index else 0.0 for position in range(EMBEDDING_DIMENSION))


def db_session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    DrugProduct.__table__.create(engine)
    DrugImage.__table__.create(engine)
    DrugImageEmbedding.__table__.create(engine)
    return Session(engine)


def add_image(session: Session, root: Path, *, image_id: str, product_id: str, payload: bytes, primary: bool = True) -> None:
    session.add(
        DrugProduct(
            id=product_id,
            legacy_drug_id=f"legacy-{product_id}",
            display_name=product_id,
            status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    storage_key = f"drug-images/v1/{product_id}/front/{image_id}.webp"
    image_path = root / storage_key
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(payload)
    session.add(
        DrugImage(
            id=image_id,
            drug_product_id=product_id,
            storage_key=storage_key,
            source_url=f"https://example.test/{image_id}",
            source_snapshot_id=f"snapshot-{image_id}",
            checksum_sha256="a" * 64,
            normalized_checksum_sha256="b" * 64,
            mime_type="image/webp",
            width=100,
            height=100,
            file_size=len(payload),
            view_type="front",
            is_primary=primary,
            validation_status="VALIDATED",
            collection_version="v1",
            source_retrieved_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_embedding_generation_persists_versioned_normalized_vectors_and_resumes(tmp_path: Path) -> None:
    session = db_session()
    add_image(session, tmp_path, image_id="image-1", product_id="product-1", payload=bytes([1]))
    add_image(session, tmp_path, image_id="image-2", product_id="product-2", payload=bytes([2]))
    storage = FileSystemStorageBackend(tmp_path)
    embedder = FakeImageEmbedder()

    first = generate_drug_image_embeddings(session, storage, embedder, batch_size=2)
    stored = session.scalars(select(DrugImageEmbedding).order_by(DrugImageEmbedding.drug_image_id)).all()
    second = generate_drug_image_embeddings(session, storage, embedder, batch_size=2)

    assert first.counters == {"TOTAL": 2, "EMBEDDED": 2, "RESUMED": 0, "FAILED": 0, "SKIPPED": 0}
    assert len(stored) == 2
    assert all(len(row.embedding) == EMBEDDING_DIMENSION for row in stored)
    assert all(row.embedding_model == "test/image" and row.embedding_version == "test-v1" for row in stored)
    assert all(row.preprocessing_version == PREPROCESSING_VERSION for row in stored)
    assert second.counters == {"TOTAL": 2, "EMBEDDED": 0, "RESUMED": 2, "FAILED": 0, "SKIPPED": 0}
    assert session.query(DrugImageEmbedding).count() == 2
    assert session.get(DrugImage, "image-1").drug_product_id == "product-1"  # type: ignore[union-attr]


def test_embedding_job_isolates_corrupt_reference_in_failure_queue(tmp_path: Path) -> None:
    session = db_session()
    add_image(session, tmp_path, image_id="image-good", product_id="product-good", payload=bytes([3]))
    add_image(session, tmp_path, image_id="image-bad", product_id="product-bad", payload=b"corrupt")

    run = generate_drug_image_embeddings(session, FileSystemStorageBackend(tmp_path), FakeImageEmbedder(), batch_size=2)

    assert run.counters == {"TOTAL": 2, "EMBEDDED": 1, "RESUMED": 0, "FAILED": 1, "SKIPPED": 0}
    assert [(item.drug_image_id, item.reason) for item in run.failures] == [("image-bad", "OSError")]
    assert session.query(DrugImageEmbedding).count() == 1


def test_exact_search_returns_top_k_product_candidates_and_deduplicates_product_images(tmp_path: Path) -> None:
    session = db_session()
    add_image(session, tmp_path, image_id="image-1", product_id="product-1", payload=bytes([1]))
    add_image(session, tmp_path, image_id="image-2", product_id="product-2", payload=bytes([2]))
    session.add(
        DrugImage(
            id="image-1-side",
            drug_product_id="product-1",
            storage_key="drug-images/v1/product-1/side/image-1-side.webp",
            source_url="https://example.test/image-1-side",
            source_snapshot_id="snapshot-image-1-side",
            checksum_sha256="c" * 64,
            normalized_checksum_sha256="d" * 64,
            mime_type="image/webp",
            width=100,
            height=100,
            file_size=1,
            view_type="side",
            is_primary=False,
            validation_status="VALIDATED",
            collection_version="v1",
            source_retrieved_at=datetime.now(UTC),
        )
    )
    session.add_all(
        [
            DrugImageEmbedding(
                drug_image_id="image-1",
                embedding_model="test/image",
                embedding_version="test-v1",
                embedding_dimension=EMBEDDING_DIMENSION,
                embedding=list(FakeImageEmbedder._unit(1)),
                preprocessing_version=PREPROCESSING_VERSION,
            ),
            DrugImageEmbedding(
                drug_image_id="image-1-side",
                embedding_model="test/image",
                embedding_version="test-v1",
                embedding_dimension=EMBEDDING_DIMENSION,
                embedding=list(FakeImageEmbedder._unit(1)),
                preprocessing_version=PREPROCESSING_VERSION,
            ),
            DrugImageEmbedding(
                drug_image_id="image-2",
                embedding_model="test/image",
                embedding_version="test-v1",
                embedding_dimension=EMBEDDING_DIMENSION,
                embedding=list(FakeImageEmbedder._unit(2)),
                preprocessing_version=PREPROCESSING_VERSION,
            ),
        ]
    )
    session.commit()

    results = search_similar_drug_images(
        session,
        FakeImageEmbedder._unit(1),
        embedding_model="test/image",
        embedding_version="test-v1",
        top_k=5,
    )

    assert [(item.rank, item.drug_image_id, item.drug_product_id) for item in results] == [
        (1, "image-1", "product-1"),
        (2, "image-2", "product-2"),
    ]
    assert results[0].similarity_score == 1.0


def test_synthetic_query_transform_is_deterministic_and_never_reuses_reference_bytes() -> None:
    reference = Image.new("RGB", (80, 40), (20, 80, 200))
    first = synthetic_query_from_reference(reference, transformation_type="jpeg_resize", seed=42)
    second = synthetic_query_from_reference(reference, transformation_type="jpeg_resize", seed=42)
    try:
        assert first.tobytes() == second.tobytes()
        assert first.size != reference.size
        assert first.tobytes() != reference.tobytes()
    finally:
        reference.close()
        first.close()
        second.close()


def test_metrics_accept_duplicate_content_product_set_without_arbitrary_identity_penalty() -> None:
    result = DrugImageSearchResult(
        rank=1,
        drug_image_id="image-duplicate",
        drug_product_id="product-b",
        similarity_score=0.99,
        embedding_model="test/image",
        embedding_version="test-v1",
    )

    metrics = evaluate_rankings(
        [EvaluatedQuery(frozenset({"product-a", "product-b"}), [result], latency_ms=12.5)]
    )

    assert metrics["top1_accuracy"] == 1.0
    assert metrics["mrr"] == 1.0
