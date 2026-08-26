"""Create metadata-only, deterministic synthetic-query cases for B-04 evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.models import DrugImage  # noqa: E402
from backend.services.drug_image_evaluation import SYNTHETIC_TRANSFORMATIONS  # noqa: E402
from backend.services.drug_images import VALIDATION_STATUS  # noqa: E402

EVALUATION_VERSION = "visual_retrieval_v1"


def assert_local_postgres_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("B-04 evaluation manifest only permits a local PostgreSQL DATABASE_URL")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def build_rows(images: list[DrugImage], *, limit: int) -> list[dict[str, object]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    products_by_checksum: dict[str, set[str]] = {}
    images_by_checksum: dict[str, list[DrugImage]] = {}
    for image in images:
        products_by_checksum.setdefault(image.normalized_checksum_sha256, set()).add(image.drug_product_id)
        images_by_checksum.setdefault(image.normalized_checksum_sha256, []).append(image)
    # Ensure every duplicate-content ambiguity group is represented at least
    # once.  The remaining cases are a deterministic, broad sample.
    ambiguous = [
        sorted(group, key=lambda image: hashlib.sha256(image.id.encode()).hexdigest())[0]
        for checksum, group in images_by_checksum.items()
        if len(products_by_checksum[checksum]) > 1
    ]
    selected_ids = {image.id for image in ambiguous}
    remaining = sorted(
        (image for image in images if image.id not in selected_ids),
        key=lambda image: hashlib.sha256(image.id.encode()).hexdigest(),
    )
    selected = ambiguous + remaining[: max(0, limit - len(ambiguous))]
    rows: list[dict[str, object]] = []
    for position, image in enumerate(selected):
        digest = hashlib.sha256(f"{EVALUATION_VERSION}:{image.id}".encode()).hexdigest()
        products = sorted(products_by_checksum[image.normalized_checksum_sha256])
        rows.append(
            {
                "query_id": f"{EVALUATION_VERSION}:{image.id}",
                "expected_drug_product_ids": products,
                "query_source_type": "SYNTHETIC_QUERY",
                "transformation_type": SYNTHETIC_TRANSFORMATIONS[position % len(SYNTHETIC_TRANSFORMATIONS)],
                "reference_image_id": image.id,
                "seed": int(digest[:8], 16),
                "difficulty": "controlled",
                "ambiguity": "AMBIGUOUS_REFERENCE" if len(products) > 1 else "UNAMBIGUOUS_REFERENCE",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=256)
    args = parser.parse_args()
    assert_local_postgres_url(args.database_url)
    engine = sa.create_engine(args.database_url)
    with Session(engine) as session:
        images = session.scalars(
            select(DrugImage)
            .where(DrugImage.validation_status == VALIDATION_STATUS, DrugImage.is_primary.is_(True))
            .order_by(DrugImage.id)
        ).all()
    rows = build_rows(images, limit=min(args.limit, len(images)))
    write_jsonl(args.output, rows)
    print(json.dumps({"evaluation_version": EVALUATION_VERSION, "queries": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
