"""Domain adapter that reuses the approved legacy pgvector + RRF retrieval."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.services.retrieval import hybrid_search


@dataclass(frozen=True)
class RetrievedKnowledgeDocument:
    """Non-patient DrugChunk projection returned to the Agent V2 boundary."""

    source_id: str
    drug_id: str
    drug_name: str
    field_group: str
    content: str
    source: str
    vector_score: float | None
    lexical_score: float | None
    relevance: float
    rank: int


@dataclass(frozen=True)
class DomainRetrievalResult:
    documents: tuple[RetrievedKnowledgeDocument, ...]
    no_source_found: bool


class AgentRetrievalDomainService:
    """Read public DrugChunk knowledge only; it never reads patient tables."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def retrieve(self, *, query: str, embedding: tuple[float, ...], top_k: int) -> DomainRetrievalResult:
        result = hybrid_search(self._db, query, list(embedding), top_k=top_k)
        documents = tuple(
            RetrievedKnowledgeDocument(
                source_id=row.chunk_id or f"drug-chunks:{row.drug_id}:{row.field_group}:{row.rank}",
                drug_id=row.drug_id,
                drug_name=row.ten_thuoc,
                field_group=row.field_group,
                content=row.noi_dung,
                source=row.source,
                vector_score=row.vector_score,
                lexical_score=row.lexical_score,
                relevance=row.rrf_score,
                rank=row.rank,
            )
            for row in result.results
        )
        return DomainRetrievalResult(documents=documents, no_source_found=result.no_source_found)
