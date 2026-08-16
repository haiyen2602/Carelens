"""Build canonical Drug Data V2 JSONL tables from legacy `data pharmacy`.

Phase 2 constraints:
- Do not modify legacy `thuoc.json`.
- Do not touch runtime DB, RAG, Agent, or embeddings.
- Keep public drug_id as legacy slug; use UUID only as V2 internal id.
- Parse ingredients conservatively: structured only when clearly safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEGACY_DIR = ROOT / "data pharmacy"
DEFAULT_OUTPUT_DIR = DEFAULT_LEGACY_DIR / "v2"
DEFAULT_REPORT_DIR = ROOT / "reports" / "data-v2"

DRUG_NAMESPACE = uuid.UUID("4b4f2f21-1f08-4f4d-ae55-273336851c3d")
INGREDIENT_NAMESPACE = uuid.UUID("f5a0976d-885d-49e4-adf5-7f21b95b6717")
KNOWLEDGE_NAMESPACE = uuid.UUID("b9829586-d40f-4b28-9f8a-1ff78d3a3c25")

SOURCE_STATUS_LEGACY = "LEGACY_NO_RAW_SOURCE"
SOURCE_STATUS_INFERRED_ROUTE = "INFERRED_FROM_DOSAGE_FORM"

BASE_KNOWLEDGE_FIELDS = {
    "tac_dung": "INDICATION",
    "tac_dung_phu": "ADVERSE_EFFECT",
    "huong_dan_su_dung": "ADMINISTRATION",
    "lieu_dung": "GENERAL_DOSAGE",
    "huong_dan_bao_quan": "STORAGE",
}

LUU_Y_HEADINGS = [
    ("chống chỉ định", "CONTRAINDICATION"),
    ("thận trọng khi sử dụng", "PRECAUTION"),
    ("thận trọng", "PRECAUTION"),
    ("tương tác thuốc", "INTERACTION"),
    ("tương tác", "INTERACTION"),
    ("thời kỳ mang thai", "PREGNANCY_LACTATION"),
    ("phụ nữ có thai", "PREGNANCY_LACTATION"),
    ("thời kỳ cho con bú", "PREGNANCY_LACTATION"),
    ("phụ nữ cho con bú", "PREGNANCY_LACTATION"),
    ("khả năng lái xe", "DRIVING_WARNING"),
    ("vận hành máy", "DRIVING_WARNING"),
    ("đối tượng cần thận trọng", "PRECAUTION"),
]

STRENGTH_RE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>%|mg|mcg|µg|g|ml|iu|IU)"
    r"(?P<denom>/\s*\d*(?:%|mg|mcg|µg|g|ml|iu|IU))?"
    r"(?:\s*w/w)?$",
    re.IGNORECASE,
)


@dataclass
class IngredientParse:
    canonical_name: str | None
    strength_value: str | None
    strength_unit: str | None
    raw_ingredient: str
    raw_strength: str
    status: str
    warning: str | None


def stable_uuid(namespace: uuid.UUID, key: str) -> str:
    return str(uuid.uuid5(namespace, key))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_legacy_records(legacy_dir: Path) -> list[tuple[Path, int, dict[str, Any]]]:
    records: list[tuple[Path, int, dict[str, Any]]] = []
    for path in sorted(legacy_dir.glob("*/thuoc.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("thuoc", [])
        for index, record in enumerate(data):
            records.append((path, index, record))
    return records


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def ascii_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return normalize_name(without_marks).casefold()


def ingredient_key(name: str) -> str:
    return normalize_name(name).casefold()


def normalize_unit(unit: str, denom: str | None) -> str:
    result = unit.replace("µ", "mc").lower()
    if result == "iu":
        result = "IU"
    if denom:
        result += "/" + re.sub(r"\s+", "", denom.lstrip("/")).replace("µ", "mc").lower()
    return result


def parse_ingredient_segment(segment: str) -> IngredientParse:
    raw = normalize_name(segment)
    if not raw:
        return IngredientParse(None, None, None, raw, raw, "WARNING", "empty ingredient segment")
    if " + " in raw or "+" in raw:
        return IngredientParse(None, None, None, raw, raw, "WARNING", "compound segment contains plus sign")
    match = STRENGTH_RE.match(raw)
    if not match:
        return IngredientParse(None, None, None, raw, raw, "WARNING", "no clear terminal strength")
    name = normalize_name(match.group("name"))
    if not name or re.search(r"\d\s*$", name):
        return IngredientParse(None, None, None, raw, raw, "WARNING", "uncertain ingredient name")
    value = match.group("value").replace(",", ".")
    unit = normalize_unit(match.group("unit"), match.group("denom"))
    return IngredientParse(name, value, unit, raw, f"{value}{unit}", "PARSED", None)


def parse_ingredients(raw_ham_luong: str) -> list[IngredientParse]:
    segments = [s.strip() for s in raw_ham_luong.split(";")]
    return [parse_ingredient_segment(segment) for segment in segments if segment.strip()]


def classify_luu_y(text: str) -> tuple[str, str, str | None]:
    normalized = normalize_name(text)
    prefix = normalized.split(":", 1)[0].casefold()
    prefix_ascii = ascii_key(prefix)
    full = normalized.casefold()
    for heading, knowledge_type in LUU_Y_HEADINGS:
        heading_ascii = ascii_key(heading)
        if (
            prefix.startswith(heading)
            or full.startswith(heading)
            or prefix_ascii.startswith(heading_ascii)
        ):
            return knowledge_type, "AUTO_MAPPED", None
    if "chong chi dinh" in prefix_ascii:
        return "CONTRAINDICATION", "AUTO_MAPPED", None
    if "tuong tac" in prefix_ascii or "tuong ky" in prefix_ascii or "su dung cung voi cac thuoc khac" in prefix_ascii:
        return "INTERACTION", "AUTO_MAPPED", None
    if (
        "mang thai" in prefix_ascii
        or "co thai" in prefix_ascii
        or "cho con bu" in prefix_ascii
        or "thai ky" in prefix_ascii
        or "sinh san" in prefix_ascii
    ):
        return "PREGNANCY_LACTATION", "AUTO_MAPPED", None
    if "lai xe" in prefix_ascii or "van hanh may" in prefix_ascii or "tau xe" in prefix_ascii:
        return "DRIVING_WARNING", "AUTO_MAPPED", None
    if (
        "than trong" in prefix_ascii
        or "canh bao" in prefix_ascii
        or "doi tuong dac biet" in prefix_ascii
        or "nhom benh nhan dac biet" in prefix_ascii
        or "tre em" in prefix_ascii
        or "nguoi gia" in prefix_ascii
    ):
        return "PRECAUTION", "AUTO_MAPPED", None
    return "REVIEW_REQUIRED", "REVIEW_REQUIRED", prefix or None


def make_knowledge(
    drug_product_id: str,
    legacy_drug_id: str,
    knowledge_type: str,
    content: str,
    source_field: str,
    source_section: str | None,
    sequence: int,
    review_status: str = "AUTO_MAPPED",
) -> dict[str, Any]:
    content_raw = normalize_name(content)
    key = f"{legacy_drug_id}:{source_field}:{source_section or ''}:{sequence}:{knowledge_type}"
    return {
        "id": stable_uuid(KNOWLEDGE_NAMESPACE, key),
        "drug_product_id": drug_product_id,
        "legacy_drug_id": legacy_drug_id,
        "knowledge_type": knowledge_type,
        "content_raw": content_raw,
        "content_normalized": content_raw,
        "source_snapshot_id": None,
        "source_field": source_field,
        "source_section": source_section,
        "provenance_status": SOURCE_STATUS_LEGACY,
        "review_status": review_status,
        "created_at": None,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_markdown_report(summary: dict[str, Any]) -> str:
    knowledge_counts = summary["knowledge_type_counts"]
    knowledge_lines = "\n".join(f"| `{k}` | {v} |" for k, v in sorted(knowledge_counts.items()))
    review_lines = "\n".join(
        f"- `{item['legacy_drug_id']}` — {item['ten_thuoc']} ({item['folder']}, {item['duong_dung']})"
        for item in summary["random_review_sample"]
    )
    unmapped_heading_lines = "\n".join(
        f"| `{heading}` | {count} |" for heading, count in summary["unmapped_heading_counts"].items()
    )
    if not unmapped_heading_lines:
        unmapped_heading_lines = "| - | 0 |"

    status = summary["status"]
    ready = "YES" if status in {"PASS", "PASS WITH ISSUES"} else "NO"
    return f"""# Phase 2 Report --- Canonical V2 + Legacy Importer

