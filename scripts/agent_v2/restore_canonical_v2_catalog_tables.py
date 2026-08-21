"""BUILD-18: data-only restore of the Canonical Drug V2 catalog tables.

``drug_product``/``drug_id_map``/``drug_product_ingredient`` are DB
Architecture V2's operational reference tables ("DB-4A creates the empty
table only. Drug V2 import/backfill happens later." -- ``backend/db/models.py``
``DrugProduct``). No migration or committed script loads them; the local dev
database has 3,556 rows because that import/backfill was run there directly
at some earlier point. This is public canonical drug reference data (names,
dosage forms, routes, ingredient lists) -- never patient/clinical data -- but
without it, ``backend.services.scheduling.write_path._identity()`` cannot
resolve any prescription item's ``drug_product_id``, and every V2 prescription
item is left ``REVIEW_REQUIRED`` with zero dose occurrences generated. This
was discovered while seeding BUILD-18's synthetic staging test data and is
restored the same way as the RAG corpus: read-only from the source, refuse
to touch a target that already has rows, byte-for-byte copy, no re-derivation.

Usage::

    python scripts/agent_v2/restore_canonical_v2_catalog_tables.py \
        --source-url "postgresql://vmec:vmec@localhost:5432/vmec04" \
        --target-url "$STAGING_DATABASE_URL"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, select  # noqa: E402

from backend.db.models import DrugIdMap, DrugProduct, DrugProductIngredient  # noqa: E402

# DrugProduct first: DrugIdMap/DrugProductIngredient reference drug_product_id
# by an unenforced (no DB-level FK) but logically dependent id.
_TABLES = (DrugProduct.__table__, DrugIdMap.__table__, DrugProductIngredient.__table__)
_BATCH_SIZE = 500


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--target-url", required=True)
    args = parser.parse_args()

    source_engine = create_engine(args.source_url)
    target_engine = create_engine(args.target_url)

    with target_engine.connect() as conn:
        for table in _TABLES:
            existing = conn.execute(select(table.c[list(table.columns.keys())[0]])).first()
            if existing is not None:
                print(f"REFUSING: target table {table.name!r} already has at least one row")
                return 1

    summary: dict[str, int] = {}
    for table in _TABLES:
        with source_engine.connect() as source_conn:
            rows = [dict(row) for row in source_conn.execute(select(table)).mappings().all()]
        if not rows:
            print(f"SKIP: source table {table.name!r} has 0 rows")
            summary[table.name] = 0
            continue
        with target_engine.begin() as target_conn:
            for start in range(0, len(rows), _BATCH_SIZE):
                target_conn.execute(table.insert(), rows[start : start + _BATCH_SIZE])
                print(f"  ... {table.name}: {min(start + _BATCH_SIZE, len(rows))}/{len(rows)}", flush=True)
        summary[table.name] = len(rows)
        print(f"RESTORED: {table.name} rows={len(rows)}")

    print("DONE:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
