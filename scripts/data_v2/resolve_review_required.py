"""Resolve V2 promotion review records from existing deterministic evidence.

The script reads only re-parse artifacts and raw snapshots. Its decisions are
an audit recommendation; it never promotes data into Canonical V2.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data pharmacy"
REPARSE_DIR = DATA_DIR / "v2" / "full_recrawl" / "reparse"
DECISIONS_PATH = REPARSE_DIR / "review_required_resolution.jsonl"
SUMMARY_PATH = REPARSE_DIR / "review_required_resolution_summary.json"
REPORT_PATH = DATA_DIR / "reports" / "v2" / "review-required-resolution-report.md"
RUNNER_VERSION = "review-required-resolution-v1.0.0"

FINAL_DECISIONS = {"APPROVE_FRESH", "KEEP_LEGACY", "HUMAN_REVIEW"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_text(value: Any) -> str:
    text = str(value or "").replace("\u0111", "d").replace("\u0110", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(character for character in text if unicodedata.category(character) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def tokens(value: Any) -> set[str]:
    return set(normalize_text(value).split())


def full_source_url(slug: str) -> str:
    return f"https://nhathuoclongchau.com.vn/{slug.lstrip('/')}"


def source_change_decision(review: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    field_reviews = review["field_review"]
    if not field_reviews:
        raise RuntimeError(f"{review['legacy_drug_id']}: changed record lacks field evidence")
    base = {
        "legacy_drug_id": review["legacy_drug_id"],
        "review_origin": "SOURCE_CHANGE",
        "source_url": review["source_url"],
        "snapshot_id": review["snapshot_id"],
        "content_hash": review["content_hash"],
        "raw_snapshot_path": event["raw_snapshot_path"],
        "retrieved_at": event.get("retrieved_at") or event.get("attempted_at"),
        "parser_version": event["parser_version"],
        "changed_fields": [field["field"] for field in field_reviews],
        "field_evidence": field_reviews,
    }

    route_fields = [field for field in field_reviews if field["field"] == "duong_dung"]
    if any("tiem truyen" not in normalize_text(field.get("source_raw_value")) for field in route_fields):
        return {
            **base,
            "final_decision": "KEEP_LEGACY",
            "reason": "raw dosage form states only injection, not a specific administration route; retain the more specific Legacy value",
        }

    if all(
        field.get("source_raw_present") and field.get("fresh_value") not in (None, "", [])
        for field in field_reviews
    ):
        return {
            **base,
            "final_decision": "APPROVE_FRESH",
            "reason": "all changed Fresh values are non-empty and deterministically extracted from captured source fields",
        }
    return {
        **base,
        "final_decision": "HUMAN_REVIEW",
        "reason": "source evidence does not prove the non-empty Fresh value",
    }


def strict_identity_candidates(products: list[dict[str, Any]], legacy: dict[str, Any]) -> list[dict[str, Any]]:
    legacy_name_tokens = tokens(legacy.get("ten_thuoc"))
    legacy_ingredients = normalize_text(legacy.get("ham_luong"))
    legacy_form = normalize_text(legacy.get("dang_thuoc"))
    legacy_package = normalize_text(legacy.get("tong_so_luong"))
    matches: list[dict[str, Any]] = []
    for product in products:
        if not legacy_name_tokens.issubset(tokens(product.get("name"))):
            continue
        if legacy_ingredients != normalize_text(product.get("ingredients")):
            continue
        if legacy_form != normalize_text(product.get("dosageForm")):
            continue
        if legacy_package != normalize_text(product.get("specification")):
            continue
        matches.append(product)
    return matches


def ambiguous_decision(event: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
    search_snapshot_path = ROOT / event["search_raw_snapshot_path"]
    snapshot = json.loads(search_snapshot_path.read_text(encoding="utf-8"))
    products = snapshot["raw_next_data"]["props"]["pageProps"]["data"]["data"]["products"]
    matches = strict_identity_candidates(products, legacy)
    base = {
        "legacy_drug_id": event["legacy_drug_id"],
        "review_origin": "AMBIGUOUS",
        "search_url": event["search_url"],
        "snapshot_id": event["search_snapshot_id"],
        "content_hash": event["search_content_hash"],
        "raw_snapshot_path": event["search_raw_snapshot_path"],
        "retrieved_at": event.get("retrieved_at") or event.get("attempted_at"),
        "parser_version": event["parser_version"],
        "legacy_identity": {
            "name": legacy.get("ten_thuoc"),
            "ingredients": legacy.get("ham_luong"),
            "dosage_form": legacy.get("dang_thuoc"),
            "package": legacy.get("tong_so_luong"),
        },
        "strict_match_count": len(matches),
        "strict_matches": [
            {
                "source_url": full_source_url(str(product["slug"])),
                "name": product.get("name"),
                "ingredients": product.get("ingredients"),
                "dosage_form": product.get("dosageForm"),
                "package": product.get("specification"),
            }
            for product in matches
        ],
    }
    if len(matches) == 1:
        return {
            **base,
            "final_decision": "APPROVE_FRESH",
            "source_url": full_source_url(str(matches[0]["slug"])),
            "reason": "exactly one captured search candidate matches name, ingredients, dosage form, and package",
        }
    if len(matches) > 1:
        return {
            **base,
            "final_decision": "HUMAN_REVIEW",
            "reason": "more than one captured candidate matches all deterministic identity fields",
        }
    return {
        **base,
        "final_decision": "HUMAN_REVIEW",
        "reason": "no captured candidate matches all deterministic identity fields",
    }


def missing_source_decision(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "legacy_drug_id": event["legacy_drug_id"],
        "review_origin": "MISSING_FROM_SOURCE",
        "final_decision": "KEEP_LEGACY",
        "reason": "deterministic source search returned no product; retain Legacy without replacement",
        "search_url": event["search_url"],
        "snapshot_id": event["search_snapshot_id"],
        "content_hash": event["search_content_hash"],
        "raw_snapshot_path": event["search_raw_snapshot_path"],
        "retrieved_at": event.get("retrieved_at") or event.get("attempted_at"),
        "parser_version": event["parser_version"],
    }


def build_report(summary: dict[str, Any]) -> str:
    human_ids = "\n".join(f"- `{item}`" for item in summary["human_review_ids"]) or "- None"
    return f"""# Review-Required Resolution

