"""Policy-gated, non-authoritative memory and artifact primitives for Agent V2.

BUILD-11 deliberately does not collect memory by default.  A caller must supply
an explicit approved policy and consent before a record can be retained.  This
module is scoped by authenticated actor, subject, and conversation and always
returns recalled content as ``MEMORY`` authority; it cannot substitute for an
Operational DB, Safety, Doctor, or Drug Knowledge V2 lookup.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import RLock

from backend.agents.v2.context import (
    ContextAuthority,
    ContextBuildResult,
    ContextItem,
    ContextLayer,
    ContextManager,
    ContextSensitivity,
    MemoryKind,
    VerificationStatus,
)
from backend.agents.v2.short_term_memory import (
    MemoryContextRequest,
    SessionMemoryKey,
    ShortTermMemoryStore,
)


class MemoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class RetentionClass(StrEnum):
    APPROVED_LONG_TERM = "APPROVED_LONG_TERM"
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"


_KIND_TO_RETENTION = {
    MemoryKind.LONG_TERM_FACT: RetentionClass.APPROVED_LONG_TERM,
    MemoryKind.EPISODIC: RetentionClass.EPISODIC,
    MemoryKind.SEMANTIC: RetentionClass.SEMANTIC,
}
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class MemoryScope:
    """Explicit boundary for all non-session Agent V2 memory reads/writes."""

    actor_id: str
    subject_user_id: str
    conversation_id: str
    patient_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("actor_id", self.actor_id),
            ("subject_user_id", self.subject_user_id),
            ("conversation_id", self.conversation_id),
        ):
            if not value or not value.strip():
                raise ValueError(f"{name} is required for memory isolation")
        if self.patient_id is not None and not self.patient_id.strip():
            raise ValueError("patient_id cannot be blank")


@dataclass(frozen=True)
class MemoryCollectionPolicy:
    """Human-approved collection policy; disabled unless all gates are explicit."""

    policy_id: str
    version: str
    approved: bool
    require_consent: bool
    allowed_categories: frozenset[str]
    allowed_kinds: frozenset[MemoryKind]
    max_retention: timedelta

    def __post_init__(self) -> None:
        if not self.policy_id or not self.version:
            raise ValueError("memory policy id and version are required")
        if not self.allowed_categories:
            raise ValueError("memory policy must name allowed categories")
        if not self.allowed_kinds <= frozenset(_KIND_TO_RETENTION):
            raise ValueError("short-term memory cannot be stored in long-term memory")
        if self.max_retention <= timedelta(0):
            raise ValueError("memory policy max_retention must be positive")


@dataclass(frozen=True)
class MemoryRecord:
    """A recalled record has metadata needed for traceability and safe expiry."""

    memory_id: str
    scope: MemoryScope
    memory_kind: MemoryKind
    category: str
    content: str
    token_count: int
    source: str
    provenance: str
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    confidence: float
    sensitivity: ContextSensitivity
    retention_class: RetentionClass
    expires_at: datetime
    status: MemoryStatus = MemoryStatus.ACTIVE
    invalidation_reason: str | None = None
    compact_summary: str | None = None
    compact_token_count: int | None = None
    artifact_reference: str | None = None
    artifact_reference_token_count: int = 12

    def __post_init__(self) -> None:
        if not self.memory_id or not self.category or not self.content:
            raise ValueError("memory id, category, and content are required")
        if self.memory_kind not in _KIND_TO_RETENTION:
            raise ValueError("only long-term, episodic, and semantic records are valid here")
        if self.retention_class is not _KIND_TO_RETENTION[self.memory_kind]:
            raise ValueError("retention_class must match memory_kind")
        if self.token_count < 0 or self.artifact_reference_token_count < 0:
            raise ValueError("memory token counts must be non-negative")
        if self.compact_summary is None and self.compact_token_count is not None:
            raise ValueError("compact_token_count requires compact_summary")
        if self.compact_token_count is not None and not 0 <= self.compact_token_count < self.token_count:
            raise ValueError("compact_token_count must be smaller than token_count")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("memory confidence must be between 0 and 1")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("memory timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("memory expires_at must be after created_at")
        if not self.source or not self.provenance:
            raise ValueError("memory source and provenance are required")
        if self.status is MemoryStatus.INVALIDATED and not self.invalidation_reason:
            raise ValueError("invalidated memory requires an invalidation_reason")

    def is_stale(self, now: datetime) -> bool:
        return self.last_verified_at is None or self.last_verified_at < self.updated_at

    def is_recallable(self, now: datetime) -> bool:
        return self.status is MemoryStatus.ACTIVE and self.expires_at > now and not self.is_stale(now)

    def to_context_item(self) -> ContextItem:
        """Convert to explicitly non-authoritative Memory Context."""
        return ContextItem(
            id=f"long-term:{self.memory_id}",
            layer=ContextLayer.MEMORY,
            content=self.content,
            token_count=self.token_count,
            authority=ContextAuthority.MEMORY,
            priority=70 if self.memory_kind is MemoryKind.LONG_TERM_FACT else 55,
            provenance=self.provenance,
            freshness=self.last_verified_at or self.updated_at,
            relevance=self.confidence,
            memory_kind=self.memory_kind,
            compact_content=self.compact_summary,
            compact_token_count=self.compact_token_count,
            reference=self.artifact_reference,
            reference_token_count=self.artifact_reference_token_count,
            sensitivity=self.sensitivity,
            verification_status=VerificationStatus.VERIFIED,
        )


@dataclass(frozen=True)
class MemoryRecallResult:
    records: tuple[MemoryRecord, ...]
    stale_or_inactive_ids: tuple[str, ...]


class LongTermMemoryStore:
    """Thread-safe local implementation with no cross-scope lookup path.

    It is an adapter boundary, not a clinical persistence mechanism. Production
    durable storage/consent administration requires a separately approved
    persistence contract before Agent V2 can be enabled.
    """

    def __init__(self, policy: MemoryCollectionPolicy, context_manager: ContextManager) -> None:
        self._policy = policy
        self._context_manager = context_manager
        self._records: dict[MemoryScope, dict[str, MemoryRecord]] = {}
        self._lock = RLock()

    def retain(self, record: MemoryRecord, *, consent_granted: bool) -> bool:
        """Store an approved record once; return False for an idempotent retry."""
        self._validate_retention(record, consent_granted)
        with self._lock:
            scoped = self._records.setdefault(record.scope, {})
            previous = scoped.get(record.memory_id)
            if previous is not None:
                if previous == record:
                    return False
                raise ValueError("memory_id cannot be reused for different content")
            scoped[record.memory_id] = record
            return True

    def invalidate(self, scope: MemoryScope, memory_id: str, *, reason: str, now: datetime | None = None) -> MemoryRecord:
        if not reason or not reason.strip():
            raise ValueError("memory invalidation reason is required")
        with self._lock:
            try:
                current = self._records[scope][memory_id]
            except KeyError as error:
                raise ValueError("memory record was not found in this scope") from error
            if current.status is MemoryStatus.INVALIDATED:
                return current
            invalidated = replace(
                current,
                status=MemoryStatus.INVALIDATED,
                invalidation_reason=reason,
                updated_at=now or datetime.now(UTC),
            )
            self._records[scope][memory_id] = invalidated
            return invalidated

    def recall(
        self,
        scope: MemoryScope,
        *,
        now: datetime | None = None,
        kinds: frozenset[MemoryKind] | None = None,
        minimum_confidence: float = 0.0,
        limit: int = 10,
    ) -> MemoryRecallResult:
        """Recall only fresh records from the exact authenticated scope."""
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if limit < 0:
            raise ValueError("memory recall limit must be non-negative")
        requested_kinds = kinds or frozenset(_KIND_TO_RETENTION)
        if not requested_kinds <= frozenset(_KIND_TO_RETENTION):
            raise ValueError("invalid long-term memory kind requested")
        at = now or datetime.now(UTC)
        with self._lock:
            records = tuple(self._records.get(scope, {}).values())
        eligible = [
            record
            for record in records
            if record.memory_kind in requested_kinds
            and record.confidence >= minimum_confidence
            and record.is_recallable(at)
        ]
        eligible.sort(key=lambda record: (record.confidence, record.last_verified_at or record.updated_at), reverse=True)
        stale_or_inactive = tuple(
            record.memory_id
            for record in records
            if record.memory_kind in requested_kinds and not record.is_recallable(at)
        )
        return MemoryRecallResult(tuple(eligible[:limit]), stale_or_inactive)

    def context_items(self, scope: MemoryScope, **recall_options: object) -> tuple[ContextItem, ...]:
        return tuple(record.to_context_item() for record in self.recall(scope, **recall_options).records)

    def build_context(self, scope: MemoryScope, **recall_options: object) -> ContextBuildResult:
        return self._context_manager.build(self.context_items(scope, **recall_options))

    def _validate_retention(self, record: MemoryRecord, consent_granted: bool) -> None:
        if not self._policy.approved:
            raise PermissionError("long-term memory collection is not approved")
        if self._policy.require_consent and not consent_granted:
            raise PermissionError("long-term memory consent is required")
        if record.category not in self._policy.allowed_categories:
            raise PermissionError("memory category is not approved")
        if record.memory_kind not in self._policy.allowed_kinds:
            raise PermissionError("memory kind is not approved")
        if record.expires_at - record.created_at > self._policy.max_retention:
            raise PermissionError("memory retention exceeds approved policy")


class AgentMemoryContextBuilder:
    """Combine bounded session and policy-gated long-term context safely."""

    def __init__(
        self,
        context_manager: ContextManager,
        short_term: ShortTermMemoryStore,
        long_term: LongTermMemoryStore,
    ) -> None:
        self._context_manager = context_manager
        self._short_term = short_term
        self._long_term = long_term

    def build(
        self,
        session_key: SessionMemoryKey,
        memory_scope: MemoryScope,
        *,
        short_term_request: MemoryContextRequest = MemoryContextRequest(),
        long_term_kinds: frozenset[MemoryKind] | None = None,
    ) -> ContextBuildResult:
        if session_key.actor_id != memory_scope.actor_id or session_key.conversation_id != memory_scope.conversation_id:
            raise PermissionError("short-term and long-term memory scopes must match")
        return self._context_manager.build(
            [
                *self._short_term.context_items(session_key, short_term_request),
                *self._long_term.context_items(memory_scope, kinds=long_term_kinds),
            ]
        )


@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    uri: str
    summary: str
    provenance: str
    sensitivity: ContextSensitivity
    sha256: str
    byte_count: int
    created_at: datetime


class FileSystemArtifactOffload:
    """Local, non-authoritative artifact offload with integrity verification.

    Personal, health, and restricted content is denied by default. This class is intentionally
    a replaceable adapter; local disk is not production durable storage.
    """

    def __init__(self, root: Path, *, allow_sensitive_offload: bool = False) -> None:
        self._root = root.resolve()
        self._allow_sensitive_offload = allow_sensitive_offload
        self._lock = RLock()

    def offload(
        self,
        *,
        artifact_id: str,
        payload: bytes,
        summary: str,
        provenance: str,
        sensitivity: ContextSensitivity = ContextSensitivity.PUBLIC,
        created_at: datetime | None = None,
    ) -> ArtifactReference:
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ValueError("artifact_id must be a safe, non-path identifier")
        if not payload or not summary.strip() or not provenance.strip():
            raise ValueError("artifact payload, summary, and provenance are required")
        if sensitivity is not ContextSensitivity.PUBLIC and not self._allow_sensitive_offload:
            raise PermissionError("sensitive artifacts require an approved durable storage adapter")
        checksum = sha256(payload).hexdigest()
        filename = f"{artifact_id}-{checksum}.bin"
        path = self._root / filename
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if path.read_bytes() != payload:
                    raise ValueError("artifact id collision with a different payload")
            else:
                temporary = self._root / f".{filename}.tmp"
                with open(temporary, "xb") as file:
                    file.write(payload)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, path)
        return ArtifactReference(
            artifact_id=artifact_id,
            uri=f"artifact://{artifact_id}/{checksum}",
            summary=summary,
            provenance=provenance,
            sensitivity=sensitivity,
            sha256=checksum,
            byte_count=len(payload),
            created_at=created_at or datetime.now(UTC),
        )

    def read(self, reference: ArtifactReference) -> bytes:
        if not _ARTIFACT_ID.fullmatch(reference.artifact_id):
            raise ValueError("invalid artifact reference")
        path = self._root / f"{reference.artifact_id}-{reference.sha256}.bin"
        with self._lock:
            try:
                payload = path.read_bytes()
            except FileNotFoundError as error:
                raise ValueError("artifact was not found") from error
        if len(payload) != reference.byte_count or sha256(payload).hexdigest() != reference.sha256:
            raise ValueError("artifact integrity verification failed")
        return payload


@dataclass(frozen=True)
class CompactionRecord:
    source_item_id: str
    source_sha256: str
    compaction_version: str
    summary: str
    token_count: int
    provenance: str
    reference: str | None


class ContextCompactor:
    """Deterministic compaction boundary; it never edits protected facts."""

    VERSION = "build-11-v1"

    def compact(self, item: ContextItem, *, summary: str, token_count: int) -> CompactionRecord:
        if item.never_drop or item.protected:
            raise PermissionError("policy and authoritative clinical context cannot be compacted")
        if not summary.strip() or not 0 <= token_count < item.token_count:
            raise ValueError("compaction must reduce a non-empty context item")
        return CompactionRecord(
            source_item_id=item.id,
            source_sha256=sha256(item.content.encode("utf-8")).hexdigest(),
            compaction_version=self.VERSION,
            summary=summary,
            token_count=token_count,
            provenance=f"{item.provenance}|context-compactor:{self.VERSION}",
            reference=item.reference,
        )

    @staticmethod
    def apply(item: ContextItem, record: CompactionRecord) -> ContextItem:
        if item.id != record.source_item_id:
            raise ValueError("compaction record does not belong to context item")
        if sha256(item.content.encode("utf-8")).hexdigest() != record.source_sha256:
            raise ValueError("compaction source content changed")
        return replace(
            item,
            compact_content=record.summary,
            compact_token_count=record.token_count,
            provenance=record.provenance,
        )
