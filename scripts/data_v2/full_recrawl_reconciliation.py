"""Resumable, conservative Long Chau recrawl and reconciliation for Legacy V1.

This runner deliberately writes only to ``data pharmacy/v2/full_recrawl``.  It
never updates the canonical V2 files or the legacy corpus.  Every attempted
legacy ID receives one terminal reconciliation status, making an interrupted
run reproducible through its checkpoint and append-only event log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests

from crawler_v2 import (
    BASE_URL,
    PARSER_VERSION,
    SOURCE_NAME,
    USER_AGENT,
    canonicalize_fresh,
    extract_legacy_like_fields,
    fetch_next_data,
    snapshot_id_for,
    validate_canonical,
    validate_snapshot,
)
from legacy_importer import normalize_name, read_legacy_records


ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT / "data pharmacy"
V2_DIR = LEGACY_DIR / "v2"
RUN_DIR = V2_DIR / "full_recrawl"
RAW_DIR = RUN_DIR / "raw_snapshots" / SOURCE_NAME
REPORT_PATH = LEGACY_DIR / "reports" / "v2" / "full-recrawl-reconciliation-report.md"
SEARCH_URL = BASE_URL + "/thuoc/tim-kiem?action=search&keyword={keyword}&typeSearch=all"
RUNNER_VERSION = "full-recrawl-v2.0.0"

TERMINAL_STATUSES = {
    "MATCHED",
    "CHANGED",
    "NEW_PRODUCT",
    "AMBIGUOUS",
    "MISSING_FROM_SOURCE",
    "CRAWL_FAILED",
}
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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def canonical_text(value: Any) -> str:
    if isinstance(value, list):
        value = " | ".join(normalize_name(str(item)) for item in value)
    return normalize_name(str(value or "")).casefold()


def name_key(value: str) -> str:
    return "".join(char for char in canonical_text(value) if char.isalnum())


def material_field_differences(legacy: dict[str, Any], fresh: dict[str, Any]) -> list[str]:
    return [field for field in COMPARE_FIELDS if canonical_text(legacy.get(field)) != canonical_text(fresh.get(field))]


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def load_legacy() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for _path, _index, record in read_legacy_records(LEGACY_DIR):
        legacy_id = str(record.get("id") or "")
        if not legacy_id or legacy_id in records:
            raise RuntimeError(f"invalid or duplicate legacy drug_id: {legacy_id!r}")
        records[legacy_id] = record
    return records


def load_v2_products() -> dict[str, dict[str, Any]]:
    products = {}
    for row in read_jsonl(V2_DIR / "drug_product.jsonl"):
        legacy_id = str(row.get("legacy_drug_id") or "")
        if legacy_id:
            products[legacy_id] = row
    return products


def initialise_inventory(legacy: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    path = RUN_DIR / "inventory.jsonl"
    if path.exists():
        rows = read_jsonl(path)
        ids = [row.get("legacy_drug_id") for row in rows]
        if len(rows) != len(legacy) or set(ids) != set(legacy):
            raise RuntimeError("existing inventory does not match the frozen Legacy V1 corpus")
        return rows

    rows = [
        {
            "legacy_drug_id": legacy_id,
            "display_name": normalize_name(str(record.get("ten_thuoc") or "")),
            "legacy_name_key": name_key(str(record.get("ten_thuoc") or "")),
            "search_url": SEARCH_URL.format(keyword=quote(normalize_name(str(record.get("ten_thuoc") or "")))),
        }
        for legacy_id, record in sorted(legacy.items())
    ]
    write_jsonl(path, rows)
    return rows


def latest_results() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(RUN_DIR / "events.jsonl"):
        legacy_id = row.get("legacy_drug_id")
        if legacy_id:
            latest[legacy_id] = row
    return latest


def write_checkpoint(inventory: list[dict[str, Any]], completed: dict[str, dict[str, Any]]) -> None:
    counts = Counter(row.get("reconciliation_status") for row in completed.values())
    write_json(
        RUN_DIR / "checkpoint.json",
        {
            "runner_version": RUNNER_VERSION,
            "updated_at": utc_now(),
            "legacy_total": len(inventory),
            "completed": len(completed),
            "remaining": len(inventory) - len(completed),
            "status_counts": dict(sorted(counts.items())),
            "resume_command": "python scripts/data_v2/full_recrawl_reconciliation.py",
        },
    )


def fetch_with_retries(session: requests.Session, url: str, max_retries: int) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: requests.RequestException | None = None
    for attempt in range(max_retries + 1):
        try:
            return fetch_next_data(session, url)
        except requests.RequestException as error:
            last_error = error
            if attempt == max_retries:
                raise
            time.sleep(min(8.0, 1.0 * (2**attempt)))
    assert last_error is not None
    raise last_error


def search_candidates(session: requests.Session, query: str, max_retries: int) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    url = SEARCH_URL.format(keyword=quote(query))
    payload, metadata = fetch_with_retries(session, url, max_retries)
    products = payload.get("props", {}).get("pageProps", {}).get("data", {}).get("data", {}).get("products") or []
    candidates = []
    for product in products:
        slug = str(product.get("slug") or "").strip()
        name = normalize_name(str(product.get("name") or product.get("webName") or ""))
        if slug and name:
            candidates.append({"name": name, "slug": slug, "url": urljoin(BASE_URL, "/" + slug.lstrip("/")), "sku": product.get("sku")})
    return payload, candidates, metadata


def choose_candidate(legacy: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]]]:
    """Return a conservative resolution; ties and fuzzy-only matches stay ambiguous."""
    legacy_id = str(legacy["id"])
    expected_slug = legacy_id.replace("-", "")
    legacy_name = str(legacy.get("ten_thuoc") or "")
    exact = [candidate for candidate in candidates if name_key(candidate["name"]) == name_key(legacy_name)]
    if len(exact) == 1:
        return "EXACT_NAME", exact[0], exact
    if len(exact) > 1:
        return "AMBIGUOUS", None, exact

    slug_exact = [candidate for candidate in candidates if candidate["slug"].rsplit("/", 1)[-1].removesuffix(".html").replace("-", "") == expected_slug]
    if len(slug_exact) == 1:
        return "EXACT_SLUG", slug_exact[0], slug_exact
    if len(slug_exact) > 1:
        return "AMBIGUOUS", None, slug_exact

    scored = []
    for candidate in candidates:
        score = SequenceMatcher(None, name_key(legacy_name), name_key(candidate["name"])).ratio()
        if score >= 0.94:
            scored.append((score, candidate))
    scored.sort(key=lambda item: (-item[0], item[1]["url"]))
    if len(scored) == 1:
        return "HIGH_CONFIDENCE_NAME", scored[0][1], [scored[0][1]]
    if scored and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.03):
        return "HIGH_CONFIDENCE_NAME", scored[0][1], [candidate for _score, candidate in scored]
    if candidates:
        return "AMBIGUOUS", None, candidates
    return "MISSING", None, []


def snapshot_path(snapshot_id: str) -> Path:
    return RAW_DIR / f"{snapshot_id}.json"


def persist_snapshot(metadata: dict[str, Any], payload: dict[str, Any], legacy_drug_id: str) -> tuple[str, Path]:
    snapshot_id = snapshot_id_for(metadata)
    path = snapshot_path(snapshot_id)
    if not path.exists():
        snapshot = {
            "id": snapshot_id,
            "legacy_drug_id": legacy_drug_id,
            "source": SOURCE_NAME,
            "source_url": metadata["source_url"],
            "retrieved_at": metadata["retrieved_at"],
            "http_status": metadata["http_status"],
            "content_hash": metadata["content_hash"],
            "parser_version": PARSER_VERSION,
            "runner_version": RUNNER_VERSION,
            "raw_next_data": payload,
        }
        write_json(path, snapshot)
    return snapshot_id, path


def run_one(
    session: requests.Session,
    item: dict[str, Any],
    legacy: dict[str, Any],
    v2_product: dict[str, Any] | None,
    max_retries: int,
) -> dict[str, Any]:
    legacy_id = str(item["legacy_drug_id"])
    base = {
        "legacy_drug_id": legacy_id,
        "legacy_display_name": item["display_name"],
        "attempted_at": utc_now(),
        "runner_version": RUNNER_VERSION,
        "parser_version": PARSER_VERSION,
        "canonical_v2_product_id": (v2_product or {}).get("id"),
        "search_url": item["search_url"],
    }
    try:
        search_payload, candidates, search_metadata = search_candidates(session, item["display_name"], max_retries)
        search_snapshot_id, search_raw_path = persist_snapshot(search_metadata, search_payload, legacy_id)
        resolution, selected, considered = choose_candidate(legacy, candidates)
        base["search_url"] = search_metadata["source_url"]
        base["search_content_hash"] = search_metadata["content_hash"]
        base["search_snapshot_id"] = search_snapshot_id
        base["search_raw_snapshot_path"] = str(search_raw_path.relative_to(ROOT)).replace("\\", "/")
        base["candidate_count"] = len(candidates)
        base["candidate_resolution"] = resolution
        base["candidate_urls"] = [candidate["url"] for candidate in considered[:20]]
        if resolution == "MISSING":
            return {**base, "reconciliation_status": "MISSING_FROM_SOURCE", "review_required": True, "reason": "no product returned by deterministic source search"}
        if resolution == "AMBIGUOUS":
            return {**base, "reconciliation_status": "AMBIGUOUS", "review_required": True, "reason": "source search does not yield a unique conservative identity match"}

        assert selected is not None
        next_data, metadata = fetch_with_retries(session, selected["url"], max_retries)
        snapshot_id, raw_path = persist_snapshot(metadata, next_data, legacy_id)
        fresh = extract_legacy_like_fields(next_data)
        fresh_source_drug_id = fresh.get("id")
        # The candidate belongs to the resolved legacy identity; the source slug
        # remains recorded separately and never changes the public ID contract.
        fresh["id"] = legacy_id
        canonical = canonicalize_fresh(fresh, snapshot_id)
        validation_errors = validate_snapshot(metadata, raw_path) + validate_canonical(fresh, canonical)
        differences = material_field_differences(legacy, fresh)
        parse_warnings = canonical["ingredient_warnings"]
        status = "MATCHED" if not differences else "CHANGED"
        return {
            **base,
            "reconciliation_status": status,
            "review_required": status == "CHANGED" or bool(validation_errors) or bool(parse_warnings),
            "reason": "fields identical" if status == "MATCHED" else "fresh fields differ; candidate requires review before promotion",
            "selected_source_url": metadata["source_url"],
            "snapshot_id": snapshot_id,
            "raw_snapshot_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
            "retrieved_at": metadata["retrieved_at"],
            "content_hash": metadata["content_hash"],
            "provenance_status": "SOURCE_CAPTURED",
            "fresh_source_drug_id": fresh_source_drug_id,
            "field_differences": differences,
            "knowledge_items": len(canonical["drug_knowledge"]),
            "ingredient_parse_warnings": len(parse_warnings),
            "validation_errors": validation_errors,
        }
    except requests.RequestException as error:
        return {**base, "reconciliation_status": "CRAWL_FAILED", "review_required": True, "reason": "network/http error", "error": str(error)}
    except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return {**base, "reconciliation_status": "CRAWL_FAILED", "review_required": True, "reason": "source/parser error", "error": str(error)}


def build_summary(inventory: list[dict[str, Any]], completed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [completed[entry["legacy_drug_id"]] for entry in inventory if entry["legacy_drug_id"] in completed]
    counts = Counter(row["reconciliation_status"] for row in rows)
    successful = [row for row in rows if row["reconciliation_status"] in {"MATCHED", "CHANGED"}]
    snapshots = [row for row in successful if row.get("snapshot_id") and row.get("content_hash") and row.get("retrieved_at")]
    candidate_knowledge = sum(int(row.get("knowledge_items") or 0) for row in successful)
    warnings = sum(int(row.get("ingredient_parse_warnings") or 0) for row in successful)
    validation_errors = sum(len(row.get("validation_errors") or []) for row in successful)
    complete = len(rows) == len(inventory)
    all_terminal = all(row.get("reconciliation_status") in TERMINAL_STATUSES for row in rows)
    status = "BLOCKED" if not complete or not all_terminal else "PASS WITH ISSUES"
    if complete and not counts["CRAWL_FAILED"] and not counts["AMBIGUOUS"] and not counts["MISSING_FROM_SOURCE"] and not validation_errors:
        status = "PASS"
    return {
        "generated_at": utc_now(),
        "runner_version": RUNNER_VERSION,
        "legacy_total": len(inventory),
        "attempted": len(rows),
        "fetch_success": len(successful),
        "fetch_failed": counts["CRAWL_FAILED"],
        "matched": counts["MATCHED"],
        "changed": counts["CHANGED"],
        "new_product": counts["NEW_PRODUCT"],
        "ambiguous": counts["AMBIGUOUS"],
        "missing_from_source": counts["MISSING_FROM_SOURCE"],
        "provenance_coverage": f"{len(snapshots)}/{len(successful)}" if successful else "0/0",
        "candidate_knowledge_items": candidate_knowledge,
        "ingredient_parse_warnings": warnings,
        "validation_errors": validation_errors,
        "all_reconciled": complete and all_terminal,
        "status": status,
        "ready_for_final_data_promotion": False,
        "silent_overwrites": 0,
    }


def build_report(summary: dict[str, Any]) -> str:
    issues = []
    if summary["attempted"] != summary["legacy_total"]:
        issues.append("Full corpus has not completed; resume from checkpoint.")
    for key, label in (("fetch_failed", "crawl failures"), ("ambiguous", "ambiguous identities"), ("missing_from_source", "source-missing records"), ("validation_errors", "validation errors")):
        if summary[key]:
            issues.append(f"{summary[key]} {label} are isolated in the review queue; no canonical row was overwritten.")
    if summary["ingredient_parse_warnings"]:
        issues.append(f"{summary['ingredient_parse_warnings']} fresh ingredient segments were preserved raw with parse warnings.")
    issue_text = "\n".join(f"- {issue}" for issue in issues) if issues else "- None."
    return f"""# Full Re-crawl + Data Reconciliation

