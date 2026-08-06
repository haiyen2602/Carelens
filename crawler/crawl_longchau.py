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
    "tac_dung",
    "tac_dung_phu",
    "huong_dan_su_dung",
    "lieu_dung",
    "duong_dung",
    "thoi_diem_dung",
    "huong_dan_bao_quan",
    "luu_y_dac_biet",
    "id",
    "danh_muc",
]

# Chuan hoa duong_dung tu dang_thuoc (dang bao che) - suy ra tu 1 field co cau
# truc san co cua site, KHONG doan tu van ban tu do. Kiem tra theo thu tu tren
# xuong (tu khoa cang dac thu dua len truoc) vi 1 chuoi dang_thuoc co the chua
# nhieu tu khoa cung luc (vd "Vien nen bao phim" chi co "vien" -> Uong, khong
# trung tu khoa nao khac).
ROUTE_KEYWORDS: list[tuple[str, str]] = [
    # "truyen" phai kiem tra TRUOC "tiem" - vi "tiem truyen"/"dung dich tiem
    # truyen" chua ca 2 tu, can uu tien nhan dien dung "Tiem truyen" (dich
    # truyen tinh mach) thay vi rung xuong "Tiem" chung chung.
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
    ("mo", "Bôi ngoài da"),
    ("kem", "Bôi ngoài da"),
    ("gel", "Bôi ngoài da"),
    ("boi", "Bôi ngoài da"),
]

# Tu khoa xac nhan duong uong - CHI dung de KHANG DINH "Uong" khi co bang
# chung ro rang, khong phai fallback mac dinh (xem ly do trong
# classify_duong_dung). "hoan" = dang vien hoan y hoc co truyen, luon uong.
ORAL_KEYWORDS = ("vien", "uong", "siro", "com", "hoan")


def classify_duong_dung(dang_thuoc: str) -> str:
    """Map dang_thuoc (dang bao che, vd 'Vien nen bao phim', 'Thuoc mo') sang
    1 gia tri duong dung chuan hoa. Dung \\b word-boundary thay vi substring
    "in" de tranh khop nham (vd tu khoa ngan "mo", "gel" lot vao giua 1 tu
    khac).

    KHONG mac dinh "Uong" cho moi truong hop khong khop - lam vay se KHANG
    DINH sai du lieu y te (vd 1 dang bao che moi/la ma khong nam trong danh
    sach tu khoa se bi gan nham thanh "Uong" du co the la tiem/dat/boi...).
    Thay vao do: chi tra "Uong" khi co tu khoa xac nhan ro rang (ORAL_KEYWORDS),
    con lai (vd "Dang bot", "Hon dich" khong kem "uong"/"tiem") tra ve rong -
    de trong bi validate_record() bao thieu truong bat buoc, buoc nguoi
    dung kiem tra thu cong thay vi am tham sai.

    "Nhu tuong (Gel)" la 1 truong hop mo ho da xac nhan thuc te: cung 1 chuoi
    dang_thuoc nay xuat hien o ca thuoc nho mat (Genteal), gel boi mieng
    (Zytee), gel dat hau mon tri tao bon (Bibonlax) LAN nhu tuong tiem
    truyen tinh mach (Nirpid) - nen khi co "nhu tuong" kem theo tu khoa ket
    cau chung chung ("gel"/"kem"/"mo"), KHONG duoc suy ra "Boi ngoai da";
    chi giu lai ket qua neu co tu khoa route manh hon di kem (vd "tiem",
    "uong nho giot" trong chinh dang_thuoc)."""
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
    return ""


def strip_diacritics(text: str) -> str:
    # "d" (U+0111) khong co dang NFD phan ra "d" + dau, phai thay tay truoc.
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    ascii_text = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    # Site nhieu khi chen \xa0 (non-breaking space) giua cac tu trong heading
    # (vd "Chi\xa0dinh") - neu khong gom ve space thuong, cac cho so sanh
    # substring theo tu khoa ("chi dinh" in ...) se khop nham that bai.
    return re.sub(r"\s+", " ", ascii_text)


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


