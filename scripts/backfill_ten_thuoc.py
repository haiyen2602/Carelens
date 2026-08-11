#!/usr/bin/env python3
"""Backfill cot drug_chunks.ten_thuoc (them o migration 0002) tu chinh nguon
that duy nhat: data pharmacy/*/thuoc.json (khop theo id == drug_id) - KHONG
parse nguoc tu noi_dung da luu trong DB (fragile, prefix co the doi format
sau nay).

Usage:
    python backfill_ten_thuoc.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data pharmacy"


def load_ten_thuoc_by_id() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in DATA_DIR.glob("*/thuoc.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for d in data:
            if d.get("id"):
                mapping[d["id"]] = d.get("ten_thuoc", "")
    return mapping


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    mapping = load_ten_thuoc_by_id()
    print(f"Da doc {len(mapping)} thuoc tu data pharmacy/*.json")

    session = SessionLocal()
    try:
        updated = 0
        for drug_id, ten_thuoc in mapping.items():
            result = session.execute(
                text("UPDATE drug_chunks SET ten_thuoc = :t WHERE drug_id = :d AND ten_thuoc IS NULL"),
                {"t": ten_thuoc, "d": drug_id},
            )
            updated += result.rowcount
        session.commit()
        print(f"Da backfill {updated} dong")

        remaining = session.execute(text("SELECT count(*) FROM drug_chunks WHERE ten_thuoc IS NULL")).scalar()
        print(f"Con lai NULL sau backfill: {remaining}")
        if remaining:
            orphans = session.execute(
                text("SELECT DISTINCT drug_id FROM drug_chunks WHERE ten_thuoc IS NULL LIMIT 10")
            ).fetchall()
            print("Vi du drug_id khong khop duoc (co the da bi xoa o buoc don du lieu sau khi embed):")
            for o in orphans:
                print("  -", o[0])
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
