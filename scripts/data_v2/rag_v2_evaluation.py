"""Phase 6 RAG V2 migration/evaluation baseline.

Builds a standalone V2 chunk/index from ``drug_knowledge`` and compares it
against legacy V1 chunks. This script does not touch production embeddings,
Agent code, public API, prescriptions, or legacy files.
"""

from __future__ import annotations

import argparse
import hashlib
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
OUTPUT_DIR = V2_DIR / "rag_eval"
REPORT_PATH = DATA_DIR / "reports" / "phase6-rag-evaluation-report.md"

TOP_K = 5
VECTOR_DIM = 512

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

V1_GROUP_TO_TYPES = {
    "cong_dung": {"INDICATION"},
    "tac_dung_phu": {
        "ADVERSE_EFFECT",
        "CONTRAINDICATION",
        "PRECAUTION",
        "INTERACTION",
        "PREGNANCY_LACTATION",
        "DRIVING_WARNING",
    },
    "cach_dung": {"ADMINISTRATION", "GENERAL_DOSAGE"},
    "bao_quan": {"STORAGE"},
}

TOPIC_KEYWORDS = [
    ("CONTRAINDICATION", ["chong chi dinh", "khong duoc dung", "ai khong dung"]),
    ("ADVERSE_EFFECT", ["tac dung phu", "phan ung bat loi", "adr", "buon non", "chong mat"]),
    ("INTERACTION", ["tuong tac", "dung chung", "uong chung"]),
    ("PREGNANCY_LACTATION", ["mang thai", "co thai", "cho con bu", "thai ky"]),
    ("DRIVING_WARNING", ["lai xe", "van hanh may", "tau xe"]),
    ("ADMINISTRATION", ["cach dung", "dung nhu the nao", "su dung nhu the nao"]),
    ("GENERAL_DOSAGE", ["lieu dung", "uong bao nhieu", "ngay may lan"]),
    ("STORAGE", ["bao quan", "cat giu", "de o dau"]),
    ("INDICATION", ["cong dung", "chi dinh", "tri gi", "dung de lam gi"]),
    ("PRECAUTION", ["than trong", "luu y", "canh bao"]),
]

STOPWORDS = {
    "thuoc",
    "toi",
    "cho",
    "hoi",
    "biet",
    "ve",
    "co",
    "gi",
    "khong",
    "la",
    "va",
    "hay",
    "thi",
    "duoc",
    "dung",
    "uong",
    "nhu",
    "the",
    "nao",
    "bao",
    "nhieu",
    "can",
    "neu",
    "bi",
}


@dataclass(frozen=True)
class Resolution:
    status: str
    drug_product_id: str | None = None
    legacy_drug_id: str | None = None
    candidates: tuple[str, ...] = ()
    method: str | None = None


@dataclass(frozen=True)
class IndexedChunk:
    id: str
    legacy_drug_id: str
    drug_product_id: str | None
    knowledge_type: str | None
    text: str
    source: str
    provenance: dict[str, Any]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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


def tokenize(value: str) -> list[str]:
    return [token for token in normalize_text(value).split() if token and token not in STOPWORDS]


def detect_topic(utterance: str) -> str | None:
    normalized = normalize_text(utterance)
    for knowledge_type, phrases in TOPIC_KEYWORDS:
        if any(phrase in normalized for phrase in phrases):
            return knowledge_type
    return None


def sparse_vector(tokens: list[str], idf: dict[str, float]) -> dict[int, float]:
    counts = Counter(tokens)
    vector: dict[int, float] = defaultdict(float)
    for token, count in counts.items():
        bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % VECTOR_DIM
        vector[bucket] += (1.0 + math.log(count)) * idf.get(token, 1.0)
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm:
        return {idx: value / norm for idx, value in vector.items()}
    return {}


