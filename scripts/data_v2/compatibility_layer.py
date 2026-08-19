"""Phase 4 compatibility layer checks for Drug Data V1/V2.

This is a standalone baseline harness. It does not modify runtime code or
production data. It proves the resolver and SHADOW comparison behavior that a
backend facade can later reuse.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT / "data pharmacy"
V2_DIR = LEGACY_DIR / "v2"
PILOT_DIR = V2_DIR / "fresh_crawl_pilot"
REPORT_PATH = LEGACY_DIR / "reports" / "phase4-compatibility-report.md"

Mode = Literal["v1", "v2", "shadow"]
FreshClass = Literal["EXACT_LEGACY_MATCH", "CHANGED_SLUG_MATCH", "NEW_PRODUCT", "AMBIGUOUS"]

FIELD_TO_KNOWLEDGE = {
    "tac_dung": "INDICATION",
    "tac_dung_phu": "ADVERSE_EFFECT",
    "huong_dan_su_dung": "ADMINISTRATION",
    "lieu_dung": "GENERAL_DOSAGE",
    "huong_dan_bao_quan": "STORAGE",
}


@dataclass(frozen=True)
class ResolveResult:
    legacy_drug_id: str
    drug_product_id: str


class DrugIdResolver:
    def __init__(self, mapping_rows: list[dict[str, Any]]) -> None:
        self._mapping: dict[str, str] = {}
        duplicates = []
        for row in mapping_rows:
            legacy_id = row["legacy_drug_id"]
            product_id = row["drug_product_id"]
            if legacy_id in self._mapping:
                duplicates.append(legacy_id)
            self._mapping[legacy_id] = product_id
        self.duplicates = sorted(set(duplicates))

    def resolve(self, legacy_drug_id: str) -> ResolveResult:
        try:
            product_id = self._mapping[legacy_drug_id]
        except KeyError as exc:
            raise KeyError(f"Unknown legacy drug_id: {legacy_drug_id}") from exc
        return ResolveResult(legacy_drug_id, product_id)


class DrugKnowledgeFacade:
    def __init__(
        self,
        legacy_records: dict[str, dict[str, Any]],
        v2_products: dict[str, dict[str, Any]],
        v2_knowledge: dict[str, list[dict[str, Any]]],
        resolver: DrugIdResolver,
        mode: Mode,
    ) -> None:
        self.legacy_records = legacy_records
        self.v2_products = v2_products
        self.v2_knowledge = v2_knowledge
        self.resolver = resolver
        self.mode = mode

    def query(self, legacy_drug_id: str) -> dict[str, Any]:
        if self.mode == "v1":
            return {"response_source": "v1", "v1": self._query_v1(legacy_drug_id)}
        if self.mode == "v2":
            return {"response_source": "v2", "v2": self._query_v2(legacy_drug_id)}
        v1_start = time.perf_counter()
        v1 = self._query_v1(legacy_drug_id)
        v1_ms = (time.perf_counter() - v1_start) * 1000
        v2_start = time.perf_counter()
        v2 = self._query_v2(legacy_drug_id)
        v2_ms = (time.perf_counter() - v2_start) * 1000
        return {
            "response_source": "v1",
            "v1": v1,
            "v2_shadow": v2,
            "comparison": compare_v1_v2(v1, v2),
            "latency_ms": {"v1": v1_ms, "v2": v2_ms},
        }

    def _query_v1(self, legacy_drug_id: str) -> dict[str, Any]:
        record = self.legacy_records.get(legacy_drug_id)
        if record is None:
            raise KeyError(f"Unknown V1 legacy drug_id: {legacy_drug_id}")
        return {
            "legacy_drug_id": legacy_drug_id,
            "ten_thuoc": record.get("ten_thuoc", ""),
            "available_fields": sorted(
                field for field in FIELD_TO_KNOWLEDGE if isinstance(record.get(field), str) and record.get(field, "").strip()
            ),
        }

    def _query_v2(self, legacy_drug_id: str) -> dict[str, Any]:
        resolved = self.resolver.resolve(legacy_drug_id)
        product = self.v2_products.get(legacy_drug_id)
        if product is None:
            raise KeyError(f"Resolved mapping exists but missing V2 product: {legacy_drug_id}")
        knowledge = self.v2_knowledge.get(legacy_drug_id, [])
        return {
            "legacy_drug_id": legacy_drug_id,
            "drug_product_id": resolved.drug_product_id,
            "display_name": product.get("display_name", ""),
            "knowledge_types": sorted({row["knowledge_type"] for row in knowledge}),
            "knowledge_count": len(knowledge),
        }


def normalize_text(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().casefold()
    return re.sub(r"\s+", " ", value)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_legacy_records() -> dict[str, dict[str, Any]]:
    result = {}
    for path in sorted(LEGACY_DIR.glob("*/thuoc.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data:
            result[record["id"]] = record
    return result


def load_v2_products() -> dict[str, dict[str, Any]]:
    return {row["legacy_drug_id"]: row for row in read_jsonl(V2_DIR / "drug_product.jsonl")}


def load_v2_knowledge() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_jsonl(V2_DIR / "drug_knowledge.jsonl"):
        grouped[row["legacy_drug_id"]].append(row)
    return grouped


def compare_v1_v2(v1: dict[str, Any], v2: dict[str, Any]) -> dict[str, Any]:
    expected_types = {FIELD_TO_KNOWLEDGE[field] for field in v1["available_fields"]}
    actual_types = set(v2["knowledge_types"])
    return {
        "identity_match": v1["legacy_drug_id"] == v2["legacy_drug_id"],
        "missing_knowledge_types": sorted(expected_types - actual_types),
        "extra_knowledge_types": sorted(actual_types - expected_types - {"REVIEW_REQUIRED"}),
        "knowledge_available": bool(actual_types),
        "name_match": normalize_text(v1["ten_thuoc"]) == normalize_text(v2["display_name"]),
    }


def build_name_index(legacy_records: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for legacy_id, record in legacy_records.items():
        key = normalize_text(str(record.get("ten_thuoc", "")))
        if key:
            index[key].append(legacy_id)
    return index


def reconcile_fresh_products(
    fresh_products: list[dict[str, Any]], legacy_records: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    name_index = build_name_index(legacy_records)
    rows = []
    for product in fresh_products:
        fresh_id = product["legacy_drug_id"]
        name_key = normalize_text(str(product.get("display_name", "")))
        if fresh_id in legacy_records:
            classification: FreshClass = "EXACT_LEGACY_MATCH"
            candidate_ids = [fresh_id]
        else:
            candidate_ids = sorted(name_index.get(name_key, []))
            if len(candidate_ids) == 1:
                classification = "CHANGED_SLUG_MATCH"
            elif len(candidate_ids) > 1:
                classification = "AMBIGUOUS"
            else:
                classification = "NEW_PRODUCT"
        rows.append(
            {
                "fresh_legacy_drug_id": fresh_id,
                "display_name": product.get("display_name", ""),
                "classification": classification,
                "candidate_legacy_drug_ids": candidate_ids,
            }
        )
    return rows


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def build_report(summary: dict[str, Any]) -> str:
    recon_lines = "\n".join(
        f"| `{row['fresh_legacy_drug_id']}` | {row['classification']} | {', '.join(row['candidate_legacy_drug_ids']) or '-'} |"
        for row in summary["fresh_reconciliation_rows"]
    )
    issue_lines = "\n".join(f"- {issue}" for issue in summary["open_issues"]) if summary["open_issues"] else "-"
    return f"""# Phase 4 Report --- V1/V2 Compatibility Layer

