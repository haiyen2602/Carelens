"""Tests for the manifest-verified DB-4H legacy category seed input."""

from __future__ import annotations

import json

import pytest

from scripts.data_v2.import_drug_identity_v2 import canonical_jsonl_sha256_file
from scripts.data_v2.seed_legacy_category_safety_policies import load_legacy_category_risks


def _write_artifacts(tmp_path, rows: list[dict[str, object]]) -> None:
    products = tmp_path / "drug_product.jsonl"
    products.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"version": "canonical-test", "artifact_hashes": {"drug_product.jsonl": canonical_jsonl_sha256_file(products)}}),
        encoding="utf-8",
    )


def _product(category: str, risk: str) -> dict[str, object]:
    return {
        "id": f"product-{category}-{risk}",
        "category": category,
        "legacy_metadata": {
            "legacy_missed_dose_risk": risk,
            "legacy_missed_dose_risk_status": "NOT_CLINICALLY_REVIEWED",
        },
    }


def test_seed_input_maps_one_verified_legacy_risk_per_category(tmp_path) -> None:
    _write_artifacts(tmp_path, [_product("category-a", "Nhẹ"), _product("category-b", "Nguy hiểm")])

    version, risks = load_legacy_category_risks(tmp_path)

    assert version == "canonical-test"
    assert risks == {"category-a": "LOW", "category-b": "HIGH"}


def test_seed_input_rejects_conflicting_category_or_changed_artifact(tmp_path) -> None:
    _write_artifacts(tmp_path, [_product("category-a", "Nhẹ"), _product("category-a", "Nguy hiểm")])
    with pytest.raises(ValueError, match="conflicts"):
        load_legacy_category_risks(tmp_path)

    _write_artifacts(tmp_path, [_product("category-a", "Nhẹ")])
    (tmp_path / "drug_product.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        load_legacy_category_risks(tmp_path)
