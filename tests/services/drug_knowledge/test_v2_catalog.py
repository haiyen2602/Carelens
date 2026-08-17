"""Regression tests for the V2 catalog-only doctor-search behavior."""

from __future__ import annotations

from backend.services.drug_knowledge.v2_agent import get_v2_agent_knowledge_service, normalize_text


def test_short_prefix_returns_selectable_catalog_suggestions() -> None:
    """One typed character must populate the doctor combobox without resolving identity."""

    service = get_v2_agent_knowledge_service()
    sample = service.catalog_items[0]
    prefix = normalize_text(sample.ten_thuoc).split()[0][0]

    results = service.search_catalog(prefix, limit=8)

    assert results
    assert len(results) <= 8
    assert all(
        any(token.startswith(prefix) for token in normalize_text(item.ten_thuoc).split())
        for item in results
    )


def test_short_prefix_does_not_make_identity_candidates_less_strict() -> None:
    """Catalog autocomplete must not weaken the safety-sensitive resolver."""

    service = get_v2_agent_knowledge_service()
    sample = service.catalog_items[0]
    prefix = normalize_text(sample.ten_thuoc).split()[0][0]

    assert service.search_identity_candidates(prefix) == []
