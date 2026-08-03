#!/usr/bin/env python3
"""Map free-text drug notes into per-category JSON arrays under `data pharmacy/`.

Zero dependencies, zero API cost. Cau truc:

    data pharmacy/
      <Ten nhom thuoc>/
        raw.md      <- noi dan noi dung tho, nhieu thuoc cach nhau boi dong `---`
        thuoc.json  <- ket qua sau khi map, la 1 JSON array cac thuoc trong nhom

Workflow:

1. Trong moi thu muc nhom thuoc, go/dan thong tin vao `raw.md` (hoac `raw.txt`),
   moi thuoc 1 khoi, dung tieu de tieng Viet nhu "Ten thuoc:", "Lieu dung:", ...
   (xem `data pharmacy/Thuoc cam lanh, ho/raw.md` lam vi du). Header khong phan
   biet hoa/thuong hay co dau/khong dau. Giua 2 thuoc, chen 1 dong rieng gom
   3 dau `-` tro len: `---`.
2. Run: python scripts/map_drug_data.py
3. Script quet moi thu muc con cua `data pharmacy/` co chua raw.md/raw.txt,
   map tung khoi thanh 1 object theo schema.json (tu dong them "id" va
   "danh_muc"), ghi ca nhom ra `<thu muc>/thuoc.json`, va bao cao truong nao
   thieu hoac header nao khong nhan dien duoc.

Ban cung co the bo qua raw.md va sua thang thuoc.json bang tay - chay lai
script voi --validate-only de kiem tra thieu truong bat buoc.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data pharmacy"
SCHEMA_PATH = DATA_DIR / "schema.json"
RAW_FILENAMES = ("raw.md", "raw.txt")
OUTPUT_FILENAME = "thuoc.json"

# header text (khong dau, thuong) -> ten field.
# Them synonym vao day neu script bao "khong nhan dien".
HEADER_SYNONYMS: dict[str, str] = {
    "ten thuoc": "ten_thuoc",
    "biet duoc": "ten_thuoc",
    "ham luong": "ham_luong",
    "nong do": "ham_luong",
    "dang thuoc": "dang_thuoc",
    "dang bao che": "dang_thuoc",
    "tong so luong": "tong_so_luong",
    "so luong": "tong_so_luong",
    "so luong thuoc": "tong_so_luong",
    "tong so luong thuoc": "tong_so_luong",
    "huong dan su dung": "huong_dan_su_dung",
    "cach dung": "huong_dan_su_dung",
    "lieu dung": "lieu_dung",
    "lieu luong": "lieu_dung",
    "duong dung": "duong_dung",
    "duong su dung": "duong_dung",
    "thoi diem dung": "thoi_diem_dung",
    "thoi gian dung": "thoi_diem_dung",
    "khi nao dung": "thoi_diem_dung",
    "luu y dac biet": "luu_y_dac_biet",
    "luu y": "luu_y_dac_biet",
    "than trong": "luu_y_dac_biet",
    "canh bao": "luu_y_dac_biet",
}

ARRAY_FIELDS = {"luu_y_dac_biet"}

HEADER_LINE_RE = re.compile(r"^([^:\n]{2,60}):\s*(.*)$")
BULLET_RE = re.compile(r"^[-•*]\s*")
BLOCK_SEP_RE = re.compile(r"(?m)^-{3,}\s*$")


def strip_diacritics(text: str) -> str:
    # "d" (U+0111) khong co dang NFD phan ra "d" + dau, phai thay tay truoc.
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def normalize_header(text: str) -> str:
    return strip_diacritics(text).lower().strip()


NORMALIZED_SYNONYMS = {normalize_header(k): v for k, v in HEADER_SYNONYMS.items()}


def blank_record() -> dict:
    return {
        "ten_thuoc": "",
        "ham_luong": "",
        "dang_thuoc": "",
        "tong_so_luong": "",
        "huong_dan_su_dung": "",
        "lieu_dung": "",
        "duong_dung": "",
        "thoi_diem_dung": "",
        "luu_y_dac_biet": [],
    }


def flush_section(data: dict, field: str | None, lines: list[str]) -> None:
    if field is None:
        return
    if field in ARRAY_FIELDS:
        items = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            items.append(BULLET_RE.sub("", line).strip())
        data[field] = items
        return
    data[field] = " ".join(l.strip() for l in lines if l.strip())


def parse_block(text: str) -> tuple[dict, list[str], list[str]]:
    """Parse 1 khoi van ban (1 thuoc). Return (record, unmapped_headers, orphan_lines).

    orphan_lines la cac dong xuat hien TRUOC khi gap tieu de hop le dau tien
    trong khoi - khong co field nao de gan vao, nen khong duoc am tham bo qua
    ma phai bao cho nguoi dung biet (tranh mat du lieu ma khong hay).
    """
    data = blank_record()
    unmapped: list[str] = []
    orphan_lines: list[str] = []
    current_field: str | None = None
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        is_bullet = bool(BULLET_RE.match(stripped))
        m = None if is_bullet else HEADER_LINE_RE.match(stripped)

        if m:
            header_text, inline = m.group(1), m.group(2)
            norm = normalize_header(header_text)
            if norm in NORMALIZED_SYNONYMS:
                flush_section(data, current_field, current_lines)
                current_field = NORMALIZED_SYNONYMS[norm]
                current_lines = [inline] if inline.strip() else []
                continue
            if len(header_text.split()) <= 6:
                unmapped.append(stripped)

        if current_field is not None:
            current_lines.append(stripped)
        else:
            orphan_lines.append(stripped)

    flush_section(data, current_field, current_lines)
    return data, unmapped, orphan_lines


def slugify(text: str, fallback: str) -> str:
    text = strip_diacritics(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def load_schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def validate_record(data: dict, schema: dict) -> list[str]:
    errors = []
    for field in schema.get("required", []):
        value = data.get(field)
        if value in (None, "", [], {}):
            errors.append(f"thieu truong bat buoc: {field}")
    return errors


def find_category_dirs() -> list[Path]:
    dirs = []
    for path in sorted(DATA_DIR.iterdir()):
        if not path.is_dir():
            continue
        if any((path / name).exists() for name in RAW_FILENAMES):
            dirs.append(path)
    return dirs


def read_raw_file(category_dir: Path) -> Path:
    for name in RAW_FILENAMES:
        candidate = category_dir / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(category_dir)


def map_category(category_dir: Path, schema: dict) -> None:
    raw_path = read_raw_file(category_dir)
    text = raw_path.read_text(encoding="utf-8")
    blocks = [b for b in BLOCK_SEP_RE.split(text) if b.strip()]

    records = []
    used_slugs: set[str] = set()
    for i, block in enumerate(blocks, start=1):
        data, unmapped, orphan_lines = parse_block(block)
        if not any(data.values()):
            if orphan_lines:
                print(f"     [{category_dir.name}] khoi #{i}: bo qua vi khong co tieu de nao hop le, noi dung: {orphan_lines}")
            continue  # khoi rong (vd chi co tieu de huong dan o dau file)

        base_slug = slugify(data.get("ten_thuoc", ""), fallback=f"thuoc-{i}")
        slug = base_slug
        n = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        used_slugs.add(slug)

        data["id"] = slug
        data["danh_muc"] = category_dir.name
        records.append(data)

        errors = validate_record(data, schema)
        label = data.get("ten_thuoc") or f"khoi #{i}"
        if orphan_lines:
            print(f"     [{category_dir.name}] '{label}': BI MAT NOI DUNG truoc tieu de dau tien (khong ro thuoc field nao): {orphan_lines}")
        if unmapped:
            print(f"     [{category_dir.name}] '{label}': header khong nhan dien: {unmapped}")
        if errors:
            print(f"     [{category_dir.name}] '{label}': CANH BAO {errors}")

    out_path = category_dir / OUTPUT_FILENAME
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] {raw_path.relative_to(DATA_DIR.parent)} -> {out_path.relative_to(DATA_DIR.parent)} ({len(records)} thuoc)")


def validate_existing(schema: dict) -> None:
    for category_dir in find_category_dirs():
        out_path = category_dir / OUTPUT_FILENAME
        if not out_path.exists():
            print(f"[BO QUA] {category_dir.name}: chua co {OUTPUT_FILENAME}")
            continue
        with out_path.open(encoding="utf-8") as f:
            records = json.load(f)
        for data in records:
            errors = validate_record(data, schema)
            label = data.get("ten_thuoc") or data.get("id") or "?"
            status = "OK" if not errors else "THIEU"
            print(f"[{status}] {category_dir.name}/{label}" + (f" -> {errors}" if errors else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--category",
        type=str,
        help="Chi map 1 thu muc nhom thuoc cu the (ten thu muc trong data pharmacy/)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Bo qua mapping, chi kiem tra cac thuoc.json da co san",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    schema = load_schema()

    if args.validate_only:
        validate_existing(schema)
        return 0

    if args.category:
        category_dir = DATA_DIR / args.category
        if not category_dir.is_dir():
            print(f"Khong tim thay thu muc: {category_dir}")
            return 1
        map_category(category_dir, schema)
        return 0

    category_dirs = find_category_dirs()
    if not category_dirs:
        print(f"Khong tim thay thu muc nhom thuoc nao co {RAW_FILENAMES} trong {DATA_DIR}")
        return 1

    for category_dir in category_dirs:
        map_category(category_dir, schema)
    return 0


if __name__ == "__main__":
    sys.exit(main())