**Ngày:** {summary['generated_at']}  
**Scope:** standalone compatibility baseline, no public API/runtime changes.

## 1. Output đã tạo

- `scripts/data_v2/compatibility_layer.py`
- `data pharmacy/v2/compatibility/legacy_resolution_report.json`
- `data pharmacy/v2/compatibility/fresh_reconciliation.jsonl`
- `data pharmacy/v2/compatibility/shadow_comparison.json`
- `data pharmacy/reports/phase4-compatibility-report.md`

## 2. Số liệu chính

| Metric | Value |
|---|---:|
| Legacy IDs total | {summary['legacy_total']} |
| Legacy IDs resolved | {summary['legacy_resolved']} |
| Legacy IDs unresolved | {summary['legacy_unresolved']} |
| Duplicate mappings | {summary['duplicate_mappings']} |
| Shadow compared IDs | {summary['shadow_compared']} |
| Shadow identity mismatches | {summary['shadow_identity_mismatches']} |
| Shadow missing knowledge cases | {summary['shadow_missing_knowledge_cases']} |
| Shadow name mismatches | {summary['shadow_name_mismatches']} |
| V1 p95 latency ms | {summary['latency_ms']['v1_p95']:.4f} |
| V2 p95 latency ms | {summary['latency_ms']['v2_p95']:.4f} |

