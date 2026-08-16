"""Build the versioned, active Canonical V2 dataset from final decisions.

This script is intentionally offline after the targeted raw capture step. It
does not alter Legacy V1, the previous V2 artifact, production chunks, or any
deployment. The final dataset is written under ``v2/final_canonical``.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_v2_evaluation import (
    DrugResolver,
    SparseIndex,
    build_eval_cases,
    build_v1_chunks,
    build_v2_chunks,
    evaluate_v1,
    evaluate_v2,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data pharmacy"
V2_DIR = DATA_DIR / "v2"
REPARSE_DIR = V2_DIR / "full_recrawl" / "reparse"
TARGETED_DIR = V2_DIR / "final_canonical" / "targeted_fresh"
FINAL_DIR = V2_DIR / "final_canonical"
RAG_DIR = FINAL_DIR / "rag"
REPORT_DIR = DATA_DIR / "reports" / "v2"

PROMOTION_REPORT = REPORT_DIR / "final-canonical-promotion-report.md"
QUALITY_REPORT = REPORT_DIR / "final-data-quality-report.md"
RAG_REPORT = REPORT_DIR / "final-search-rag-rebuild-report.md"

RUNNER_VERSION = "final-canonical-v2.0.0"
EXCLUDED_IDS = {
    "bisoprolol-stada-5mg-3x10",
    "pantogen-500ml",
    "esonix-40-3x10",
    "lucass-200-2x10",
    "scort-100-10x10",
    "vicometrim-960-10x10",
}
TERMINAL_DECISIONS = {"PROMOTED_FRESH", "KEEP_LEGACY", "EXCLUDE_ACTIVE_CORPUS"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def rows_by_legacy(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["legacy_drug_id"])].append(row)
    return grouped


def unique_row(rows: dict[str, list[dict[str, Any]]], legacy_id: str, name: str) -> dict[str, Any]:
    candidates = rows.get(legacy_id, [])
    if len(candidates) != 1:
        raise RuntimeError(f"{legacy_id}: expected exactly one {name}, found {len(candidates)}")
    return candidates[0]


def build_terminal_decisions() -> list[dict[str, Any]]:
    prior = read_jsonl(REPARSE_DIR / "promotion_decisions.jsonl")
    resolutions = {
        row["legacy_drug_id"]: row
        for row in read_jsonl(REPARSE_DIR / "review_required_resolution.jsonl")
    }
    terminal: list[dict[str, Any]] = []
    for prior_row in prior:
        legacy_id = prior_row["legacy_drug_id"]
        initial = prior_row["promotion_decision"]
        resolution = resolutions.get(legacy_id)
        if legacy_id in EXCLUDED_IDS:
            decision = "EXCLUDE_ACTIVE_CORPUS"
            reason = "human-approved exclusion from active Canonical, RAG, and Agent corpora"
        elif initial == "APPROVED":
            decision = "PROMOTED_FRESH"
            reason = "matched Fresh candidate with captured raw provenance"
        elif initial == "KEEP_LEGACY":
            decision = "KEEP_LEGACY"
            reason = prior_row["reason"]
        elif resolution and resolution["final_decision"] == "APPROVE_FRESH":
            decision = "PROMOTED_FRESH"
            reason = resolution["reason"]
        elif resolution and resolution["final_decision"] == "KEEP_LEGACY":
            decision = "KEEP_LEGACY"
            reason = resolution["reason"]
        else:
            raise RuntimeError(f"{legacy_id}: no terminal decision")
        terminal.append(
            {
                "legacy_drug_id": legacy_id,
                "terminal_decision": decision,
                "active": decision != "EXCLUDE_ACTIVE_CORPUS",
                "data_origin": "fresh" if decision == "PROMOTED_FRESH" else ("legacy" if decision == "KEEP_LEGACY" else "excluded"),
                "reason": reason,
                "initial_promotion_decision": initial,
                "initial_decision_path": str((REPARSE_DIR / "promotion_decisions.jsonl").relative_to(ROOT)),
                "resolution_path": str((REPARSE_DIR / "review_required_resolution.jsonl").relative_to(ROOT)) if resolution else None,
                "source_url": (resolution or prior_row).get("source_url"),
                "snapshot_id": (resolution or prior_row).get("snapshot_id"),
                "content_hash": (resolution or prior_row).get("content_hash"),
                "parser_version": (resolution or prior_row).get("parser_version"),
            }
        )
    ids = [row["legacy_drug_id"] for row in terminal]
    if len(terminal) != 3562 or len(set(ids)) != 3562:
        raise RuntimeError("terminal decisions must cover all 3,562 Legacy IDs exactly once")
    if any(row["terminal_decision"] not in TERMINAL_DECISIONS for row in terminal):
        raise RuntimeError("invalid terminal decision")
    return sorted(terminal, key=lambda row: row["legacy_drug_id"])


def select_final_rows(terminal: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    base_products = rows_by_legacy(read_jsonl(V2_DIR / "drug_product.jsonl"))
    base_refs = rows_by_legacy(read_jsonl(V2_DIR / "drug_product_ingredient.jsonl"))
    base_knowledge = rows_by_legacy(read_jsonl(V2_DIR / "drug_knowledge.jsonl"))
    base_warnings = rows_by_legacy(read_jsonl(V2_DIR / "ingredient_parse_warnings.jsonl"))
    base_ingredients = {row["id"]: row for row in read_jsonl(V2_DIR / "ingredient.jsonl")}

    fresh_products = rows_by_legacy(read_jsonl(REPARSE_DIR / "candidate_drug_product.jsonl"))
    fresh_refs = rows_by_legacy(read_jsonl(REPARSE_DIR / "candidate_drug_product_ingredient.jsonl"))
    fresh_knowledge = rows_by_legacy(read_jsonl(REPARSE_DIR / "candidate_drug_knowledge.jsonl"))
    fresh_warnings = rows_by_legacy(read_jsonl(REPARSE_DIR / "candidate_ingredient_warnings.jsonl"))
    fresh_ingredients = {row["id"]: row for row in read_jsonl(REPARSE_DIR / "candidate_ingredient.jsonl")}

    targeted_products = rows_by_legacy(read_jsonl(TARGETED_DIR / "drug_product.jsonl"))
    targeted_refs = rows_by_legacy(read_jsonl(TARGETED_DIR / "drug_product_ingredient.jsonl"))
    targeted_knowledge = rows_by_legacy(read_jsonl(TARGETED_DIR / "drug_knowledge.jsonl"))
    targeted_warnings = rows_by_legacy(read_jsonl(TARGETED_DIR / "ingredient_parse_warnings.jsonl"))
    targeted_ingredients = {row["id"]: row for row in read_jsonl(TARGETED_DIR / "ingredient.jsonl")}

    outputs: dict[str, list[dict[str, Any]]] = {
        "drug_product": [],
        "drug_id_map": [],
        "drug_product_ingredient": [],
        "drug_knowledge": [],
        "ingredient_parse_warnings": [],
    }
    ingredient_rows: dict[str, dict[str, Any]] = {}
    for decision in terminal:
        legacy_id = decision["legacy_drug_id"]
        outcome = decision["terminal_decision"]
        if outcome == "EXCLUDE_ACTIVE_CORPUS":
            continue
        if outcome == "KEEP_LEGACY":
            product_rows, ref_rows, knowledge_rows, warning_rows, ingredients = (
                base_products,
                base_refs,
                base_knowledge,
                base_warnings,
                base_ingredients,
            )
        elif legacy_id in targeted_products:
            product_rows, ref_rows, knowledge_rows, warning_rows, ingredients = (
                targeted_products,
                targeted_refs,
                targeted_knowledge,
                targeted_warnings,
                targeted_ingredients,
            )
        else:
            product_rows, ref_rows, knowledge_rows, warning_rows, ingredients = (
                fresh_products,
                fresh_refs,
                fresh_knowledge,
                fresh_warnings,
                fresh_ingredients,
            )
        product = dict(unique_row(product_rows, legacy_id, "selected product"))
        if outcome == "PROMOTED_FRESH":
            product["legacy_metadata"] = unique_row(base_products, legacy_id, "Legacy product").get("legacy_metadata") or {}
            if product.get("provenance_status") != "SOURCE_CAPTURED" or not product.get("source_snapshot_id"):
                raise RuntimeError(f"{legacy_id}: promoted Fresh product lacks provenance")
        outputs["drug_product"].append(product)
        outputs["drug_id_map"].append({"legacy_drug_id": legacy_id, "drug_product_id": product["id"]})
        for ref in ref_rows.get(legacy_id, []):
            outputs["drug_product_ingredient"].append(ref)
            ingredient_id = ref.get("ingredient_id")
            if ingredient_id:
                ingredient = ingredients.get(ingredient_id)
                if not ingredient:
                    raise RuntimeError(f"{legacy_id}: orphan ingredient reference {ingredient_id}")
                existing = ingredient_rows.setdefault(ingredient_id, ingredient)
                if existing != ingredient:
                    raise RuntimeError(f"{legacy_id}: conflicting ingredient definition {ingredient_id}")
        selected_knowledge = knowledge_rows.get(legacy_id, [])
        if not selected_knowledge:
            raise RuntimeError(f"{legacy_id}: active product has no knowledge")
        if outcome == "PROMOTED_FRESH" and any(
            row.get("provenance_status") != "SOURCE_CAPTURED" or not row.get("source_snapshot_id")
            for row in selected_knowledge
        ):
            raise RuntimeError(f"{legacy_id}: promoted Fresh knowledge lacks provenance")
        outputs["drug_knowledge"].extend(selected_knowledge)
        outputs["ingredient_parse_warnings"].extend(warning_rows.get(legacy_id, []))

    outputs["ingredient"] = sorted(ingredient_rows.values(), key=lambda row: row["id"])
    for name, rows in outputs.items():
        if name != "ingredient":
            rows.sort(key=lambda row: (str(row.get("legacy_drug_id", "")), str(row.get("id", "")), str(row.get("sequence", ""))))
    return outputs


def quality_audit(terminal: list[dict[str, Any]], outputs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    errors: list[str] = []
    active_ids = {row["legacy_drug_id"] for row in terminal if row["active"]}
    excluded_ids = {row["legacy_drug_id"] for row in terminal if not row["active"]}
    products = outputs["drug_product"]
    mappings = outputs["drug_id_map"]
    product_ids = {row["id"] for row in products}
    product_legacy_ids = [row["legacy_drug_id"] for row in products]
    mapping_legacy_ids = [row["legacy_drug_id"] for row in mappings]
    mapping_product_ids = [row["drug_product_id"] for row in mappings]
    duplicate_identity = sum(count > 1 for count in Counter(product_legacy_ids).values())
    duplicate_identity += sum(count > 1 for count in Counter(mapping_legacy_ids).values())
    duplicate_identity += sum(count > 1 for count in Counter(mapping_product_ids).values())
    if len(products) != len(active_ids) or set(product_legacy_ids) != active_ids:
        errors.append("active products do not match terminal decisions")
    if len(mappings) != len(active_ids) or set(mapping_legacy_ids) != active_ids:
        errors.append("active mappings do not match terminal decisions")
    if len(set(product_legacy_ids)) != len(products) or len(set(mapping_legacy_ids)) != len(mappings):
        errors.append("duplicate active legacy identity")
    if set(mapping_product_ids) != product_ids or len(set(mapping_product_ids)) != len(mappings):
        errors.append("orphan or duplicate active ID mapping")
    active_knowledge_ids = {row["legacy_drug_id"] for row in outputs["drug_knowledge"]}
    if not active_knowledge_ids.issubset(active_ids) or active_knowledge_ids & excluded_ids:
        errors.append("excluded record appears in active knowledge")
    if any(row["drug_product_id"] not in product_ids for row in outputs["drug_knowledge"]):
        errors.append("knowledge row has orphan product ID")
    if any(row["drug_product_id"] not in product_ids for row in outputs["drug_product_ingredient"]):
        errors.append("ingredient reference has orphan product ID")
    ingredient_ids = {row["id"] for row in outputs["ingredient"]}
    if any(row.get("ingredient_id") and row["ingredient_id"] not in ingredient_ids for row in outputs["drug_product_ingredient"]):
        errors.append("ingredient reference has orphan ingredient ID")
    fresh_ids = {row["legacy_drug_id"] for row in terminal if row["terminal_decision"] == "PROMOTED_FRESH"}
    products_by_legacy = {row["legacy_drug_id"]: row for row in products}
    knowledge_by_legacy = rows_by_legacy(outputs["drug_knowledge"])
    missing_provenance = [
        legacy_id
        for legacy_id in fresh_ids
        if not products_by_legacy[legacy_id].get("source_snapshot_id")
        or any(not row.get("source_snapshot_id") for row in knowledge_by_legacy[legacy_id])
    ]
    if missing_provenance:
        errors.append("Fresh promotion is missing provenance")
    missing_reviews = read_jsonl(REPARSE_DIR / "missing_field_review.jsonl")
    silent_data_loss = sum(
        row["legacy_drug_id"] in fresh_ids and not row.get("fresh_value")
        for row in missing_reviews
    )
    if silent_data_loss:
        errors.append("blank Fresh field would overwrite Legacy")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "active_canonical": len(active_ids),
        "excluded_active": len(excluded_ids),
        "promoted_fresh": len(fresh_ids),
        "keep_legacy": sum(row["terminal_decision"] == "KEEP_LEGACY" for row in terminal),
        "review_required": sum(row["terminal_decision"] not in TERMINAL_DECISIONS for row in terminal),
        "provenance_coverage": f"{len(fresh_ids) - len(missing_provenance)}/{len(fresh_ids)}",
        "data_loss": silent_data_loss,
        "duplicates": duplicate_identity,
        "p0_p1": "None" if not errors else "Validation failures require investigation",
        "errors": errors,
    }


def build_rag(outputs: dict[str, list[dict[str, Any]]], quality: dict[str, Any]) -> dict[str, Any]:
    products = outputs["drug_product"]
    mappings = outputs["drug_id_map"]
    knowledge = outputs["drug_knowledge"]
    v1_rows = read_jsonl(DATA_DIR / "data-version1" / "_chunks.jsonl")
    resolver = DrugResolver(products, mappings)
    v2_chunks = build_v2_chunks(knowledge)
    v1_chunks = build_v1_chunks(v1_rows, {row["legacy_drug_id"]: row["drug_product_id"] for row in mappings})
    v2_index = SparseIndex(v2_chunks)
    v1_index = SparseIndex(v1_chunks)
    cases = build_eval_cases()
    v1_eval = evaluate_v1(v1_index, cases)
    v2_eval = evaluate_v2(resolver, v2_index, cases)

    excluded_resolution = {
        legacy_id: resolver.resolve_from_utterance(legacy_id).status
        for legacy_id in sorted(EXCLUDED_IDS)
    }
    excluded_lookup_leaks = [
        legacy_id for legacy_id in EXCLUDED_IDS
        if any(chunk.legacy_drug_id == legacy_id for chunk in v2_chunks)
    ]
    regressions = []
    if quality["status"] != "PASS":
        regressions.append("final data quality audit failed")
    if v2_eval["wrong_drug_rate"] > 0 or v2_eval["safety_wrong_drug_rate"] > 0:
        regressions.append("wrong-drug retrieval detected")
    if v2_eval["wrong_type_rate"] > 0:
        regressions.append("wrong knowledge type retrieval detected")
    if v2_eval["hit_at_k"] + 0.05 < v1_eval["hit_at_k"]:
        regressions.append("V2 Hit@K is more than 5 percentage points below V1")
    if excluded_lookup_leaks:
        regressions.append("excluded records leaked into active RAG chunks")

    RAG_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        RAG_DIR / "v2_chunks.jsonl",
        [
            {
                "id": chunk.id,
                "legacy_drug_id": chunk.legacy_drug_id,
                "drug_product_id": chunk.drug_product_id,
                "knowledge_type": chunk.knowledge_type,
                "content": chunk.text,
                "source": chunk.source,
                "provenance": chunk.provenance,
            }
            for chunk in v2_chunks
        ],
    )
    write_jsonl(RAG_DIR / "v2_embedding_index.jsonl", v2_index.export())
    summary = {
        "status": "PASS" if not regressions else "BLOCKED",
        "embedding_model": "local-tfidf-hash-v1",
        "v2_chunks": len(v2_chunks),
        "v1_chunks": len(v1_chunks),
        "v1": v1_eval,
        "v2": v2_eval,
        "excluded_lookup_resolution": excluded_resolution,
        "excluded_chunk_leaks": excluded_lookup_leaks,
        "regressions": regressions,
    }
    (RAG_DIR / "eval_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def write_final_artifacts(terminal: list[dict[str, Any]], outputs: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(FINAL_DIR / "final_promotion_decisions.jsonl", terminal)
    for name, rows in outputs.items():
        write_jsonl(FINAL_DIR / f"{name}.jsonl", rows)
    return {
        path.name: sha256_file(path)
        for path in sorted(FINAL_DIR.glob("*.jsonl"))
    }


def write_reports(quality: dict[str, Any], rag: dict[str, Any], manifest: dict[str, Any]) -> None:
    status = "PASS" if quality["status"] == "PASS" and rag["status"] == "PASS" else "BLOCKED"
    PROMOTION_REPORT.write_text(
        f"""# Final Canonical V2 Promotion