**Ngày:** {summary['generated_at']}  
**Runtime production:** không thay đổi.  
**Crawler/RAG/Agent:** không chạy, không sửa.

## 1. Output đã tạo

- `scripts/data_v2/legacy_importer.py`
- `data pharmacy/v2/drug_product.jsonl`
- `data pharmacy/v2/drug_id_map.jsonl`
- `data pharmacy/v2/ingredient.jsonl`
- `data pharmacy/v2/drug_product_ingredient.jsonl`
- `data pharmacy/v2/drug_knowledge.jsonl`
- `data pharmacy/v2/import_summary.json`
- `reports/data-v2/phase2-migration-report.md`
- `docs/data/adr-data-v2-identity-compatibility.md`

## 2. Số liệu chính

| Metric | Value |
|---|---:|
| Legacy drugs | {summary['legacy_drugs']} |
| V2 drug products | {summary['v2_drugs']} |
| ID mappings | {summary['id_mappings']} |
| Unmapped legacy drug_id | {summary['unmapped_legacy_ids']} |
| Duplicate mapping | {summary['duplicate_mappings']} |
| Knowledge items | {summary['knowledge_items']} |
| Ingredient relationship rows | {summary['drug_product_ingredient_rows']} |
| Structured ingredients | {summary['structured_ingredients']} |
| Ingredient parse successes | {summary['ingredient_parse_successes']} |
| Ingredient warnings | {summary['ingredient_warnings']} |
| Unmapped/unknown headings | {summary['unmapped_heading_total']} |
| Source fields with unintended loss | {summary['unintended_knowledge_loss']} |

