from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import get_settings
from backend.services.drug_knowledge import v2_agent
from backend.services.drug_knowledge.v2_agent import (
    FINAL_CANONICAL_DIR,
    get_v2_agent_knowledge_service,
)

EXCLUDED_IDS = (
    "bisoprolol-stada-5mg-3x10",
    "esonix-40-3x10",
    "lucass-200-2x10",
    "pantogen-500ml",
    "scort-100-10x10",
    "vicometrim-960-10x10",
)


def test_final_canonical_is_agent_default_and_excludes_reviewed_records(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "test-final-canonical-internal-secret")
    monkeypatch.setenv("JWT_SECRET", "test-final-canonical-jwt-secret")
    monkeypatch.delenv("DRUG_KNOWLEDGE_V2_DIR", raising=False)
    get_settings.cache_clear()
    get_v2_agent_knowledge_service.cache_clear()

    service = get_v2_agent_knowledge_service()

    assert FINAL_CANONICAL_DIR == Path("data pharmacy/v2/final_canonical").resolve()
    assert len(service.product_id_by_legacy) == 3556
    assert len(service.chunks) == 42588
    for legacy_drug_id in EXCLUDED_IDS:
        lookup = service.retrieve(legacy_drug_id, "tac dung phu va chong chi dinh")
        assert service.resolve_legacy_id(legacy_drug_id) is None
        assert service.get_catalog_item(legacy_drug_id) is None
        assert lookup.results == []
        assert lookup.trace["path"] == "fail_closed"
        assert lookup.trace["resolution_status"] == "NOT_FOUND"

    known_lookup = service.retrieve(
        "tardyferon-b9-3x10",
        "Tardyferon b9 3x10 phu nu mang thai dung duoc khong?",
    )
    assert known_lookup.results
    assert known_lookup.trace["path"] == "structured_lookup"
    assert {result.drug_id for result in known_lookup.results} == {"tardyferon-b9-3x10"}


def test_default_v2_fails_clearly_when_final_artifacts_are_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "test-final-canonical-internal-secret")
    monkeypatch.setenv("JWT_SECRET", "test-final-canonical-jwt-secret")
    monkeypatch.delenv("DRUG_KNOWLEDGE_V2_DIR", raising=False)
    monkeypatch.setattr(v2_agent, "FINAL_CANONICAL_DIR", tmp_path)
    get_settings.cache_clear()
    get_v2_agent_knowledge_service.cache_clear()

    with pytest.raises(RuntimeError, match="Final Canonical V2 artifacts are incomplete"):
        get_v2_agent_knowledge_service()