## 3. Fresh Product Reconciliation

| Class | Count |
|---|---:|
| EXACT_LEGACY_MATCH | {summary['fresh_reconciliation_counts'].get('EXACT_LEGACY_MATCH', 0)} |
| CHANGED_SLUG_MATCH | {summary['fresh_reconciliation_counts'].get('CHANGED_SLUG_MATCH', 0)} |
| NEW_PRODUCT | {summary['fresh_reconciliation_counts'].get('NEW_PRODUCT', 0)} |
| AMBIGUOUS | {summary['fresh_reconciliation_counts'].get('AMBIGUOUS', 0)} |

Rows:

| Fresh ID | Class | Candidate legacy IDs |
|---|---|---|
{recon_lines}

## 4. Vấn đề phát hiện

{issue_lines}

## 5. Quyết định còn mở

- Có tự động đưa `NEW_PRODUCT` vào corpus chính ở Phase 5 không, hay phải qua review queue.
- Có chấp nhận `CHANGED_SLUG_MATCH` bằng exact normalized name là đủ để auto-map không.
- Ngưỡng shadow production cuối cùng cho Phase 5/6 vẫn chưa chốt.

## 6. Trạng thái

**{summary['status']}**

Compatibility layer chứng minh được resolver legacy slug → UUID, V1/V2/SHADOW facade behavior, và baseline shadow comparison mà không đổi response production.

## PHASE 4 RESULT