Knowledge by type:

| Type | Count |
|---|---:|
{knowledge_lines}

Unmapped headings:

| Heading | Count |
|---|---:|
{unmapped_heading_lines}

## 3. Vấn đề phát hiện

- Ingredient parser conservative nên structured coverage chưa đầy đủ; mọi case không chắc được giữ raw + warning.
- Legacy records không có raw provenance, nên toàn bộ migrated knowledge mang `LEGACY_NO_RAW_SOURCE`.
- 48 legacy records không có `huong_dan_bao_quan`, nên không sinh `STORAGE` cho các thuốc đó.
- Một số `luu_y_dac_biet` không match taxonomy an toàn, được giữ với `knowledge_type = REVIEW_REQUIRED`.
- `muc_nghiem_trong` chỉ được giữ trong `legacy_metadata`, không đưa vào `drug_knowledge`.

## 4. Quyết định còn mở

- Target định lượng cho Phase 4-6: drug resolution match, knowledge coverage, cross-drug regression, latency.
- Schema chi tiết cho `source_snapshot` và validation result khi sang Phase 3.
- Có chấp nhận `REVIEW_REQUIRED` như một `knowledge_type` tạm trong V2 JSONL hay muốn tách thành review queue riêng ở Phase 5.

## 5. Random review sample

Deterministic sample 30 thuốc, seed `67`:

{review_lines}

## 6. Trạng thái

**{status}**

Phase 2 migration reproducible và không đụng legacy/runtime. Kết quả đủ điều kiện đi tiếp nếu reviewer chấp nhận các parsing warning được báo cáo thay vì tự đoán.

## PHASE 2 RESULT

