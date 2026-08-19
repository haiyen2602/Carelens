"""Seed DB-4H category-only legacy missed-dose fallback policies.

This is a local operational seed, not an importer/runtime switch.  It verifies
the Final Canonical V2 product artifact before reading its preserved legacy
metadata and never changes the artifact itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.safety_policy_domain.service import seed_legacy_category_policies  # noqa: E402
from scripts.data_v2.import_drug_identity_v2 import assert_local_postgres_url, canonical_jsonl_sha256_file  # noqa: E402

DEFAULT_ARTIFACT_DIR = ROOT / "data pharmacy" / "v2" / "final_canonical"
LEGACY_RISK_LEVEL_MAP = {"Nhẹ": "LOW", "Trung bình": "MODERATE", "Nguy hiểm": "HIGH"}
LEGACY_STATUS = "NOT_CLINICALLY_REVIEWED"


def load_legacy_category_risks(artifact_dir: Path) -> tuple[str, dict[str, str]]:
    """Return one unambiguous mapped risk per category after manifest validation."""

    manifest_path = artifact_dir / "manifest.json"
    products_path = artifact_dir / "drug_product.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hash = (manifest.get("artifact_hashes") or {}).get("drug_product.jsonl")
    if expected_hash != canonical_jsonl_sha256_file(products_path):
        raise ValueError("drug_product.jsonl hash does not match Final Canonical V2 manifest")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("manifest.json version is required")

    raw_by_category: dict[str, set[str]] = defaultdict(set)
    for line_number, line in enumerate(products_path.read_text(encoding="utf-8").splitlines(), start=1):
        row = json.loads(line)
        category = row.get("category")
        metadata = row.get("legacy_metadata") or {}
        risk = metadata.get("legacy_missed_dose_risk")
        status = metadata.get("legacy_missed_dose_risk_status")
        if not category or not risk:
            continue
        if status != LEGACY_STATUS:
            raise ValueError(f"drug_product.jsonl:{line_number} has an unapproved legacy risk status")
        if risk not in LEGACY_RISK_LEVEL_MAP:
            raise ValueError(f"drug_product.jsonl:{line_number} has unsupported legacy risk {risk!r}")
        raw_by_category[str(category)].add(str(risk))

    conflicting = {category: sorted(risks) for category, risks in raw_by_category.items() if len(risks) != 1}
    if conflicting:
        raise ValueError(f"legacy risk conflicts by category: {conflicting}")
    return version, {
        category: LEGACY_RISK_LEVEL_MAP[next(iter(risks))] for category, risks in raw_by_category.items()
    }


def seed_from_artifacts(database_url: str, artifact_dir: Path) -> tuple[int, int]:
    """Safely seed local Postgres and return created/existing category-policy counts."""

    assert_local_postgres_url(database_url)
    version, category_risks = load_legacy_category_risks(artifact_dir)
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            result = seed_legacy_category_policies(
                db,
                category_risks=category_risks,
                source_reference=f"{version}:drug_product.jsonl",
                valid_from=datetime.now(UTC),
            )
            db.commit()
            return result.created, result.existing
    finally:
        engine.dispose()


def main() -> int:
    """Run the seed only when the caller explicitly supplies a local database URL."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    version, category_risks = load_legacy_category_risks(args.artifact_dir.resolve())
    if args.dry_run:
        print(json.dumps({"manifest_version": version, "category_count": len(category_risks)}, ensure_ascii=False))
        return 0
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required unless --dry-run")
    created, existing = seed_from_artifacts(args.database_url, args.artifact_dir.resolve())
    print(json.dumps({"created": created, "existing": existing}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
