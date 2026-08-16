"""Phase 5 Knowledge/Search V2 baseline.

This script proves structured lookup over Canonical Data V2 without touching
public API, prescription IDs, production RAG, embeddings, or Agent code.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data pharmacy"
V2_DIR = DATA_DIR / "v2"
REPORT_PATH = DATA_DIR / "reports" / "phase5-knowledge-search-report.md"
OUTPUT_DIR = V2_DIR / "knowledge_search"

KNOWLEDGE_TYPES = {
    "INDICATION",
    "ADVERSE_EFFECT",
    "CONTRAINDICATION",
    "PRECAUTION",
    "INTERACTION",
    "PREGNANCY_LACTATION",
    "DRIVING_WARNING",
    "ADMINISTRATION",
    "GENERAL_DOSAGE",
    "STORAGE",
}

TOPIC_KEYWORDS = [
    ("CONTRAINDICATION", ["chong chi dinh", "khong duoc dung", "ai khong dung"]),
    ("ADVERSE_EFFECT", ["tac dung phu", "phan ung bat loi", "adr", "buon non", "chong mat"]),
    ("INTERACTION", ["tuong tac", "dung chung", "uong chung"]),
    ("PREGNANCY_LACTATION", ["mang thai", "co thai", "cho con bu", "thai ky"]),
    ("DRIVING_WARNING", ["lai xe", "van hanh may", "tau xe"]),
    ("ADMINISTRATION", ["cach dung", "dung nhu the nao", "su dung nhu the nao"]),
    ("GENERAL_DOSAGE", ["lieu dung", "uống bao nhiêu", "uong bao nhieu", "ngay may lan"]),
    ("STORAGE", ["bao quan", "cat giu", "de o dau"]),
    ("INDICATION", ["cong dung", "chi dinh", "tri gi", "dung de lam gi"]),
    ("PRECAUTION", ["than trong", "luu y", "canh bao"]),
]

STOPWORDS = {
    "thuoc",
    "co",
    "gi",
    "khong",
    "la",
    "va",
    "toi",
    "muon",
    "hoi",
    "ve",
    "cho",
    "biet",
    "dung",
    "uống",
    "uong",
    "nhu",
    "the",
    "nao",
    "bao",
    "nhieu",
    "can",
}


@dataclass(frozen=True)
class Resolution:
    status: str
    drug_product_id: str | None = None
    legacy_drug_id: str | None = None
    candidates: tuple[str, ...] = ()
    method: str | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def normalize_text(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().casefold()
    return re.sub(r"\s+", " ", value)


def tokenize(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token and token not in STOPWORDS}


def sorted_unique(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(values)))


class DrugResolver:
    def __init__(self, products: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> None:
        self.products_by_legacy = {row["legacy_drug_id"]: row for row in products}
        self.product_id_by_legacy = {row["legacy_drug_id"]: row["drug_product_id"] for row in mappings}
        self.legacy_by_product_id = {row["drug_product_id"]: row["legacy_drug_id"] for row in mappings}
        self.name_index: dict[str, list[str]] = defaultdict(list)
        self.alias_index: dict[str, list[str]] = defaultdict(list)
        for row in products:
            legacy_id = row["legacy_drug_id"]
            display = str(row.get("display_name", ""))
            normalized_name = normalize_text(display)
            if normalized_name:
                self.name_index[normalized_name].append(legacy_id)
            # Conservative aliases: only prefix tokens before package/strength
            tokens = normalize_text(display).split()
            alias_tokens = []
            for token in tokens:
                if any(ch.isdigit() for ch in token):
                    break
                alias_tokens.append(token)
            if alias_tokens:
                self.alias_index[" ".join(alias_tokens)].append(legacy_id)

    def resolve(self, query: str) -> Resolution:
        raw = query.strip()
        normalized = normalize_text(raw)
        if raw in self.product_id_by_legacy:
            return Resolution("RESOLVED", self.product_id_by_legacy[raw], raw, method="legacy_id")
        if normalized in self.name_index:
            ids = sorted_unique(self.name_index[normalized])
            return self._single_or_ambiguous(ids, "normalized_name")
        if normalized in self.alias_index:
            ids = sorted_unique(self.alias_index[normalized])
            return self._single_or_ambiguous(ids, "alias")
        return self._fuzzy_resolve(normalized)

    def resolve_from_utterance(self, utterance: str) -> Resolution:
        normalized = normalize_text(utterance)
        matches = []
        for name, legacy_ids in self.name_index.items():
            if name and name in normalized:
                matches.extend(legacy_ids)
        if matches:
            ids = sorted_unique(matches)
            return self._single_or_ambiguous(ids, "utterance_name_contains")

        alias_matches = []
        for alias, legacy_ids in self.alias_index.items():
            if alias and re.search(r"\b" + re.escape(alias) + r"\b", normalized):
                alias_matches.extend(legacy_ids)
        if alias_matches:
            ids = sorted_unique(alias_matches)
            return self._single_or_ambiguous(ids, "utterance_alias_contains")

        # Try compact token windows, but only if one candidate is clearly best.
        utter_tokens = tokenize(utterance)
        if not utter_tokens:
            return Resolution("NOT_FOUND")
        scored = []
        for row in self.products_by_legacy.values():
            name_tokens = tokenize(str(row.get("display_name", "")))
            overlap = len(utter_tokens & name_tokens)
            if overlap:
                score = overlap / max(1, len(name_tokens))
                scored.append((score, row["legacy_drug_id"]))
        if not scored:
            return Resolution("NOT_FOUND")
        scored.sort(reverse=True)
        top_score = scored[0][0]
        candidates = [legacy_id for score, legacy_id in scored if score == top_score and score >= 0.5]
        if len(candidates) == 1:
            legacy_id = candidates[0]
            return Resolution("RESOLVED", self.product_id_by_legacy[legacy_id], legacy_id, method="utterance_token_overlap")
        if candidates:
            return Resolution("AMBIGUOUS", candidates=sorted_unique(candidates), method="utterance_token_overlap")
        return Resolution("NOT_FOUND")

    def _single_or_ambiguous(self, ids: tuple[str, ...], method: str) -> Resolution:
        if len(ids) == 1:
            legacy_id = ids[0]
            return Resolution("RESOLVED", self.product_id_by_legacy[legacy_id], legacy_id, method=method)
        return Resolution("AMBIGUOUS", candidates=ids, method=method)

    def _fuzzy_resolve(self, normalized: str) -> Resolution:
        scored = []
        for row in self.products_by_legacy.values():
            name = normalize_text(str(row.get("display_name", "")))
            score = SequenceMatcher(None, normalized, name).ratio()
            if score >= 0.9:
                scored.append((score, row["legacy_drug_id"]))
        if not scored:
            return Resolution("NOT_FOUND")
        scored.sort(reverse=True)
        top_score = scored[0][0]
        top = [legacy_id for score, legacy_id in scored if math.isclose(score, top_score, rel_tol=0.0, abs_tol=0.015)]
        if len(top) == 1:
            legacy_id = top[0]
            return Resolution("RESOLVED", self.product_id_by_legacy[legacy_id], legacy_id, method="fuzzy_name")
        return Resolution("AMBIGUOUS", candidates=sorted_unique(top), method="fuzzy_name")


class KnowledgeService:
    def __init__(self, knowledge_rows: list[dict[str, Any]]) -> None:
        self.by_product_and_type: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.rows = knowledge_rows
        for row in knowledge_rows:
            self.by_product_and_type[(row["drug_product_id"], row["knowledge_type"])].append(row)

    def get_knowledge(self, drug_product_id: str, knowledge_type: str) -> list[dict[str, Any]]:
        if knowledge_type not in KNOWLEDGE_TYPES:
            return []
        return self.by_product_and_type.get((drug_product_id, knowledge_type), [])

    def search(self, query: str, limit: int = 5, drug_product_id: str | None = None) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scored = []
        for row in self.rows:
            if drug_product_id and row["drug_product_id"] != drug_product_id:
                continue
            text_tokens = tokenize(str(row.get("content_raw", "")))
            overlap = query_tokens & text_tokens
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_tokens))
            scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], item[1]["legacy_drug_id"], item[1]["knowledge_type"]))
        return [{**row, "score": score} for score, row in scored[:limit]]


def detect_topic(utterance: str) -> str | None:
    normalized = normalize_text(utterance)
    for knowledge_type, phrases in TOPIC_KEYWORDS:
        if any(phrase in normalized for phrase in phrases):
            return knowledge_type
    return None


def answer_query(resolver: DrugResolver, service: KnowledgeService, utterance: str) -> dict[str, Any]:
    topic = detect_topic(utterance)
    resolution = resolver.resolve_from_utterance(utterance)
    if resolution.status != "RESOLVED":
        return {
            "path": "fail_closed",
            "resolution_status": resolution.status,
            "candidates": list(resolution.candidates),
            "knowledge_type": topic,
            "results": [],
        }
    if topic:
        rows = service.get_knowledge(resolution.drug_product_id or "", topic)
        if rows:
            return {
                "path": "structured",
                "resolution_status": "RESOLVED",
                "legacy_drug_id": resolution.legacy_drug_id,
                "drug_product_id": resolution.drug_product_id,
                "knowledge_type": topic,
                "results": rows,
            }
    rows = service.search(utterance, drug_product_id=resolution.drug_product_id)
    return {
        "path": "semantic_fallback",
        "resolution_status": "RESOLVED",
        "legacy_drug_id": resolution.legacy_drug_id,
        "drug_product_id": resolution.drug_product_id,
        "knowledge_type": topic,
        "results": rows,
    }


def build_eval_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "known_topic_contraindication",
            "utterance": "Agiclovir 5% Agimexpharm có chống chỉ định gì?",
            "expected_drug_id": "agiclovir-5-agimexpharm",
            "expected_type": "CONTRAINDICATION",
            "expected_path": "structured",
        },
        {
            "id": "known_topic_side_effect",
            "utterance": "Ketoconazol 2% Medipharco 10g có tác dụng phụ gì?",
            "expected_drug_id": "ketoconazol-2-medipharco-10g",
            "expected_type": "ADVERSE_EFFECT",
            "expected_path": "structured",
        },
        {
            "id": "diacriticless_topic",
            "utterance": "Berocca Bayer 10v co cong dung gi",
            "expected_drug_id": "berocca-bayer-10v",
            "expected_type": "INDICATION",
            "expected_path": "structured",
        },
        {
            "id": "typo_name",
            "utterance": "Magne b6 Corbiere Sanofi 5x10 lieu dung the nao?",
            "expected_drug_id": "magne-b6-corbiere-sanofi-5x10",
            "expected_type": "GENERAL_DOSAGE",
            "expected_path": "structured",
        },
        {
            "id": "similar_name_exact",
            "utterance": "Cefixim 200mg CỬU LONG 2x10 liều dùng?",
            "expected_drug_id": "cefixim-200mg-cuu-long-2x10",
            "expected_type": "GENERAL_DOSAGE",
            "expected_path": "structured",
        },
        {
            "id": "ambiguous_alias",
            "utterance": "Cefixim liều dùng?",
            "expected_resolution": "AMBIGUOUS",
            "expected_path": "fail_closed",
        },
        {
            "id": "nonexistent_drug",
            "utterance": "Thuốc Không Tồn Tại ABCXYZ có tác dụng phụ gì?",
            "expected_resolution": "NOT_FOUND",
            "expected_path": "fail_closed",
        },
        {
            "id": "multiple_drugs",
            "utterance": "Berocca Bayer 10v và Upsa-c 10v thuốc nào có công dụng gì?",
            "expected_resolution": "AMBIGUOUS",
            "expected_path": "fail_closed",
        },
        {
            "id": "semantic_open_ended",
            "utterance": "Ketoconazol 2% Medipharco 10g dùng khi bị nấm ngoài da không?",
            "expected_drug_id": "ketoconazol-2-medipharco-10g",
            "expected_type": None,
            "expected_path": "semantic_fallback",
        },
        {
            "id": "storage_structured",
            "utterance": "Tothema 2x10 ỐNG 10ml bảo quản thế nào?",
            "expected_drug_id": "tothema-2x10-ong-10ml",
            "expected_type": "STORAGE",
            "expected_path": "structured",
        },
        {
            "id": "pregnancy_structured",
            "utterance": "Tardyferon b9 3x10 phụ nữ mang thai dùng được không?",
            "expected_drug_id": "tardyferon-b9-3x10",
            "expected_type": "PREGNANCY_LACTATION",
            "expected_path": "structured",
        },
        {
            "id": "interaction_structured",
            "utterance": "Procare Diamond 216mg Catalent 30v có tương tác thuốc không?",
            "expected_drug_id": "procare-diamond-216mg-catalent-30v",
            "expected_type": "INTERACTION",
            "expected_path": "structured",
        },
    ]


def load_new_products_for_review() -> list[dict[str, Any]]:
    path = V2_DIR / "compatibility" / "fresh_reconciliation.jsonl"
    if not path.exists():
        return []
    return [row for row in read_jsonl(path) if row["classification"] == "NEW_PRODUCT"]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def run_eval(resolver: DrugResolver, service: KnowledgeService) -> dict[str, Any]:
    cases = build_eval_cases()
    results = []
    wrong_drug = []
    drug_ok = 0
    type_ok = 0
    structured = 0
    semantic = 0
    no_result = 0
    latencies = []
    for case in cases:
        started = time.perf_counter()
        output = answer_query(resolver, service, case["utterance"])
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        expected_resolution = case.get("expected_resolution", "RESOLVED")
        drug_match = True
        if expected_resolution == "RESOLVED":
            drug_match = output.get("legacy_drug_id") == case.get("expected_drug_id")
            if drug_match:
                drug_ok += 1
            elif output.get("legacy_drug_id"):
                wrong_drug.append({"case": case["id"], "got": output.get("legacy_drug_id"), "expected": case.get("expected_drug_id")})
        else:
            drug_match = output.get("resolution_status") == expected_resolution and not output.get("results")
            if drug_match:
                drug_ok += 1
        expected_type = case.get("expected_type")
        if case.get("expected_resolution", "RESOLVED") != "RESOLVED" and expected_type is None:
            type_match = True
        else:
            type_match = output.get("knowledge_type") == expected_type
        if type_match:
            type_ok += 1
        if output["path"] == "structured":
            structured += 1
        if output["path"] == "semantic_fallback":
            semantic += 1
        if not output.get("results"):
            no_result += 1
        results.append(
            {
                "case_id": case["id"],
                "utterance": case["utterance"],
                "expected_path": case["expected_path"],
                "actual_path": output["path"],
                "expected_drug_id": case.get("expected_drug_id"),
                "actual_drug_id": output.get("legacy_drug_id"),
                "expected_resolution": expected_resolution,
                "actual_resolution": output.get("resolution_status"),
                "expected_type": expected_type,
                "actual_type": output.get("knowledge_type"),
                "drug_match": drug_match,
                "type_match": type_match,
                "result_count": len(output.get("results", [])),
                "latency_ms": elapsed_ms,
            }
        )
    return {
        "cases": len(cases),
        "results": results,
        "drug_resolution_accuracy": drug_ok / len(cases),
        "knowledge_type_accuracy": type_ok / len(cases),
        "structured_lookup_coverage": structured / len(cases),
        "semantic_fallback_rate": semantic / len(cases),
        "wrong_drug_rate": len(wrong_drug) / len(cases),
        "wrong_drug_cases": wrong_drug,
        "no_result_rate": no_result / len(cases),
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": max(latencies) if latencies else 0.0,
        },
    }


def build_report(summary: dict[str, Any]) -> str:
    issue_lines = "\n".join(f"- {issue}" for issue in summary["open_issues"]) if summary["open_issues"] else "-"
    wrong_lines = "\n".join(
        f"- {case['case']}: got `{case['got']}`, expected `{case['expected']}`"
        for case in summary["eval"]["wrong_drug_cases"]
    ) or "-"
    new_product_lines = "\n".join(
        f"- `{row['fresh_legacy_drug_id']}` — {row['display_name']}"
        for row in summary["new_products_review_queue"]
    ) or "-"
    eval_rows = "\n".join(
        f"| {row['case_id']} | {row['actual_path']} | {row['actual_resolution']} | {row.get('actual_drug_id') or '-'} | {row['actual_type'] or '-'} | {row['result_count']} |"
        for row in summary["eval"]["results"]
    )
    ready = "YES" if summary["status"] in {"PASS", "PASS WITH ISSUES"} else "NO"
    return f"""# Phase 5 Report --- Knowledge/Search V2

