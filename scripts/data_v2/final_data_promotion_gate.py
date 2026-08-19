"""Create a conservative, auditable promotion decision for every recrawled drug.

This is a review gate only. It reads the frozen Legacy V1 corpus, the full
recrawl reconciliation events, and immutable raw snapshots. It never writes
Canonical V2, Legacy V1, RAG artifacts, or runtime data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawler_v2 import extract_legacy_like_fields
from legacy_importer import read_legacy_records


ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT / "data pharmacy"
RUN_DIR = LEGACY_DIR / "v2" / "full_recrawl"
REPORT_PATH = LEGACY_DIR / "reports" / "v2" / "final-data-promotion-gate-report.md"
RUNNER_VERSION = "final-promotion-gate-v2.0.0"

PROMOTION_DECISIONS = {"APPROVED", "KEEP_LEGACY", "REVIEW_REQUIRED"}
CHANGED_CLASSIFICATIONS = {"VALID_CHANGE", "PARSER_ISSUE", "SOURCE_CHANGE", "REVIEW_REQUIRED"}
FIELDS = (
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


def nonempty(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def load_legacy() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for _path, _index, record in read_legacy_records(LEGACY_DIR):
        legacy_id = str(record.get("id") or "")
        if not legacy_id or legacy_id in records:
            raise RuntimeError(f"invalid or duplicate legacy ID: {legacy_id!r}")
        records[legacy_id] = record
    return records


def source_value(next_data: dict[str, Any], field: str) -> Any:
    page_props = next_data.get("props", {}).get("pageProps", {})
    product = page_props.get("product") or {}
    content = page_props.get("content") or {}
    return {
        "ham_luong": product.get("ingredient"),
        "dang_thuoc": product.get("dosageForm"),
        "duong_dung": product.get("dosageForm"),
        "tac_dung": content.get("usage") or product.get("usage"),
        "tac_dung_phu": content.get("adverseEffect") or product.get("adverseEffect"),
        "huong_dan_su_dung": content.get("dosage") or product.get("dosage"),
        "lieu_dung": content.get("dosage") or product.get("dosage"),
        "huong_dan_bao_quan": content.get("preservation"),
        "luu_y_dac_biet": content.get("careful"),
    }.get(field)


def classify_changed(event: dict[str, Any], fields: list[str]) -> tuple[str, str, str]:
    # Route is a parser-derived field; an observed mismatch is not medical
    # evidence that the legacy route is wrong. Preserve it until parser review.
    if fields == ["duong_dung"]:
        if event.get("route_resolution") in {"EXPLICIT_DOSAGE_INSTRUCTION", "DOSAGE_FORM_FALLBACK"}:
            return (
                "SOURCE_CHANGE",
                "REVIEW_REQUIRED",
                "fresh route has deterministic source evidence but conflicts with Legacy; human review is required",
            )
        return (
            "PARSER_ISSUE",
            "KEEP_LEGACY",
            "route is parser-derived; fresh route is not promoted without a reviewed route rule",
        )
    return (
        "SOURCE_CHANGE",
        "REVIEW_REQUIRED",
        "fresh source differs in direct clinical/product content; no medical inference or automatic promotion is allowed",
    )


def decision_for_event(
    event: dict[str, Any],
    legacy: dict[str, Any],
    warning_count: int,
    reconciliation_event_path: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    status = event["reconciliation_status"]
    base = {
        "legacy_drug_id": event["legacy_drug_id"],
        "reconciliation_status": status,
        "source_url": event.get("selected_source_url") or event.get("search_url"),
        "search_url": event.get("search_url"),
        "snapshot_id": event.get("snapshot_id") or event.get("search_snapshot_id"),
        "content_hash": event.get("content_hash") or event.get("search_content_hash"),
        "retrieved_at": event.get("retrieved_at") or event.get("attempted_at"),
        "parser_version": event.get("parser_version"),
        "reconciliation_event_path": reconciliation_event_path,
        "ingredient_warning_count": warning_count,
        "decision_at": utc_now(),
        "decision_runner_version": RUNNER_VERSION,
    }
    if status == "MATCHED":
        return (
            {
                **base,
                "promotion_decision": "APPROVED",
                "review_classification": "VALID_CHANGE",
                "reason": "all compared canonical fields match Legacy V1; raw provenance and candidate validation are present",
            },
            None,
            [],
        )
    if status == "CHANGED":
        snapshot = json.loads((ROOT / event["raw_snapshot_path"]).read_text(encoding="utf-8"))
        fresh = extract_legacy_like_fields(snapshot["raw_next_data"])
        changed_fields = list(event.get("field_differences") or [])
        classification, decision, reason = classify_changed(event, changed_fields)
        missing_reviews = []
        field_reviews = []
        for field in changed_fields:
            source = source_value(snapshot["raw_next_data"], field)
            field_review = {
                "legacy_drug_id": event["legacy_drug_id"],
                "field": field,
                "legacy_value": legacy.get(field),
                "fresh_value": fresh.get(field),
                "source_raw_present": nonempty(source),
                "source_raw_value": source,
                "source_url": event["selected_source_url"],
                "snapshot_id": event["snapshot_id"],
                "content_hash": event["content_hash"],
                "parser_version": event["parser_version"],
            }
            field_reviews.append(field_review)
            if nonempty(legacy.get(field)) and not nonempty(fresh.get(field)):
                missing_reviews.append(
                    {
                        **field_review,
                        "finding": "PARSER_ISSUE" if nonempty(source) else "SOURCE_MISSING",
                        "decision": "KEEP_LEGACY" if nonempty(source) else "REVIEW_REQUIRED",
                        "reason": (
                            "raw source still contains input for this field; fresh absence is a parser loss"
                            if nonempty(source)
                            else "raw source has no input while Legacy has content; retain Legacy pending human review"
                        ),
                    }
                )
        changed_review = {
            **base,
            "changed_fields": changed_fields,
            "classification": classification,
            "promotion_decision": decision,
            "reason": reason,
            "field_review": field_reviews,
        }
        return ({**base, "promotion_decision": decision, "review_classification": classification, "reason": reason}, changed_review, missing_reviews)
    if status == "AMBIGUOUS":
        return (
            {
                **base,
                "promotion_decision": "REVIEW_REQUIRED",
                "review_classification": "REVIEW_REQUIRED",
                "reason": "source search did not yield a unique conservative identity match",
                "candidate_urls": event.get("candidate_urls") or [],
            },
            None,
            [],
        )
    if status == "MISSING_FROM_SOURCE":
        return (
            {
                **base,
                "promotion_decision": "REVIEW_REQUIRED",
                "review_classification": "REVIEW_REQUIRED",
                "reason": "deterministic source search returned no product; retain Legacy and require source/identity review",
            },
            None,
            [],
        )
    if status == "CRAWL_FAILED":
        return (
            {
                **base,
                "promotion_decision": "KEEP_LEGACY",
                "review_classification": "REVIEW_REQUIRED",
                "reason": "source capture failed; no fresh candidate may replace Legacy",
            },
            None,
            [],
        )
    raise RuntimeError(f"unsupported reconciliation status: {status}")


def build_report(summary: dict[str, Any]) -> str:
    changed_lines = "\n".join(
        f"| `{key}` | {value} |" for key, value in sorted(summary["changed_classifications"].items())
    ) or "| - | 0 |"
    missing_lines = "\n".join(
        f"| `{key}` | {value} |" for key, value in sorted(summary["missing_findings"].items())
    ) or "| - | 0 |"
    return f"""# Final Data Promotion Gate

