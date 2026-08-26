"""Evaluate B-04 self-retrieval and synthetic queries without patient photos."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import sqlalchemy as sa
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.models import DrugImage, DrugImageEmbedding  # noqa: E402
from backend.services.drug_image_evaluation import (  # noqa: E402
    EvaluatedQuery,
    evaluate_rankings,
    measure_query,
    synthetic_query_from_reference,
)
from backend.services.drug_image_retrieval import OpenClipImageEmbedder, search_similar_drug_images  # noqa: E402
from backend.services.drug_images import FileSystemStorageBackend  # noqa: E402


def assert_local_postgres_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("B-04 evaluation only permits a local PostgreSQL DATABASE_URL")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def search(session: Session, vector: list[float], embedder: OpenClipImageEmbedder):
    return search_similar_drug_images(
        session,
        vector,
        embedding_model=embedder.embedding_model,
        embedding_version=embedder.embedding_version,
        top_k=10,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--evaluation-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert_local_postgres_url(args.database_url)
    cases = read_jsonl(args.evaluation_manifest)
    embedder = OpenClipImageEmbedder(device="cpu")
    storage = FileSystemStorageBackend(args.storage_root)
    engine = sa.create_engine(args.database_url)
    self_queries: list[EvaluatedQuery] = []
    synthetic_queries: list[EvaluatedQuery] = []
    with Session(engine) as session:
        for case in cases:
            image_id = str(case["reference_image_id"])
            expected = frozenset(str(value) for value in case["expected_drug_product_ids"])
            image = session.get(DrugImage, image_id)
            embedding = session.scalar(
                select(DrugImageEmbedding.embedding).where(
                    DrugImageEmbedding.drug_image_id == image_id,
                    DrugImageEmbedding.embedding_model == embedder.embedding_model,
                    DrugImageEmbedding.embedding_version == embedder.embedding_version,
                )
            )
            if image is None or embedding is None:
                raise RuntimeError(f"missing B-04 reference embedding for {image_id}")
            self_results, self_latency = measure_query(lambda: search(session, list(embedding), embedder))
            self_queries.append(EvaluatedQuery(expected, self_results, self_latency))
            path = storage.path_for(image.storage_key)
            with Image.open(path) as reference:
                query_image = synthetic_query_from_reference(
                    reference,
                    transformation_type=str(case["transformation_type"]),
                    seed=int(case["seed"]),
                )
            try:
                query_vector = embedder.embed_image(query_image)
            finally:
                query_image.close()
            synthetic_results, synthetic_latency = measure_query(lambda: search(session, list(query_vector), embedder))
            synthetic_queries.append(EvaluatedQuery(expected, synthetic_results, synthetic_latency))
    payload = {
        "evaluation_manifest": str(args.evaluation_manifest),
        "embedding_model": embedder.embedding_model,
        "embedding_version": embedder.embedding_version,
        "preprocessing_version": embedder.preprocessing_version,
        "hardware": {"platform": platform.platform(), "processor": platform.processor(), "device": "cpu"},
        "self_retrieval_sanity_only": evaluate_rankings(self_queries),
        "synthetic_query_evaluation": evaluate_rankings(synthetic_queries),
        "unknown_rejection": "NOT_AVAILABLE",
    }
    write_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