**Generated:** {summary['generated_at']}  
**Scope:** local source capture and candidate reconciliation only. Canonical V2, V1, RAG, and deployment were not changed.

## Reproducibility

- Runner: `scripts/data_v2/full_recrawl_reconciliation.py` (`{summary['runner_version']}`)
- Resume: `python scripts/data_v2/full_recrawl_reconciliation.py`
- State: `data pharmacy/v2/full_recrawl/checkpoint.json`; append-only event log: `events.jsonl`.
- Raw snapshots are immutable filesystem JSON files with source URL, retrieval time, SHA-256 content hash, parser version, and provenance.

## Outputs

- `data pharmacy/v2/full_recrawl/inventory.jsonl`
- `data pharmacy/v2/full_recrawl/events.jsonl`
- `data pharmacy/v2/full_recrawl/reconciliation.jsonl`
- `data pharmacy/v2/full_recrawl/review_queue.jsonl`
- `data pharmacy/v2/full_recrawl/raw_snapshots/nhathuoclongchau/*.json`
- candidate JSONL tables under `data pharmacy/v2/full_recrawl/`

## Validation

| Check | Result |
|---|---:|
| Legacy corpus | {summary['legacy_total']} |
| Attempted | {summary['attempted']} |
| All legacy IDs reconciled | {'YES' if summary['all_reconciled'] else 'NO'} |
| Silent canonical overwrites | {summary['silent_overwrites']} |
| Candidate knowledge items | {summary['candidate_knowledge_items']} |
| Ingredient parse warnings | {summary['ingredient_parse_warnings']} |
| Validation errors | {summary['validation_errors']} |
| Provenance coverage (successful fetches) | {summary['provenance_coverage']} |
| Duplicate candidate product IDs | {summary['duplicate_candidate_product_ids']} |
| Duplicate candidate knowledge IDs | {summary['duplicate_candidate_knowledge_ids']} |
| Fresh fields missing where Legacy had content | {summary['missing_fresh_fields']} |

