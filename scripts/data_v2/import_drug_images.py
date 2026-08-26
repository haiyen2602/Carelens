"""Import validated B-02 image artifacts into a local B-03 storage backend."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402
from backend.services.drug_images import FileSystemStorageBackend, import_manifest  # noqa: E402


def assert_local_postgres_url(database_url: str) -> None:
    """Prevent the B-03 importer from targeting a shared or production database."""

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("B-03 importer only permits a local PostgreSQL DATABASE_URL")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--database-url")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    database_url = args.database_url or settings.database_url
    assert_local_postgres_url(database_url)
    storage_root = args.storage_root or Path(settings.drug_image_storage_dir)
    engine = sa.create_engine(database_url)
    with Session(engine) as session:
        counters = import_manifest(
            session,
            FileSystemStorageBackend(storage_root),
            manifest_path=args.manifest,
            artifact_root=args.artifact_root,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    print(json.dumps(dict(counters), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