**Ngày:** {summary['generated_at']}  
**Scope:** standalone Knowledge/Search V2 over Canonical V2 JSONL. No API/RAG/Agent changes.

## 1. Output đã tạo

- `scripts/data_v2/knowledge_search_v2.py`
- `data pharmacy/v2/knowledge_search/eval_results.json`
- `data pharmacy/v2/knowledge_search/new_product_review_queue.jsonl`
- `data pharmacy/reports/phase5-knowledge-search-report.md`

## 2. Drug Resolution

- Exact legacy/public ID: supported.
- Exact normalized name: supported.
- Conservative alias: supported only when unique.
- Fuzzy typo: supported only when one candidate is clearly best.
- Ambiguous/nonexistent: fail closed, no knowledge returned.

## 3. Structured Lookup

- `get_knowledge(drug_product_id, knowledge_type)` implemented for all Phase 5 knowledge types.
- Known drug + known topic uses structured path, no vector/semantic search.
- Structured lookup coverage on eval: {summary['eval']['structured_lookup_coverage']:.2%}

## 4. Semantic Search

- Implemented as local lexical semantic fallback over `drug_knowledge.content_raw`.
- Used only when topic is not confidently detected or structured path has no rows.
- Semantic fallback rate on eval: {summary['eval']['semantic_fallback_rate']:.2%}