**Generated:** {summary['generated_at']}  
**Scope:** deterministic review of 44 existing `REVIEW_REQUIRED` records. No Canonical V2 promotion, index rebuild, deployment, or source crawl occurred.

## Decision Rules

- Route changes are approved only when the raw dosage form explicitly says infusion. A generic injection form retains Legacy.
- An ambiguous identity is approved only with exactly one captured search candidate matching name, ingredients/strength, dosage form, and package.
- A missing source result retains Legacy.
- All decisions include the snapshot, hash, URL, parser version, and source evidence in `review_required_resolution.jsonl`.

## Human Review

{human_ids}

## Result

```text
REVIEW RESOLUTION RESULT

STATUS:
{summary['status']}

TOTAL: 44
APPROVE FRESH:
{summary['approve_fresh']}
KEEP LEGACY:
{summary['keep_legacy']}
HUMAN REVIEW:
{summary['human_review']}

AMBIGUOUS RESOLVED:
{summary['ambiguous_resolved']}
SOURCE CHANGES RESOLVED:
{summary['source_changes_resolved']}
MISSING SOURCE:
{summary['missing_source']}

P0/P1:
{summary['p0_p1']}

READY FOR CANONICAL PROMOTION:
{summary['ready_for_promotion']}
```
"""


def run() -> dict[str, Any]:
    reviews = read_jsonl(REPARSE_DIR / "changed_review.jsonl")
    reconciliation = read_jsonl(REPARSE_DIR / "reconciliation.jsonl")
    prior_decisions = read_jsonl(REPARSE_DIR / "promotion_decisions.jsonl")
    events = {row["legacy_drug_id"]: row for row in reconciliation}
    legacy_records: dict[str, dict[str, Any]] = {}
    for path in (DATA_DIR / "data-version1").glob("*/thuoc.json"):
        for record in json.loads(path.read_text(encoding="utf-8")):
            legacy_records[record["id"]] = record

    review_ids = {
        row["legacy_drug_id"]
        for row in prior_decisions
        if row.get("promotion_decision") == "REVIEW_REQUIRED"
    }
    rows: list[dict[str, Any]] = []
    source_reviews = [row for row in reviews if row.get("classification") == "SOURCE_CHANGE"]
    for review in source_reviews:
        rows.append(source_change_decision(review, events[review["legacy_drug_id"]]))
    for event in reconciliation:
        status = event.get("reconciliation_status")
        if status == "AMBIGUOUS":
            rows.append(ambiguous_decision(event, legacy_records[event["legacy_drug_id"]]))
        elif status == "MISSING_FROM_SOURCE":
            rows.append(missing_source_decision(event))

    errors: list[str] = []
    final_ids = [row["legacy_drug_id"] for row in rows]
    if len(rows) != 44 or set(final_ids) != review_ids or len(set(final_ids)) != len(final_ids):
        errors.append("resolution output does not cover exactly the 44 review-required IDs")
    if any(row["final_decision"] not in FINAL_DECISIONS for row in rows):
        errors.append("invalid final decision")
    if any(not (ROOT / row["raw_snapshot_path"]).is_file() for row in rows):
        errors.append("a decision references a missing raw snapshot")

    counts = Counter(row["final_decision"] for row in rows)
    ambiguous_rows = [row for row in rows if row["review_origin"] == "AMBIGUOUS"]
    source_rows = [row for row in rows if row["review_origin"] == "SOURCE_CHANGE"]
    missing_rows = [row for row in rows if row["review_origin"] == "MISSING_FROM_SOURCE"]
    if len(source_rows) != 35 or any(row["final_decision"] == "HUMAN_REVIEW" for row in source_rows):
        errors.append("source changes were not fully resolved")
    if len(missing_rows) != 1 or missing_rows[0]["final_decision"] != "KEEP_LEGACY":
        errors.append("missing source record is not protected by KEEP_LEGACY")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runner_version": RUNNER_VERSION,
        "total": len(rows),
        "approve_fresh": counts["APPROVE_FRESH"],
        "keep_legacy": counts["KEEP_LEGACY"],
        "human_review": counts["HUMAN_REVIEW"],
        "ambiguous_resolved": sum(row["final_decision"] != "HUMAN_REVIEW" for row in ambiguous_rows),
        "source_changes_resolved": sum(row["final_decision"] != "HUMAN_REVIEW" for row in source_rows),
        "missing_source": len(missing_rows),
        "human_review_ids": sorted(row["legacy_drug_id"] for row in rows if row["final_decision"] == "HUMAN_REVIEW"),
        "p0_p1": "None" if not errors else "Validation failures require investigation",
        "status": "PASS WITH ISSUES" if not errors else "BLOCKED",
        "ready_for_promotion": "NO",
        "validation_errors": errors,
    }
    write_jsonl(DECISIONS_PATH, sorted(rows, key=lambda row: row["legacy_drug_id"]))
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    raise SystemExit(0 if result["status"] != "BLOCKED" else 1)
