"""tra_cuu_thuoc_chung - RAG hybrid search tren data pharmacy chung (KHONG
gan voi 1 benh nhan cu the). Xem chatbot-rag-design.md muc 4, muc 6."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from backend.services.retrieval import RetrievalResult

EmbedFn = Callable[[str], list[float]]


def tra_cuu_thuoc_chung(db: Session, query: str, embed_query: EmbedFn) -> RetrievalResult:
    """Legacy generic retrieval retained only for an un-routed compatibility builder.

    The HTTP agent resolves a drug through V2 before knowledge lookup. Keep
    this import lazy so starting the V2 backend does not load V1 retrieval.
    """
    from backend.services.retrieval import hybrid_search

    query_embedding = embed_query(query)
    return hybrid_search(db, query, query_embedding)