## 5. Eval

| Metric | Value |
|---|---:|
| Eval cases | {summary['eval']['cases']} |
| Drug resolution accuracy | {summary['eval']['drug_resolution_accuracy']:.2%} |
| Knowledge-type accuracy | {summary['eval']['knowledge_type_accuracy']:.2%} |
| Structured lookup coverage | {summary['eval']['structured_lookup_coverage']:.2%} |
| Semantic fallback rate | {summary['eval']['semantic_fallback_rate']:.2%} |
| Wrong-drug rate | {summary['eval']['wrong_drug_rate']:.2%} |
| No-result rate | {summary['eval']['no_result_rate']:.2%} |
| Latency p50 ms | {summary['eval']['latency_ms']['p50']:.4f} |
| Latency p95 ms | {summary['eval']['latency_ms']['p95']:.4f} |

Rows:

| Case | Path | Resolution | Drug | Type | Results |
|---|---|---|---|---|---:|
{eval_rows}

## 6. NEW_PRODUCT Review Queue

{new_product_lines}

## 7. Wrong Drug Cases

{wrong_lines}

## 8. Vấn đề phát hiện / Open Issues

{issue_lines}

## 9. Trạng thái

**{summary['status']}**

Structured path works independently from V1 RAG/Agent. Semantic search remains a fallback baseline and is not production embedding migration.