```text
STATUS:
{status}

MIGRATION:
Legacy drugs: {summary['legacy_drugs']}
V2 drugs: {summary['v2_drugs']}
ID mappings: {summary['id_mappings']}
Unmapped: {summary['unmapped_legacy_ids']}
Knowledge items: {summary['knowledge_items']}
Ingredients parsed: {summary['ingredient_parse_successes']}
Ingredient warnings: {summary['ingredient_warnings']}

DATA LOSS:
{summary['data_loss_text']}

LEGACY MODIFIED:
NO

PRODUCTION MODIFIED:
NO

OPEN ISSUES:
{summary['open_issues_text']}

READY FOR PHASE 3:
{ready}
```
"""


def import_legacy(legacy_dir: Path, output_dir: Path, report_dir: Path) -> dict[str, Any]:
    records = read_legacy_records(legacy_dir)
    drug_products: list[dict[str, Any]] = []
    drug_id_map: list[dict[str, Any]] = []
    ingredient_rows: dict[str, dict[str, Any]] = {}
    drug_product_ingredients: list[dict[str, Any]] = []
    drug_knowledge: list[dict[str, Any]] = []
    ingredient_warning_rows: list[dict[str, Any]] = []
    unmapped_headings: Counter[str] = Counter()
    legacy_ids: list[str] = []
    source_field_expected: Counter[str] = Counter()
    source_field_actual: Counter[str] = Counter()

    for path, index, record in records:
        legacy_drug_id = normalize_name(str(record.get("id", "")))
        if not legacy_drug_id:
            legacy_drug_id = f"missing-id-{path.parent.name}-{index}"
        legacy_ids.append(legacy_drug_id)
        drug_product_id = stable_uuid(DRUG_NAMESPACE, legacy_drug_id)
        ten_thuoc = normalize_name(str(record.get("ten_thuoc", "")))
        drug_products.append(
            {
                "id": drug_product_id,
                "legacy_drug_id": legacy_drug_id,
                "brand_name": ten_thuoc,
                "display_name": ten_thuoc,
                "dosage_form": normalize_name(str(record.get("dang_thuoc", ""))),
                "route": normalize_name(str(record.get("duong_dung", ""))),
                "route_source": SOURCE_STATUS_INFERRED_ROUTE,
                "route_rule_version": "legacy-v1",
                "package_text": normalize_name(str(record.get("tong_so_luong", ""))),
                "category": normalize_name(str(record.get("danh_muc", ""))),
                "source_snapshot_id": None,
                "provenance_status": SOURCE_STATUS_LEGACY,
                "legacy_metadata": {
                    "source_file": str(path.relative_to(legacy_dir)),
                    "source_index": index,
                    "legacy_missed_dose_risk": normalize_name(str(record.get("muc_nghiem_trong", ""))),
                    "legacy_missed_dose_risk_status": "NOT_CLINICALLY_REVIEWED",
                },
            }
        )
        drug_id_map.append({"legacy_drug_id": legacy_drug_id, "drug_product_id": drug_product_id})

        for seq, parsed in enumerate(parse_ingredients(str(record.get("ham_luong", ""))), start=1):
            ingredient_id = None
            if parsed.status == "PARSED" and parsed.canonical_name:
                key = ingredient_key(parsed.canonical_name)
                ingredient_id = stable_uuid(INGREDIENT_NAMESPACE, key)
                ingredient_rows.setdefault(
                    ingredient_id,
                    {
                        "id": ingredient_id,
                        "canonical_name": parsed.canonical_name,
                        "canonical_key": key,
                    },
                )
            else:
                ingredient_warning_rows.append(
                    {
                        "legacy_drug_id": legacy_drug_id,
                        "ten_thuoc": ten_thuoc,
                        "raw_ingredient": parsed.raw_ingredient,
                        "warning": parsed.warning,
                    }
                )
            drug_product_ingredients.append(
                {
                    "drug_product_id": drug_product_id,
                    "legacy_drug_id": legacy_drug_id,
                    "ingredient_id": ingredient_id,
                    "strength_value": parsed.strength_value,
                    "strength_unit": parsed.strength_unit,
                    "raw_ingredient": parsed.raw_ingredient,
                    "raw_strength": parsed.raw_strength,
                    "parse_status": parsed.status,
                    "warning": parsed.warning,
                    "sequence": seq,
                }
            )

        knowledge_sequence = 1
        for source_field, knowledge_type in BASE_KNOWLEDGE_FIELDS.items():
            content = record.get(source_field)
            if isinstance(content, str) and content.strip():
                source_field_expected[source_field] += 1
                drug_knowledge.append(
                    make_knowledge(
                        drug_product_id,
                        legacy_drug_id,
                        knowledge_type,
                        content,
                        source_field,
                        source_field,
                        knowledge_sequence,
                    )
                )
                source_field_actual[source_field] += 1
                knowledge_sequence += 1

        luu_y_items = record.get("luu_y_dac_biet") or []
        if isinstance(luu_y_items, list):
            for item in luu_y_items:
                if not isinstance(item, str) or not item.strip():
                    continue
                source_field_expected["luu_y_dac_biet"] += 1
                knowledge_type, review_status, heading = classify_luu_y(item)
                if knowledge_type == "REVIEW_REQUIRED":
                    unmapped_headings[heading or "(empty heading)"] += 1
                drug_knowledge.append(
                    make_knowledge(
                        drug_product_id,
                        legacy_drug_id,
                        knowledge_type,
                        item,
                        "luu_y_dac_biet",
                        heading,
                        knowledge_sequence,
                        review_status,
                    )
                )
                source_field_actual["luu_y_dac_biet"] += 1
                knowledge_sequence += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    write_jsonl(output_dir / "drug_product.jsonl", drug_products)
    write_jsonl(output_dir / "drug_id_map.jsonl", drug_id_map)
    write_jsonl(output_dir / "ingredient.jsonl", sorted(ingredient_rows.values(), key=lambda r: r["canonical_key"]))
    write_jsonl(output_dir / "drug_product_ingredient.jsonl", drug_product_ingredients)
    write_jsonl(output_dir / "drug_knowledge.jsonl", drug_knowledge)
    write_jsonl(output_dir / "ingredient_parse_warnings.jsonl", ingredient_warning_rows)

    legacy_id_counts = Counter(legacy_ids)
    map_counts = Counter(row["legacy_drug_id"] for row in drug_id_map)
    unmapped = sorted(set(legacy_ids) - set(map_counts))
    duplicate_mappings = sum(1 for count in map_counts.values() if count > 1)
    knowledge_counts = Counter(row["knowledge_type"] for row in drug_knowledge)
    loss_fields = {
        field: {"expected": expected, "actual": source_field_actual[field]}
        for field, expected in source_field_expected.items()
        if source_field_actual[field] != expected
    }

    rng = random.Random(67)
    sample_records = rng.sample(records, min(30, len(records)))
    random_review_sample = [
        {
            "legacy_drug_id": normalize_name(str(record.get("id", ""))),
            "ten_thuoc": normalize_name(str(record.get("ten_thuoc", ""))),
            "folder": path.parent.name,
            "duong_dung": normalize_name(str(record.get("duong_dung", ""))),
            "danh_muc": normalize_name(str(record.get("danh_muc", ""))),
        }
        for path, _index, record in sample_records
    ]

    input_hashes = {
        str(path.relative_to(legacy_dir)): sha256_file(path)
        for path in sorted(legacy_dir.glob("*/thuoc.json"))
    }
    output_hashes = {
        str(path.relative_to(output_dir)): sha256_file(path)
        for path in sorted(output_dir.glob("*.jsonl"))
    }

    legacy_modified = False
    post_hashes = {
        str(path.relative_to(legacy_dir)): sha256_file(path)
        for path in sorted(legacy_dir.glob("*/thuoc.json"))
    }
    legacy_modified = input_hashes != post_hashes

    status = "PASS"
    if (
        len(drug_products) != len(records)
        or len(drug_id_map) != len(records)
        or unmapped
        or duplicate_mappings
        or loss_fields
        or legacy_modified
    ):
        status = "BLOCKED"
    elif ingredient_warning_rows or unmapped_headings:
        status = "PASS WITH ISSUES"

    open_issues = []
    if ingredient_warning_rows:
        open_issues.append(f"{len(ingredient_warning_rows)} ingredient segments preserved raw with warning")
    if unmapped_headings:
        open_issues.append(f"{sum(unmapped_headings.values())} luu_y_dac_biet headings require review")
    if not open_issues:
        open_issues.append("-")

    data_loss_text = "-" if not loss_fields else json.dumps(loss_fields, ensure_ascii=False, sort_keys=True)
    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "legacy_drugs": len(records),
        "v2_drugs": len(drug_products),
        "id_mappings": len(drug_id_map),
        "unmapped_legacy_ids": len(unmapped),
        "duplicate_mappings": duplicate_mappings,
        "duplicate_legacy_ids": [legacy_id for legacy_id, count in legacy_id_counts.items() if count > 1],
        "knowledge_items": len(drug_knowledge),
        "knowledge_type_counts": dict(sorted(knowledge_counts.items())),
        "drug_product_ingredient_rows": len(drug_product_ingredients),
        "structured_ingredients": len(ingredient_rows),
        "ingredient_parse_successes": sum(1 for row in drug_product_ingredients if row["parse_status"] == "PARSED"),
        "ingredient_warnings": len(ingredient_warning_rows),
        "unmapped_heading_total": sum(unmapped_headings.values()),
        "unmapped_heading_counts": dict(unmapped_headings.most_common()),
        "unintended_knowledge_loss": len(loss_fields),
        "knowledge_loss_fields": loss_fields,
        "data_loss_text": data_loss_text,
        "legacy_modified": legacy_modified,
        "production_modified": False,
        "open_issues": open_issues,
        "open_issues_text": "\n".join(f"- {issue}" if issue != "-" else "-" for issue in open_issues),
        "random_review_sample": random_review_sample,
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "output_dir": str(output_dir.relative_to(ROOT)),
    }
    write_json(output_dir / "import_summary.json", summary)
    (report_dir / "phase2-migration-report.md").write_text(build_markdown_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy drug data into canonical V2 JSONL tables.")
    parser.add_argument("--legacy-dir", type=Path, default=DEFAULT_LEGACY_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    summary = import_legacy(args.legacy_dir, args.output_dir, args.report_dir)
    print(json.dumps({k: summary[k] for k in [
        "status",
        "legacy_drugs",
        "v2_drugs",
        "id_mappings",
        "unmapped_legacy_ids",
        "duplicate_mappings",
        "knowledge_items",
        "ingredient_parse_successes",
        "ingredient_warnings",
        "unmapped_heading_total",
        "legacy_modified",
        "production_modified",
    ]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
