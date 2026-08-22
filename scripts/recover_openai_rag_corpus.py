#!/usr/bin/env python3
"""Recover the active-only legacy RAG corpus using OpenAI embeddings.

The default is a no-cost preflight.  ``--execute`` is intentionally required
for the paid operation; it rejects every signed-input, model, dimension, and
cost mismatch before requesting an embedding.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import RagCorpus  # noqa: E402
from backend.services.rag_corpus_recovery import (  # noqa: E402
    CORPUS_VERSION,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    CorpusIngestor,
    build_preflight,
    token_capped_batches,
)

MAX_APPROVED_COST_USD = 0.29
DEFAULT_BATCH_TOKEN_CAP = 30_000
MANIFEST_PATH = ROOT / "data pharmacy" / "v2" / "rag_openai" / CORPUS_VERSION / "manifest.json"


def _value(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _api_key(settings: Any) -> str:
    key = str(getattr(settings, "openai_embedding_api_key", "") or getattr(settings, "openai_api_key", "")).strip()
    if not key or key == "sk-your-key-here":
        raise RuntimeError("OPENAI_EMBEDDING_API_KEY or OPENAI_API_KEY must be configured")
    return key


def _preflight_summary(preflight: Any, batches: list[tuple[Any, ...]]) -> dict[str, Any]:
    return {
        "corpus_version": CORPUS_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "active_drugs": len(preflight.active_drug_ids),
        "excluded_drugs": len(preflight.excluded_drug_ids),
        "chunks": len(preflight.chunks),
        "field_group_counts": preflight.field_group_counts,
        "source_manifest_hash": preflight.source_manifest_hash,
        "chunk_manifest_hash": preflight.chunk_manifest_hash,
        "estimated_tokens": preflight.estimated_tokens,
        "estimated_cost_usd": round(preflight.estimated_cost_usd, 6),
        "batches": len(batches),
    }


def _write_manifest(
    summary: dict[str, Any], actual_tokens: int, actual_cost: float, validation: dict[str, Any]
) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **summary,
        "generated_at": datetime.now(UTC).isoformat(),
        "actual_tokens": actual_tokens,
        "actual_cost_usd": round(actual_cost, 6),
        "validation": validation,
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def _run(args: argparse.Namespace) -> int:
    preflight = build_preflight()
    batches = token_capped_batches(preflight.chunks, args.batch_token_cap)
    summary = _preflight_summary(preflight, batches)
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if preflight.estimated_cost_usd > args.max_cost_usd:
        print("PREFLIGHT_FAIL: estimated cost exceeds approved cap", file=sys.stderr)
        return 2
    if not args.execute:
        print("PREFLIGHT_PASS: no OpenAI request or database write was made")
        return 0

    settings = get_settings()
    if settings.embedding_model != EMBEDDING_MODEL:
        print("PREFLIGHT_FAIL: EMBEDDING_MODEL mismatch", file=sys.stderr)
        return 2
    import openai

    client = openai.OpenAI(api_key=_api_key(settings))
    db = SessionLocal()
    started = time.monotonic()
    try:
        ingestor = CorpusIngestor(db, preflight)
        ingestor.prepare()
        historical = ingestor.reconcile_historical_usage()
        newly_unresolved = ingestor.mark_interrupted_reservations_unresolved()
        by_key = {chunk.chunk_key: chunk for chunk in preflight.chunks}
        # A staged response is applied after restart without a second API call.
        for reservation in ingestor.recorded_response_reservations():
            ingestor.commit_recorded_response(
                reservation.id,
                tuple(by_key[key] for key in reservation.chunk_keys),
                batch_number=0,
            )
        blocked = ingestor.unresolved_reservations()
        if blocked:
            raise RuntimeError(
                "UNRESOLVED_RESERVATIONS: manual provider reconciliation is required before retry: "
                + ",".join(reservation.id for reservation in blocked)
            )
        pending = ingestor.pending_chunks()
        pending_batches = token_capped_batches(pending, args.batch_token_cap)
        for number, batch in enumerate(pending_batches, start=1):
            reservation = ingestor.reserve_batch(batch, max_cost_usd=args.max_cost_usd)
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=[chunk.noi_dung for chunk in batch])
            data = _value(response, "data", ())
            usage = _value(response, "usage")
            input_tokens = _value(usage, "prompt_tokens", _value(usage, "total_tokens"))
            if not isinstance(input_tokens, int) or input_tokens <= 0:
                raise RuntimeError("Embedding API response omitted billable token usage")
            vectors = tuple(tuple(float(item) for item in _value(row, "embedding", ())) for row in data)
            if len(vectors) != len(batch) or any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
                raise RuntimeError("Embedding API returned an unexpected vector count or dimension")
            ingestor.record_provider_response(
                reservation.id,
                input_tokens=input_tokens,
                request_id=_value(response, "_request_id") or _value(response, "request_id"),
                vectors=vectors,
            )
            ingestor.commit_recorded_response(reservation.id, batch, batch_number=number)
            if number == 1 or number % 10 == 0 or number == len(pending_batches):
                corpus = db.get(RagCorpus, CORPUS_VERSION)
                print(
                    f"PROGRESS batches={number}/{len(pending_batches)} tokens={corpus.actual_tokens if corpus else 0}"
                )

        validation = ingestor.validate()
        expected = len(preflight.chunks)
        if (
            validation["rows"] != expected
            or validation["checkpoint_complete"] != expected
            or validation["field_group_counts"] != preflight.field_group_counts
            or validation["duplicate_chunk_keys"]
            or validation["unexpected_drug_ids"]
            or validation["missing_drug_ids"]
            or validation["invalid_dimensions"]
        ):
            raise RuntimeError(f"POST_INGEST_VALIDATION_FAILED: {json.dumps(validation, sort_keys=True)}")
        ingestor.complete()
        corpus = db.get(RagCorpus, CORPUS_VERSION)
        if corpus is None:
            raise RuntimeError("Corpus registry disappeared before manifest write")
        actual_tokens = int(corpus.actual_tokens)
        actual_cost = float(corpus.actual_cost_usd)
        _write_manifest(summary, actual_tokens, actual_cost, validation)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "actual_tokens": actual_tokens,
                    "actual_cost_usd": round(actual_cost, 6),
                    "historical_reservation_id": historical.id,
                    "newly_unresolved_reservations": newly_unresolved,
                    "pending_batches": len(pending_batches),
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "validation": validation,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="allow OpenAI embedding and PostgreSQL writes")
    parser.add_argument("--batch-token-cap", type=int, default=DEFAULT_BATCH_TOKEN_CAP)
    parser.add_argument("--max-cost-usd", type=float, default=MAX_APPROVED_COST_USD)
    args = parser.parse_args()
    if args.batch_token_cap <= 0 or not 0 < args.max_cost_usd <= MAX_APPROVED_COST_USD:
        parser.error(f"--max-cost-usd must be in (0, {MAX_APPROVED_COST_USD}]")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
