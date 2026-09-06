#!/usr/bin/env python3
"""Dung san moi thu de thu bot Telegram end-to-end (TASK-TELEGRAM-BOT).

Chay MOT LAN sau khi `docker compose up -d` la co du:
  - 1 tai khoan benh nhan dang nhap duoc (co mat khau that)
  - don thuoc + dose_event hom nay -> hoi "hom nay uong thuoc gi" co du lieu that
  - 1 ho so "me" + CaregiverLink accepted -> thu duoc luong "dang hoi ve ai"
  - link ghep Telegram in ra man hinh -> khong can dang nhap web de bat dau

TAI CHAY DUOC (idempotent): xoa dung du lieu cua chinh script nay roi tao lai,
khong bao gio cham vao du lieu benh nhan khac.

Usage:
    .venv/Scripts/python scripts/setup_telegram_test.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import (  # noqa: E402
    Account,
    CaregiverLink,
    DoseEvent,
    Patient,
    Prescription,
    TelegramLink,
    TelegramLinkToken,
)
from backend.services.auth import hash_password  # noqa: E402
from backend.services.telegram import link_ghep, tao_token_ghep, telegram_is_configured  # noqa: E402

# Tien to rieng de xoa lai duoc chinh xac, khong dung vao du lieu khac.
BENH_NHAN_ID = "tgtest-benhnhan"
ME_ID = "tgtest-me"
ACCOUNT_ID = "tgtest-account"
EMAIL = "telegram-test@vmec04.dev"
MAT_KHAU = "TelegramTest@123"


def _don_cu(db) -> None:
    ids = [BENH_NHAN_ID, ME_ID]
    db.query(TelegramLink).filter(TelegramLink.account_id == ACCOUNT_ID).delete(synchronize_session=False)
    db.query(TelegramLinkToken).filter(TelegramLinkToken.account_id == ACCOUNT_ID).delete(
        synchronize_session=False
    )
    db.query(CaregiverLink).filter(CaregiverLink.caregiver_account_id == ACCOUNT_ID).delete(
        synchronize_session=False
    )
    db.query(DoseEvent).filter(DoseEvent.patient_id.in_(ids)).delete(synchronize_session=False)
    db.query(Prescription).filter(Prescription.patient_id.in_(ids)).delete(synchronize_session=False)
    db.query(Account).filter(Account.id == ACCOUNT_ID).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def _tao_lieu(db, patient_id: str, presc_id: str, ten_thuoc: str, gio_truoc: int) -> None:
    """1 lieu PENDING dat trong qua khu gan - de vua hoi duoc lich hom nay,
    vua co cai de job nhac gio uong thuoc bat duoc neu muon thu luon."""
    moc = datetime.now(UTC) - timedelta(hours=gio_truoc)
    db.add(
        DoseEvent(
            prescription_id=presc_id,
            patient_id=patient_id,
            scheduled_at=moc,
            window_start=moc - timedelta(minutes=30),
            window_end=moc + timedelta(minutes=30),
            status="PENDING",
            expected_items=[{"drug_id": "tgtest-drug", "ten_thuoc": ten_thuoc, "so_vien": 1}],
        )
    )


def main() -> int:
    settings = get_settings()
    db = SessionLocal()
    try:
        _don_cu(db)

        db.add(Patient(id=BENH_NHAN_ID, full_name="Nguyễn Thị Ba", year_of_birth=1968))
        db.add(Patient(id=ME_ID, full_name="Trần Thị Sáu", year_of_birth=1942))
        db.add(
            Account(
                id=ACCOUNT_ID,
                full_name="Nguyễn Thị Ba",
                email=EMAIL,
                password_hash=hash_password(MAT_KHAU),
                role="patient",
                patient_id=BENH_NHAN_ID,
                status="active",
                is_email_verified=True,
            )
        )
        # VUA la benh nhan VUA cham me - dung boi canh de thu luong "hoi ve ai".
        db.add(
            CaregiverLink(
                caregiver_account_id=ACCOUNT_ID,
                patient_id=ME_ID,
                relationship="Con gái",
                status="accepted",
            )
        )

        hom_nay = datetime.now(UTC).date().isoformat()
        p1 = Prescription(
            patient_id=BENH_NHAN_ID,
            doctor_id="tgtest-doctor",
            status="active",
            items=[{"drug_id": "tgtest-drug", "ten_thuoc": "Paracetamol 500mg", "so_vien": 1}],
            start_date=hom_nay,
            duration_days=7,
        )
        p2 = Prescription(
            patient_id=ME_ID,
            doctor_id="tgtest-doctor",
            status="active",
            items=[{"drug_id": "tgtest-drug", "ten_thuoc": "Amlodipin 5mg", "so_vien": 1}],
            start_date=hom_nay,
            duration_days=30,
        )
        db.add(p1)
        db.add(p2)
        db.flush()

        _tao_lieu(db, BENH_NHAN_ID, p1.id, "Paracetamol 500mg", gio_truoc=2)
        _tao_lieu(db, ME_ID, p2.id, "Amlodipin 5mg", gio_truoc=3)
        db.commit()

        print("=" * 68)
        print("DA DUNG XONG MOI TRUONG THU BOT TELEGRAM")
        print("=" * 68)
        print()
        print("Tai khoan dang nhap web:")
        print(f"  email    = {EMAIL}")
        print(f"  mat khau = {MAT_KHAU}")
        print()
        print("Ho so:")
        print(f"  Ban than : Nguyễn Thị Ba  ({BENH_NHAN_ID})  - Paracetamol 500mg")
        print(f"  Theo doi : Trần Thị Sáu   ({ME_ID})  - Amlodipin 5mg")
        print()

        if not telegram_is_configured():
            print("!! TELEGRAM_BOT_TOKEN chua cau hinh - khong tao duoc link ghep.")
            return 1

        token = tao_token_ghep(db, ACCOUNT_ID)
        db.commit()
        print(f"Bot dang dung : @{settings.telegram_bot_username}")
        print(f"Che do nhan tin: {settings.telegram_update_mode}")
        print()
        print("LINK GHEP (bam roi bam Start, han 10 phut):")
        print(f"  {link_ghep(token)}")
        print()
        print("=" * 68)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
