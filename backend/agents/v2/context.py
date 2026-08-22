"""Context budgeting and provenance handling for the disabled Agent V2 path.

This module does not persist memory, retrieve RAG documents, or mutate domain
facts. It only creates a bounded model-input view of ContextItems supplied by
future domain adapters.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any


class ContextLayer(StrEnum):
    POLICY = "POLICY"
    SYSTEM = "SYSTEM"
    TASK = "TASK"
    USER = "USER"
    MEMORY = "MEMORY"
    RETRIEVAL = "RETRIEVAL"
    TOOL = "TOOL"


class ContextAuthority(IntEnum):
    UNTRUSTED = 0
    USER_ASSERTED = 10
    MEMORY = 20
    RETRIEVAL = 30
    TOOL = 40
    DRUG_KNOWLEDGE_V2 = 70
    OPERATIONAL_DB = 80
    SAFETY_DOMAIN = 90
    DOCTOR = 95
    SYSTEM = 100
    POLICY = 110


class MemoryKind(StrEnum):
    SHORT_TERM = "SHORT_TERM"
    LONG_TERM_FACT = "LONG_TERM_FACT"
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"


class ContextSensitivity(StrEnum):
    """Data-handling classification carried with a context item."""

    PUBLIC = "PUBLIC"
    PERSONAL = "PERSONAL"
    HEALTH = "HEALTH"
    RESTRICTED = "RESTRICTED"


class VerificationStatus(StrEnum):
    """Whether a context value is a claim, verified reference, or stale."""

    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    STALE = "STALE"


class ContextDisposition(StrEnum):
    KEPT = "KEPT"
    COMPACTED = "COMPACTED"
    OFFLOADED_REFERENCE = "OFFLOADED_REFERENCE"
    DROPPED = "DROPPED"


class ContextBuildStatus(StrEnum):
    READY = "READY"
    OVERFLOW = "OVERFLOW"


_AUTHORITATIVE_CLINICAL_AUTHORITIES = frozenset(
    {
        ContextAuthority.DRUG_KNOWLEDGE_V2,
        ContextAuthority.OPERATIONAL_DB,
        ContextAuthority.SAFETY_DOMAIN,
        ContextAuthority.DOCTOR,
    }
)


@dataclass(frozen=True)
class ContextItem:
    id: str
    layer: ContextLayer
    content: str
    token_count: int
    authority: ContextAuthority
    priority: int
    provenance: str
    freshness: datetime | None = None
    relevance: float = 0.0
    memory_kind: MemoryKind | None = None
    compact_content: str | None = None
    compact_token_count: int | None = None
    reference: str | None = None
    reference_token_count: int = 12
    sensitivity: ContextSensitivity = ContextSensitivity.PUBLIC
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED

    def __post_init__(self) -> None:
        if self.token_count < 0 or self.reference_token_count < 0:
            raise ValueError("context token counts must be non-negative")
        if self.memory_kind is not None and self.layer is not ContextLayer.MEMORY:
            raise ValueError("memory_kind is valid only for MEMORY context")
        if self.memory_kind is not None and self.authority not in {
            ContextAuthority.UNTRUSTED,
            ContextAuthority.USER_ASSERTED,
            ContextAuthority.MEMORY,
        }:
            raise ValueError("recalled memory cannot claim authoritative domain authority")
        if self.compact_content is None and self.compact_token_count is not None:
            raise ValueError("compact_token_count requires compact_content")
        if self.compact_token_count is not None and not 0 <= self.compact_token_count < self.token_count:
            raise ValueError("compact_token_count must be smaller than the original token_count")

    @property
    def never_drop(self) -> bool:
        return self.layer is ContextLayer.POLICY

    @property
    def protected(self) -> bool:
        return self.layer is ContextLayer.SYSTEM or self.authority in _AUTHORITATIVE_CLINICAL_AUTHORITIES


@dataclass(frozen=True)
class ContextBudget:
    input_token_budget: int
    output_token_reserve: int
    total_run_token_budget: int
    memory_fractions: dict[MemoryKind, float]

    @classmethod
    def from_settings(cls, settings: Any) -> "ContextBudget":
        total = int(settings.agent_token_budget)
        configured_input = int(settings.agent_context_token_budget)
        output_reserve = int(settings.agent_output_token_reserve)
        if configured_input + output_reserve > total:
            raise ValueError("AGENT_CONTEXT_TOKEN_BUDGET + AGENT_OUTPUT_TOKEN_RESERVE exceeds AGENT_TOKEN_BUDGET")
        fractions = {
            MemoryKind.SHORT_TERM: float(settings.agent_context_short_term_fraction),
            MemoryKind.LONG_TERM_FACT: float(settings.agent_context_long_term_facts_fraction),
            MemoryKind.EPISODIC: float(settings.agent_context_episodic_fraction),
            MemoryKind.SEMANTIC: float(settings.agent_context_semantic_fraction),
        }
        if sum(fractions.values()) > 1:
            raise ValueError("Agent memory context fractions exceed the context budget")
        return cls(configured_input, output_reserve, total, fractions)

    def memory_cap(self, kind: MemoryKind) -> int:
        return int(self.input_token_budget * self.memory_fractions[kind])


@dataclass(frozen=True)
class ContextSelection:
    item: ContextItem
    disposition: ContextDisposition
    rendered_content: str | None
    rendered_token_count: int
    reason: str | None = None


@dataclass(frozen=True)
class ContextBuildResult:
    status: ContextBuildStatus
    selections: tuple[ContextSelection, ...]
    input_token_budget: int
    output_token_reserve: int
    consumed_input_tokens: int
    overflow_reason: str | None = None

    @property
    def included(self) -> tuple[ContextSelection, ...]:
        return tuple(selection for selection in self.selections if selection.disposition is not ContextDisposition.DROPPED)


class ContextManager:
    """Build a prioritized model-input view without changing source facts."""

    def __init__(self, budget: ContextBudget) -> None:
        self._budget = budget

    def build(self, items: list[ContextItem] | tuple[ContextItem, ...]) -> ContextBuildResult:
        if len({item.id for item in items}) != len(items):
            raise ValueError("context item ids must be unique")

        selections: list[ContextSelection] = []
        consumed = 0
        overflow_reason: str | None = None
        memory_used = {kind: 0 for kind in MemoryKind}
        for item in self._ordered(items):
            if item.never_drop or item.protected:
                selections.append(ContextSelection(item, ContextDisposition.KEPT, item.content, item.token_count))
                consumed += item.token_count
                if consumed > self._budget.input_token_budget:
                    overflow_reason = overflow_reason or "PROTECTED_CONTEXT_EXCEEDS_INPUT_BUDGET"
                continue

            remaining = self._budget.input_token_budget - consumed
            memory_remaining = self._memory_remaining(item, memory_used)
            allowed = min(remaining, memory_remaining) if memory_remaining is not None else remaining
            selection = self._fit(item, allowed)
            selections.append(selection)
            if selection.disposition is ContextDisposition.DROPPED:
                continue
            consumed += selection.rendered_token_count
            if item.memory_kind is not None:
                memory_used[item.memory_kind] += selection.rendered_token_count

        status = ContextBuildStatus.OVERFLOW if overflow_reason else ContextBuildStatus.READY
        return ContextBuildResult(
            status=status,
            selections=tuple(selections),
            input_token_budget=self._budget.input_token_budget,
            output_token_reserve=self._budget.output_token_reserve,
            consumed_input_tokens=consumed,
            overflow_reason=overflow_reason,
        )

    def _memory_remaining(self, item: ContextItem, memory_used: dict[MemoryKind, int]) -> int | None:
        if item.memory_kind is None:
            return None
        return self._budget.memory_cap(item.memory_kind) - memory_used[item.memory_kind]

    @staticmethod
    def _fit(item: ContextItem, allowed: int) -> ContextSelection:
        if item.token_count <= allowed:
            return ContextSelection(item, ContextDisposition.KEPT, item.content, item.token_count)
        if item.compact_content is not None and item.compact_token_count is not None and item.compact_token_count <= allowed:
            return ContextSelection(
                item,
                ContextDisposition.COMPACTED,
                item.compact_content,
                item.compact_token_count,
                "BUDGET_COMPACTION",
            )
        if item.reference is not None and item.reference_token_count <= allowed:
            return ContextSelection(
                item,
                ContextDisposition.OFFLOADED_REFERENCE,
                f"[context reference: {item.reference}]",
                item.reference_token_count,
                "BUDGET_OFFLOAD_REFERENCE",
            )
        reason = "MEMORY_ALLOCATION_CAP" if allowed < item.token_count and item.memory_kind is not None else "BUDGET_IRRELEVANT"
        return ContextSelection(item, ContextDisposition.DROPPED, None, 0, reason)

    @staticmethod
    def _ordered(items: list[ContextItem] | tuple[ContextItem, ...]) -> list[ContextItem]:
        layer_order = {ContextLayer.POLICY: 0, ContextLayer.SYSTEM: 1}

        def key(item: ContextItem) -> tuple[int, int, int, float, float]:
            protected_order = layer_order.get(item.layer, 2)
            freshness = item.freshness.timestamp() if item.freshness else 0.0
            return (protected_order, -item.priority, -int(item.authority), -item.relevance, -freshness)

        return sorted(items, key=key)
