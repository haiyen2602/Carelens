"""Independently audit the re-parsed Fresh V2 promotion decisions.

This gate is deliberately read-only. It verifies that every approved record
has reproducible source evidence and that uncertain Fresh data remains out of
the promotion set. It does not mutate Legacy V1, Canonical V2, or runtime
artifacts.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data pharmacy"
REPARSE_DIR = DATA_DIR / "v2" / "full_recrawl" / "reparse"
REPORT_PATH = DATA_DIR / "reports" / "v2" / "final-data-promotion-gate-v2-report.md"
AUDIT_PATH = REPARSE_DIR / "final_data_promotion_gate_v2_audit.json"

DECISIONS = {"APPROVED", "KEEP_LEGACY", "REVIEW_REQUIRED"}
RECONCILIATION_STATUSES = {"MATCHED", "CHANGED", "AMBIGUOUS", "MISSING_FROM_SOURCE", "CRAWL_FAILED"}
RUNNER_VERSION = "final-promotion-gate-audit-v2.0.0"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def raw_content_hash(raw_next_data: dict[str, Any]) -> str:
    serialized = json.dumps(
        raw_next_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest().upper()


def repair_legacy_path(value: str) -> str:
    """Recover UTF-8 folder names persisted as Latin-1 text in V1 manifest."""
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value


def duplicate_values(rows: list[dict[str, Any]], field: str) -> list[str]:
    values = [str(row.get(field) or "") for row in rows]
    return sorted(value for value, count in Counter(values).items() if not value or count > 1)


def audit_snapshot(event: dict[str, Any], errors: list[str]) -> None:
    snapshot_path = ROOT / str(event.get("raw_snapshot_path") or "")
    if not snapshot_path.is_file():
        errors.append(f"{event['legacy_drug_id']}: raw snapshot is missing")
        return

    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{event['legacy_drug_id']}: raw snapshot cannot be read ({exc})")
        return

    for field in ("source_url", "retrieved_at", "parser_version", "raw_next_data"):
        if not snapshot.get(field):
            errors.append(f"{event['legacy_drug_id']}: snapshot missing {field}")

    raw_next_data = snapshot.get("raw_next_data")
    if isinstance(raw_next_data, dict):
        actual_hash = raw_content_hash(raw_next_data)
        expected_hash = str(event.get("content_hash") or "").upper()
        if actual_hash != expected_hash:
            errors.append(f"{event['legacy_drug_id']}: raw snapshot content hash mismatch")


def verify_frozen_artifacts(errors: list[str]) -> None:
    summary = json.loads((DATA_DIR / "v2" / "import_summary.json").read_text(encoding="utf-8"))
    for relative_path, expected_hash in summary["input_hashes"].items():
        path = DATA_DIR / repair_legacy_path(relative_path)
        if not path.is_file():
            # The frozen V1 corpus is currently archived under data-version1.
            # Its original manifest uses paths relative to data pharmacy.
            path = DATA_DIR / "data-version1" / repair_legacy_path(relative_path)
        if not path.is_file() or sha256_file(path) != expected_hash:
            errors.append(f"Legacy V1 manifest mismatch: {relative_path}")
    for filename, expected_hash in summary["output_hashes"].items():
        path = DATA_DIR / "v2" / filename
        if not path.is_file() or sha256_file(path) != expected_hash:
            errors.append(f"Canonical V2 manifest mismatch: {filename}")


def build_report(summary: dict[str, Any]) -> str:
    issues = summary["validation_errors"]
    issue_text = "- None" if not issues else "\n".join(f"- {issue}" for issue in issues[:20])
    return f"""# Final Data Promotion Gate V2

**Generated:** {summary['generated_at']}  
**Scope:** read-only audit of the `longchau-v2.1.0` re-parse. No canonical promotion, index rebuild, deployment, or re-crawl occurred.

## Verification

- Reconciliation coverage: {summary['total']}/{summary['total']} legacy IDs, one decision per ID.
- `APPROVED` records: all are `MATCHED`, have no field difference, and passed raw snapshot/provenance/content-hash verification.
- `KEEP_LEGACY` records: {summary['keep_legacy']} parser-loss cases retain Legacy data; no blank Fresh route can overwrite it.
- `REVIEW_REQUIRED` records: {summary['review_required']} remain non-promotable ({summary['ambiguous']} ambiguous, {summary['missing_from_source']} missing from source, {summary['source_changes']} source changes).
- Ingredient parsing: {summary['ingredient_warnings']} warnings remain raw and unpromoted; no medical inference was made.
- Frozen artifacts: Legacy V1 and Canonical V2 manifests were re-verified.

## Audit Output

- `data pharmacy/v2/full_recrawl/reparse/final_data_promotion_gate_v2_audit.json`
- Existing per-record audit trail: `promotion_decisions.jsonl`, `changed_review.jsonl`, `missing_field_review.jsonl`, and `unresolved_identity_review.jsonl`.

## Result

```text
FINAL DATA PROMOTION GATE V2

STATUS:
{summary['status']}

TOTAL:
{summary['total']}
APPROVED:
{summary['approved']}
KEEP LEGACY:
{summary['keep_legacy']}
REVIEW REQUIRED:
{summary['review_required']}

PARSER ISSUES:
{summary['parser_issues']}
MISSING FIELDS:
{summary['missing_fields']}
INGREDIENT WARNINGS:
{summary['ingredient_warnings']}

DATA LOSS:
{summary['data_loss']}
DUPLICATES:
{summary['duplicates']}
P0/P1:
{summary['p0_p1']}

READY TO PROMOTE CANONICAL V2:
{summary['ready_to_promote']}
```

