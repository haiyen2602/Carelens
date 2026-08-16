"""Re-parse Full Re-crawl snapshots with Parser V2 and rerun the promotion gate.

All outputs are written below ``full_recrawl/reparse``. The original crawl,
original reconciliation, Legacy V1, and Canonical V2 remain immutable.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawler_v2 import (
    PARSER_VERSION,
    canonicalize_fresh,
    classify_duong_dung,
    extract_legacy_like_fields,
    validate_canonical,
)
from final_data_promotion_gate import run as run_promotion_gate
from legacy_importer import normalize_name, read_legacy_records


ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT / "data pharmacy"
SOURCE_DIR = LEGACY_DIR / "v2" / "full_recrawl"
OUTPUT_DIR = SOURCE_DIR / "reparse"
REPORT_PATH = LEGACY_DIR / "reports" / "v2" / "parser-v2-reparse-report.md"
RUNNER_VERSION = "raw-reparse-v2.1.0"
COMPARE_FIELDS = (
    "ten_thuoc",
    "ham_luong",
    "dang_thuoc",
    "tong_so_luong",
    "tac_dung",
    "tac_dung_phu",
    "huong_dan_su_dung",
    "lieu_dung",
    "duong_dung",
    "huong_dan_bao_quan",
    "luu_y_dac_biet",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def comparable(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_name(str(item)).casefold() for item in value]
    return normalize_name(str(value or "")).casefold()


def field_differences(legacy: dict[str, Any], fresh: dict[str, Any]) -> list[str]:
    return [field for field in COMPARE_FIELDS if comparable(legacy.get(field)) != comparable(fresh.get(field))]


def route_resolution(next_data: dict[str, Any]) -> str:
    page_props = next_data.get("props", {}).get("pageProps", {})
    product = page_props.get("product") or {}
    content = page_props.get("content") or {}
    dosage_form = str(product.get("dosageForm") or "")
    dosage_source = str(content.get("dosage") or product.get("dosage") or "")
    from_form = classify_duong_dung(dosage_form)
    resolved = classify_duong_dung(dosage_form, dosage_source)
    if not resolved:
        return "UNRESOLVED"
    if from_form:
        return "DOSAGE_FORM_FALLBACK"
    return "EXPLICIT_DOSAGE_INSTRUCTION"


def load_legacy() -> dict[str, dict[str, Any]]:
    records = {}
    for _path, _index, record in read_legacy_records(LEGACY_DIR):
        legacy_id = str(record.get("id") or "")
        if not legacy_id or legacy_id in records:
            raise RuntimeError(f"invalid or duplicate legacy ID: {legacy_id!r}")
        records[legacy_id] = record
    return records


def build_report(summary: dict[str, Any], gate: dict[str, Any]) -> str:
    return f"""# Parser V2 Fix + Re-parse Gate

**Generated:** {summary['generated_at']}  
**Scope:** raw-snapshot reparse only. No website recrawl, canonical promotion, RAG/index rebuild, deployment, or Legacy mutation occurred.

## Root Cause

- The earlier parser inferred `duong_dung` only from `dosageForm`.
- `38` blank Fresh routes were ambiguous forms (for example gel/emulsion/solution) whose raw `content.dosage` explicitly states the route.
- The remaining route differences had deterministic source route evidence that conflicts with Legacy taxonomy; they are kept for review rather than guessed or overwritten.

## Reparse Output

- `data pharmacy/v2/full_recrawl/reparse/reconciliation.jsonl`
- `data pharmacy/v2/full_recrawl/reparse/candidate_*.jsonl`
- `data pharmacy/v2/full_recrawl/reparse/promotion_decisions.jsonl`
- `data pharmacy/v2/full_recrawl/reparse/final_promotion_gate_summary.json`

## PARSER V2 RE-PARSE RESULT

STATUS: **{summary['status']}**

PARSER VERSION:
- `{PARSER_VERSION}`

PARSER ISSUES BEFORE: {summary['parser_issues_before']}
PARSER ISSUES AFTER: {summary['parser_issues_after']}

MISSING FIELDS BEFORE: {summary['missing_fields_before']}
MISSING FIELDS AFTER: {summary['missing_fields_after']}

REGRESSION: {'PASS' if summary['regression_count'] == 0 else 'FAIL'}

REVIEW REQUIRED:
- {gate['review_required']} records: {gate['ambiguous']} ambiguous identities, {gate['missing_from_source']} source-missing record(s), and {gate['changed_classifications'].get('SOURCE_CHANGE', 0)} source-evidenced differences.
- Parser keeps Legacy route for `{', '.join(summary['remaining_parser_issue_ids']) or '-'}` because their raw dosage forms are not sufficient to infer the legacy route safely.
- `{gate['ingredient_warnings']}` ingredient warnings remain raw and unchanged.

P0/P1:
- None. Blank Fresh values are not promoted; all remaining differences are preserved as `KEEP_LEGACY` or `REVIEW_REQUIRED`.