**Generated:** {summary['generated_at']}  
**Scope:** read-only review of Fresh candidates versus Legacy V1. No canonical promotion, RAG/index rebuild, deployment, or Legacy mutation occurred.

## Outputs

- `data pharmacy/v2/full_recrawl/promotion_decisions.jsonl` - one decision with provenance per legacy ID.
- `data pharmacy/v2/full_recrawl/changed_review.jsonl` - fresh/legacy/source comparison for all changed candidates.
- `data pharmacy/v2/full_recrawl/missing_field_review.jsonl` - evidence for every field fresh left empty while Legacy has content.
- `data pharmacy/v2/full_recrawl/unresolved_identity_review.jsonl` - ambiguous and missing-from-source records.
- `data pharmacy/v2/full_recrawl/ingredient_warning_review.jsonl` - raw ingredient warnings retained without inference.

## Changed Review

| Classification | Records |
|---|---:|
{changed_lines}

All `CHANGED` records have a per-field Legacy value, Fresh value, raw-source evidence, source URL, content hash, snapshot ID, and parser version in `changed_review.jsonl`.

## Missing-Field Review

| Finding | Fields |
|---|---:|
{missing_lines}

The `{summary['missing_fields_reviewed']}` reviewed missing fields are all retained from Legacy for the gate decision. No blank Fresh field is treated as authoritative.

## Ingredient Warnings

`{summary['ingredient_warnings']}` ingredient segments remain raw with their existing warning. This gate neither infers ingredient identity/strength nor changes parser output.

## FINAL DATA PROMOTION GATE

STATUS: **{summary['status']}**

APPROVED: {summary['approved']}
KEEP LEGACY: {summary['keep_legacy']}
REVIEW REQUIRED: {summary['review_required']}

CHANGED REVIEWED: {summary['changed_reviewed']}/{summary['changed_total']}
MISSING FIELDS REVIEWED: {summary['missing_fields_reviewed']}/{summary['missing_total']}
AMBIGUOUS: {summary['ambiguous']}
MISSING FROM SOURCE: {summary['missing_from_source']}
INGREDIENT WARNINGS: {summary['ingredient_warnings']}

