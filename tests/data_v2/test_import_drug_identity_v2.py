"""Unit tests for DB-4B Final Canonical identity import validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.data_v2.import_drug_identity_v2 import (
    assert_local_postgres_url,
    canonical_jsonl_sha256_file,
    deterministic_id,
    load_import_plan,
)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a small UTF-8 JSONL fixture."""

    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def write_artifacts(
    tmp_path: Path, links: list[dict[str, object]], mapping_product_id: str = "product-1"
) -> None:
    """Create the smallest valid Final Canonical identity fixture set."""

    write_jsonl(
        tmp_path / "drug_product.jsonl",
        [
            {
                "id": "product-1",
                "legacy_drug_id": "legacy-1",
                "display_name": "Drug One",
                "dosage_form": "tablet",
                "route": "oral",
                "category": "category-1",
            }
        ],
    )
    write_jsonl(
        tmp_path / "drug_id_map.jsonl",
        [{"legacy_drug_id": "legacy-1", "drug_product_id": mapping_product_id}],
    )
    write_jsonl(
        tmp_path / "ingredient.jsonl",
        [{"id": "ingredient-1", "canonical_name": "Ingredient One"}],
    )
    write_jsonl(tmp_path / "drug_product_ingredient.jsonl", links)
    artifact_hashes = {
        name: canonical_jsonl_sha256_file(tmp_path / name)
        for name in (
            "drug_product.jsonl",
            "drug_id_map.jsonl",
            "ingredient.jsonl",
            "drug_product_ingredient.jsonl",
        )
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps({"version": "test-v2", "active_canonical": 1, "artifact_hashes": artifact_hashes}),
        encoding="utf-8",
    )


def test_import_plan_skips_unmapped_links_and_deduplicates_pairs(tmp_path: Path) -> None:
    """Importer preserves uncertainty and represents each valid relationship once."""

    write_artifacts(
        tmp_path,
        [
            {"drug_product_id": "product-1", "ingredient_id": "ingredient-1", "legacy_drug_id": "legacy-1"},
            {"drug_product_id": "product-1", "ingredient_id": "ingredient-1", "legacy_drug_id": "legacy-1"},
            {"drug_product_id": "product-1", "ingredient_id": None, "legacy_drug_id": "legacy-1"},
        ],
    )

    plan = load_import_plan(tmp_path)

    assert len(plan.product_ingredients) == 1
    assert len(plan.duplicate_valid_pairs) == 1
    assert len(plan.skipped_links) == 1
    assert plan.skipped_links[0].reason == "MISSING_CANONICAL_INGREDIENT"
    assert plan.drug_id_maps[0]["mapping_status"] == "ACTIVE"


def test_import_plan_rejects_mapping_to_unknown_product(tmp_path: Path) -> None:
    """Importer never invents a product ID for an unresolved legacy mapping."""

    write_artifacts(tmp_path, [], mapping_product_id="missing-product")

    with pytest.raises(ValueError, match="references missing product"):
        load_import_plan(tmp_path)


def test_import_plan_rejects_artifacts_that_do_not_match_manifest(tmp_path: Path) -> None:
    """Importer fails closed when a supposedly canonical artifact is altered."""

    write_artifacts(tmp_path, [])
    write_jsonl(tmp_path / "ingredient.jsonl", [{"id": "ingredient-1", "canonical_name": "Altered"}])

    with pytest.raises(ValueError, match="hash mismatch"):
        load_import_plan(tmp_path)


def test_import_plan_accepts_crlf_checkout_of_lf_canonical_jsonl(tmp_path: Path) -> None:
    """A Windows checkout must validate against the same canonical manifest hash."""

    write_artifacts(tmp_path, [])
    product_path = tmp_path / "drug_product.jsonl"
    product_path.write_bytes(
        product_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    )

    assert len(load_import_plan(tmp_path).drug_products) == 1


def test_deterministic_ids_are_stable_per_identity_pair() -> None:
    """Synthetic IDs remain stable across repeated imports."""

    assert deterministic_id("drug-id-map", "legacy-1", "product-1") == deterministic_id(
        "drug-id-map", "legacy-1", "product-1"
    )
    assert deterministic_id("drug-id-map", "legacy-1", "product-1") != deterministic_id(
        "drug-id-map", "legacy-2", "product-1"
    )


def test_import_refuses_non_local_database() -> None:
    """DB-4B cannot accidentally target Railway or any shared database."""

    assert_local_postgres_url("postgresql://vmec:vmec@localhost:5432/db4b")
    with pytest.raises(ValueError, match="local PostgreSQL"):
        assert_local_postgres_url("postgresql://vmec:vmec@railway.example:5432/db4b")