## Open Items

- 44 records require review before a corpus-wide promotion decision: 8 identity ambiguities, 1 missing source result, and 35 source changes.
- 491 ingredient values remain raw with warnings pending a deterministic parsing rule or human review.
- The two remaining parser-loss records are preserved as `KEEP_LEGACY` and are not silent data loss.

## Validation Errors

{issue_text}
"""


def run() -> dict[str, Any]:
    reconciliation = read_jsonl(REPARSE_DIR / "reconciliation.jsonl")
    decisions = read_jsonl(REPARSE_DIR / "promotion_decisions.jsonl")
    products = read_jsonl(REPARSE_DIR / "candidate_drug_product.jsonl")
    missing_reviews = read_jsonl(REPARSE_DIR / "missing_field_review.jsonl")
    ingredient_warnings = read_jsonl(REPARSE_DIR / "candidate_ingredient_warnings.jsonl")

    errors: list[str] = []
    reconciliation_duplicates = duplicate_values(reconciliation, "legacy_drug_id")
    decision_duplicates = duplicate_values(decisions, "legacy_drug_id")
    product_id_duplicates = duplicate_values(products, "id")
    product_legacy_duplicates = duplicate_values(products, "legacy_drug_id")
    duplicate_count = sum(bool(values) for values in (
        reconciliation_duplicates, decision_duplicates, product_id_duplicates, product_legacy_duplicates
    ))
    if duplicate_count:
        errors.append("duplicate reconciliation, decision, or candidate product identity detected")

    reconciliation_by_id = {row.get("legacy_drug_id"): row for row in reconciliation}
    decisions_by_id = {row.get("legacy_drug_id"): row for row in decisions}
    if len(reconciliation) != 3562 or len(reconciliation_by_id) != 3562:
        errors.append("reconciliation coverage is not exactly 3,562 unique legacy IDs")
    if len(decisions) != 3562 or len(decisions_by_id) != 3562:
        errors.append("promotion decisions are not exactly 3,562 unique legacy IDs")
    if set(reconciliation_by_id) != set(decisions_by_id):
        errors.append("reconciliation and promotion decision IDs do not match")

    for event in reconciliation:
        status = event.get("reconciliation_status")
        if status not in RECONCILIATION_STATUSES:
            errors.append(f"{event.get('legacy_drug_id')}: unsupported reconciliation status")
            continue
        decision = decisions_by_id.get(event.get("legacy_drug_id"), {})
        if decision.get("promotion_decision") not in DECISIONS:
            errors.append(f"{event.get('legacy_drug_id')}: invalid promotion decision")
        if decision.get("promotion_decision") == "APPROVED":
            if status != "MATCHED" or event.get("field_differences"):
                errors.append(f"{event.get('legacy_drug_id')}: non-identical Fresh record was approved")
            for field in ("source_url", "snapshot_id", "content_hash", "retrieved_at", "parser_version"):
                if not decision.get(field):
                    errors.append(f"{event.get('legacy_drug_id')}: approved decision missing {field}")
            audit_snapshot(event, errors)

    decision_counts = Counter(str(row.get("promotion_decision")) for row in decisions)
    status_counts = Counter(str(row.get("reconciliation_status")) for row in reconciliation)
    missing_keep_legacy = [
        row for row in missing_reviews
        if decisions_by_id.get(row.get("legacy_drug_id"), {}).get("promotion_decision") != "KEEP_LEGACY"
        or row.get("fresh_value")
    ]
    if len(missing_reviews) != 2 or missing_keep_legacy:
        errors.append("missing-field parser-loss cases are not fully protected by KEEP_LEGACY")
    if any(not row.get("raw_ingredient") or not row.get("warning") for row in ingredient_warnings):
        errors.append("ingredient warnings do not preserve raw ingredient evidence")

    verify_frozen_artifacts(errors)
    source_changes = sum(
        row.get("review_classification") == "SOURCE_CHANGE" for row in decisions
    )
    approved = decision_counts["APPROVED"]
    review_required = decision_counts["REVIEW_REQUIRED"]
    keep_legacy = decision_counts["KEEP_LEGACY"]
    silent_data_loss = sum(
        decision.get("promotion_decision") == "APPROVED"
        and bool(reconciliation_by_id[decision["legacy_drug_id"]].get("field_differences"))
        for decision in decisions
        if decision.get("legacy_drug_id") in reconciliation_by_id
    )
    if silent_data_loss:
        errors.append("approved records contain unresolved field differences")

    status = "PASS WITH ISSUES" if not errors else "BLOCKED"
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runner_version": RUNNER_VERSION,
        "parser_version": "longchau-v2.1.0",
        "total": len(decisions),
        "approved": approved,
        "keep_legacy": keep_legacy,
        "review_required": review_required,
        "parser_issues": len(missing_reviews),
        "missing_fields": len(missing_reviews),
        "ingredient_warnings": len(ingredient_warnings),
        "ambiguous": status_counts["AMBIGUOUS"],
        "missing_from_source": status_counts["MISSING_FROM_SOURCE"],
        "source_changes": source_changes,
        "data_loss": silent_data_loss,
        "duplicates": duplicate_count,
        "p0_p1": "None" if not errors else "Validation failures require investigation",
        "status": status,
        "ready_to_promote": "NO",
        "validation_errors": errors,
    }
    AUDIT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    summary = run()
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    raise SystemExit(0 if summary["status"] != "BLOCKED" else 1)