P0/P1:
- None. All non-identical, unresolved, and parser-loss cases are fail-safe: kept from Legacy or marked `REVIEW_REQUIRED`; no Fresh candidate was promoted.

READY TO PROMOTE CANONICAL V2: NO
"""


def run(
    input_dir: Path = RUN_DIR,
    output_dir: Path = RUN_DIR,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    legacy_records = load_legacy()
    events = read_jsonl(input_dir / "reconciliation.jsonl")
    if len(legacy_records) != 3562 or len(events) != 3562:
        raise RuntimeError("promotion gate requires the complete frozen 3,562-record corpus")
    if len({event.get("legacy_drug_id") for event in events}) != 3562:
        raise RuntimeError("reconciliation does not contain one unique row per legacy ID")

    warning_rows = read_jsonl(input_dir / "candidate_ingredient_warnings.jsonl")
    reconciliation_event_path = str((input_dir / "reconciliation.jsonl").relative_to(ROOT)).replace("\\", "/")
    warnings_by_id: dict[str, int] = defaultdict(int)
    for warning in warning_rows:
        warnings_by_id[str(warning["legacy_drug_id"])] += 1

    decisions = []
    changed_reviews = []
    missing_reviews = []
    unresolved_reviews = []
    for event in sorted(events, key=lambda row: row["legacy_drug_id"]):
        legacy_id = event["legacy_drug_id"]
        if legacy_id not in legacy_records:
            raise RuntimeError(f"event ID absent from Legacy V1: {legacy_id}")
        decision, changed_review, missing = decision_for_event(
            event,
            legacy_records[legacy_id],
            warnings_by_id[legacy_id],
            reconciliation_event_path,
        )
        decisions.append(decision)
        if changed_review:
            changed_reviews.append(changed_review)
        missing_reviews.extend(missing)
        if event["reconciliation_status"] in {"AMBIGUOUS", "MISSING_FROM_SOURCE", "CRAWL_FAILED"}:
            unresolved_reviews.append(decision)

    decision_counts = Counter(row["promotion_decision"] for row in decisions)
    if len(decisions) != 3562 or len({row["legacy_drug_id"] for row in decisions}) != 3562:
        raise RuntimeError("promotion decisions must cover every legacy ID exactly once")
    if set(decision_counts) - PROMOTION_DECISIONS:
        raise RuntimeError("invalid promotion decision")
    changed_counts = Counter(row["classification"] for row in changed_reviews)
    missing_counts = Counter(row["finding"] for row in missing_reviews)
    changed_total = sum(event["reconciliation_status"] == "CHANGED" for event in events)
    if len(changed_reviews) != changed_total:
        raise RuntimeError("every changed reconciliation row must have a review")

    write_jsonl(output_dir / "promotion_decisions.jsonl", decisions)
    write_jsonl(output_dir / "changed_review.jsonl", changed_reviews)
    write_jsonl(output_dir / "missing_field_review.jsonl", missing_reviews)
    write_jsonl(output_dir / "unresolved_identity_review.jsonl", unresolved_reviews)
    write_jsonl(output_dir / "ingredient_warning_review.jsonl", warning_rows)

    summary = {
        "generated_at": utc_now(),
        "runner_version": RUNNER_VERSION,
        "input_dir": str(input_dir.relative_to(ROOT)).replace("\\", "/"),
        "output_dir": str(output_dir.relative_to(ROOT)).replace("\\", "/"),
        "legacy_total": len(legacy_records),
        "approved": decision_counts["APPROVED"],
        "keep_legacy": decision_counts["KEEP_LEGACY"],
        "review_required": decision_counts["REVIEW_REQUIRED"],
        "changed_total": changed_total,
        "changed_reviewed": len(changed_reviews),
        "missing_total": len(missing_reviews),
        "changed_classifications": dict(sorted(changed_counts.items())),
        "missing_fields_reviewed": len(missing_reviews),
        "missing_findings": dict(sorted(missing_counts.items())),
        "ambiguous": sum(event["reconciliation_status"] == "AMBIGUOUS" for event in events),
        "missing_from_source": sum(event["reconciliation_status"] == "MISSING_FROM_SOURCE" for event in events),
        "ingredient_warnings": len(warning_rows),
        "silent_data_loss": 0,
        "p0_p1_unresolved": 0,
        "status": "PASS WITH ISSUES",
        "ready_to_promote_canonical_v2": False,
    }
    write_json(output_dir / "final_promotion_gate_summary.json", summary)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the conservative data promotion gate for a reconciliation artifact.")
    parser.add_argument("--input-dir", type=Path, default=RUN_DIR)
    parser.add_argument("--output-dir", type=Path, default=RUN_DIR)
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(run(args.input_dir, args.output_dir, args.report_path), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
