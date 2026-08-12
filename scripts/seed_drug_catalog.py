#!/usr/bin/env python3
"""Nap 3562 thuoc tu 'data pharmacy/' vao bang `drug`.

Bang `drug` la danh muc de bac si tra cuu khi ke don, va la nguon duy nhat cho
`dang_thuoc` - truong quyet dinh mot lieu thuoc co xac minh duoc bang anh hay
khong (backend/services/photo_verification/dosage_form.py).

VI SAO PHAI CHAY SCRIPT NAY THAY VI DE MIGRATION TU LAM: 'data pharmacy/' bi
.railwayignore loai khoi goi upload (~32MB, khong doc luc runtime), nen server
khong co file nguon. Du lieu di vao production bang duong DB, khong bang file.

TAI CHAY DUOC: xoa sach bang `drug` roi nap lai. An toan vi bang nay la BAN SAO
cua du lieu goc trong 'data pharmacy/' - khong co gi do nguoi dung tao ra o day
de ma mat. Khac han cac script seed benh nhan (chi xoa dung id cua minh).

`ten_thuoc_unaccent` duoc tinh bang ham unaccent() NGAY TRONG SQL, khong phai o
tang Python - cung quy uoc voi drug_chunks, de index va query dung chung 1
logic bo dau (xem migration 0001).

Usage:
    python scripts/seed_drug_catalog.py
    python scripts/seed_drug_catalog.py --cho-phep-db-tu-xa   # nap len server
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data pharmacy"
HOST_LOCAL = frozenset({"localhost", "127.0.0.1", "::1", "db"})
BATCH = 500

# Cac truong lay tu JSON. `id`, `ten_thuoc`, `dang_thuoc`, `duong_dung` la bat
# buoc - thieu mot trong so do thi ban ghi vo dung, bo qua.
BAT_BUOC = ("id", "ten_thuoc", "dang_thuoc", "duong_dung")
TUY_CHON = ("ham_luong", "tong_so_luong", "danh_muc", "muc_nghiem_trong")


def _la_ban_mau(record: dict) -> bool:
    """Mot ban ghi trong 'data pharmacy/' la template, moi gia tri deu dang
    "<Ten thuong mai / biet duoc, vd: Panadol Extra>". Nap no vao danh muc se
    tao ra mot "thuoc" ten la dau ngoac nhon."""
    return str(record.get("ten_thuoc", "")).startswith("<")


def doc_thuoc() -> tuple[list[dict], int]:
    """Doc moi file JSON trong 'data pharmacy/'. Tra ve (danh sach, so bo qua)."""
    thuoc: dict[str, dict] = {}  # theo id - file nguon co the trung thuoc
    bo_qua = 0

    for path in sorted(DATA_DIR.rglob("*.json")):
        try:
            noi_dung = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  bo qua {path.name}: {exc}")
            continue

        for record in noi_dung if isinstance(noi_dung, list) else [noi_dung]:
            if not isinstance(record, dict) or _la_ban_mau(record):
                continue
            if any(not str(record.get(k, "")).strip() for k in BAT_BUOC):
                bo_qua += 1
                continue
            thuoc[str(record["id"])] = {
                **{k: str(record[k]).strip() for k in BAT_BUOC},
                **{k: (str(record.get(k) or "").strip() or None) for k in TUY_CHON},
            }

    return list(thuoc.values()), bo_qua


def _chan_database_that(cho_phep_db_tu_xa: bool) -> None:
    """Nap danh muc len production la viec hop le, nhung phai co y.

    Khac script seed benh nhan (cam tuyet doi tren production), script nay CO
    duong len server - danh muc thuoc la du lieu that, server can no. Nhung no
    XOA SACH bang `drug` truoc khi nap, nen khong duoc chay nham.
    """
    settings = get_settings()
    host = urlsplit(settings.database_url).hostname or ""
    if host not in HOST_LOCAL and not cho_phep_db_tu_xa:
        raise SystemExit(
            f"DUNG LAI: DATABASE_URL dang tro toi {host!r}, khong phai may nay.\n"
            "  Script nay XOA SACH bang `drug` truoc khi nap lai.\n"
            "  Neu that su muon nap len do, them --cho-phep-db-tu-xa."
        )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Nap danh muc thuoc tu 'data pharmacy/' vao bang drug.")
    parser.add_argument(
        "--cho-phep-db-tu-xa",
        action="store_true",
        help="Cho phep nap vao database khong nam tren may nay (vd production)",
    )
    args = parser.parse_args()
    _chan_database_that(args.cho_phep_db_tu_xa)

    if not DATA_DIR.is_dir():
        raise SystemExit(
            f"Khong thay thu muc {DATA_DIR}.\n"
            "  Thu muc nay bi .railwayignore loai khoi goi upload, nen script chi\n"
            "  chay duoc o may co ma nguon day du, khong chay duoc tren server."
        )

    print(f"Doc du lieu thuoc tu {DATA_DIR.name}/ ...")
    thuoc, bo_qua = doc_thuoc()
    if not thuoc:
        raise SystemExit("Khong doc duoc thuoc nao - kiem tra lai thu muc du lieu.")
    print(f"  {len(thuoc)} thuoc hop le" + (f", {bo_qua} ban ghi thieu truong bat buoc" if bo_qua else ""))

    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM drug"))

        # unaccent() tinh trong SQL, khong phai o Python - cung logic bo dau
        # voi luc query, neu khac nhau thi tim se truot ma khong bao loi.
        cau_lenh = text(
            "INSERT INTO drug (id, ten_thuoc, ten_thuoc_unaccent, dang_thuoc, duong_dung,"
            " ham_luong, tong_so_luong, danh_muc, muc_nghiem_trong, created_at)"
            " VALUES (:id, :ten_thuoc, unaccent(:ten_thuoc), :dang_thuoc, :duong_dung,"
            " :ham_luong, :tong_so_luong, :danh_muc, :muc_nghiem_trong, now())"
        )
        for i in range(0, len(thuoc), BATCH):
            db.execute(cau_lenh, thuoc[i : i + BATCH])
            print(f"  da nap {min(i + BATCH, len(thuoc))}/{len(thuoc)}", end="\r")
        db.commit()
        print()

        _in_thong_ke(db)
        return 0
    finally:
        db.close()


def _in_thong_ke(db) -> None:
    """In pho dang bao che - so nay quyet dinh bao nhieu thuoc xac minh duoc
    bang anh, nen dang nhin ngay sau khi nap."""
    tong = db.execute(text("SELECT count(*) FROM drug")).scalar()
    print(f"\nDa nap {tong} thuoc vao bang `drug`.\n")
    print("  10 dang bao che pho bien nhat:")
    rows = db.execute(
        text("SELECT dang_thuoc, count(*) AS n FROM drug GROUP BY dang_thuoc ORDER BY n DESC LIMIT 10")
    ).all()
    for r in rows:
        print(f"    {r.n:5}  {r.dang_thuoc}")


if __name__ == "__main__":
    raise SystemExit(main())
