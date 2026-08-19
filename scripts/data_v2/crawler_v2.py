"""Crawler V2 for Long Chau product pages.

Phase 3 scope:
- Fetch a small pilot sample, not the full 3,562 legacy corpus.
- Persist RAW SNAPSHOT before parsing.
- Parse raw snapshot into canonical V2 JSONL rows.
- Validate and compare Legacy V1 vs migrated V2 vs fresh crawled V2.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import sys
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from legacy_importer import (
    BASE_KNOWLEDGE_FIELDS,
    DRUG_NAMESPACE,
    INGREDIENT_NAMESPACE,
    KNOWLEDGE_NAMESPACE,
    classify_luu_y,
    ingredient_key,
    normalize_name,
    parse_ingredients,
    stable_uuid,
)


ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT / "data pharmacy"
V2_DIR = LEGACY_DIR / "v2"
RAW_DIR = V2_DIR / "raw_snapshots" / "longchau"
PILOT_DIR = V2_DIR / "fresh_crawl_pilot"
REPORT_PATH = LEGACY_DIR / "reports" / "phase3-crawler-v2-report.md"

BASE_URL = "https://nhathuoclongchau.com.vn"
PARSER_VERSION = "longchau-v2.1.0"
SOURCE_NAME = "nhathuoclongchau"
SOURCE_STATUS_CAPTURED = "SOURCE_CAPTURED"
SOURCE_STATUS_INFERRED_ROUTE = "INFERRED_FROM_DOSAGE_FORM"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

DEFAULT_CATEGORY_URLS = [
    "https://nhathuoclongchau.com.vn/thuoc/thuoc-da-lieu",
    "https://nhathuoclongchau.com.vn/thuoc/thuoc-bo-and-vitamin",
    "https://nhathuoclongchau.com.vn/thuoc/thuoc-khang-sinh-khang-nam",
    "https://nhathuoclongchau.com.vn/thuoc/thuoc-tim-mach-and-mau",
]

NEXT_DATA_RE = re.compile(
    r"<script[^>]+id=[\"']__NEXT_DATA__[\"'][^>]*>(?P<json>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

ROUTE_KEYWORDS: list[tuple[str, str]] = [
    ("truyen", "Tiêm truyền"),
    ("tiem", "Tiêm"),
    ("tra mat", "Nhỏ mắt"),
    ("nho mat", "Nhỏ mắt"),
    ("nho mui", "Nhỏ mũi"),
    ("nho tai", "Nhỏ tai"),
    ("dat truc trang", "Đặt"),
    ("dat am dao", "Đặt"),
    ("dat hau mon", "Đặt"),
    ("thuoc dat", "Đặt"),
    ("xit", "Xịt"),
    ("ngam", "Ngậm"),
    ("mieng dan", "Dán ngoài da"),
    ("cao dan", "Dán ngoài da"),
    ("dung ngoai", "Bôi ngoài da"),
    ("mo", "Bôi ngoài da"),
    ("kem", "Bôi ngoài da"),
    ("gel", "Bôi ngoài da"),
    ("boi", "Bôi ngoài da"),
]
ORAL_KEYWORDS = ("vien", "uong", "siro", "com", "hoan")

# A dosage form can be ambiguous (for example, a gel, emulsion, solution, or
# powder). Route is only upgraded from the source dosage instructions when the
# source explicitly names a route. The fallback form rules remain for existing
# unambiguous forms and deliberately leave ambiguous ones blank.
EXPLICIT_ROUTE_PATTERNS: list[tuple[str, str]] = [
    ("tiem truyen", "Ti\u00eam truy\u1ec1n"),
    ("truyen tinh mach", "Ti\u00eam truy\u1ec1n"),
    ("duong truyen", "Ti\u00eam truy\u1ec1n"),
    ("nho mat", "Nh\u1ecf m\u1eaft"),
    ("tra mat", "Nh\u1ecf m\u1eaft"),
    ("nho mui", "Nh\u1ecf m\u0169i"),
    ("nho tai", "Nh\u1ecf tai"),
    ("dat truc trang", "\u0110\u1eb7t"),
    ("dat hau mon", "\u0110\u1eb7t"),
    ("dat am dao", "\u0110\u1eb7t"),
    ("dung ngoai da", "B\u00f4i ngo\u00e0i da"),
    ("boi ngoai da", "B\u00f4i ngo\u00e0i da"),
    ("thoa len da", "B\u00f4i ngo\u00e0i da"),
    ("xoa len da", "B\u00f4i ngo\u00e0i da"),
    ("boi len da", "B\u00f4i ngo\u00e0i da"),
    ("boi len vung", "B\u00f4i ngo\u00e0i da"),
    ("boi thuoc", "B\u00f4i ngo\u00e0i da"),
    ("thoa thuoc", "B\u00f4i ngo\u00e0i da"),
    ("thoa mot luong", "B\u00f4i ngo\u00e0i da"),
    ("xoa nhe", "B\u00f4i ngo\u00e0i da"),
    ("dung tai cho", "B\u00f4i ngo\u00e0i da"),
    ("chi dung ben ngoai", "B\u00f4i ngo\u00e0i da"),
    ("dung ngoai", "B\u00f4i ngo\u00e0i da"),
    ("goi dau", "B\u00f4i ngo\u00e0i da"),
    ("duong uong", "U\u1ed1ng"),
    ("dung bang duong uong", "U\u1ed1ng"),
    ("duong tiem", "Ti\u00eam"),
    ("tiem bap", "Ti\u00eam"),
    ("tiem duoi da", "Ti\u00eam"),
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return normalize_name(" ".join(self.parts))


class SectionExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sections: dict[str, str] = {}
        self.current_heading: str | None = None
        self.current_parts: list[str] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"h2", "h3", "h4"}:
            self._flush()
            self._heading_tag = tag.lower()
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._heading_tag and tag.lower() == self._heading_tag:
            self.current_heading = normalize_name(" ".join(self._heading_parts))
            self.current_parts = []
            self._heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._heading_tag:
            self._heading_parts.append(text)
        elif self.current_heading:
            self.current_parts.append(text)

    def _flush(self) -> None:
        if self.current_heading:
            text = normalize_name(" ".join(self.current_parts))
            if text:
                self.sections[self.current_heading] = text

    def close(self) -> None:
        super().close()
        self._flush()


def strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    ascii_text = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", ascii_text)


def slugify(text: str) -> str:
    text = strip_diacritics(text or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def normalize_product_name(name: str) -> str:
    words = name.split()
    out = []
    for word in words:
        if any(ch.isdigit() for ch in word):
            out.append(word.lower())
        elif word.isalpha() and word.isupper() and len(word) <= 4:
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


def strip_html(fragment: str) -> str:
    if not fragment:
        return ""
    parser = TextExtractor()
    parser.feed(fragment)
    parser.close()
    return parser.text()


def html_fragment_to_sections(fragment: str) -> dict[str, str]:
    if not fragment:
        return {}
    parser = SectionExtractor()
    parser.feed(fragment)
    parser.close()
    return parser.sections


def find_section(sections: dict[str, str], *keywords: str) -> str:
    for heading, text in sections.items():
        norm = strip_diacritics(heading).lower()
        if any(keyword in norm for keyword in keywords):
            return text
    return ""


def classify_duong_dung(dang_thuoc: str, dosage_source: str = "") -> str:
    normalized = strip_diacritics(dang_thuoc or "").lower()
    is_ambiguous_emulsion = "nhu tuong" in normalized
    for keyword, route in ROUTE_KEYWORDS:
        if is_ambiguous_emulsion and route == "Bôi ngoài da":
            continue
        if re.search(r"\b" + re.escape(keyword) + r"\b", normalized):
            return route
    for keyword in ORAL_KEYWORDS:
        if re.search(r"\b" + re.escape(keyword) + r"\b", normalized):
            return "Uống"
    dosage_normalized = strip_diacritics(strip_html(dosage_source)).lower()
    for pattern, route in EXPLICIT_ROUTE_PATTERNS:
        if re.search(r"\b" + re.escape(pattern) + r"\b", dosage_normalized):
            return route
    return ""


def format_ingredient(ingredients: list[dict[str, Any]] | None) -> str:
    parts = []
    for item in ingredients or []:
        name = normalize_name(str(item.get("name") or ""))
        amount = normalize_name(str(item.get("shortDescription") or ""))
        if not name or "ta duoc" in strip_diacritics(name).lower() or "excipient" in name.lower():
            continue
        parts.append(f"{name} {amount}".strip())
    return "; ".join(parts)


def extract_next_data(html_text: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html_text)
    if not match:
        raise RuntimeError("missing __NEXT_DATA__ script")
    return json.loads(html.unescape(match.group("json")))


def fetch_next_data(session: requests.Session, url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    response = session.get(url, timeout=25)
    response.raise_for_status()
    next_data = extract_next_data(response.text)
    raw_payload = json.dumps(next_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest().upper()
    metadata = {
        "source": SOURCE_NAME,
        "source_url": response.url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "http_status": response.status_code,
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
    }
    return next_data, metadata


def discover_product_urls(session: requests.Session, category_urls: list[str], per_category: int) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for category_url in category_urls:
        next_data, _metadata = fetch_next_data(session, category_url)
        view_data = next_data.get("props", {}).get("pageProps", {}).get("viewData", {})
        for product in (view_data.get("products") or [])[:per_category]:
            slug = product.get("slug")
            if not slug:
                continue
            url = urljoin(BASE_URL, "/" + slug.lstrip("/"))
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def extract_legacy_like_fields(next_data: dict[str, Any]) -> dict[str, Any]:
    page_props = next_data.get("props", {}).get("pageProps", {})
    product = page_props.get("product") or {}
    content = page_props.get("content") or {}
    breadcrumbs = page_props.get("breadcrumbs") or []

    raw_name = product.get("name") or product.get("webName") or ""
    ten_thuoc = normalize_product_name(raw_name)

    dosage_html = content.get("dosage") or product.get("dosage") or ""
    dosage_sections = html_fragment_to_sections(dosage_html)
    huong_dan_su_dung = find_section(dosage_sections, "cach dung")
    lieu_dung = find_section(dosage_sections, "lieu dung")
    if not huong_dan_su_dung and not lieu_dung and not dosage_sections:
        huong_dan_su_dung = strip_html(dosage_html)

    usage_html = content.get("usage") or product.get("usage") or ""
    usage_sections = html_fragment_to_sections(usage_html)
    tac_dung = find_section(usage_sections, "chi dinh")
    if not tac_dung and not usage_sections:
        tac_dung = strip_html(usage_html)

    careful_sections = html_fragment_to_sections(content.get("careful") or "")
    luu_y_dac_biet = [f"{heading}: {text}" for heading, text in careful_sections.items()]
    for warning in product.get("warning") or []:
        if warning:
            luu_y_dac_biet.append(f"Đối tượng cần thận trọng: {warning}")

    categories = product.get("categories") or []
    if categories:
        danh_muc = categories[-1].get("name", "")
    elif breadcrumbs:
        danh_muc = breadcrumbs[-1].get("name", "")
    else:
        danh_muc = ""

    dang_thuoc = product.get("dosageForm") or ""
    return {
        "ten_thuoc": ten_thuoc,
        "ham_luong": format_ingredient(product.get("ingredient")),
        "dang_thuoc": dang_thuoc,
        "tong_so_luong": product.get("specification") or "",
        "tac_dung": tac_dung,
        "tac_dung_phu": strip_html(content.get("adverseEffect") or product.get("adverseEffect") or ""),
        "huong_dan_su_dung": huong_dan_su_dung,
        "lieu_dung": lieu_dung,
        "duong_dung": classify_duong_dung(dang_thuoc, dosage_html),
        "thoi_diem_dung": "",
        "huong_dan_bao_quan": strip_html(content.get("preservation") or ""),
        "luu_y_dac_biet": luu_y_dac_biet,
        "id": slugify(product.get("name") or ten_thuoc),
        "danh_muc": danh_muc,
    }


def snapshot_id_for(metadata: dict[str, Any]) -> str:
    key = f"{metadata['source']}:{metadata['source_url']}:{metadata['content_hash']}"
    return str(uuid.uuid5(uuid.UUID("78e80c96-2070-4b87-8b3b-84bb4a9a52bb"), key))


def make_knowledge(
    drug_product_id: str,
    legacy_drug_id: str,
    snapshot_id: str,
    knowledge_type: str,
    content: str,
    source_field: str,
    source_section: str | None,
    sequence: int,
    review_status: str = "AUTO_MAPPED",
) -> dict[str, Any]:
    content_raw = normalize_name(content)
    key = f"{legacy_drug_id}:{snapshot_id}:{source_field}:{source_section or ''}:{sequence}:{knowledge_type}"
    return {
        "id": stable_uuid(KNOWLEDGE_NAMESPACE, key),
        "drug_product_id": drug_product_id,
        "legacy_drug_id": legacy_drug_id,
        "knowledge_type": knowledge_type,
        "content_raw": content_raw,
        "content_normalized": content_raw,
        "source_snapshot_id": snapshot_id,
        "source_field": source_field,
        "source_section": source_section,
        "provenance_status": SOURCE_STATUS_CAPTURED,
        "review_status": review_status,
        "created_at": None,
    }


def canonicalize_fresh(record: dict[str, Any], snapshot_id: str) -> dict[str, list[dict[str, Any]]]:
    legacy_drug_id = normalize_name(str(record.get("id") or ""))
    drug_product_id = stable_uuid(DRUG_NAMESPACE, legacy_drug_id)
    product = {
        "id": drug_product_id,
        "legacy_drug_id": legacy_drug_id,
        "brand_name": normalize_name(str(record.get("ten_thuoc") or "")),
        "display_name": normalize_name(str(record.get("ten_thuoc") or "")),
        "dosage_form": normalize_name(str(record.get("dang_thuoc") or "")),
        "route": normalize_name(str(record.get("duong_dung") or "")),
        "route_source": SOURCE_STATUS_INFERRED_ROUTE,
        "route_rule_version": PARSER_VERSION,
        "package_text": normalize_name(str(record.get("tong_so_luong") or "")),
        "category": normalize_name(str(record.get("danh_muc") or "")),
        "source_snapshot_id": snapshot_id,
        "provenance_status": SOURCE_STATUS_CAPTURED,
        "legacy_metadata": {},
    }
    ingredients = []
    ingredient_refs = []
    ingredient_warnings = []
    for seq, parsed in enumerate(parse_ingredients(str(record.get("ham_luong") or "")), start=1):
        ingredient_id = None
        if parsed.status == "PARSED" and parsed.canonical_name:
            key = ingredient_key(parsed.canonical_name)
            ingredient_id = stable_uuid(INGREDIENT_NAMESPACE, key)
            ingredients.append({"id": ingredient_id, "canonical_name": parsed.canonical_name, "canonical_key": key})
        else:
            ingredient_warnings.append(
                {
                    "legacy_drug_id": legacy_drug_id,
                    "raw_ingredient": parsed.raw_ingredient,
                    "warning": parsed.warning,
                }
            )
        ingredient_refs.append(
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

    knowledge = []
    sequence = 1
    for field, knowledge_type in BASE_KNOWLEDGE_FIELDS.items():
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            knowledge.append(make_knowledge(drug_product_id, legacy_drug_id, snapshot_id, knowledge_type, value, field, field, sequence))
            sequence += 1
    for item in record.get("luu_y_dac_biet") or []:
        if not isinstance(item, str) or not item.strip():
            continue
        knowledge_type, review_status, heading = classify_luu_y(item)
        knowledge.append(
            make_knowledge(
                drug_product_id,
                legacy_drug_id,
                snapshot_id,
                knowledge_type,
                item,
                "luu_y_dac_biet",
                heading,
                sequence,
                review_status,
            )
        )
        sequence += 1
    return {
        "drug_product": [product],
        "ingredient": ingredients,
        "drug_product_ingredient": ingredient_refs,
        "drug_knowledge": knowledge,
        "ingredient_warnings": ingredient_warnings,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_jsonl_by_key(path: Path, key: str) -> dict[str, dict[str, Any]]:
    result = {}
    if not path.exists():
        return result
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                result[row[key]] = row
    return result


def load_legacy_records() -> dict[str, dict[str, Any]]:
    records = {}
    for path in sorted(LEGACY_DIR.glob("*/thuoc.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data:
            records[record.get("id", "")] = record
    return records


def compare_field(a: Any, b: Any) -> str:
    if isinstance(a, list):
        a_norm = [normalize_name(str(x)) for x in a]
    else:
        a_norm = normalize_name(str(a or ""))
    if isinstance(b, list):
        b_norm = [normalize_name(str(x)) for x in b]
    else:
        b_norm = normalize_name(str(b or ""))
    if a_norm == b_norm:
        return "exact"
    if not a_norm or not b_norm:
        return "missing_one_side"
    return "different"


def validate_snapshot(metadata: dict[str, Any], snapshot_path: Path) -> list[str]:
    errors = []
    for field in ("source_url", "retrieved_at", "content_hash", "parser_version"):
        if not metadata.get(field):
            errors.append(f"missing {field}")
    if not snapshot_path.exists():
        errors.append("missing raw snapshot file")
    return errors


def validate_canonical(record: dict[str, Any], canonical: dict[str, list[dict[str, Any]]]) -> list[str]:
    errors = []
    if not canonical["drug_product"]:
        errors.append("missing drug_product")
    expected_fields = [field for field in BASE_KNOWLEDGE_FIELDS if isinstance(record.get(field), str) and record.get(field).strip()]
    knowledge_fields = Counter(row["source_field"] for row in canonical["drug_knowledge"])
    for field in expected_fields:
        if knowledge_fields[field] < 1:
            errors.append(f"knowledge lost for {field}")
    if record.get("thoi_diem_dung"):
        errors.append("thoi_diem_dung should not enter canonical drug data")
    return errors


def build_report(summary: dict[str, Any]) -> str:
    field_lines = "\n".join(
        f"| `{field}` | {counts.get('exact', 0)} | {counts.get('different', 0)} | {counts.get('missing_one_side', 0)} |"
        for field, counts in summary["legacy_vs_fresh_field_comparison"].items()
    )
    category_lines = "\n".join(f"| `{url}` | {count} |" for url, count in summary["category_url_counts"].items())
    issue_lines = "\n".join(f"- {issue}" for issue in summary["open_issues"]) if summary["open_issues"] else "-"
    return f"""# Phase 3 Report --- Crawler V2 Raw Snapshot Pilot

