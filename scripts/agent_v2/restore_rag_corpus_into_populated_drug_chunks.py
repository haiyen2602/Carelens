"""BUILD-21: additive V2 RAG corpus restore into a target whose ``drug_chunks``
already holds real, live legacy rows (production).

``restore_rag_corpus_tables.py`` (BUILD-18) is intentionally unusable here:
it fails closed if the target has *any* existing row in ``drug_chunks``,
``rag_corpus``, or ``rag_embedding_reservation`` -- correct for staging
(a freshly migrated, empty database) but wrong for production, whose
``drug_chunks`` already carries the real legacy v1 corpus that
``backend/services/retrieval.py`` (legacy `/api/v1/chat`, live patient
traffic) reads from today via explicit column lists (never `SELECT *`),
so the migration-added nullable ``corpus_version``/``chunk_key``/
``embedding_model``/``embedding_dimensions`` columns are inert to it.

This script is deliberately narrower and more paranoid than a generic
restore:

- ``rag_corpus`` / ``rag_embedding_reservation`` still fail closed if the
  target has any existing row (BUILD-18's exact guarantee, unchanged --
  these are new, isolated tables and must still start empty).
- ``drug_chunks`` is the one exception, explicitly allowed to have existing
  rows -- but only ever **inserted into**, never updated or deleted. Before
  writing anything: (1) every existing target row's full content is
  snapshotted (id -> content hash) so it can be proven byte-for-byte
  unchanged afterward; (2) the script refuses to run if any target row
  already carries the ``corpus_version`` about to be inserted (protects
  against double-running); (3) every inserted row's primary key is a fresh
  UUID (BUILD-18's own source data), so a PK collision with an existing
  legacy row is not expected but would still fail the INSERT rather than
  silently overwrite -- there is no upsert/ON CONFLICT anywhere in this
  script.

Usage::

    python scripts/agent_v2/restore_rag_corpus_into_populated_drug_chunks.py \
        --source-url "$STAGING_DATABASE_URL" \
        --target-url "$PRODUCTION_DATABASE_URL"

Both URLs are read from the command line or environment, never hard-coded,
and this script never prints either URL.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, select  # noqa: E402

from backend.db.models import DrugChunk, RagCorpus, RagEmbeddingReservation  # noqa: E402

_EMPTY_MUST_TABLES = (RagCorpus.__table__, RagEmbeddingReservation.__table__)
_CHUNKS_TABLE = DrugChunk.__table__
_BATCH_SIZE = 500


def _row_hash(row: dict) -> str:
    # Stable content hash independent of column/dict ordering -- used only to
    # prove "unchanged before vs. after", never to identify or merge rows.
    payload = "|".join(f"{key}={row[key]!r}" for key in sorted(row))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True, help="Source Postgres DATABASE_URL (a verified-clean V2 corpus)")
    parser.add_argument("--target-url", required=True, help="Target Postgres DATABASE_URL (drug_chunks may already hold live legacy rows)")
    args = parser.parse_args()

    source_engine = create_engine(args.source_url)
    target_engine = create_engine(args.target_url)

    with target_engine.connect() as conn:
        for table in _EMPTY_MUST_TABLES:
            existing = conn.execute(select(table.c[list(table.columns.keys())[0]])).first()
            if existing is not None:
                print(f"REFUSING: target table {table.name!r} already has at least one row (expected empty)")
                return 1

    with source_engine.connect() as source_conn:
        source_rows = [dict(row) for row in source_conn.execute(select(_CHUNKS_TABLE)).mappings().all()]
    source_versions = {row["corpus_version"] for row in source_rows if row.get("corpus_version")}
    if not source_rows or not source_versions:
        print("REFUSING: source drug_chunks has no corpus_version-tagged rows to restore")
        return 1

    with target_engine.connect() as target_conn:
        pre_snapshot = {
            row["id"]: _row_hash(dict(row))
            for row in target_conn.execute(select(_CHUNKS_TABLE)).mappings().all()
        }
        clashing = target_conn.execute(
            select(_CHUNKS_TABLE.c.corpus_version).where(_CHUNKS_TABLE.c.corpus_version.in_(source_versions)).limit(1)
        ).first()
        if clashing is not None:
            print(f"REFUSING: target drug_chunks already has rows tagged corpus_version={clashing[0]!r} -- refusing to risk a duplicate run")
            return 1

    pre_count = len(pre_snapshot)
    print(f"Target drug_chunks currently has {pre_count} row(s) (untouched, insert-only from here).")
    print(f"Restoring {len(source_rows)} row(s) tagged corpus_version in {sorted(source_versions)!r}.")

    with target_engine.begin() as target_conn:
        for start in range(0, len(source_rows), _BATCH_SIZE):
            batch = source_rows[start : start + _BATCH_SIZE]
            target_conn.execute(_CHUNKS_TABLE.insert(), batch)
            print(f"  ... drug_chunks: {min(start + _BATCH_SIZE, len(source_rows))}/{len(source_rows)}", flush=True)

    # Also restore rag_corpus / rag_embedding_reservation now that the
    # corpus-shaped data landed cleanly (same unchanged BUILD-18 copy).
    for table in _EMPTY_MUST_TABLES:
        with source_engine.connect() as source_conn:
            rows = [dict(row) for row in source_conn.execute(select(table)).mappings().all()]
        if not rows:
            print(f"SKIP: source table {table.name!r} has 0 rows")
            continue
        with target_engine.begin() as target_conn:
            target_conn.execute(table.insert(), rows)
        print(f"RESTORED: {table.name} rows={len(rows)}")

    # Prove the legacy rows are byte-for-byte unchanged and the new total is
    # exactly what was expected -- this is the safety proof, not a formality.
    with target_engine.connect() as target_conn:
        post_rows = {row["id"]: _row_hash(dict(row)) for row in target_conn.execute(select(_CHUNKS_TABLE)).mappings().all()}
    unchanged_legacy = all(post_rows.get(row_id) == row_hash for row_id, row_hash in pre_snapshot.items())
    expected_total = pre_count + len(source_rows)
    if not unchanged_legacy:
        print("FAIL: at least one pre-existing (legacy) drug_chunks row changed -- this must never happen")
        return 1
    if len(post_rows) != expected_total:
        print(f"FAIL: expected {expected_total} total rows after restore, found {len(post_rows)}")
        return 1

    print(f"VERIFIED: {pre_count} pre-existing row(s) byte-for-byte unchanged; {len(source_rows)} new row(s) added; total now {len(post_rows)}.")
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