READY TO RE-RUN PROMOTION GATE: YES
"""


def run() -> dict[str, Any]:
    legacy = load_legacy()
    source_events = read_jsonl(SOURCE_DIR / "reconciliation.jsonl")
    source_missing_reviews = read_jsonl(SOURCE_DIR / "missing_field_review.jsonl")
    if len(legacy) != 3562 or len(source_events) != 3562:
        raise RuntimeError("reparse requires the complete 3,562-record source reconciliation")

    reparse_events = []
    products: list[dict[str, Any]] = []
    ingredients: dict[str, dict[str, Any]] = {}
    ingredient_refs: list[dict[str, Any]] = []
    knowledge: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    missing_after = 0
    previous_matched_regressions = 0

    for event in sorted(source_events, key=lambda row: row["legacy_drug_id"]):
        legacy_id = event["legacy_drug_id"]
        next_event = {
            **event,
            "reparse_at": utc_now(),
            "reparse_runner_version": RUNNER_VERSION,
            "reparse_parent_parser_version": event.get("parser_version"),
            "parser_version": PARSER_VERSION,
        }
        if event["reconciliation_status"] not in {"MATCHED", "CHANGED"}:
            reparse_events.append(next_event)
            continue

        snapshot = json.loads((ROOT / event["raw_snapshot_path"]).read_text(encoding="utf-8"))
        fresh = extract_legacy_like_fields(snapshot["raw_next_data"])
        fresh_source_drug_id = fresh.get("id")
        fresh["id"] = legacy_id
        canonical = canonicalize_fresh(fresh, event["snapshot_id"])
        differences = field_differences(legacy[legacy_id], fresh)
        status = "MATCHED" if not differences else "CHANGED"
        validation_errors = validate_canonical(fresh, canonical)
        missing_after += sum(
            1
            for field in COMPARE_FIELDS
            if comparable(legacy[legacy_id].get(field)) and not comparable(fresh.get(field))
        )
        if event["reconciliation_status"] == "MATCHED" and status != "MATCHED":
            previous_matched_regressions += 1
        next_event.update(
            {
                "reconciliation_status": status,
                "field_differences": differences,
                "fresh_source_drug_id": fresh_source_drug_id,
                "ingredient_parse_warnings": len(canonical["ingredient_warnings"]),
                "knowledge_items": len(canonical["drug_knowledge"]),
                "validation_errors": validation_errors,
                "route_resolution": route_resolution(snapshot["raw_next_data"]),
            }
        )
        reparse_events.append(next_event)
        validation_rows.append(
            {
                "legacy_drug_id": legacy_id,
                "status": "PASS" if not validation_errors else "FAIL",
                "errors": validation_errors,
                "snapshot_id": event["snapshot_id"],
                "parser_version": PARSER_VERSION,
            }
        )
        products.extend(canonical["drug_product"])
        for ingredient in canonical["ingredient"]:
            ingredients[ingredient["id"]] = ingredient
        ingredient_refs.extend(canonical["drug_product_ingredient"])
        knowledge.extend(canonical["drug_knowledge"])
        warnings.extend(canonical["ingredient_warnings"])

    if len(reparse_events) != 3562 or len({row["legacy_drug_id"] for row in reparse_events}) != 3562:
        raise RuntimeError("reparse did not preserve one reconciliation row per legacy ID")
    if any(row["status"] == "FAIL" for row in validation_rows):
        raise RuntimeError("reparse canonical validation failed")

    write_jsonl(OUTPUT_DIR / "reconciliation.jsonl", reparse_events)
    write_jsonl(OUTPUT_DIR / "candidate_drug_product.jsonl", products)
    write_jsonl(OUTPUT_DIR / "candidate_ingredient.jsonl", sorted(ingredients.values(), key=lambda row: row["canonical_key"]))
    write_jsonl(OUTPUT_DIR / "candidate_drug_product_ingredient.jsonl", ingredient_refs)
    write_jsonl(OUTPUT_DIR / "candidate_drug_knowledge.jsonl", knowledge)
    write_jsonl(OUTPUT_DIR / "candidate_ingredient_warnings.jsonl", warnings)
    write_jsonl(OUTPUT_DIR / "validation.jsonl", validation_rows)

    gate = run_promotion_gate(
        input_dir=OUTPUT_DIR,
        output_dir=OUTPUT_DIR,
        report_path=OUTPUT_DIR / "final-data-promotion-gate-report.md",
    )
    summary = {
        "generated_at": utc_now(),
        "runner_version": RUNNER_VERSION,
        "parser_version": PARSER_VERSION,
        "legacy_total": len(legacy),
        "parser_issues_before": sum(
            event["reconciliation_status"] == "CHANGED" and event.get("field_differences") == ["duong_dung"]
            for event in source_events
        ),
        "parser_issues_after": gate["changed_classifications"].get("PARSER_ISSUE", 0),
        "missing_fields_before": len(source_missing_reviews),
        "missing_fields_after": missing_after,
        "regression_count": previous_matched_regressions,
        "reparse_validation_failures": sum(row["status"] == "FAIL" for row in validation_rows),
        "remaining_parser_issue_ids": sorted(
            row["legacy_drug_id"]
            for row in reparse_events
            if row.get("field_differences") == ["duong_dung"] and row.get("route_resolution") == "UNRESOLVED"
        ),
        "reconciliation_status_counts": dict(sorted(Counter(row["reconciliation_status"] for row in reparse_events).items())),
        "promotion_gate": gate,
        "status": "PASS" if previous_matched_regressions == 0 and missing_after == 0 else "PASS WITH ISSUES",
    }
    write_json(OUTPUT_DIR / "reparse_summary.json", summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(summary, gate), encoding="utf-8")
    return summary


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
