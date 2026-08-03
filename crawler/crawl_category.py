#!/usr/bin/env python3
"""Crawl toan bo san pham trong 1 danh muc tren nhathuoclongchau.com.vn.

Van de: trang danh muc la Next.js SSR nhung __NEXT_DATA__ chi nhung san 12
san pham dau tien (trong initTotalProducts co the len den ~80-90). Phan con
lai chi load qua 1 API noi bo khi nguoi dung cuon trang tren trinh duyet
that - khong the goi thang bang requests (xem README trong report.md cua
crawl_longchau.py ve viec nay).

Cach giai quyet o day - KHONG dung API noi bo, KHONG dung browser gia lap:
trang danh muc co san cac bo loc (filter) hien thi ben trai (thuong hieu,
doi tuong su dung, nuoc san xuat, chi dinh, thanh phan...). Moi bo loc AP
DUNG SERVER-SIDE va lam initTotalProducts giam xuong dung so SP khop loc do.
Neu 1 gia tri loc cho ra <= 12 san pham, SSR tra ve DAY DU nhom do. Vi 1 danh
muc thuong co vai chuc gia tri loc (vd 38 thuong hieu) trai deu tren so san
pham, hop toan bo cac nhom nho lai gan nhu luon phu duoc toan bo danh muc,
ma khong can doan/goi API rieng nao.

Tham so loc (key trong query string) duoc xac dinh bang thu nghiem thuc te
(xem lich su chat), KHONG phai suy ra tu ten field - map co dinh trong
FILTER_QUERY_KEYS ben duoi:

    prescription -> thuoc-ke-don
    objectUse    -> doi-tuong-su-dung
    manufactor   -> nuoc-san-xuat
    indications  -> chi-dinh
    brand        -> thuong-hieu
    brandOrigin  -> xuat-xu-thuong-hieu
    ingredient   -> thanh-phan

Usage:
    python crawl_category.py <category_url> --danh-muc "Thuoc khang virus" --output "../data pharmacy/Thuoc khang virus/thuoc.json"
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_longchau import extract_fields  # noqa: E402

BASE_URL = "https://nhathuoclongchau.com.vn"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# code (trong filterAttributes tra ve tu server) -> ten tham so query da xac
# nhan hoat dong bang thu nghiem thuc te tren trang nay. priceSystem KHONG
# co trong danh sach vi chua tim ra dung format tham so cho no.
FILTER_QUERY_KEYS = {
    "prescription": "thuoc-ke-don",
    "objectUse": "doi-tuong-su-dung",
    "manufactor": "nuoc-san-xuat",
    "indications": "chi-dinh",
    "brand": "thuong-hieu",
    "brandOrigin": "xuat-xu-thuong-hieu",
    "ingredient": "thanh-phan",
}

MIN_DELAY = 1.2
MAX_DELAY = 2.2
MAX_RETRIES = 3


def polite_sleep() -> None:
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def slugify(text: str) -> str:
    text = strip_diacritics(text or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def get_json(session: requests.Session, url: str, params: list[tuple[str, str]] | None = None) -> dict:
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            if script is None or not script.string:
                raise RuntimeError("Khong tim thay __NEXT_DATA__ trong response")
            return json.loads(script.string)
        except Exception as e:  # noqa: BLE001 - retry moi loai loi mang/parse
            last_err = e
            wait = 2 ** attempt
            print(f"  [retry {attempt}/{MAX_RETRIES}] {e} - cho {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"That bai sau {MAX_RETRIES} lan thu: {last_err}")


def slug_path_to_params(category_url: str) -> list[tuple[str, str]]:
    path = urlparse(category_url).path.strip("/")
    parts = path.split("/")
    return [("slug", p) for p in parts if p]


def discover_products(session: requests.Session, category_url: str) -> tuple[dict, int]:
    """Tra ve (dict sku -> product listing entry, initTotalProducts) cho toan bo
    danh muc, bang cach hop ket qua tu moi gia tri cua moi filter co san."""
    base_params = slug_path_to_params(category_url)

    data = get_json(session, category_url, base_params)
    vd = data["props"]["pageProps"]["viewData"]
    total = vd.get("initTotalProducts", 0)
    products: dict[str, dict] = {p["sku"]: p for p in (vd.get("products") or [])}
    print(f"[discover] trang goc: initTotalProducts={total}, SSR tra ve {len(products)} SP")
    polite_sleep()

    filter_attrs = vd.get("filterAttributes") or []
    for attr in filter_attrs:
        code = attr.get("code")
        query_key = FILTER_QUERY_KEYS.get(code)
        if not query_key:
            continue  # khong biet tham so query cho filter nay (vd priceSystem)
        for value in attr.get("values", []):
            params = base_params + [(query_key, value)]
            fdata = get_json(session, category_url, params)
            fvd = fdata["props"]["pageProps"]["viewData"]
            ftotal = fvd.get("initTotalProducts", 0)
            fprods = fvd.get("products") or []
            new = 0
            for p in fprods:
                if p["sku"] not in products:
                    new += 1
                products[p["sku"]] = p
            warn = "  (BUCKET > 12, co the con sot SP)" if ftotal and ftotal > 12 else ""
            print(f"[discover] {query_key}={value!r}: total={ftotal} got={len(fprods)} new={new}{warn}")
            polite_sleep()

    print(f"[discover] TONG HOP: {len(products)}/{total} san pham duy nhat tim duoc")
    if len(products) < total:
        missing = total - len(products)
        print(
            f"[discover] CANH BAO: con thieu {missing} san pham khong khop bat ky "
            "gia tri filter nao da thu - kiem tra thu cong neu can du 100%.",
            file=sys.stderr,
        )
    return products, total


def crawl_details(session: requests.Session, listing_products: dict) -> list[dict]:
    records = []
    items = sorted(listing_products.values(), key=lambda p: p.get("slug", ""))
    for i, item in enumerate(items, start=1):
        slug = item["slug"]
        url = f"{BASE_URL}/{slug}"
        print(f"[{i}/{len(items)}] {url}")
        try:
            next_data = get_json(session, url)
        except Exception as e:  # noqa: BLE001
            print(f"  [BO QUA] loi khi crawl: {e}", file=sys.stderr)
            polite_sleep()
            continue
        record = extract_fields(next_data)
        records.append(record)
        polite_sleep()
    return records


def validate_record(data: dict, schema: dict) -> list[str]:
    errors = []
    for field in schema.get("required", []):
        value = data.get(field)
        if value in (None, "", [], {}):
            errors.append(f"thieu truong bat buoc: {field}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category_url", help="URL trang danh muc tren nhathuoclongchau.com.vn")
    parser.add_argument("--danh-muc", required=True, help="Ten danh muc (dung cho field danh_muc va ten thu muc output)")
    parser.add_argument("--output", help="Duong dan file thuoc.json dau ra (mac dinh: data pharmacy/<danh-muc>/thuoc.json)")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    schema_path = Path(__file__).resolve().parent.parent / "data pharmacy" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    listing_products, total = discover_products(session, args.category_url)
    records = crawl_details(session, listing_products)

    used_slugs: set[str] = set()
    for r in records:
        r["danh_muc"] = args.danh_muc
        # extract_fields() da tu sinh 1 "id" gon tu ten ngan (product.name),
        # chi doi lai neu bi trung slug voi 1 SP khac trong cung lan crawl nay.
        base_slug = r.get("id") or slugify(r.get("ten_thuoc", "")) or "thuoc"
        slug = base_slug
        n = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        used_slugs.add(slug)
        r["id"] = slug

        errors = validate_record(r, schema)
        if errors:
            print(f"  [CANH BAO] '{r.get('ten_thuoc')}': {errors}", file=sys.stderr)

    out_path = Path(args.output) if args.output else (
        Path(__file__).resolve().parent.parent / "data pharmacy" / args.danh_muc / "thuoc.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] Da crawl {len(records)}/{total} san pham -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
