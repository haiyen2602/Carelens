#!/usr/bin/env python3
"""Xoa cac ban ghi thuoc con thieu field bat buoc (theo schema.json) khoi
data pharmacy/*/thuoc.json - lam LAI cho toan bo danh muc hien co.

Tien le: lan dau chay ad-hoc cho 4 danh muc (2026-08-04, xoa 51 SP). Script
nay tong quat hoa buoc do thanh cong cu tai su dung, vi du datacon them
danh muc moi sau nay ma chua qua buoc don du lieu (thuc te da xay ra - xem
report 2026-08-08: 5 ban ghi lot qua o 7 danh muc them sau).

Nguyen tac: KHONG backfill/suy dien gia tri con thieu tu ten san pham hay bat
ky nguon nao khac - dung nguyen tac da nhat quan xuyen suot du an (BR-7.3,
tinh than giong fix duong_dung khong con mac dinh "Uong"). Ban ghi thieu
field bat buoc thi XOA, khong doan.

thoi_diem_dung LOAI TRU khoi kiem tra - field nay luon de trong theo thiet
ke (xem memory/schema.json), khong tinh la loi.

Usage:
    python clean_incomplete_records.py                # xoa that, ghi de file
    python clean_incomplete_records.py --report-only   # chi in bao cao, khong xoa
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data pharmacy"
SCHEMA_PATH = DATA_DIR / "schema.json"
EXCLUDE_FROM_CHECK = {"thoi_diem_dung"}  # luon de trong theo thiet ke, khong phai loi


def load_required_fields() -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return [f for f in schema["required"] if f not in EXCLUDE_FROM_CHECK]


def find_missing(thuoc: dict, required: list[str]) -> list[str]:
    return [f for f in required if not thuoc.get(f)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="Chi in bao cao, khong xoa/ghi file")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    required = load_required_fields()
    print("Cac field kiem tra (loai thoi_diem_dung):", required)
    print()

    total_before = total_removed = 0
    removed_log: list[str] = []

    for path in sorted(DATA_DIR.glob("*/thuoc.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        keep, removed = [], []
        for d in data:
            missing = find_missing(d, required)
            if missing:
                removed.append((d.get("ten_thuoc", "?"), missing))
            else:
                keep.append(d)

        total_before += len(data)
        total_removed += len(removed)
        print(f"[{path.parent.name}] {len(data)} -> {len(keep)} (xoa {len(removed)})")
        for name, missing in removed:
            line = f"   - {name} | thieu: {missing}"
            print(line)
            removed_log.append(f"{path.parent.name}/{name} | thieu: {missing}")

        if not args.report_only and removed:
            with path.open("w", encoding="utf-8") as f:
                json.dump(keep, f, ensure_ascii=False, indent=2)
                f.write("\n")

    print()
    print(f"TONG: {total_before} -> xoa {total_removed} -> con lai {total_before - total_removed}")

    if removed_log:
        log_path = DATA_DIR / "_removed_incomplete_log.txt"
        if not args.report_only:
            with log_path.open("a", encoding="utf-8") as f:
                f.write("--- clean_incomplete_records.py run ---\n")
                f.write("\n".join(removed_log) + "\n\n")
            print(f"[OK] Da ghi log vao {log_path.relative_to(DATA_DIR.parent)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