def normalize_product_name(name: str) -> str:
    """Chuan hoa ten san pham ALL CAPS (vd 'ACICLOVIR 800MG MEYER - BPC 3X10')
    thanh dang de doc hon ('Aciclovir 800mg Meyer - BPC 3x10'), khong dung
    str.title() vi no viet hoa sai o token co chu so (vd '800Mg').

    Quy tac tung tu, tach theo khoang trang:
    - Tu co chu so (vd '800MG', '3X10') -> ha het thanh chu thuong.
    - Tu toan chu, <=4 ky tu, dang ALL CAPS -> giu nguyen (coi la ten viet tat
      nha san xuat, vd 'BPC', 'OPV', 'SPM').
    - Tu toan chu con lai -> viet hoa chu dau, ha cac chu sau.
    """
    words = name.split()
    out = []
    for w in words:
        if any(ch.isdigit() for ch in w):
            out.append(w.lower())
        elif w.isalpha() and w.isupper() and len(w) <= 4:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


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

    # Dung ten ngan (product.name, vd "ACICLOVIR 800MG MEYER - BPC 3X10")
    # thay vi webName (cau SEO day du kem cong dung + quy cach) vi schema
    # yeu cau ten_thuoc la ten thuong mai ngan gon (vd "Panadol Extra"),
    # khong phai mo ta cong dung. webName chi dung khi san pham thieu name.
    raw_name = product.get("name") or product.get("webName") or ""
    ten_thuoc = normalize_product_name(raw_name)

    dosage_html = content.get("dosage") or product.get("dosage") or ""
    dosage_sections = html_fragment_to_sections(dosage_html)
    huong_dan_su_dung = find_section(dosage_sections, "cach dung")
    lieu_dung = find_section(dosage_sections, "lieu dung")
    if not huong_dan_su_dung and not lieu_dung and not dosage_sections:
        # Giong tac_dung ben duoi: 1 so trang khong dung <h2/h3/h4> de tach
        # section. Khong the tach rieng "cach dung" khoi "lieu dung" tu 1
        # doan van khong co tieu de, nen don ca doan vao huong_dan_su_dung
        # (truong tong quat hon) va de lieu_dung trong, tranh trung lap
        # noi dung o ca 2 field.
        huong_dan_su_dung = strip_html(dosage_html)

    # "usage" chua nhieu section gop chung (Chi dinh, Duoc luc hoc, Duoc dong
    # hoc...) - chi lay rieng "Chi dinh" lam tac_dung, khong lay ca khoi vi
    # 2 section con lai la kien thuc duoc ly chuyen sau, khong phai cong dung
    # de hieu cho benh nhan.
    usage_html = content.get("usage") or product.get("usage") or ""
    usage_sections = html_fragment_to_sections(usage_html)
    tac_dung = find_section(usage_sections, "chi dinh")
    if not tac_dung and not usage_sections:
        # 1 so trang khong dung <h2/h3/h4> de tach section (toan bo "usage"
        # chi la 1 doan van ban chi dinh, khong co Duoc luc hoc/Duoc dong hoc
        # di kem) - luc do lay thang ca doan, khong co gi de loc bo.
        tac_dung = strip_html(usage_html)

    # "adverseEffect" khong co the <h2/h3/h4> ngan cach section (khac voi
    # dosage/usage/careful) nen khong dung html_fragment_to_sections duoc -
    # lay thang toan bo doan van ban da lam sach.
    tac_dung_phu = strip_html(content.get("adverseEffect") or product.get("adverseEffect") or "")

    dang_thuoc = product.get("dosageForm") or ""
    duong_dung = classify_duong_dung(dang_thuoc)

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
        "dang_thuoc": dang_thuoc,
        "tong_so_luong": product.get("specification") or "",
        "tac_dung": tac_dung,
        "tac_dung_phu": tac_dung_phu,
        "huong_dan_su_dung": huong_dan_su_dung,
        "lieu_dung": lieu_dung,
        # duong_dung: suy ra tu dang_thuoc (field co cau truc, xem
        # classify_duong_dung), khong phai doan tu van ban tu do.
        "duong_dung": duong_dung,
        # Long Chau khong co field rieng cho "thoi diem dung" (khong xuat
        # hien tach biet trong du lieu san pham) nen luon de trong o day -
        # KHONG tu suy dien tu van ban tu do. Field nay se duoc dien sau dua
        # tren don thuoc bac si ke cho tung benh nhan cu the (nguon du lieu
        # khac hoan toan voi cac field con lai - la du lieu ca nhan hoa theo
        # don, khong phai du lieu tham chieu chung cua thuoc).
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
