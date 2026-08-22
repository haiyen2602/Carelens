"""Bounded, typed Retrieval Gateway for Agent V2 public drug knowledge."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import ceil
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.agents.v2.context import ContextAuthority, ContextItem, ContextLayer
from backend.agents.v2.model_gateway import EmbeddingGateway
from backend.services.agent_retrieval import DomainRetrievalResult, RetrievedKnowledgeDocument


class RetrievalStatus(StrEnum):
    READY = "READY"
    NO_RESULTS = "NO_RESULTS"
    INVALID_QUERY = "INVALID_QUERY"
    UNAVAILABLE = "UNAVAILABLE"


class RetrievalRequest(BaseModel):
    """Public knowledge query only; patient/user fields are forbidden by schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=5_000)


@dataclass(frozen=True)
class RetrievalConfig:
    embedding_model: str
    top_k: int
    token_budget: int

    @classmethod
    def from_settings(cls, settings: object) -> RetrievalConfig:
        model = str(getattr(settings, "agent_embedding_model", "") or "").strip()
        if model != "text-embedding-3-small":
            raise ValueError("BUILD-7 requires AGENT_EMBEDDING_MODEL=text-embedding-3-small")
        top_k = int(getattr(settings, "agent_retrieval_top_k"))
        token_budget = int(getattr(settings, "agent_retrieval_token_budget"))
        if top_k < 1 or token_budget < 1:
            raise ValueError("Agent retrieval top-k and token budget must be positive")
        return cls(embedding_model=model, top_k=top_k, token_budget=token_budget)


class RetrievalDomain(Protocol):
    def retrieve(self, *, query: str, embedding: tuple[float, ...], top_k: int) -> DomainRetrievalResult: ...


@dataclass(frozen=True)
class RetrievalContextDocument:
    source_id: str
    drug_id: str
    field_group: str
    content: str
    source: str
    relevance: float
    rank: int
    token_count: int
    vector_score: float | None
    lexical_score: float | None

    def to_context_item(self, *, freshness: datetime) -> ContextItem:
        rendered = json.dumps(
            {
                "drug_id": self.drug_id,
                "field": self.field_group,
                "content": self.content,
                "source": self.source,
                "rank": self.rank,
                "vector_score": self.vector_score,
                "lexical_score": self.lexical_score,
                "rrf_score": self.relevance,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return ContextItem(
            id=f"retrieval:{self.source_id}",
            layer=ContextLayer.RETRIEVAL,
            content=rendered,
            token_count=self.token_count,
            authority=ContextAuthority.RETRIEVAL,
            priority=50,
            provenance=f"legacy-rag:drug_chunks:{self.source_id}",
            freshness=freshness,
            relevance=self.relevance,
        )


@dataclass(frozen=True)
class RetrievalGatewayResult:
    status: RetrievalStatus
    documents: tuple[RetrievalContextDocument, ...] = ()
    retrieved_at: datetime | None = None
    no_source_found: bool = False
    excluded_by_budget: int = 0
    safe_reason: str | None = None

    def to_context_items(self) -> tuple[ContextItem, ...]:
        if self.status is not RetrievalStatus.READY or self.retrieved_at is None:
            return ()
        return tuple(document.to_context_item(freshness=self.retrieved_at) for document in self.documents)


class RetrievalGateway:
    """Embed and retrieve public knowledge without patient/user data access."""

    def __init__(
        self,
        embedding_gateway: EmbeddingGateway,
        domain: RetrievalDomain,
        *,
        config: RetrievalConfig,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._embedding_gateway = embedding_gateway
        self._domain = domain
        self._config = config
        self._now = now or (lambda: datetime.now(UTC))

    def retrieve(self, request: RetrievalRequest | dict[str, object]) -> RetrievalGatewayResult:
        try:
            validated = request if isinstance(request, RetrievalRequest) else RetrievalRequest.model_validate(request)
        except ValidationError:
            return RetrievalGatewayResult(RetrievalStatus.INVALID_QUERY, safe_reason="INVALID_RETRIEVAL_QUERY")
        try:
            embedding = self._embedding_gateway.embed_query(text=validated.query)
            if embedding.model != self._config.embedding_model:
                return RetrievalGatewayResult(RetrievalStatus.UNAVAILABLE, safe_reason="EMBEDDING_MODEL_MISMATCH")
            domain_result = self._domain.retrieve(
                query=validated.query,
                embedding=embedding.vector,
                top_k=self._config.top_k,
            )
        except Exception:
            return RetrievalGatewayResult(RetrievalStatus.UNAVAILABLE, safe_reason="RETRIEVAL_UNAVAILABLE")

        retrieved_at = self._as_utc(self._now())
        if domain_result.no_source_found or not domain_result.documents:
            return RetrievalGatewayResult(
                RetrievalStatus.NO_RESULTS,
                retrieved_at=retrieved_at,
                no_source_found=True,
                safe_reason="NO_RETRIEVAL_EVIDENCE",
            )
        documents, excluded = self._within_budget(domain_result.documents)
        if not documents:
            return RetrievalGatewayResult(
                RetrievalStatus.NO_RESULTS,
                retrieved_at=retrieved_at,
                no_source_found=False,
                excluded_by_budget=excluded,
                safe_reason="RETRIEVAL_CONTEXT_BUDGET_EXCEEDED",
            )
        return RetrievalGatewayResult(
            RetrievalStatus.READY,
            documents=documents,
            retrieved_at=retrieved_at,
            excluded_by_budget=excluded,
        )

    def _within_budget(
        self, documents: tuple[RetrievedKnowledgeDocument, ...]
    ) -> tuple[tuple[RetrievalContextDocument, ...], int]:
        selected: list[RetrievalContextDocument] = []
        consumed = 0
        excluded = 0
        for document in documents[: self._config.top_k]:
            token_count = self._token_count(document)
            if consumed + token_count > self._config.token_budget:
                excluded += 1
                continue
            selected.append(
                RetrievalContextDocument(
                    source_id=document.source_id,
                    drug_id=document.drug_id,
                    field_group=document.field_group,
                    content=document.content,
                    source=document.source,
                    relevance=document.relevance,
                    rank=document.rank,
                    token_count=token_count,
                    vector_score=document.vector_score,
                    lexical_score=document.lexical_score,
                )
            )
            consumed += token_count
        return tuple(selected), excluded

    @staticmethod
    def _token_count(document: RetrievedKnowledgeDocument) -> int:
        rendered = json.dumps(
            {
                "drug_id": document.drug_id,
                "field": document.field_group,
                "content": document.content,
                "source": document.source,
                "rank": document.rank,
                "vector_score": document.vector_score,
                "lexical_score": document.lexical_score,
                "rrf_score": document.relevance,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return max(1, ceil(len(rendered) / 4))

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
