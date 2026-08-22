"""BUILD-18: data-only restore of the BUILD-7D RAG corpus into a target DB.

Copies exactly the three tables the corpus identity depends on --
``rag_corpus``, ``drug_chunks``, ``rag_embedding_reservation`` -- from a
source Postgres (the local dev database BUILD-7C/7D actually embedded into)
to a target Postgres (a freshly migrated, empty staging database). It never
calls OpenAI and never computes a new embedding; every vector is copied
byte-for-byte from the source row. This is a data-only restore, not a
generic pg_dump/pg_restore replacement -- it fails closed (refuses to run)
if the target already has rows in any of the three tables, so it can never
silently merge with or duplicate an existing corpus.

Usage::

    python scripts/agent_v2/restore_rag_corpus_tables.py \
        --source-url "postgresql://vmec:vmec@localhost:5432/vmec04" \
        --target-url "$STAGING_DATABASE_URL"

Both URLs are read from the command line or environment, never hard-coded,
and this script never prints either URL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, select  # noqa: E402

from backend.db.models import DrugChunk, RagCorpus, RagEmbeddingReservation  # noqa: E402

# Order matters: rag_corpus/rag_embedding_reservation carry no FK to
# drug_chunks in this schema, but copying the corpus registry row first keeps
# the restore's intent (identity, then data, then accounting) legible.
_TABLES = (RagCorpus.__table__, DrugChunk.__table__, RagEmbeddingReservation.__table__)
_BATCH_SIZE = 500


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True, help="Source Postgres DATABASE_URL (the corpus's current home)")
    parser.add_argument("--target-url", required=True, help="Target Postgres DATABASE_URL (must be empty of these 3 tables)")
    args = parser.parse_args()

    source_engine = create_engine(args.source_url)
    target_engine = create_engine(args.target_url)

    # Fail closed: refuse to touch a target that already has rows in any of
    # the three tables, rather than risk a silent merge/duplicate.
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