Final Canonical V2 was built as a versioned artifact at `data pharmacy/v2/final_canonical`.
Legacy V1, the prior V2 artifact, raw history, and reconciliation history were not modified.

- Active Canonical records: {quality['active_canonical']}
- Promoted Fresh: {quality['promoted_fresh']}
- Keep Legacy: {quality['keep_legacy']}
- Excluded from active corpus: {quality['excluded_active']}
- Excluded IDs: {', '.join(manifest['excluded_ids'])}
- Terminal decisions: 3562/3562
- Manifest: `data pharmacy/v2/final_canonical/manifest.json`
""",
        encoding="utf-8",
    )
    QUALITY_REPORT.write_text(
        f"""# Final Data Quality Audit

**Status:** {quality['status']}

- Active product/map coverage: {quality['active_canonical']}/{quality['active_canonical']}
- Fresh provenance coverage: {quality['provenance_coverage']}
- Silent data loss: {quality['data_loss']}
- Duplicate identity: {quality['duplicates']}
- P0/P1: {quality['p0_p1']}
- Errors: {quality['errors'] or 'None'}
""",
        encoding="utf-8",
    )
    RAG_REPORT.write_text(
        f"""# Final Search/RAG Rebuild

**Status:** {rag['status']}

- Active V2 chunks: {rag['v2_chunks']}
- Embedding/index: `{rag['embedding_model']}`
- V1 Hit@5: {rag['v1']['hit_at_k']:.2%}
- V2 Hit@5: {rag['v2']['hit_at_k']:.2%}
- V2 wrong-drug rate: {rag['v2']['wrong_drug_rate']:.2%}
- V2 wrong-type rate: {rag['v2']['wrong_type_rate']:.2%}
- Excluded chunk leaks: {rag['excluded_chunk_leaks'] or 'None'}
- Regressions: {rag['regressions'] or 'None'}
""",
        encoding="utf-8",
    )
    final_report = f"""# Final Data V2 Result