def cosine(left: dict[int, float], right: dict[int, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(idx, 0.0) for idx, value in left.items())


class DrugResolver:
    def __init__(self, products: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> None:
        self.products_by_legacy = {row["legacy_drug_id"]: row for row in products}
        self.product_id_by_legacy = {row["legacy_drug_id"]: row["drug_product_id"] for row in mappings}
        self.name_index: dict[str, list[str]] = defaultdict(list)
        self.alias_index: dict[str, list[str]] = defaultdict(list)
        for row in products:
            legacy_id = row["legacy_drug_id"]
            name = normalize_text(str(row.get("display_name", "")))
            if name:
                self.name_index[name].append(legacy_id)
            alias_tokens = []
            for token in name.split():
                if any(ch.isdigit() for ch in token):
                    break
                alias_tokens.append(token)
            if alias_tokens:
                self.alias_index[" ".join(alias_tokens)].append(legacy_id)

    def resolve_from_utterance(self, utterance: str) -> Resolution:
        normalized = normalize_text(utterance)
        name_matches = []
        for name, legacy_ids in self.name_index.items():
            if name and name in normalized:
                name_matches.extend(legacy_ids)
        if name_matches:
            return self._single_or_ambiguous(name_matches, "utterance_name_contains")

        alias_matches = []
        for alias, legacy_ids in self.alias_index.items():
            if alias and re.search(r"\b" + re.escape(alias) + r"\b", normalized):
                alias_matches.extend(legacy_ids)
        if alias_matches:
            return self._single_or_ambiguous(alias_matches, "utterance_alias_contains")

        return self._token_or_fuzzy(normalized, utterance)

    def _single_or_ambiguous(self, ids: list[str], method: str) -> Resolution:
        unique = tuple(sorted(dict.fromkeys(ids)))
        if len(unique) == 1:
            legacy_id = unique[0]
            return Resolution("RESOLVED", self.product_id_by_legacy[legacy_id], legacy_id, method=method)
        return Resolution("AMBIGUOUS", candidates=unique, method=method)

    def _token_or_fuzzy(self, normalized: str, utterance: str) -> Resolution:
        utter_tokens = set(tokenize(utterance))
        scored: list[tuple[float, str]] = []
        for row in self.products_by_legacy.values():
            name = normalize_text(str(row.get("display_name", "")))
            name_tokens = set(tokenize(name))
            overlap = len(utter_tokens & name_tokens)
            token_score = overlap / max(1, len(name_tokens)) if overlap else 0.0
            fuzzy_score = SequenceMatcher(None, normalized, name).ratio()
            score = max(token_score, fuzzy_score if fuzzy_score >= 0.9 else 0.0)
            if score >= 0.5:
                scored.append((score, row["legacy_drug_id"]))
        if not scored:
            return Resolution("NOT_FOUND")
        scored.sort(reverse=True)
        top_score = scored[0][0]
        top = [legacy_id for score, legacy_id in scored if math.isclose(score, top_score, abs_tol=0.015)]
        if len(top) == 1:
            legacy_id = top[0]
            return Resolution("RESOLVED", self.product_id_by_legacy[legacy_id], legacy_id, method="token_or_fuzzy")
        return Resolution("AMBIGUOUS", candidates=tuple(sorted(top)), method="token_or_fuzzy")


class SparseIndex:
    def __init__(self, chunks: list[IndexedChunk]) -> None:
        self.chunks = chunks
        doc_tokens = [tokenize(chunk.text) for chunk in chunks]
        df = Counter(token for tokens in doc_tokens for token in set(tokens))
        doc_count = max(1, len(chunks))
        self.idf = {token: math.log((doc_count + 1) / (freq + 1)) + 1.0 for token, freq in df.items()}
        self.vectors = [sparse_vector(tokens, self.idf) for tokens in doc_tokens]

    def search(
        self,
        query: str,
        *,
        top_k: int = TOP_K,
        drug_product_id: str | None = None,
        legacy_drug_id: str | None = None,
        knowledge_type: str | None = None,
    ) -> list[dict[str, Any]]:
        qvec = sparse_vector(tokenize(query), self.idf)
        scored = []
        for chunk, vector in zip(self.chunks, self.vectors, strict=True):
            if drug_product_id and chunk.drug_product_id != drug_product_id:
                continue
            if legacy_drug_id and chunk.legacy_drug_id != legacy_drug_id:
                continue
            if knowledge_type and chunk.knowledge_type != knowledge_type:
                continue
            score = cosine(qvec, vector)
            if score > 0.0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].legacy_drug_id, item[1].source))
        return [{"score": score, "chunk": chunk} for score, chunk in scored[:top_k]]

    def export(self) -> list[dict[str, Any]]:
        rows = []
        for chunk, vector in zip(self.chunks, self.vectors, strict=True):
            rows.append(
                {
                    "id": chunk.id,
                    "legacy_drug_id": chunk.legacy_drug_id,
                    "drug_product_id": chunk.drug_product_id,
                    "knowledge_type": chunk.knowledge_type,
                    "source": chunk.source,
                    "provenance": chunk.provenance,
                    "embedding_model": "local-tfidf-hash-v1",
                    "embedding_dim": VECTOR_DIM,
                    "embedding_sparse": {str(idx): round(value, 8) for idx, value in sorted(vector.items())},
                }
            )
        return rows