```text
STATUS:
{summary['status']}

LEGACY IDS:
Total: {summary['legacy_total']}
Resolved: {summary['legacy_resolved']}
Unresolved: {summary['legacy_unresolved']}

FRESH RECONCILIATION:
Exact: {summary['fresh_reconciliation_counts'].get('EXACT_LEGACY_MATCH', 0)}
Changed slug: {summary['fresh_reconciliation_counts'].get('CHANGED_SLUG_MATCH', 0)}
New product: {summary['fresh_reconciliation_counts'].get('NEW_PRODUCT', 0)}
Ambiguous: {summary['fresh_reconciliation_counts'].get('AMBIGUOUS', 0)}

SHADOW MODE:
{summary['shadow_mode']}

BREAKING API CHANGE:
NO

OPEN ISSUES:
{summary['open_issues_text']}

READY FOR PHASE 5:
{summary['ready_for_phase5']}
```
"""


def run_phase4() -> dict[str, Any]:
    mapping_rows = read_jsonl(V2_DIR / "drug_id_map.jsonl")
    resolver = DrugIdResolver(mapping_rows)
    legacy_records = load_legacy_records()
    v2_products = load_v2_products()
    v2_knowledge = load_v2_knowledge()
    facade = DrugKnowledgeFacade(legacy_records, v2_products, v2_knowledge, resolver, "shadow")

    unresolved = []
    resolved = 0
    for legacy_id in sorted(legacy_records):
        try:
            resolver.resolve(legacy_id)
            resolved += 1
        except KeyError:
            unresolved.append(legacy_id)

    identity_mismatches = 0
    missing_knowledge_cases = 0
    name_mismatches = 0
    v1_latencies = []
    v2_latencies = []
    conflict_samples = []
    for legacy_id in sorted(legacy_records):
        result = facade.query(legacy_id)
        comparison = result["comparison"]
        v1_latencies.append(result["latency_ms"]["v1"])
        v2_latencies.append(result["latency_ms"]["v2"])
        if not comparison["identity_match"]:
            identity_mismatches += 1
        if comparison["missing_knowledge_types"]:
            missing_knowledge_cases += 1
            if len(conflict_samples) < 20:
                conflict_samples.append({"legacy_drug_id": legacy_id, **comparison})
        if not comparison["name_match"]:
            name_mismatches += 1

    fresh_products = read_jsonl(PILOT_DIR / "drug_product.jsonl")
    reconciliation_rows = reconcile_fresh_products(fresh_products, legacy_records)
    reconciliation_counts = Counter(row["classification"] for row in reconciliation_rows)

    open_issues = []
    if reconciliation_counts["NEW_PRODUCT"]:
        open_issues.append(f"{reconciliation_counts['NEW_PRODUCT']} fresh products are NEW_PRODUCT and must not be auto-merged")
    if reconciliation_counts["CHANGED_SLUG_MATCH"]:
        open_issues.append(f"{reconciliation_counts['CHANGED_SLUG_MATCH']} fresh products are CHANGED_SLUG_MATCH and need review before mapping")
    if reconciliation_counts["AMBIGUOUS"]:
        open_issues.append(f"{reconciliation_counts['AMBIGUOUS']} fresh products are AMBIGUOUS")
    if missing_knowledge_cases:
        open_issues.append(f"{missing_knowledge_cases} legacy IDs have missing V2 knowledge types")

    shadow_mode = "PASS"
    status = "PASS"
    ready = "YES"
    if unresolved or resolver.duplicates or identity_mismatches:
        status = "BLOCKED"
        shadow_mode = "FAIL"
        ready = "NO"
    elif open_issues:
        status = "PASS WITH ISSUES"
        ready = "YES"

    compatibility_dir = V2_DIR / "compatibility"
    compatibility_dir.mkdir(parents=True, exist_ok=True)
    resolution_report = {
        "legacy_total": len(legacy_records),
        "resolved": resolved,
        "unresolved": unresolved,
        "duplicate_mappings": resolver.duplicates,
    }
    (compatibility_dir / "legacy_resolution_report.json").write_text(
        json.dumps(resolution_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (compatibility_dir / "fresh_reconciliation.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in reconciliation_rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "legacy_total": len(legacy_records),
        "legacy_resolved": resolved,
        "legacy_unresolved": len(unresolved),
        "duplicate_mappings": len(resolver.duplicates),
        "shadow_compared": len(legacy_records),
        "shadow_identity_mismatches": identity_mismatches,
        "shadow_missing_knowledge_cases": missing_knowledge_cases,
        "shadow_name_mismatches": name_mismatches,
        "shadow_mode": shadow_mode,
        "latency_ms": {
            "v1_p50": percentile(v1_latencies, 50),
            "v1_p95": percentile(v1_latencies, 95),
            "v2_p50": percentile(v2_latencies, 50),
            "v2_p95": percentile(v2_latencies, 95),
        },
        "fresh_reconciliation_counts": dict(reconciliation_counts),
        "fresh_reconciliation_rows": reconciliation_rows,
        "conflict_samples": conflict_samples,
        "open_issues": open_issues,
        "open_issues_text": "\n".join(f"- {issue}" for issue in open_issues) if open_issues else "-",
        "ready_for_phase5": ready,
        "breaking_api_change": False,
    }
    (compatibility_dir / "shadow_comparison.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 4 V1/V2 compatibility baseline.")
    parser.parse_args()
    summary = run_phase4()
    print(
        json.dumps(
            {
                "status": summary["status"],
                "legacy_total": summary["legacy_total"],
                "legacy_resolved": summary["legacy_resolved"],
                "legacy_unresolved": summary["legacy_unresolved"],
                "fresh_reconciliation_counts": summary["fresh_reconciliation_counts"],
                "shadow_mode": summary["shadow_mode"],
                "breaking_api_change": summary["breaking_api_change"],
                "ready_for_phase5": summary["ready_for_phase5"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
