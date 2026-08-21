"""BUILD-17: fail-closed RAG corpus identity verification for a target Postgres.

Run this against a target database *before* enabling any Agent V2 traffic
against it (`AGENT_RUNTIME_ENABLED=true`) -- for example, right after
restoring the BUILD-7D corpus into a new Railway staging Postgres, or as a
periodic health check. It never re-embeds anything and never calls OpenAI; it
only reads ``rag_corpus``/``drug_chunks``/``pg_indexes``/``pg_extension`` and
compares them against the known-good BUILD-7D identity recorded in
``data pharmacy/v2/rag_openai/legacy-drug-chunks-openai-v1/manifest.json``.

Usage (local venv, DATABASE_URL pointed at the target database)::

    python scripts/agent_v2/verify_rag_corpus_identity.py

Usage against a live Railway environment, without ever printing the
connection string::

    railway run --service BE --environment staging -- \
        python scripts/agent_v2/verify_rag_corpus_identity.py

Exit code 0 = identity confirmed. Exit code 1 = fail-closed: at least one
mismatch was found and the printed JSON lists every reason. No embedding
vector content, prompt, or secret is ever printed.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Support the documented direct invocation from the repository root without
# relying on a caller's PYTHONPATH (same convention as smoke_model_gateway.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402

# Known-good identity, pinned from BUILD-7C/7D's committed manifest
# (data pharmacy/v2/rag_openai/legacy-drug-chunks-openai-v1/manifest.json).
# This is intentionally a static constant, not read from the target DB it is
# checking, so a corrupted/mismatched target cannot report itself as correct.
EXPECTED_IDENTITY: dict[str, Any] = {
    "corpus_version": "legacy-drug-chunks-openai-v1",
    "status": "COMPLETE",
    "source_manifest_hash": "39ABC318DCEF1AD5D4817005DC4621DA328DE3DB26CDE56FED5A412092A2C2C0",
    "chunk_manifest_hash": "E57B24693AE64F7B1514D820911C5804DCD71CB3AAF4CF45B17A2D87603E0C04",
    "embedding_model": "text-embedding-3-small",
    "embedding_dimensions": 1536,
    "index_version": "pgvector-hnsw-cosine-v1",
    "expected_chunks": 14423,
}


@dataclass(frozen=True)
class CorpusIdentitySnapshot:
    """Raw facts read from the target database; no comparison logic here."""

    rag_corpus_row: dict[str, Any] | None
    drug_chunks_total: int
    drug_chunks_distinct_keys: int
    invalid_dimension_rows: int
    hnsw_cosine_index_present: bool
    pgvector_extension_version: str | None


def evaluate_identity(
    snapshot: CorpusIdentitySnapshot, expected: dict[str, Any] = EXPECTED_IDENTITY
) -> list[str]:
    """Pure comparison (no I/O): return every mismatch reason, empty = PASS."""

    if snapshot.rag_corpus_row is None:
        return ["RAG_CORPUS_ROW_MISSING"]

    reasons: list[str] = []
    row = snapshot.rag_corpus_row
    for field in (
        "corpus_version", "status", "source_manifest_hash", "chunk_manifest_hash",
        "embedding_model", "embedding_dimensions", "index_version",
    ):
        if row.get(field) != expected[field]:
            reasons.append(f"{field.upper()}_MISMATCH: expected={expected[field]!r} actual={row.get(field)!r}")
    if row.get("expected_chunks") != expected["expected_chunks"]:
        reasons.append(
            f"RAG_CORPUS_EXPECTED_CHUNKS_MISMATCH: expected={expected['expected_chunks']} actual={row.get('expected_chunks')!r}"
        )
    if snapshot.drug_chunks_total != expected["expected_chunks"]:
        reasons.append(
            f"DRUG_CHUNKS_ROW_COUNT_MISMATCH: expected={expected['expected_chunks']} actual={snapshot.drug_chunks_total}"
        )
    if snapshot.drug_chunks_distinct_keys != expected["expected_chunks"]:
        reasons.append(
            f"DUPLICATE_CHUNK_KEYS_DETECTED: distinct_keys={snapshot.drug_chunks_distinct_keys} expected={expected['expected_chunks']}"
        )
    if snapshot.invalid_dimension_rows != 0:
        reasons.append(f"INVALID_EMBEDDING_DIMENSIONS: rows={snapshot.invalid_dimension_rows}")
    if not snapshot.hnsw_cosine_index_present:
        reasons.append("HNSW_COSINE_INDEX_MISSING")
    if snapshot.pgvector_extension_version is None:
        reasons.append("PGVECTOR_EXTENSION_MISSING")
    return reasons


def fetch_snapshot(session: Any, *, corpus_version: str = EXPECTED_IDENTITY["corpus_version"]) -> CorpusIdentitySnapshot:
    """Thin I/O boundary: read-only queries only, never mutates the target."""

    row = session.execute(
        text("SELECT * FROM rag_corpus WHERE corpus_version = :v"), {"v": corpus_version}
    ).mappings().first()
    total = session.execute(text("SELECT count(*) FROM drug_chunks")).scalar_one()
    distinct = session.execute(text("SELECT count(DISTINCT chunk_key) FROM drug_chunks")).scalar_one()
    invalid = session.execute(
        text("SELECT count(*) FROM drug_chunks WHERE vector_dims(embedding) <> :d"),
        {"d": EXPECTED_IDENTITY["embedding_dimensions"]},
    ).scalar_one()
    hnsw_count = session.execute(
        text(
            "SELECT count(*) FROM pg_indexes WHERE tablename = 'drug_chunks' "
            "AND indexdef ILIKE '%hnsw%' AND indexdef ILIKE '%vector_cosine_ops%'"
        )
    ).scalar_one()
    extension_version = session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    return CorpusIdentitySnapshot(
        rag_corpus_row=dict(row) if row is not None else None,
        drug_chunks_total=total,
        drug_chunks_distinct_keys=distinct,
        invalid_dimension_rows=invalid,
        hnsw_cosine_index_present=hnsw_count > 0,
        pgvector_extension_version=extension_version,
    )


def main() -> int:
    from backend.db.base import SessionLocal  # deferred: needs DATABASE_URL resolved first

    session = SessionLocal()
    try:
        snapshot = fetch_snapshot(session)
    finally:
        session.close()

    mismatches = evaluate_identity(snapshot)
    result = {
        "status": "PASS" if not mismatches else "FAIL_CLOSED",
        "corpus_version": EXPECTED_IDENTITY["corpus_version"],
        "drug_chunks_rows": snapshot.drug_chunks_total,
        "mismatches": mismatches,
    }
    print(json.dumps(result, ensure_ascii=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
