"""Generate resumable B-04 visual embeddings from local validated B-03 storage."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.drug_image_retrieval import OpenClipImageEmbedder, generate_drug_image_embeddings  # noqa: E402
from backend.services.drug_images import FileSystemStorageBackend  # noqa: E402


def assert_local_postgres_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("B-04 embedding job only permits a local PostgreSQL DATABASE_URL")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--failure-queue", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    assert_local_postgres_url(args.database_url)
    engine = sa.create_engine(args.database_url)
    with Session(engine) as session:
        run = generate_drug_image_embeddings(
            session,
            FileSystemStorageBackend(args.storage_root),
            OpenClipImageEmbedder(device="cpu"),
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    write_jsonl(args.failure_queue, [asdict(item) for item in run.failures])
    print(json.dumps({"counters": dict(run.counters), "failures": len(run.failures)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