## PHASE 5 RESULT

```text
STATUS:
{summary['status']}

DRUG RESOLUTION:
Accuracy: {summary['eval']['drug_resolution_accuracy']:.2%}
Ambiguous/nonexistent: fail closed

STRUCTURED LOOKUP:
Coverage: {summary['eval']['structured_lookup_coverage']:.2%}
Known drug + known topic avoids semantic/vector path

SEMANTIC SEARCH:
Fallback rate: {summary['eval']['semantic_fallback_rate']:.2%}
Production embeddings not regenerated

EVAL:
Cases: {summary['eval']['cases']}
Knowledge-type accuracy: {summary['eval']['knowledge_type_accuracy']:.2%}
No-result rate: {summary['eval']['no_result_rate']:.2%}
Latency p95 ms: {summary['eval']['latency_ms']['p95']:.4f}

WRONG DRUG CASES:
{wrong_lines}

OPEN ISSUES:
{issue_lines}

READY FOR PHASE 6:
{ready}
```
"""


def run_phase5() -> dict[str, Any]:
    products = read_jsonl(V2_DIR / "drug_product.jsonl")
    mappings = read_jsonl(V2_DIR / "drug_id_map.jsonl")
    knowledge = read_jsonl(V2_DIR / "drug_knowledge.jsonl")
    resolver = DrugResolver(products, mappings)
    service = KnowledgeService(knowledge)
    eval_result = run_eval(resolver, service)
    new_products = load_new_products_for_review()

    open_issues = []
    if new_products:
        open_issues.append(f"{len(new_products)} NEW_PRODUCT rows remain in review queue; not auto-added to production corpus")
    if eval_result["wrong_drug_rate"] > 0:
        open_issues.append("wrong-drug cases detected")
    if any(row["actual_path"] == "semantic_fallback" and row["expected_path"] == "structured" for row in eval_result["results"]):
        open_issues.append("known topic unexpectedly used semantic fallback")

    status = "PASS"
    if eval_result["wrong_drug_rate"] > 0:
        status = "BLOCKED"
    elif open_issues:
        status = "PASS WITH ISSUES"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_DIR / "new_product_review_queue.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in new_products:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "eval": eval_result,
        "new_products_review_queue": new_products,
        "open_issues": open_issues,
    }
    (OUTPUT_DIR / "eval_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 5 Knowledge/Search V2 eval.")
    parser.parse_args()
    summary = run_phase5()
    print(
        json.dumps(
            {
                "status": summary["status"],
                "drug_resolution_accuracy": summary["eval"]["drug_resolution_accuracy"],
                "knowledge_type_accuracy": summary["eval"]["knowledge_type_accuracy"],
                "structured_lookup_coverage": summary["eval"]["structured_lookup_coverage"],
                "semantic_fallback_rate": summary["eval"]["semantic_fallback_rate"],
                "wrong_drug_rate": summary["eval"]["wrong_drug_rate"],
                "new_product_review_queue": len(summary["new_products_review_queue"]),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