**Ngày:** {summary['generated_at']}  
**Scope:** Crawler V2 pilot only, no full-corpus crawl.  
**Legacy/runtime:** not modified.

## 1. Output đã tạo

- `scripts/data_v2/crawler_v2.py`
- `data pharmacy/v2/raw_snapshots/longchau/*.json`
- `data pharmacy/v2/source_snapshot.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/drug_product.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/drug_knowledge.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/drug_product_ingredient.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/validation.jsonl`
- `data pharmacy/reports/phase3-crawler-v2-report.md`

## 2. Số liệu chính

| Metric | Value |
|---|---:|
| Category URLs used | {len(summary['category_url_counts'])} |
| Product URLs discovered | {summary['product_urls_discovered']} |
| Product URLs fetched | {summary['product_urls_fetched']} |
| Raw snapshots written | {summary['raw_snapshots_written']} |
| Source metadata rows | {summary['source_metadata_rows']} |
| Fresh V2 drug products | {summary['fresh_v2_drugs']} |
| Fresh V2 knowledge items | {summary['fresh_v2_knowledge_items']} |
| Validation PASS | {summary['validation_pass']} |
| Validation WARNING | {summary['validation_warning']} |
| Validation FAIL | {summary['validation_fail']} |
| Matched Legacy V1 by `drug_id` | {summary['matched_legacy_v1']} |
| Matched Migrated V2 by `drug_id` | {summary['matched_migrated_v2']} |
| Knowledge lost from parsed fields | {summary['knowledge_loss']} |

