#!/usr/bin/env python3
"""Crawl 1 trang chi tiet thuoc tren nhathuoclongchau.com.vn ra JSON theo schema chuan.

Cach hoat dong (chi tiet ly do xem report.md):
- Trang san pham cua nhathuoclongchau.com.vn la Next.js SSR: toan bo du lieu
  san pham (ten, hoat chat, cach dung, luu y, danh muc...) da duoc server
  nhung san vao the <script id="__NEXT_DATA__" type="application/json"> ngay
  trong HTML tra ve tu request dau tien - KHONG can render JavaScript, nen
  KHONG can Playwright de lay du lieu day du va chinh xac.
- Chi can 1 request bang `requests`, dung BeautifulSoup de:
    1) tim the __NEXT_DATA__ va lay JSON ben trong (day chinh la "API noi bo"
       ma trang goi luc server-side render, duoc nhung san cho minh - khong
       can tu do nguoc endpoint API rieng cua ho).
    2) parse cac doan HTML con nam trong JSON (vd noi dung "Cach dung",
       "Luu y") thanh text sach theo tung tieu de <h3>.
- Nut "Xem them" tren trang nay chi mo rong ANH/BINH LUAN (hanh vi hien thi
  o client), khong che giau noi dung thuoc. Vi lay du lieu thang tu
  __NEXT_DATA__ (nguon du lieu goc, chua qua truncate CSS/JS) nen du lieu
  luon day du bat ke co bam "Xem them" hay khong.

Usage:
    python crawl_longchau.py [URL] [--output output.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

DEFAULT_URL = "https://nhathuoclongchau.com.vn/thuoc/agiclovir-5-agimexpharm-30338.html"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

OUTPUT_SCHEMA_KEYS = [
    "ten_thuoc",
    "ham_luong",
    "dang_thuoc",
    "tong_so_luong",
    "huong_dan_su_dung",
    "lieu_dung",
    "duong_dung",
    "thoi_diem_dung",
    "huong_dan_bao_quan",
    "luu_y_dac_biet",
    "id",
    "danh_muc",
]


def strip_diacritics(text: str) -> str:
    # "d" (U+0111) khong co dang NFD phan ra "d" + dau, phai thay tay truoc.
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def slugify(text: str) -> str:
    text = strip_diacritics(text or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def fetch_next_data(url: str) -> dict:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        raise RuntimeError(
            "Khong tim thay the __NEXT_DATA__ - trang co the da doi cau truc "
            "hoac can render JavaScript de co du lieu (thu lai voi Playwright)."
        )
    return json.loads(script.string)


def html_fragment_to_sections(html: str) -> dict[str, str]:
    """Tach 1 doan HTML dang '<h3>Tieu de</h3><p>...</p><h3>...</h3>...'
    thanh dict {tieu de: noi dung text da lam sach}. Dung chung cho moi
    field tra ve dang HTML tu JSON (dosage, usage, careful...).
    """
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        if current_heading is not None:
            text = " ".join(p for p in current_parts if p).strip()
            if text:
                sections[current_heading] = text

    for node in soup.contents:
        if not isinstance(node, Tag):
            continue
        if node.name in ("h2", "h3", "h4"):
            flush()
            current_heading = node.get_text(strip=True)
            current_parts = []
        else:
            text = node.get_text(" ", strip=True)
            if text:
                current_parts.append(text)
    flush()
    return sections


def find_section(sections: dict[str, str], *keywords: str) -> str:
    """Tim value trong `sections` co tieu de (da bo dau) chua 1 trong cac keyword."""
    for heading, text in sections.items():
        norm = strip_diacritics(heading).lower()
        if any(kw in norm for kw in keywords):
            return text
    return ""


def strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def format_ingredient(ingredient: list[dict] | None) -> str:
    """Ghep cac hoat chat chinh (loai tru ta duoc) thanh chuoi ham luong."""
    exclude_re = re.compile(r"excipient|ta duoc", re.IGNORECASE)
    parts = []
    for item in ingredient or []:
        name = (item.get("name") or "").strip()
        amount = (item.get("shortDescription") or "").strip()
        if not name or exclude_re.search(strip_diacritics(name)):
            continue
        parts.append(f"{name} {amount}".strip())
    return "; ".join(parts)


def extract_fields(next_data: dict) -> dict:
    page_props = next_data.get("props", {}).get("pageProps", {})
    product = page_props.get("product") or {}
    content = page_props.get("content") or {}
    breadcrumbs = page_props.get("breadcrumbs") or []

    ten_thuoc = product.get("webName") or product.get("name") or ""

    dosage_html = content.get("dosage") or product.get("dosage") or ""
    dosage_sections = html_fragment_to_sections(dosage_html)
    huong_dan_su_dung = find_section(dosage_sections, "cach dung")
    lieu_dung = find_section(dosage_sections, "lieu dung")

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

    return {
        "ten_thuoc": ten_thuoc,
        "ham_luong": format_ingredient(product.get("ingredient")),
        "dang_thuoc": product.get("dosageForm") or "",
        "tong_so_luong": product.get("specification") or "",
        "huong_dan_su_dung": huong_dan_su_dung,
        "lieu_dung": lieu_dung,
        # Long Chau khong co field rieng cho "duong dung" / "thoi diem dung"
        # (khong xuat hien tach biet trong du lieu san pham) - de trong thay
        # vi tu suy dien tu van ban tu do, dung theo yeu cau cua de bai.
        "duong_dung": "",
        "thoi_diem_dung": "",
        "huong_dan_bao_quan": strip_html(content.get("preservation") or ""),
        "luu_y_dac_biet": luu_y_dac_biet,
        # Dung ten ngan gon (product.name) lam nguon slug thay vi ten_thuoc
        # (webName) qua dai, cho id gon va de dung hon.
        "id": slugify(product.get("name") or ten_thuoc),
        "danh_muc": danh_muc,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="URL trang chi tiet thuoc")
    parser.add_argument("--output", default="output.json", help="Duong dan file JSON dau ra")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    next_data = fetch_next_data(args.url)
    data = extract_fields(next_data)

    out_path = Path(args.output)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] Da luu {out_path}")
    for key in OUTPUT_SCHEMA_KEYS:
        value = data[key]
        preview = f"[{len(value)} muc]" if isinstance(value, list) else value
        print(f"  {key}: {str(preview)[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
