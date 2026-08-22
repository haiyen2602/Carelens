"""Session-scoped, non-authoritative short-term memory for Agent V2.

The store is deliberately in-process only for BUILD-5.  It is keyed by the
authenticated actor, conversation, and session; it is never a source of
clinical or operational truth.  Callers must obtain authoritative patient,
prescription, dose, and safety facts through the approved domain tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock

from backend.agents.v2.context import (
    ContextAuthority,
    ContextBuildResult,
    ContextItem,
    ContextLayer,
    ContextManager,
    MemoryKind,
)


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class ShortTermMemoryEntryType(StrEnum):
    MESSAGE = "MESSAGE"
    CURRENT_TASK = "CURRENT_TASK"
    RESOLVED_REFERENCE = "RESOLVED_REFERENCE"
    PENDING_CLARIFICATION = "PENDING_CLARIFICATION"


@dataclass(frozen=True)
class SessionMemoryKey:
    """Privacy boundary for a single current Agent conversation session."""

    actor_id: str
    conversation_id: str
    session_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("actor_id", self.actor_id),
            ("conversation_id", self.conversation_id),
            ("session_id", self.session_id),
        ):
            if not value or not value.strip():
                raise ValueError(f"{name} is required for short-term memory isolation")


@dataclass(frozen=True)
class MemoryContextRequest:
    """Explicit relevance controls; BUILD-5 performs no semantic retrieval."""

    minimum_relevance: float = 0.5
    max_recent_messages: int = 8
    resolved_reference_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_relevance <= 1.0:
            raise ValueError("minimum_relevance must be between 0 and 1")
        if self.max_recent_messages < 0:
            raise ValueError("max_recent_messages must be non-negative")


@dataclass(frozen=True)
class ShortTermMemoryEntry:
    id: str
    entry_type: ShortTermMemoryEntryType
    content: str
    token_count: int
    relevance: float
    created_at: datetime
    role: MessageRole | None = None
    reference_id: str | None = None
    provenance: str = ""
    compact_content: str | None = None
    compact_token_count: int | None = None
    reference: str | None = None
    reference_token_count: int = 12

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("short-term memory entry id is required")
        if self.token_count < 0 or self.reference_token_count < 0:
            raise ValueError("short-term memory token counts must be non-negative")
        if not 0.0 <= self.relevance <= 1.0:
            raise ValueError("short-term memory relevance must be between 0 and 1")
        if self.entry_type is ShortTermMemoryEntryType.MESSAGE and self.role is None:
            raise ValueError("message entries require a role")
        if self.entry_type is not ShortTermMemoryEntryType.MESSAGE and self.role is not None:
            raise ValueError("only message entries may have a role")
        if self.entry_type is ShortTermMemoryEntryType.RESOLVED_REFERENCE and not self.reference_id:
            raise ValueError("resolved references require a reference_id")
        if self.compact_content is None and self.compact_token_count is not None:
            raise ValueError("compact_token_count requires compact_content")
        if self.compact_token_count is not None and not 0 <= self.compact_token_count < self.token_count:
            raise ValueError("compact_token_count must be smaller than token_count")


class ShortTermMemoryStore:
    """Thread-safe, process-local store with no cross-session lookup API."""

    def __init__(self, context_manager: ContextManager) -> None:
        self._context_manager = context_manager
        self._entries: dict[SessionMemoryKey, list[ShortTermMemoryEntry]] = {}
        self._lock = RLock()

    def append_message(
        self,
        key: SessionMemoryKey,
        *,
        entry_id: str,
        role: MessageRole,
        content: str,
        token_count: int,
        relevance: float = 1.0,
        created_at: datetime | None = None,
        compact_content: str | None = None,
        compact_token_count: int | None = None,
        reference: str | None = None,
        reference_token_count: int = 12,
    ) -> None:
        self._append(
            key,
            ShortTermMemoryEntry(
                id=entry_id,
                entry_type=ShortTermMemoryEntryType.MESSAGE,
                content=content,
                token_count=token_count,
                relevance=relevance,
                created_at=created_at or datetime.now(UTC),
                role=role,
                provenance=f"short-term-memory:message:{role.value.lower()}",
                compact_content=compact_content,
                compact_token_count=compact_token_count,
                reference=reference,
                reference_token_count=reference_token_count,
            ),
        )

    def set_current_task(
        self,
        key: SessionMemoryKey,
        *,
        entry_id: str,
        task_or_intent: str,
        token_count: int,
        created_at: datetime | None = None,
    ) -> None:
        self._replace_singleton(
            key,
            ShortTermMemoryEntry(
                id=entry_id,
                entry_type=ShortTermMemoryEntryType.CURRENT_TASK,
                content=task_or_intent,
                token_count=token_count,
                relevance=1.0,
                created_at=created_at or datetime.now(UTC),
                provenance="short-term-memory:current-task",
            ),
        )

    def add_resolved_reference(
        self,
        key: SessionMemoryKey,
        *,
        entry_id: str,
        reference_id: str,
        content: str,
        token_count: int,
        provenance: str,
        relevance: float = 1.0,
        created_at: datetime | None = None,
        compact_content: str | None = None,
        compact_token_count: int | None = None,
        reference: str | None = None,
        reference_token_count: int = 12,
    ) -> None:
        if not provenance or not provenance.strip():
            raise ValueError("resolved reference provenance is required")
        self._append(
            key,
            ShortTermMemoryEntry(
                id=entry_id,
                entry_type=ShortTermMemoryEntryType.RESOLVED_REFERENCE,
                content=content,
                token_count=token_count,
                relevance=relevance,
                created_at=created_at or datetime.now(UTC),
                reference_id=reference_id,
                provenance=provenance,
                compact_content=compact_content,
                compact_token_count=compact_token_count,
                reference=reference,
                reference_token_count=reference_token_count,
            ),
        )

    def set_pending_clarification(
        self,
        key: SessionMemoryKey,
        *,
        entry_id: str,
        clarification: str,
        token_count: int,
        created_at: datetime | None = None,
    ) -> None:
        self._replace_singleton(
            key,
            ShortTermMemoryEntry(
                id=entry_id,
                entry_type=ShortTermMemoryEntryType.PENDING_CLARIFICATION,
                content=clarification,
                token_count=token_count,
                relevance=1.0,
                created_at=created_at or datetime.now(UTC),
                provenance="short-term-memory:pending-clarification",
            ),
        )

    def context_items(
        self,
        key: SessionMemoryKey,
        request: MemoryContextRequest = MemoryContextRequest(),
    ) -> tuple[ContextItem, ...]:
        """Return only relevant session entries, all explicitly non-authoritative."""
        with self._lock:
            entries = tuple(self._entries.get(key, ()))

        selected = self._select_relevant(entries, request)
        return tuple(self._to_context_item(entry) for entry in selected)

    def build_context(
        self,
        key: SessionMemoryKey,
        request: MemoryContextRequest = MemoryContextRequest(),
    ) -> ContextBuildResult:
        """Integrate short-term entries with the BUILD-4 Context Manager."""
        return self._context_manager.build(self.context_items(key, request))

    def clear(self, key: SessionMemoryKey) -> None:
        """Clear exactly one session; no global cross-user/session mutation exists."""
        with self._lock:
            self._entries.pop(key, None)

    def _append(self, key: SessionMemoryKey, entry: ShortTermMemoryEntry) -> None:
        with self._lock:
            entries = self._entries.setdefault(key, [])
            if any(existing.id == entry.id for existing in entries):
                raise ValueError("short-term memory entry ids must be unique within a session")
            entries.append(entry)

    def _replace_singleton(self, key: SessionMemoryKey, entry: ShortTermMemoryEntry) -> None:
        with self._lock:
            entries = self._entries.setdefault(key, [])
            if any(existing.id == entry.id and existing.entry_type is not entry.entry_type for existing in entries):
                raise ValueError("short-term memory entry ids must be unique within a session")
            entries[:] = [existing for existing in entries if existing.entry_type is not entry.entry_type]
            entries.append(entry)

    @staticmethod
    def _select_relevant(
        entries: tuple[ShortTermMemoryEntry, ...], request: MemoryContextRequest
    ) -> tuple[ShortTermMemoryEntry, ...]:
        always = [
            entry
            for entry in entries
            if entry.entry_type
            in {ShortTermMemoryEntryType.CURRENT_TASK, ShortTermMemoryEntryType.PENDING_CLARIFICATION}
        ]
        relevant_messages = [
            entry
            for entry in entries
            if entry.entry_type is ShortTermMemoryEntryType.MESSAGE and entry.relevance >= request.minimum_relevance
        ]
        recent_messages = sorted(relevant_messages, key=lambda entry: entry.created_at, reverse=True)[: request.max_recent_messages]
        references = [
            entry
            for entry in entries
            if entry.entry_type is ShortTermMemoryEntryType.RESOLVED_REFERENCE
            and entry.reference_id in request.resolved_reference_ids
            and entry.relevance >= request.minimum_relevance
        ]
        return tuple(always + recent_messages + references)

    @staticmethod
    def _to_context_item(entry: ShortTermMemoryEntry) -> ContextItem:
        authority = (
            ContextAuthority.USER_ASSERTED
            if entry.entry_type is ShortTermMemoryEntryType.MESSAGE and entry.role is MessageRole.USER
            else ContextAuthority.MEMORY
        )
        priority = {
            ShortTermMemoryEntryType.PENDING_CLARIFICATION: 90,
            ShortTermMemoryEntryType.CURRENT_TASK: 80,
            ShortTermMemoryEntryType.RESOLVED_REFERENCE: 60,
            ShortTermMemoryEntryType.MESSAGE: 50,
        }[entry.entry_type]
        return ContextItem(
            id=f"short-term:{entry.id}",
            layer=ContextLayer.MEMORY,
            content=entry.content,
            token_count=entry.token_count,
            authority=authority,
            priority=priority,
            provenance=entry.provenance,
            freshness=entry.created_at,
            relevance=entry.relevance,
            memory_kind=MemoryKind.SHORT_TERM,
            compact_content=entry.compact_content,
            compact_token_count=entry.compact_token_count,
            reference=entry.reference,
            reference_token_count=entry.reference_token_count,
        )
