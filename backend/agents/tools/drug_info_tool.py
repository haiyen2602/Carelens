"""tra_cuu_thuoc_chung - RAG hybrid search tren data pharmacy chung (KHONG
gan voi 1 benh nhan cu the). Xem chatbot-rag-design.md muc 4, muc 6."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.services.retrieval import RetrievalResult, hybrid_search

EmbedFn = Callable[[str], list[float]]


def tra_cuu_thuoc_chung(db: Session, query: str, embed_query: EmbedFn) -> RetrievalResult:
    """`embed_query` injectable (goi OpenAI that trong production, mock duoc
    trong test de khong ton API) - xem chatbot-rag-design.md muc 8 "goi bang
    query_embedding co san"."""
    query_embedding = embed_query(query)
    return hybrid_search(db, query, query_embedding)
