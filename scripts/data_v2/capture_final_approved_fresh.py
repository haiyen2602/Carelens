"""Capture the two approved Fresh identity records missing product snapshots.

The first run writes immutable raw snapshots. Subsequent runs reuse those
snapshots and only re-parse them, making final promotion reproducible offline.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import requests

from crawler_v2 import (
    PARSER_VERSION,
    USER_AGENT,
    canonicalize_fresh,
    extract_legacy_like_fields,
    fetch_next_data,
    snapshot_id_for,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data pharmacy"
OUTPUT_DIR = DATA_DIR / "v2" / "final_canonical" / "targeted_fresh"
RAW_DIR = OUTPUT_DIR / "raw_snapshots" / "nhathuoclongchau"

TARGETS = {
    "lamivudine-savi-100mg-3x10": "https://nhathuoclongchau.com.vn/thuoc/lamivudin-100mg-savi-3x10-15900.html",
    "philclonestyl-125mg-boston-5x10": "https://nhathuoclongchau.com.vn/thuoc/philclonestyl-125mg-hop-5-vi-x-10-vien-boston-viet-nam-34079.html",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def load_or_capture(legacy_drug_id: str, source_url: str, session: requests.Session) -> tuple[dict[str, Any], dict[str, Any]]:
    index_path = OUTPUT_DIR / "source_snapshot.jsonl"
    for row in read_jsonl(index_path):
        if row.get("legacy_drug_id") != legacy_drug_id:
            continue
        snapshot_path = ROOT / str(row["raw_snapshot_path"])
        if snapshot_path.is_file():
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            return snapshot, row

    next_data, metadata = fetch_next_data(session, source_url)
    snapshot_id = snapshot_id_for(metadata)
    snapshot = {**metadata, "id": snapshot_id, "raw_next_data": next_data}
    snapshot_path = RAW_DIR / f"{snapshot_id}.json"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index_row = {
        "legacy_drug_id": legacy_drug_id,
        "snapshot_id": snapshot_id,
        "source_url": metadata["source_url"],
        "retrieved_at": metadata["retrieved_at"],
        "content_hash": metadata["content_hash"],
        "parser_version": metadata["parser_version"],
        "raw_snapshot_path": str(snapshot_path.relative_to(ROOT)),
    }
    return snapshot, index_row


def run() -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    source_rows: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    ingredients: dict[str, dict[str, Any]] = {}
    product_ingredients: list[dict[str, Any]] = []
    knowledge: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for legacy_drug_id, source_url in TARGETS.items():
        snapshot, source_row = load_or_capture(legacy_drug_id, source_url, session)
        record = extract_legacy_like_fields(snapshot["raw_next_data"])
        record["id"] = legacy_drug_id
        canonical = canonicalize_fresh(record, str(snapshot["id"]))
        product = canonical["drug_product"][0]
        if product["legacy_drug_id"] != legacy_drug_id:
            raise RuntimeError(f"{legacy_drug_id}: canonical product ID mismatch")
        source_rows.append(source_row)
        products.extend(canonical["drug_product"])
        ingredients.update({row["id"]: row for row in canonical["ingredient"]})
        product_ingredients.extend(canonical["drug_product_ingredient"])
        knowledge.extend(canonical["drug_knowledge"])
        warnings.extend(canonical["ingredient_warnings"])

    if {row["legacy_drug_id"] for row in products} != set(TARGETS):
        raise RuntimeError("targeted capture did not produce both approved Fresh products")
    write_jsonl(OUTPUT_DIR / "source_snapshot.jsonl", sorted(source_rows, key=lambda row: row["legacy_drug_id"]))
    write_jsonl(OUTPUT_DIR / "drug_product.jsonl", sorted(products, key=lambda row: row["legacy_drug_id"]))
    write_jsonl(OUTPUT_DIR / "ingredient.jsonl", sorted(ingredients.values(), key=lambda row: row["id"]))
    write_jsonl(OUTPUT_DIR / "drug_product_ingredient.jsonl", sorted(product_ingredients, key=lambda row: (row["legacy_drug_id"], row["sequence"])))
    write_jsonl(OUTPUT_DIR / "drug_knowledge.jsonl", sorted(knowledge, key=lambda row: (row["legacy_drug_id"], row["id"])))
    write_jsonl(OUTPUT_DIR / "ingredient_parse_warnings.jsonl", sorted(warnings, key=lambda row: (row["legacy_drug_id"], row["raw_ingredient"])))
    summary = {
        "parser_version": PARSER_VERSION,
        "targets": len(TARGETS),
        "products": len(products),
        "knowledge_items": len(knowledge),
        "ingredient_warnings": len(warnings),
        "source_hashes": {row["legacy_drug_id"]: row["content_hash"] for row in source_rows},
        "artifact_hash": sha256_json({"products": products, "knowledge": knowledge}),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
