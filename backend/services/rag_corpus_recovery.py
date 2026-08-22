"""Deterministic recovery primitives for the OpenAI-backed legacy RAG corpus.

This module deliberately handles corpus identity and database idempotency only.
The command-line runner owns the OpenAI client so the application runtime never
starts a bulk embedding job implicitly.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tiktoken
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.db.models import DrugChunk, RagCorpus, RagCorpusCheckpoint, RagEmbeddingReservation
from scripts.chunk_drugs import build_chunks_for_drug

ROOT = Path(__file__).resolve().parents[2]
V1_SOURCE_DIR = ROOT / "data pharmacy" / "data-version1"
FINAL_CANONICAL_DIR = ROOT / "data pharmacy" / "v2" / "final_canonical"
CORPUS_VERSION = "legacy-drug-chunks-openai-v1"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
INDEX_VERSION = "pgvector-hnsw-cosine-v1"
USD_PER_MILLION_TOKENS = 0.02
CHECKPOINT_PENDING = "PENDING"
CHECKPOINT_COMPLETE = "COMPLETE"
CORPUS_IN_PROGRESS = "IN_PROGRESS"
CORPUS_COMPLETE = "COMPLETE"
RESERVATION_RESERVED = "RESERVED"
RESERVATION_RESPONSE_RECORDED = "RESPONSE_RECORDED"
RESERVATION_COMMITTED = "COMMITTED"
RESERVATION_UNRESOLVED = "UNRESOLVED"
RESERVATION_HISTORICAL_RECONCILED = "HISTORICAL_RECONCILED"


class EmbeddingReservationBlockedError(RuntimeError):
    """A prior request might be billable and must be reconciled manually first."""


@dataclass(frozen=True)
class CorpusChunk:
    """One active, deterministic source chunk ready for an embedding request."""

    chunk_key: str
    drug_chunk_id: str
    source_path: str
    drug_id: str
    ten_thuoc: str
    danh_muc: str
    muc_nghiem_trong: str
    field_group: str
    split_ordinal: int
    noi_dung: str
    token_count: int


@dataclass(frozen=True)
class CorpusPreflight:
    """Signed inputs and deterministic estimates for a corpus execution."""

    chunks: tuple[CorpusChunk, ...]
    source_manifest_hash: str
    chunk_manifest_hash: str
    active_drug_ids: frozenset[str]
    excluded_drug_ids: frozenset[str]
    field_group_counts: dict[str, int]
    estimated_tokens: int

    @property
    def estimated_cost_usd(self) -> float:
        return self.estimated_tokens * USD_PER_MILLION_TOKENS / 1_000_000


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def batch_key_for(chunks: tuple[CorpusChunk, ...]) -> str:
    """Stable request identity: corpus/model plus the ordered complete batch."""

    return _sha256_text(
        _canonical_json(
            {
                "corpus_version": CORPUS_VERSION,
                "embedding_model": EMBEDDING_MODEL,
                "chunk_keys": [chunk.chunk_key for chunk in chunks],
            }
        )
    )


def reservation_usage_liability(
    *, status: str, planned_tokens: int, actual_tokens: int | None, accounted_in_corpus: bool
) -> int:
    """Tokens that must consume the guard before a new provider request.

    Staged provider usage uses the reported value; unknown/reserved calls use
    their pre-authorized ceiling. Historical/committed rows already included in
    `rag_corpus.actual_tokens` contribute zero here.
    """

    if accounted_in_corpus:
        return 0
    if status in {RESERVATION_RESERVED, RESERVATION_UNRESOLVED}:
        return planned_tokens
    if status == RESERVATION_RESPONSE_RECORDED:
        return actual_tokens if actual_tokens is not None else planned_tokens
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _canonical_active_ids(canonical_dir: Path) -> tuple[frozenset[str], frozenset[str]]:
    manifest = json.loads((canonical_dir / "manifest.json").read_text(encoding="utf-8"))
    mappings = _read_jsonl(canonical_dir / "drug_id_map.jsonl")
    active_ids = frozenset(str(row["legacy_drug_id"]) for row in mappings)
    excluded_ids = frozenset(str(value) for value in manifest["excluded_ids"])
    expected_active = int(manifest["active_canonical"])
    if len(active_ids) != expected_active or active_ids.intersection(excluded_ids):
        raise ValueError("Canonical V2 active/excluded identity artifacts are inconsistent")
    return active_ids, excluded_ids


def build_preflight(
    source_dir: Path = V1_SOURCE_DIR,
    canonical_dir: Path = FINAL_CANONICAL_DIR,
) -> CorpusPreflight:
    """Build the signed active-only corpus without calling OpenAI or PostgreSQL."""

    active_ids, excluded_ids = _canonical_active_ids(canonical_dir)
    encoding = tiktoken.encoding_for_model(EMBEDDING_MODEL)
    source_manifest_rows: list[dict[str, str]] = []
    chunks: list[CorpusChunk] = []
    source_ids: set[str] = set()

    for path in sorted(source_dir.glob("*/thuoc.json")):
        relative_path = path.relative_to(source_dir).as_posix()
        rows = json.loads(path.read_text(encoding="utf-8"))
        source_manifest_rows.append(
            {"path": relative_path, "canonical_json_sha256": _sha256_text(_canonical_json(rows))}
        )
        for row in rows:
            drug_id = str(row["id"])
            source_ids.add(drug_id)
            if drug_id not in active_ids:
                continue
            split_ordinals: Counter[str] = Counter()
            for chunk in build_chunks_for_drug(row):
                field_group = str(chunk["field_group"])
                split_ordinal = split_ordinals[field_group]
                split_ordinals[field_group] += 1
                payload = {
                    "source_path": relative_path,
                    "drug_id": drug_id,
                    "ten_thuoc": str(chunk["ten_thuoc"]),
                    "danh_muc": str(chunk["danh_muc"]),
                    "muc_nghiem_trong": str(chunk["muc_nghiem_trong"]),
                    "field_group": field_group,
                    "split_ordinal": split_ordinal,
                    "noi_dung": str(chunk["noi_dung"]),
                }
                chunk_key = _sha256_text(_canonical_json(payload))
                chunks.append(
                    CorpusChunk(
                        chunk_key=chunk_key,
                        drug_chunk_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"vmec04:{CORPUS_VERSION}:{chunk_key}")),
                        source_path=relative_path,
                        drug_id=drug_id,
                        ten_thuoc=payload["ten_thuoc"],
                        danh_muc=payload["danh_muc"],
                        muc_nghiem_trong=payload["muc_nghiem_trong"],
                        field_group=field_group,
                        split_ordinal=split_ordinal,
                        noi_dung=payload["noi_dung"],
                        token_count=len(encoding.encode(payload["noi_dung"])),
                    )
                )

    if source_ids - active_ids != excluded_ids or not chunks:
        raise ValueError("V1 source and Canonical V2 active/excluded IDs are not reproducible")
    ordered_payload = [
        {
            "chunk_key": chunk.chunk_key,
            "source_path": chunk.source_path,
            "drug_id": chunk.drug_id,
            "field_group": chunk.field_group,
            "split_ordinal": chunk.split_ordinal,
        }
        for chunk in chunks
    ]
    return CorpusPreflight(
        chunks=tuple(chunks),
        source_manifest_hash=_sha256_text(_canonical_json(source_manifest_rows)),
        chunk_manifest_hash=_sha256_text(_canonical_json(ordered_payload)),
        active_drug_ids=active_ids,
        excluded_drug_ids=excluded_ids,
        field_group_counts=dict(sorted(Counter(chunk.field_group for chunk in chunks).items())),
        estimated_tokens=sum(chunk.token_count for chunk in chunks),
    )


def token_capped_batches(chunks: tuple[CorpusChunk, ...], max_tokens: int) -> list[tuple[CorpusChunk, ...]]:
    """Preserve corpus order while keeping every request within a token budget."""

    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    batches: list[tuple[CorpusChunk, ...]] = []
    current: list[CorpusChunk] = []
    current_tokens = 0
    for chunk in chunks:
        if chunk.token_count > max_tokens:
            raise ValueError(f"chunk {chunk.chunk_key} exceeds the batch token budget")
        if current and current_tokens + chunk.token_count > max_tokens:
            batches.append(tuple(current))
            current, current_tokens = [], 0
        current.append(chunk)
        current_tokens += chunk.token_count
    if current:
        batches.append(tuple(current))
    return batches


class CorpusIngestor:
    """Transaction-safe PostgreSQL persistence for a preflighted corpus."""

    def __init__(self, db: Session, preflight: CorpusPreflight) -> None:
        self._db = db
        self._preflight = preflight

    def prepare(self) -> None:
        """Register immutable metadata and pending checkpoints exactly once."""

        corpus = self._db.get(RagCorpus, CORPUS_VERSION)
        if corpus is None:
            self._db.add(
                RagCorpus(
                    corpus_version=CORPUS_VERSION,
                    source_manifest_hash=self._preflight.source_manifest_hash,
                    chunk_manifest_hash=self._preflight.chunk_manifest_hash,
                    embedding_model=EMBEDDING_MODEL,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                    index_version=INDEX_VERSION,
                    status=CORPUS_IN_PROGRESS,
                    expected_chunks=len(self._preflight.chunks),
                    estimated_tokens=self._preflight.estimated_tokens,
                    actual_tokens=0,
                    actual_cost_usd=0.0,
                )
            )
            self._db.commit()
        elif (
            corpus.source_manifest_hash != self._preflight.source_manifest_hash
            or corpus.chunk_manifest_hash != self._preflight.chunk_manifest_hash
            or corpus.embedding_model != EMBEDDING_MODEL
            or corpus.embedding_dimensions != EMBEDDING_DIMENSIONS
            or corpus.expected_chunks != len(self._preflight.chunks)
        ):
            raise ValueError("Existing corpus registry does not match this signed preflight")

        now = datetime.now(UTC)
        for offset in range(0, len(self._preflight.chunks), 1_000):
            values = [
                {
                    "id": f"{CORPUS_VERSION}:{chunk.chunk_key}",
                    "corpus_version": CORPUS_VERSION,
                    "chunk_key": chunk.chunk_key,
                    "drug_chunk_id": None,
                    "token_count": chunk.token_count,
                    "status": CHECKPOINT_PENDING,
                    "batch_number": None,
                    "request_id": None,
                    "created_at": now,
                    "updated_at": now,
                }
                for chunk in self._preflight.chunks[offset : offset + 1_000]
            ]
            self._db.execute(insert(RagCorpusCheckpoint).values(values).on_conflict_do_nothing())
            self._db.commit()

    def pending_chunks(self) -> tuple[CorpusChunk, ...]:
        """Return only chunks not committed as COMPLETE in PostgreSQL."""

        completed = set(
            self._db.scalars(
                select(RagCorpusCheckpoint.chunk_key).where(
                    RagCorpusCheckpoint.corpus_version == CORPUS_VERSION,
                    RagCorpusCheckpoint.status == CHECKPOINT_COMPLETE,
                )
            )
        )
        return tuple(chunk for chunk in self._preflight.chunks if chunk.chunk_key not in completed)

    def mark_interrupted_reservations_unresolved(self) -> int:
        """Fail closed on startup: a leftover pre-call reservation is unknown.

        We cannot distinguish a crash before the provider request from a crash
        immediately after it.  Either could be billable, so it is never retried
        automatically.
        """

        now = datetime.now(UTC)
        rows = self._db.scalars(
            select(RagEmbeddingReservation)
            .where(
                RagEmbeddingReservation.corpus_version == CORPUS_VERSION,
                RagEmbeddingReservation.status == RESERVATION_RESERVED,
            )
            .with_for_update()
        ).all()
        for row in rows:
            row.status = RESERVATION_UNRESOLVED
            row.reconciliation_note = "Process restarted before a durable provider response was recorded."
            row.updated_at = now
        self._db.commit()
        return len(rows)

    def recorded_response_reservations(self) -> tuple[RagEmbeddingReservation, ...]:
        """Staged responses can be committed on restart without another API call."""

        return tuple(
            self._db.scalars(
                select(RagEmbeddingReservation)
                .where(
                    RagEmbeddingReservation.corpus_version == CORPUS_VERSION,
                    RagEmbeddingReservation.status == RESERVATION_RESPONSE_RECORDED,
                )
                .order_by(RagEmbeddingReservation.created_at)
            )
        )

    def unresolved_reservations(self) -> tuple[RagEmbeddingReservation, ...]:
        """Unknown potentially billed requests are a terminal fail-closed gate."""

        return tuple(
            self._db.scalars(
                select(RagEmbeddingReservation)
                .where(
                    RagEmbeddingReservation.corpus_version == CORPUS_VERSION,
                    RagEmbeddingReservation.status == RESERVATION_UNRESOLVED,
                )
                .order_by(RagEmbeddingReservation.created_at)
            )
        )

    def _outstanding_usage_tokens(self) -> int:
        """Reserved, unresolved, and staged response usage not in the registry."""

        rows = self._db.execute(
            select(
                RagEmbeddingReservation.status,
                RagEmbeddingReservation.planned_token_ceiling,
                RagEmbeddingReservation.provider_input_tokens,
            ).where(
                RagEmbeddingReservation.corpus_version == CORPUS_VERSION,
                RagEmbeddingReservation.accounted_in_corpus.is_(False),
            )
        ).all()
        outstanding = 0
        for status, planned, actual in rows:
            outstanding += reservation_usage_liability(
                status=str(status),
                planned_tokens=int(planned),
                actual_tokens=int(actual) if actual is not None else None,
                accounted_in_corpus=False,
            )
        return outstanding

    def reserve_batch(self, batch: tuple[CorpusChunk, ...], *, max_cost_usd: float) -> RagEmbeddingReservation:
        """Commit a deterministic request reservation before any provider call."""

        if not batch:
            raise ValueError("Cannot reserve an empty embedding batch")
        key = batch_key_for(batch)
        now = datetime.now(UTC)
        try:
            existing = self._db.scalar(
                select(RagEmbeddingReservation)
                .where(
                    RagEmbeddingReservation.corpus_version == CORPUS_VERSION,
                    RagEmbeddingReservation.batch_key == key,
                )
                .with_for_update()
            )
            if existing is not None:
                if existing.status == RESERVATION_COMMITTED:
                    return existing
                raise EmbeddingReservationBlockedError(
                    f"Reservation {existing.id} is {existing.status}; reconcile before any retry"
                )
            corpus = self._db.scalar(
                select(RagCorpus).where(RagCorpus.corpus_version == CORPUS_VERSION).with_for_update()
            )
            if corpus is None:
                raise ValueError("Corpus registry is missing")
            planned = sum(chunk.token_count for chunk in batch)
            projected = int(corpus.actual_tokens) + self._outstanding_usage_tokens() + planned
            if projected * USD_PER_MILLION_TOKENS / 1_000_000 > max_cost_usd:
                raise EmbeddingReservationBlockedError("COST_CAP_REACHED before reserving an embedding request")
            reservation = RagEmbeddingReservation(
                corpus_version=CORPUS_VERSION,
                batch_key=key,
                chunk_keys=[chunk.chunk_key for chunk in batch],
                planned_token_ceiling=planned,
                status=RESERVATION_RESERVED,
                created_at=now,
                updated_at=now,
            )
            self._db.add(reservation)
            self._db.commit()
            return reservation
        except Exception:
            self._db.rollback()
            raise

    def record_provider_response(
        self,
        reservation_id: str,
        *,
        input_tokens: int,
        request_id: str | None,
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        """Durably store usage and vectors before touching chunks/checkpoints."""

        try:
            reservation = self._db.scalar(
                select(RagEmbeddingReservation).where(RagEmbeddingReservation.id == reservation_id).with_for_update()
            )
            if reservation is None or reservation.status != RESERVATION_RESERVED:
                raise EmbeddingReservationBlockedError("Reservation is not available to record a provider response")
            if not isinstance(input_tokens, int) or input_tokens <= 0:
                raise ValueError("Embedding API response omitted billable token usage")
            if len(vectors) != len(reservation.chunk_keys) or any(
                len(vector) != EMBEDDING_DIMENSIONS for vector in vectors
            ):
                raise ValueError("Embedding response count or vector dimension does not match reservation")
            reservation.provider_request_id = request_id
            reservation.provider_input_tokens = input_tokens
            reservation.response_embeddings = [list(vector) for vector in vectors]
            reservation.response_recorded_at = datetime.now(UTC)
            reservation.updated_at = reservation.response_recorded_at
            reservation.status = RESERVATION_RESPONSE_RECORDED
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def _apply_batch_rows(
        self,
        batch: tuple[CorpusChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
        *,
        batch_number: int,
        request_id: str | None,
        now: datetime,
    ) -> None:
        for chunk, vector in zip(batch, vectors, strict=True):
            statement = (
                insert(DrugChunk)
                .values(
                    id=chunk.drug_chunk_id,
                    drug_id=chunk.drug_id,
                    ten_thuoc=chunk.ten_thuoc,
                    danh_muc=chunk.danh_muc,
                    muc_nghiem_trong=chunk.muc_nghiem_trong,
                    field_group=chunk.field_group,
                    noi_dung=chunk.noi_dung,
                    noi_dung_unaccent=func.unaccent(chunk.noi_dung),
                    ten_thuoc_unaccent=func.unaccent(chunk.ten_thuoc),
                    embedding=list(vector),
                    corpus_version=CORPUS_VERSION,
                    chunk_key=chunk.chunk_key,
                    embedding_model=EMBEDDING_MODEL,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                    created_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["corpus_version", "chunk_key"],
                    index_where=text("corpus_version IS NOT NULL AND chunk_key IS NOT NULL"),
                )
            )
            self._db.execute(statement)
            self._db.execute(
                update(RagCorpusCheckpoint)
                .where(
                    RagCorpusCheckpoint.corpus_version == CORPUS_VERSION,
                    RagCorpusCheckpoint.chunk_key == chunk.chunk_key,
                )
                .values(
                    drug_chunk_id=chunk.drug_chunk_id,
                    status=CHECKPOINT_COMPLETE,
                    batch_number=batch_number,
                    request_id=request_id,
                    updated_at=now,
                )
            )

    def commit_recorded_response(
        self, reservation_id: str, batch: tuple[CorpusChunk, ...], *, batch_number: int
    ) -> bool:
        """Atomically apply a staged response; it is safe to call after a crash."""

        try:
            reservation = self._db.scalar(
                select(RagEmbeddingReservation).where(RagEmbeddingReservation.id == reservation_id).with_for_update()
            )
            if reservation is None:
                raise ValueError("Embedding reservation is missing")
            if reservation.status == RESERVATION_COMMITTED:
                return False
            if reservation.status != RESERVATION_RESPONSE_RECORDED:
                raise EmbeddingReservationBlockedError("Reservation has no staged provider response")
            if list(reservation.chunk_keys) != [chunk.chunk_key for chunk in batch]:
                raise ValueError("Reservation chunk keys do not match the deterministic batch")
            vectors = tuple(tuple(float(value) for value in vector) for vector in reservation.response_embeddings or ())
            if len(vectors) != len(batch):
                raise ValueError("Staged response vectors are incomplete")
            now = datetime.now(UTC)
            self._apply_batch_rows(
                batch,
                vectors,
                batch_number=batch_number,
                request_id=reservation.provider_request_id,
                now=now,
            )
            corpus = self._db.scalar(
                select(RagCorpus).where(RagCorpus.corpus_version == CORPUS_VERSION).with_for_update()
            )
            if corpus is None:
                raise ValueError("Corpus registry disappeared during ingestion")
            if not reservation.accounted_in_corpus:
                corpus.actual_tokens += int(reservation.provider_input_tokens or 0)
                corpus.actual_cost_usd = corpus.actual_tokens * USD_PER_MILLION_TOKENS / 1_000_000
            corpus.updated_at = now
            reservation.accounted_in_corpus = True
            reservation.status = RESERVATION_COMMITTED
            reservation.response_embeddings = None
            reservation.committed_at = now
            reservation.updated_at = now
            self._db.commit()
            return True
        except Exception:
            self._db.rollback()
            raise

    def reconcile_historical_usage(self) -> RagEmbeddingReservation:
        """Make the pre-0031 durable registry total explicit without rewriting it."""

        key = "HISTORICAL-0030-REGISTRY-USAGE"
        try:
            existing = self._db.scalar(
                select(RagEmbeddingReservation).where(
                    RagEmbeddingReservation.corpus_version == CORPUS_VERSION,
                    RagEmbeddingReservation.batch_key == key,
                )
            )
            if existing is not None:
                return existing
            corpus = self._db.scalar(
                select(RagCorpus).where(RagCorpus.corpus_version == CORPUS_VERSION).with_for_update()
            )
            if corpus is None:
                raise ValueError("Corpus registry is missing")
            now = datetime.now(UTC)
            reservation = RagEmbeddingReservation(
                corpus_version=CORPUS_VERSION,
                batch_key=key,
                chunk_keys=[],
                planned_token_ceiling=int(corpus.actual_tokens),
                status=RESERVATION_HISTORICAL_RECONCILED,
                provider_input_tokens=int(corpus.actual_tokens),
                accounted_in_corpus=True,
                reconciliation_note=(
                    "Historical 0030 aggregate retained verbatim; provider response IDs were not durably "
                    "recorded before BUILD-7D. This row does not assert an invoice-level reconciliation."
                ),
                created_at=now,
                updated_at=now,
            )
            self._db.add(reservation)
            self._db.commit()
            return reservation
        except Exception:
            self._db.rollback()
            raise

    def persist_batch(
        self,
        batch: tuple[CorpusChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
        *,
        batch_number: int,
        request_id: str | None,
        input_tokens: int,
    ) -> None:
        """Atomically insert vectors, complete checkpoints, and record usage."""

        if len(batch) != len(vectors) or any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
            raise ValueError("Embedding response count or vector dimension does not match the signed corpus")
        now = datetime.now(UTC)
        try:
            for chunk, vector in zip(batch, vectors, strict=True):
                statement = (
                    insert(DrugChunk)
                    .values(
                        id=chunk.drug_chunk_id,
                        drug_id=chunk.drug_id,
                        ten_thuoc=chunk.ten_thuoc,
                        danh_muc=chunk.danh_muc,
                        muc_nghiem_trong=chunk.muc_nghiem_trong,
                        field_group=chunk.field_group,
                        noi_dung=chunk.noi_dung,
                        noi_dung_unaccent=func.unaccent(chunk.noi_dung),
                        ten_thuoc_unaccent=func.unaccent(chunk.ten_thuoc),
                        embedding=list(vector),
                        corpus_version=CORPUS_VERSION,
                        chunk_key=chunk.chunk_key,
                        embedding_model=EMBEDDING_MODEL,
                        embedding_dimensions=EMBEDDING_DIMENSIONS,
                        created_at=now,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["corpus_version", "chunk_key"],
                        index_where=text("corpus_version IS NOT NULL AND chunk_key IS NOT NULL"),
                    )
                )
                self._db.execute(statement)
                self._db.execute(
                    update(RagCorpusCheckpoint)
                    .where(
                        RagCorpusCheckpoint.corpus_version == CORPUS_VERSION,
                        RagCorpusCheckpoint.chunk_key == chunk.chunk_key,
                    )
                    .values(
                        drug_chunk_id=chunk.drug_chunk_id,
                        status=CHECKPOINT_COMPLETE,
                        batch_number=batch_number,
                        request_id=request_id,
                        updated_at=now,
                    )
                )
            corpus = self._db.get(RagCorpus, CORPUS_VERSION)
            if corpus is None:
                raise ValueError("Corpus registry disappeared during ingestion")
            corpus.actual_tokens += input_tokens
            corpus.actual_cost_usd = corpus.actual_tokens * USD_PER_MILLION_TOKENS / 1_000_000
            corpus.updated_at = now
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def validate(self) -> dict[str, Any]:
        """Return post-ingestion integrity facts without changing corpus state."""

        rows = self._db.execute(
            select(
                DrugChunk.drug_id,
                DrugChunk.field_group,
                DrugChunk.chunk_key,
                DrugChunk.embedding_dimensions,
                func.vector_dims(DrugChunk.embedding),
            ).where(DrugChunk.corpus_version == CORPUS_VERSION)
        ).all()
        keys = [str(row.chunk_key) for row in rows]
        checkpoint_count = self._db.scalar(
            select(func.count())
            .select_from(RagCorpusCheckpoint)
            .where(
                RagCorpusCheckpoint.corpus_version == CORPUS_VERSION,
                RagCorpusCheckpoint.status == CHECKPOINT_COMPLETE,
            )
        )
        return {
            "rows": len(rows),
            "checkpoint_complete": int(checkpoint_count or 0),
            "field_group_counts": dict(sorted(Counter(str(row.field_group) for row in rows).items())),
            "duplicate_chunk_keys": len(keys) - len(set(keys)),
            "unexpected_drug_ids": sorted({str(row.drug_id) for row in rows} - self._preflight.active_drug_ids),
            "missing_drug_ids": sorted(self._preflight.active_drug_ids - {str(row.drug_id) for row in rows}),
            "invalid_dimensions": sum(
                row.embedding_dimensions != EMBEDDING_DIMENSIONS or row.vector_dims != EMBEDDING_DIMENSIONS
                for row in rows
            ),
        }

    def complete(self) -> None:
        """Mark the registry complete only after caller-owned validation passes."""

        corpus = self._db.get(RagCorpus, CORPUS_VERSION)
        if corpus is None:
            raise ValueError("Corpus registry is missing")
        corpus.status = CORPUS_COMPLETE
        corpus.updated_at = datetime.now(UTC)
        self._db.commit()