def build_v2_chunks(knowledge_rows: list[dict[str, Any]]) -> list[IndexedChunk]:
    chunks = []
    for row in knowledge_rows:
        chunks.append(
            IndexedChunk(
                id=row["id"],
                legacy_drug_id=row["legacy_drug_id"],
                drug_product_id=row["drug_product_id"],
                knowledge_type=row["knowledge_type"],
                text=row.get("content_raw") or row.get("content_normalized") or "",
                source=f"{row['knowledge_type']} - {row['legacy_drug_id']}",
                provenance={
                    "source_snapshot_id": row.get("source_snapshot_id"),
                    "provenance_status": row.get("provenance_status"),
                    "source_field": row.get("source_field"),
                    "source_section": row.get("source_section"),
                    "review_status": row.get("review_status"),
                },
            )
        )
    return chunks


def build_v1_chunks(v1_rows: list[dict[str, Any]], product_id_by_legacy: dict[str, str]) -> list[IndexedChunk]:
    chunks = []
    for index, row in enumerate(v1_rows):
        chunks.append(
            IndexedChunk(
                id=f"v1-{index:05d}-{row['drug_id']}-{row['field_group']}",
                legacy_drug_id=row["drug_id"],
                drug_product_id=product_id_by_legacy.get(row["drug_id"]),
                knowledge_type=None,
                text=row.get("noi_dung", ""),
                source=f"{row['field_group']} - {row['drug_id']}",
                provenance={"source": "legacy drug_chunks", "field_group": row.get("field_group")},
            )
        )
    return chunks


