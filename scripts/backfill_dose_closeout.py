#!/usr/bin/env python3
"""Chot MOT LAN cac lieu PENDING ton dong tu truoc khi job dose_closeout ton tai.

BOI CANH: he thong chua bao gio co gi chuyen PENDING -> MISSED (xem docstring
backend/services/dose_lifecycle.py), nen tai thoi diem viet script nay DB that
con 122 tren 142 lieu PENDING da qua han nam lai vinh vien. Job dinh ky moi
them se don sach dan tu ngay mai tro di, nhung dong ton dong cu van can mot
lan chay co chu dich - va co ban ghi lai da dung vao nhung dong nao.

KHONG kich hoat escalation: chot 122 lieu cu se ban mot loat canh bao
"missed_dose" cho benh nhan lan nguoi than ve nhung lieu tu nhieu tuan truoc,
vo nghia va gay hoang mang. chot_lieu_qua_han() chi doi cot `status`, khong
goi sang escalation domain - day la ly do script nay goi thang no thay vi
dung lai duong xac nhan cua benh nhan.

VET AUDIT: bang `dose_event` (legacy) khong co cot `status_reason`, va bang
`dose_event_log` cua V2 doi `dose_occurrence_id` NOT NULL nen khong nhan duoc
lieu legacy. Thay vi them migration chi de phuc vu mot lan chay, script ghi
danh sach ID day du ra file JSON - du de doi chieu ve sau "dong nay bi doi
boi backfill hay bi chot tu nhien".

Usage:
    # xem truoc, KHONG ghi gi
    python scripts/backfill_dose_lifecycle.py --dry-run

    # chay that
    python scripts/backfill_dose_lifecycle.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import DoseEvent  # noqa: E402
from backend.services.dose_lifecycle import (  # noqa: E402
    TRANG_THAI_CHOT_DUOC,
    chot_lieu_qua_han,
    qua_ngay_moi,
)


def _ung_vien(db, now: datetime) -> list[DoseEvent]:
    """Dung DUNG dieu kien loc cua chot_lieu_qua_han() - neu hai cho lech nhau
    thi bao cao dry-run se noi doi ve viec chay that se lam gi."""
    rows = db.execute(
        select(DoseEvent).where(
            DoseEvent.status == TRANG_THAI_CHOT_DUOC,
            DoseEvent.scheduled_at < now,
        )
    ).scalars()
    return [r for r in rows if qua_ngay_moi(r.scheduled_at, now)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Chi liet ke, khong ghi gi")
    parser.add_argument(
        "--report",
        default="scripts/backfill_dose_closeout_report.json",
        help="Noi ghi danh sach ID da doi (mac dinh: scripts/backfill_dose_closeout_report.json)",
    )
    args = parser.parse_args()

    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        ung_vien = _ung_vien(db, now)
        theo_benh_nhan: dict[str, int] = {}
        for row in ung_vien:
            theo_benh_nhan[row.patient_id] = theo_benh_nhan.get(row.patient_id, 0) + 1

        print(f"Tim thay {len(ung_vien)} lieu PENDING qua han can chot:")
        for patient_id, so_luong in sorted(theo_benh_nhan.items(), key=lambda kv: -kv[1]):
            print(f"  {patient_id:<24} {so_luong} lieu")

        if args.dry_run:
            print("\n--dry-run: KHONG ghi gi.")
            return 0

        if not ung_vien:
            print("Khong co gi de chot.")
            return 0

        bao_cao = {
            "chay_luc": now.isoformat(),
            "so_lieu": len(ung_vien),
            "theo_benh_nhan": theo_benh_nhan,
            "dose_event_ids": [
                {
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "scheduled_at": r.scheduled_at.isoformat(),
                }
                for r in ung_vien
            ],
        }

        da_chot = chot_lieu_qua_han(db, now=now)

        # Ghi bao cao TRUOC khi commit: bao cao la audit trail duy nhat cua lan
        # va nay (dose_event khong co cot status_reason, xem docstring dau file).
        # Ghi file that bai ma DB da commit thi mat dau vet vinh vien - thu tu
        # nay doi lai bang mot lan chay khong bi ghi nhan neu commit hong, ma
        # lan do vo hai vi ham chot idempotent, chay lai la xong.
        duong_dan = Path(args.report)
        duong_dan.parent.mkdir(parents=True, exist_ok=True)
        duong_dan.write_text(json.dumps(bao_cao, ensure_ascii=False, indent=2), encoding="utf-8")

        db.commit()

        print(f"\nDa chot {da_chot} lieu thanh MISSED.")
        print(f"Bao cao chi tiet: {duong_dan}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
