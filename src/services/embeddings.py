"""Embedding client that (text-embedding-3-small) dung cho retrieval_node
luc chay that (Phase 6) - cung 1 model/client pattern voi
scripts/embed_and_insert.py (Phase 3), KHONG tu dung client rieng de tranh
lech cau hinh giua luc index va luc query."""

from __future__ import annotations

from functools import lru_cache

import openai

from src.config import get_settings


@lru_cache
def _get_client() -> openai.OpenAI:
    settings = get_settings()
    return openai.OpenAI(api_key=settings.openai_api_key)


def embed_query(text: str) -> list[float]:
    """EmbedFn (src/agents/tools/drug_info_tool.py) - 1 cau hoi/lan, khong
    batch (khac scripts/embed_and_insert.py batch nhieu chunk luc index)."""
    settings = get_settings()
    client = _get_client()
    resp = client.embeddings.create(model=settings.embedding_model, input=[text])
    return resp.data[0].embedding