def build_eval_cases() -> list[dict[str, Any]]:
    return [
        {"id": "indication_known", "utterance": "Berocca Bayer 10v có công dụng gì?", "expected_drug_id": "berocca-bayer-10v", "expected_type": "INDICATION"},
        {"id": "adr_known", "utterance": "Ketoconazol 2% Medipharco 10g có tác dụng phụ gì?", "expected_drug_id": "ketoconazol-2-medipharco-10g", "expected_type": "ADVERSE_EFFECT"},
        {"id": "contraindication_known", "utterance": "Agiclovir 5% Agimexpharm chống chỉ định gì?", "expected_drug_id": "agiclovir-5-agimexpharm", "expected_type": "CONTRAINDICATION"},
        {"id": "interaction_known", "utterance": "Procare Diamond 216mg Catalent 30v có tương tác thuốc không?", "expected_drug_id": "procare-diamond-216mg-catalent-30v", "expected_type": "INTERACTION"},
        {"id": "dosage_typo", "utterance": "Magne b6 Corbiere Sanofi 5x10 lieu dung the nao?", "expected_drug_id": "magne-b6-corbiere-sanofi-5x10", "expected_type": "GENERAL_DOSAGE"},
        {"id": "storage_known", "utterance": "Tothema 2x10 ỐNG 10ml bảo quản thế nào?", "expected_drug_id": "tothema-2x10-ong-10ml", "expected_type": "STORAGE"},
        {"id": "pregnancy_known", "utterance": "Tardyferon b9 3x10 phụ nữ mang thai dùng được không?", "expected_drug_id": "tardyferon-b9-3x10", "expected_type": "PREGNANCY_LACTATION"},
        {"id": "administration_known", "utterance": "3b Agi-neurin Agimexpharm 10x10 cách dùng như thế nào?", "expected_drug_id": "3b-agi-neurin-agimexpharm-10x10", "expected_type": "ADMINISTRATION"},
        {"id": "driving_warning", "utterance": "3b Agi-neurin Agimexpharm 10x10 có ảnh hưởng lái xe không?", "expected_drug_id": "3b-agi-neurin-agimexpharm-10x10", "expected_type": "DRIVING_WARNING"},
        {"id": "precaution", "utterance": "3b Agi-neurin Agimexpharm 10x10 cần thận trọng gì?", "expected_drug_id": "3b-agi-neurin-agimexpharm-10x10", "expected_type": "PRECAUTION"},
        {"id": "similar_name_exact", "utterance": "Cefixim 200mg CỬU LONG 2x10 liều dùng?", "expected_drug_id": "cefixim-200mg-cuu-long-2x10", "expected_type": "GENERAL_DOSAGE"},
        {"id": "diacriticless", "utterance": "Upsa c 10v co cong dung gi?", "expected_drug_id": "upsa-c-10v", "expected_type": "INDICATION"},
        {"id": "semantic_open", "utterance": "Ketoconazol 2% Medipharco 10g dùng khi bị nấm ngoài da không?", "expected_drug_id": "ketoconazol-2-medipharco-10g", "expected_type": None},
        {"id": "semantic_open_2", "utterance": "Tôi thiếu sắt thì Tardyferon b9 3x10 liên quan gì?", "expected_drug_id": "tardyferon-b9-3x10", "expected_type": None},
        {"id": "ambiguous_alias", "utterance": "Cefixim liều dùng?", "expected_resolution": "AMBIGUOUS"},
        {"id": "multiple_drugs", "utterance": "Berocca Bayer 10v và Upsa-c 10v thuốc nào có công dụng gì?", "expected_resolution": "AMBIGUOUS"},
        {"id": "nonexistent", "utterance": "Thuốc Không Tồn Tại ABCXYZ có tác dụng phụ gì?", "expected_resolution": "NOT_FOUND"},
        {"id": "near_name_fail_closed", "utterance": "Panadol Extra Plus Ultra tác dụng phụ gì?", "expected_resolution": "NOT_FOUND"},
    ]