Category sample:

| Category URL | Detail URLs |
|---|---:|
{category_lines}

Legacy V1 vs Fresh Crawled V2 field comparison:

| Field | Exact | Different | Missing one side |
|---|---:|---:|---:|
{field_lines}

## 3. Vấn đề phát hiện

{issue_lines}

## 4. Quyết định còn mở

- Chốt raw snapshot retention convention: giữ trong repo demo hay chuyển sang ignored artifact khi raw tăng lớn.
- Chốt target Phase 4 shadow comparison: field exact match có cần đạt ngưỡng nào hay chỉ dùng để phát hiện drift.
- Chốt có cho phép Crawler V2 dùng category SSR để discover pilot URL hay Phase 3 production chỉ nhận explicit product URL.

## 5. Trạng thái

**{summary['status']}**

Phase 3 chứng minh được pipeline mới: fetch URL → ghi raw snapshot có timestamp/hash/parser version → parse → sinh Canonical V2 → validation → so sánh với V1/V2 migrated, không crawl toàn bộ corpus.
"""


def run_pilot(args: argparse.Namespace) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    if args.urls_file:
        urls = [line.strip() for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines() if line.strip()]
        category_counts: dict[str, int] = {"explicit_urls_file": len(urls)}
    else:
        category_urls = args.category_url or DEFAULT_CATEGORY_URLS
        urls = discover_product_urls(session, category_urls, args.per_category)
        category_counts = {url: 0 for url in category_urls}
        for index, _url in enumerate(urls):
            bucket = category_urls[min(index // args.per_category, len(category_urls) - 1)]
            category_counts[bucket] += 1
    urls = urls[: args.limit]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    legacy_records = load_legacy_records()
    migrated_products = load_jsonl_by_key(V2_DIR / "drug_product.jsonl", "legacy_drug_id")

    source_snapshots = []
    fresh_products = []
    fresh_ingredients = {}
    fresh_refs = []
    fresh_knowledge = []
    ingredient_warnings = []
    validations = []
    field_comparison: dict[str, Counter[str]] = defaultdict(Counter)
    validation_counts = Counter()
    matched_legacy = 0
    matched_migrated = 0
    knowledge_loss = 0
    open_issues = []

    fields_to_compare = [
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
    ]

    for position, url in enumerate(urls, start=1):
        next_data, metadata = fetch_next_data(session, url)
        snapshot_id = snapshot_id_for(metadata)
        metadata["id"] = snapshot_id
        snapshot_path = RAW_DIR / f"{snapshot_id}.json"
        snapshot = {**metadata, "raw_next_data": next_data}
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        record = extract_legacy_like_fields(next_data)
        canonical = canonicalize_fresh(record, snapshot_id)
        legacy_id = record.get("id", "")
        source_snapshots.append({k: metadata[k] for k in ("id", "source", "source_url", "retrieved_at", "http_status", "content_hash", "parser_version")})
        fresh_products.extend(canonical["drug_product"])
        for ingredient in canonical["ingredient"]:
            fresh_ingredients[ingredient["id"]] = ingredient
        fresh_refs.extend(canonical["drug_product_ingredient"])
        fresh_knowledge.extend(canonical["drug_knowledge"])
        ingredient_warnings.extend(canonical["ingredient_warnings"])

        errors = validate_snapshot(metadata, snapshot_path) + validate_canonical(record, canonical)
        status = "PASS" if not errors else "FAIL"
        if status == "FAIL":
            knowledge_loss += sum(1 for err in errors if err.startswith("knowledge lost"))
        if canonical["ingredient_warnings"] and status == "PASS":
            status = "WARNING"
        validation_counts[status] += 1
        validations.append(
            {
                "source_url": url,
                "snapshot_id": snapshot_id,
                "legacy_drug_id": legacy_id,
                "status": status,
                "errors": errors,
                "ingredient_warnings": canonical["ingredient_warnings"],
            }
        )

        legacy = legacy_records.get(legacy_id)
        if legacy:
            matched_legacy += 1
            for field in fields_to_compare:
                field_comparison[field][compare_field(legacy.get(field), record.get(field))] += 1
        else:
            open_issues.append(f"Fresh drug_id `{legacy_id}` not found in Legacy V1")

        if legacy_id in migrated_products:
            matched_migrated += 1
        else:
            open_issues.append(f"Fresh drug_id `{legacy_id}` not found in migrated V2")

        if args.delay_seconds and position < len(urls):
            time.sleep(args.delay_seconds)

    write_jsonl(V2_DIR / "source_snapshot.jsonl", source_snapshots)
    write_jsonl(PILOT_DIR / "drug_product.jsonl", fresh_products)
    write_jsonl(PILOT_DIR / "ingredient.jsonl", sorted(fresh_ingredients.values(), key=lambda row: row["canonical_key"]))
    write_jsonl(PILOT_DIR / "drug_product_ingredient.jsonl", fresh_refs)
    write_jsonl(PILOT_DIR / "drug_knowledge.jsonl", fresh_knowledge)
    write_jsonl(PILOT_DIR / "ingredient_parse_warnings.jsonl", ingredient_warnings)
    write_jsonl(PILOT_DIR / "validation.jsonl", validations)

    status = "PASS"
    if validation_counts["FAIL"] or not urls:
        status = "BLOCKED"
    elif validation_counts["WARNING"] or matched_legacy < len(urls) or matched_migrated < len(urls):
        status = "PASS WITH ISSUES"

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "category_url_counts": category_counts,
        "product_urls_discovered": len(urls),
        "product_urls_fetched": len(source_snapshots),
        "raw_snapshots_written": len(list(RAW_DIR.glob("*.json"))),
        "source_metadata_rows": len(source_snapshots),
        "fresh_v2_drugs": len(fresh_products),
        "fresh_v2_knowledge_items": len(fresh_knowledge),
        "validation_pass": validation_counts["PASS"],
        "validation_warning": validation_counts["WARNING"],
        "validation_fail": validation_counts["FAIL"],
        "matched_legacy_v1": matched_legacy,
        "matched_migrated_v2": matched_migrated,
        "knowledge_loss": knowledge_loss,
        "legacy_vs_fresh_field_comparison": {field: dict(counts) for field, counts in field_comparison.items()},
        "open_issues": sorted(set(open_issues)),
    }
    (PILOT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Crawler V2 pilot with raw snapshots and canonical output.")
    parser.add_argument("--limit", type=int, default=48)
    parser.add_argument("--per-category", type=int, default=12)
    parser.add_argument("--category-url", action="append")
    parser.add_argument("--urls-file")
    parser.add_argument("--delay-seconds", type=float, default=0.2)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    summary = run_pilot(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