## Review Requirements

{issue_text}

## FULL RE-CRAWL RESULT

STATUS: **{summary['status']}**

LEGACY TOTAL: {summary['legacy_total']}
ATTEMPTED: {summary['attempted']}
FETCH SUCCESS: {summary['fetch_success']}
FETCH FAILED: {summary['fetch_failed']}

MATCHED: {summary['matched']}
CHANGED: {summary['changed']}
NEW PRODUCT: {summary['new_product']}
AMBIGUOUS: {summary['ambiguous']}
MISSING FROM SOURCE: {summary['missing_from_source']}

PROVENANCE COVERAGE: {summary['provenance_coverage']}

DATA CONFLICTS: `{summary['changed']}` changed candidates; `{summary['missing_fresh_fields']}` fresh fields missing where Legacy had content; no candidate was promoted or overwrote Canonical V2.

P0/P1 ISSUES: {'None detected' if not summary['fetch_failed'] and not summary['validation_errors'] else 'No silent data-loss issue; unresolved source/parser cases remain in review queue.'}

READY FOR FINAL DATA PROMOTION: NO
"""


def materialise_views(inventory: list[dict[str, Any]], completed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [completed[entry["legacy_drug_id"]] for entry in inventory if entry["legacy_drug_id"] in completed]
    write_jsonl(RUN_DIR / "reconciliation.jsonl", rows)
    review = [row for row in rows if row.get("review_required")]
    write_jsonl(RUN_DIR / "review_queue.jsonl", review)

    # Candidate tables are derived from terminal events and immutable raw files,
    # rather than appended during fetch. A process interruption therefore cannot
    # duplicate or partially promote a candidate row.
    products: list[dict[str, Any]] = []
    ingredients: dict[str, dict[str, Any]] = {}
    ingredient_refs: list[dict[str, Any]] = []
    knowledge: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    missing_fresh_fields = 0
    field_difference_counts: Counter[str] = Counter()
    legacy = load_legacy()
    for row in rows:
        if row.get("reconciliation_status") not in {"MATCHED", "CHANGED"}:
            continue
        raw_path_value = row.get("raw_snapshot_path")
        if not raw_path_value:
            continue
        snapshot = json.loads((ROOT / raw_path_value).read_text(encoding="utf-8"))
        fresh = extract_legacy_like_fields(snapshot["raw_next_data"])
        for field in COMPARE_FIELDS:
            if canonical_text(legacy[row["legacy_drug_id"]].get(field)) and not canonical_text(fresh.get(field)):
                missing_fresh_fields += 1
        field_difference_counts.update(row.get("field_differences") or [])
        fresh["id"] = row["legacy_drug_id"]
        canonical = canonicalize_fresh(fresh, row["snapshot_id"])
        products.extend(canonical["drug_product"])
        for ingredient in canonical["ingredient"]:
            ingredients[ingredient["id"]] = ingredient
        ingredient_refs.extend(canonical["drug_product_ingredient"])
        knowledge.extend(canonical["drug_knowledge"])
        warnings.extend(canonical["ingredient_warnings"])
    write_jsonl(RUN_DIR / "candidate_drug_product.jsonl", products)
    write_jsonl(RUN_DIR / "candidate_ingredient.jsonl", sorted(ingredients.values(), key=lambda row: row["canonical_key"]))
    write_jsonl(RUN_DIR / "candidate_drug_product_ingredient.jsonl", ingredient_refs)
    write_jsonl(RUN_DIR / "candidate_drug_knowledge.jsonl", knowledge)
    write_jsonl(RUN_DIR / "candidate_ingredient_warnings.jsonl", warnings)

    summary = build_summary(inventory, completed)
    product_ids = [row["id"] for row in products]
    knowledge_ids = [row["id"] for row in knowledge]
    summary.update(
        {
            "candidate_products": len(products),
            "duplicate_candidate_product_ids": len(product_ids) - len(set(product_ids)),
            "duplicate_candidate_knowledge_ids": len(knowledge_ids) - len(set(knowledge_ids)),
            "missing_fresh_fields": missing_fresh_fields,
            "field_difference_counts": dict(sorted(field_difference_counts.items())),
            "knowledge_type_coverage": dict(sorted(Counter(row["knowledge_type"] for row in knowledge).items())),
        }
    )
    write_json(RUN_DIR / "summary.json", summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    return summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    legacy = load_legacy()
    v2_products = load_v2_products()
    if len(legacy) != 3562:
        raise RuntimeError(f"expected frozen legacy corpus of 3562 drugs, found {len(legacy)}")
    if set(legacy) != set(v2_products):
        raise RuntimeError("Canonical V2 mappings do not match frozen legacy IDs")

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    inventory = initialise_inventory(legacy)
    completed = latest_results()
    pending = [
        entry
        for entry in inventory
        if entry["legacy_drug_id"] not in completed
        or (args.retry_failed and completed[entry["legacy_drug_id"]].get("reconciliation_status") == "CRAWL_FAILED")
    ]
    if args.limit is not None:
        pending = pending[: args.limit]

    def crawl_item(item: dict[str, Any]) -> dict[str, Any]:
        # A requests Session is not shared between workers. Events/checkpoints
        # remain single-writer in the parent loop below.
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        legacy_id = item["legacy_drug_id"]
        result = run_one(session, item, legacy[legacy_id], v2_products.get(legacy_id), args.max_retries)
        if args.delay_seconds:
            time.sleep(args.delay_seconds)
        return result

    if args.workers == 1:
        results = (crawl_item(item) for item in pending)
    else:
        executor = ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="longchau-recrawl")
        results = (future.result() for future in as_completed([executor.submit(crawl_item, item) for item in pending]))

    try:
        for result in results:
            legacy_id = result["legacy_drug_id"]
            if result["reconciliation_status"] not in TERMINAL_STATUSES:
                raise RuntimeError(f"non-terminal reconciliation status for {legacy_id}")
            append_jsonl(RUN_DIR / "events.jsonl", result)
            completed[legacy_id] = result
            write_checkpoint(inventory, completed)
    finally:
        if args.workers > 1:
            executor.shutdown(wait=True, cancel_futures=False)

    return materialise_views(inventory, completed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Full resumable Long Chau recrawl with conservative reconciliation.")
    parser.add_argument("--limit", type=int, help="Process only this many pending IDs; useful for a controlled batch.")
    parser.add_argument("--delay-seconds", type=float, default=0.5, help="Delay between legacy IDs; source-friendly default is 0.5 seconds.")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries for transient HTTP failures before recording CRAWL_FAILED.")
    parser.add_argument("--retry-failed", action="store_true", help="Re-attempt only prior CRAWL_FAILED rows along with unattempted IDs.")
    parser.add_argument("--workers", type=int, default=1, help="Bounded parallel fetch workers; default is one.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds cannot be negative")
    if args.max_retries < 0:
        parser.error("--max-retries cannot be negative")
    if args.workers < 1:
        parser.error("--workers must be positive")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(run(args), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