def evaluate_v2(resolver: DrugResolver, index: SparseIndex, cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    latencies = []
    for case in cases:
        started = time.perf_counter()
        expected_resolution = case.get("expected_resolution", "RESOLVED")
        topic = detect_topic(case["utterance"])
        resolution = resolver.resolve_from_utterance(case["utterance"])
        retrieved: list[dict[str, Any]] = []
        if resolution.status == "RESOLVED":
            retrieved = index.search(
                case["utterance"],
                drug_product_id=resolution.drug_product_id,
                knowledge_type=topic,
            )
            if not retrieved and topic:
                retrieved = index.search(case["utterance"], drug_product_id=resolution.drug_product_id)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        result = score_case(case, retrieved, resolution.status, topic, elapsed_ms, strict_type=True)
        result["resolver_method"] = resolution.method
        result["resolved_drug_id"] = resolution.legacy_drug_id
        result["candidates"] = list(resolution.candidates)
        result["expected_resolution"] = expected_resolution
        results.append(result)
    return summarize_results(results, latencies)


def evaluate_v1(index: SparseIndex, cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    latencies = []
    for case in cases:
        started = time.perf_counter()
        topic = detect_topic(case["utterance"])
        retrieved = index.search(case["utterance"])
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        result = score_case(case, retrieved, "GLOBAL_SEARCH", topic, elapsed_ms, strict_type=False)
        result["expected_resolution"] = case.get("expected_resolution", "RESOLVED")
        results.append(result)
    return summarize_results(results, latencies)


def score_case(
    case: dict[str, Any],
    retrieved: list[dict[str, Any]],
    resolution_status: str,
    topic: str | None,
    latency_ms: float,
    *,
    strict_type: bool,
) -> dict[str, Any]:
    expected_resolution = case.get("expected_resolution", "RESOLVED")
    expected_drug = case.get("expected_drug_id")
    expected_type = case.get("expected_type")
    top_chunks = [item["chunk"] for item in retrieved]
    top_scores = [item["score"] for item in retrieved]
    hit_rank = None
    type_hit_rank = None
    wrong_drug = False
    wrong_type = False
    leaked_on_unresolved = expected_resolution != "RESOLVED" and bool(top_chunks)

    if expected_resolution == "RESOLVED":
        for rank, chunk in enumerate(top_chunks, start=1):
            if chunk.legacy_drug_id == expected_drug:
                hit_rank = rank
                break
        if top_chunks and all(chunk.legacy_drug_id != expected_drug for chunk in top_chunks):
            wrong_drug = True
        if expected_type:
            for rank, chunk in enumerate(top_chunks, start=1):
                if chunk.legacy_drug_id != expected_drug:
                    continue
                if strict_type:
                    type_ok = chunk.knowledge_type == expected_type
                else:
                    field_group = chunk.provenance.get("field_group")
                    type_ok = expected_type in V1_GROUP_TO_TYPES.get(str(field_group), set())
                if type_ok:
                    type_hit_rank = rank
                    break
            if hit_rank is not None and type_hit_rank is None:
                wrong_type = True
    else:
        if leaked_on_unresolved:
            wrong_drug = True

    return {
        "case_id": case["id"],
        "utterance": case["utterance"],
        "expected_drug_id": expected_drug,
        "expected_type": expected_type,
        "detected_type": topic,
        "resolution_status": resolution_status,
        "hit_rank": hit_rank,
        "type_hit_rank": type_hit_rank,
        "hit_at_k": hit_rank is not None,
        "type_hit_at_k": expected_type is None or type_hit_rank is not None,
        "wrong_drug": wrong_drug,
        "wrong_type": wrong_type,
        "leaked_on_unresolved": leaked_on_unresolved,
        "no_result": not top_chunks,
        "latency_ms": latency_ms,
        "top_results": [
            {
                "rank": rank,
                "score": round(score, 6),
                "legacy_drug_id": chunk.legacy_drug_id,
                "drug_product_id": chunk.drug_product_id,
                "knowledge_type": chunk.knowledge_type,
                "source": chunk.source,
            }
            for rank, (score, chunk) in enumerate(zip(top_scores, top_chunks, strict=True), start=1)
        ],
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def summarize_results(results: list[dict[str, Any]], latencies: list[float]) -> dict[str, Any]:
    resolved_cases = [row for row in results if row["expected_drug_id"]]
    safety_cases = [row for row in results if row["expected_resolution"] != "RESOLVED"]
    type_cases = [row for row in results if row["expected_type"]]
    return {
        "cases": len(results),
        "resolved_cases": len(resolved_cases),
        "safety_cases": len(safety_cases),
        "hit_at_k": sum(1 for row in resolved_cases if row["hit_at_k"]) / max(1, len(resolved_cases)),
        "recall_at_k": sum(1 for row in resolved_cases if row["hit_at_k"]) / max(1, len(resolved_cases)),
        "wrong_drug_rate": sum(1 for row in results if row["wrong_drug"]) / max(1, len(results)),
        "safety_wrong_drug_rate": sum(1 for row in safety_cases if row["wrong_drug"]) / max(1, len(safety_cases)),
        "wrong_type_rate": sum(1 for row in type_cases if row["wrong_type"]) / max(1, len(type_cases)),
        "type_hit_at_k": sum(1 for row in type_cases if row["type_hit_at_k"]) / max(1, len(type_cases)),
        "no_result_rate": sum(1 for row in results if row["no_result"]) / max(1, len(results)),
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": max(latencies) if latencies else 0.0,
        },
        "results": results,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_report(summary: dict[str, Any]) -> str:
    v1 = summary["v1"]
    v2 = summary["v2"]
    open_issues = "\n".join(f"- {issue}" for issue in summary["open_issues"]) or "-"
    regressions = "\n".join(f"- {item}" for item in summary["regressions"]) or "-"
    v2_rows = "\n".join(
        f"| {row['case_id']} | {row['resolution_status']} | {row['hit_at_k']} | {row['type_hit_at_k']} | {row['wrong_drug']} | {row['no_result']} |"
        for row in v2["results"]
    )
    ready = "YES" if summary["status"] in {"PASS", "PASS WITH ISSUES"} else "NO"
    return f"""# Phase 6 Report --- RAG V2 Migration & Evaluation

**Ngày:** {summary['generated_at']}  
**Scope:** standalone offline RAG V2 over `drug_knowledge`; no Agent/API/prescription changes.

## 1. Output đã tạo

- `scripts/data_v2/rag_v2_evaluation.py`
- `data pharmacy/v2/rag_eval/v2_chunks.jsonl`
- `data pharmacy/v2/rag_eval/v2_embedding_index.jsonl`
- `data pharmacy/v2/rag_eval/eval_results.json`
- `data pharmacy/reports/phase6-rag-evaluation-report.md`

## 2. Chunk/Index V2

- V2 chunks: {summary['v2_chunks']}
- V1 chunks compared: {summary['v1_chunks']}
- Rule: one `drug_knowledge` row = one chunk; no cross-knowledge-type merge.
- Each V2 chunk keeps `drug_product_id`, `legacy_drug_id`, `knowledge_type`, and provenance metadata.
- Embedding/index mode: local reproducible TF-IDF hash vectors (`local-tfidf-hash-v1`) stored outside production.

## 3. Metrics

| Metric | V1 | V2 |
|---|---:|---:|
| Eval cases | {v1['cases']} | {v2['cases']} |
| Hit@{TOP_K} | {v1['hit_at_k']:.2%} | {v2['hit_at_k']:.2%} |
| Recall@{TOP_K} | {v1['recall_at_k']:.2%} | {v2['recall_at_k']:.2%} |
| Wrong-drug rate | {v1['wrong_drug_rate']:.2%} | {v2['wrong_drug_rate']:.2%} |
| Safety wrong-drug rate | {v1['safety_wrong_drug_rate']:.2%} | {v2['safety_wrong_drug_rate']:.2%} |
| Wrong-knowledge-type rate | {v1['wrong_type_rate']:.2%} | {v2['wrong_type_rate']:.2%} |
| Type Hit@{TOP_K} | {v1['type_hit_at_k']:.2%} | {v2['type_hit_at_k']:.2%} |
| No-result rate | {v1['no_result_rate']:.2%} | {v2['no_result_rate']:.2%} |
| Latency p50 ms | {v1['latency_ms']['p50']:.4f} | {v2['latency_ms']['p50']:.4f} |
| Latency p95 ms | {v1['latency_ms']['p95']:.4f} | {v2['latency_ms']['p95']:.4f} |

## 4. V2 Eval Rows

| Case | Resolution | Hit@{TOP_K} | Type Hit@{TOP_K} | Wrong Drug | No Result |
|---|---|---:|---:|---:|---:|
{v2_rows}

## 5. Regression

{regressions}

## 6. Open Issues

{open_issues}

## 7. Trạng thái

**{summary['status']}**

V2 demonstrates the intended safety shape: resolve drug first, filter by `drug_product_id`, filter by `knowledge_type` when detected, then vector search. V1 remains untouched for rollback.

## PHASE 6 RESULT

```text
STATUS:
{summary['status']}

EVAL CASES:
{v2['cases']}

V1:
Hit@K: {v1['hit_at_k']:.2%}
Wrong drug: {v1['wrong_drug_rate']:.2%}
Wrong type: {v1['wrong_type_rate']:.2%}
Latency: p50={v1['latency_ms']['p50']:.4f}ms, p95={v1['latency_ms']['p95']:.4f}ms

V2:
Hit@K: {v2['hit_at_k']:.2%}
Wrong drug: {v2['wrong_drug_rate']:.2%}
Wrong type: {v2['wrong_type_rate']:.2%}
Latency: p50={v2['latency_ms']['p50']:.4f}ms, p95={v2['latency_ms']['p95']:.4f}ms

REGRESSION:
{regressions}

OPEN ISSUES:
{open_issues}

READY FOR PHASE 7:
{ready}
```
"""


def run_phase6() -> dict[str, Any]:
    products = read_jsonl(V2_DIR / "drug_product.jsonl")
    mappings = read_jsonl(V2_DIR / "drug_id_map.jsonl")
    knowledge = read_jsonl(V2_DIR / "drug_knowledge.jsonl")
    v1_rows = read_jsonl(DATA_DIR / "_chunks.jsonl")

    product_id_by_legacy = {row["legacy_drug_id"]: row["drug_product_id"] for row in mappings}
    resolver = DrugResolver(products, mappings)
    v2_chunks = build_v2_chunks(knowledge)
    v1_chunks = build_v1_chunks(v1_rows, product_id_by_legacy)
    v2_index = SparseIndex(v2_chunks)
    v1_index = SparseIndex(v1_chunks)
    cases = build_eval_cases()

    v1_eval = evaluate_v1(v1_index, cases)
    v2_eval = evaluate_v2(resolver, v2_index, cases)

    regressions = []
    open_issues = []
    if v2_eval["wrong_drug_rate"] > 0 or v2_eval["safety_wrong_drug_rate"] > 0:
        regressions.append("V2 wrong-drug retrieval detected")
    if v2_eval["hit_at_k"] + 0.05 < v1_eval["hit_at_k"]:
        regressions.append("V2 Hit@K is more than 5 percentage points below V1")
    if v2_eval["wrong_type_rate"] > v1_eval["wrong_type_rate"] + 0.05:
        regressions.append("V2 wrong-knowledge-type rate regressed versus V1")
    if v2_eval["no_result_rate"] > v1_eval["no_result_rate"] + 0.20:
        open_issues.append("V2 no-result rate is materially higher than V1 because ambiguous/nonexistent cases fail closed")
    if v2_eval["latency_ms"]["p95"] > v1_eval["latency_ms"]["p95"] * 3:
        open_issues.append("V2 p95 latency is higher in offline eval due resolver scan; index resolver before runtime use")
    if any(row["expected_resolution"] != "RESOLVED" and row["top_results"] for row in v2_eval["results"]):
        regressions.append("V2 leaked retrieval results for ambiguous/nonexistent case")

    status = "PASS"
    if regressions:
        status = "BLOCKED"
    elif open_issues:
        status = "PASS WITH ISSUES"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        OUTPUT_DIR / "v2_chunks.jsonl",
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
    write_jsonl(OUTPUT_DIR / "v2_embedding_index.jsonl", v2_index.export())

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "v1_chunks": len(v1_chunks),
        "v2_chunks": len(v2_chunks),
        "v1": v1_eval,
        "v2": v2_eval,
        "regressions": regressions,
        "open_issues": open_issues,
        "production_modified": False,
        "legacy_modified": False,
    }
    (OUTPUT_DIR / "eval_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 6 RAG V2 migration/evaluation.")
    parser.parse_args()
    summary = run_phase6()
    print(
        json.dumps(
            {
                "status": summary["status"],
                "eval_cases": summary["v2"]["cases"],
                "v1_hit_at_k": summary["v1"]["hit_at_k"],
                "v2_hit_at_k": summary["v2"]["hit_at_k"],
                "v1_wrong_drug_rate": summary["v1"]["wrong_drug_rate"],
                "v2_wrong_drug_rate": summary["v2"]["wrong_drug_rate"],
                "v1_wrong_type_rate": summary["v1"]["wrong_type_rate"],
                "v2_wrong_type_rate": summary["v2"]["wrong_type_rate"],
                "regressions": summary["regressions"],
                "open_issues": summary["open_issues"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