```text
FINAL DATA V2 RESULT

STATUS:
{status}

TOTAL LEGACY:
3562
ACTIVE CANONICAL:
{quality['active_canonical']}
PROMOTED FRESH:
{quality['promoted_fresh']}
KEEP LEGACY:
{quality['keep_legacy']}
EXCLUDED ACTIVE:
{quality['excluded_active']}
REVIEW REQUIRED:
{quality['review_required']}

PROVENANCE COVERAGE:
{quality['provenance_coverage']}
DATA LOSS:
{quality['data_loss']}
DUPLICATES:
{quality['duplicates']}
P0/P1:
{quality['p0_p1']}

SEARCH/RAG REBUILD:
{'PASS' if rag['status'] == 'PASS' else 'FAIL'}

REGRESSION:
{'PASS' if not rag['regressions'] else 'FAIL'}

READY FOR FINAL DOCKER VALIDATION:
{'YES' if status == 'PASS' else 'NO'}
```
"""
    (FINAL_DIR / "final_result.md").write_text(final_report, encoding="utf-8")


def run() -> dict[str, Any]:
    terminal = build_terminal_decisions()
    outputs = select_final_rows(terminal)
    quality = quality_audit(terminal, outputs)
    hashes = write_final_artifacts(terminal, outputs)
    rag = build_rag(outputs, quality)
    manifest = {
        "version": "canonical-v2-final-2026-08-16",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runner_version": RUNNER_VERSION,
        "terminal_decision_counts": dict(Counter(row["terminal_decision"] for row in terminal)),
        "active_canonical": quality["active_canonical"],
        "excluded_ids": sorted(EXCLUDED_IDS),
        "artifact_hashes": hashes,
        "rag_artifact_hashes": {
            str(path.relative_to(FINAL_DIR)): sha256_file(path)
            for path in sorted(path for path in RAG_DIR.iterdir() if path.is_file())
        },
        "quality_status": quality["status"],
        "rag_status": rag["status"],
        "source_artifacts": {
            "reparse": str(REPARSE_DIR.relative_to(ROOT)),
            "targeted_fresh": str(TARGETED_DIR.relative_to(ROOT)),
        },
    }
    (FINAL_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_reports(quality, rag, manifest)
    return {"quality": quality, "rag": rag, "manifest": manifest}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    raise SystemExit(0 if result["quality"]["status"] == "PASS" and result["rag"]["status"] == "PASS" else 1)
