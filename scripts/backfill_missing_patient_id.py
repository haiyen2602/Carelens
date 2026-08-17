#!/usr/bin/env python3
"""Cap patient_id (BNxxxxx) + dong `Patient` cho cac Account role=patient con
thieu - va cho tat ca bac si theo doi ho ngay (auto_watch_new_patient).

VI SAO CAN SCRIPT NAY (bug that, phat hien 2026-08-17 khi so localhost voi
production): nhanh "tai khoan DA CO SAN" cua POST /api/v1/auth/oauth/google
tung khong goi _provision_patient(), nen tai khoan role=patient tao TRUOC
luong Google (hoac do admin tao) sau khi dang nhap Google van co
patient_id = NULL. Hau qua tren production:
  - header trang /patient hien "Bệnh nhân ·" bo trong (JWT claim patient_id
    = None);
  - MeResponse.profile_completed = None nen cong onboarding
    (frontend/src/app/patient/layout.tsx chi bat khi === false) khong bao gio
    mo -> ho so benh nhan trong vinh vien;
  - moi endpoint doc du lieu benh nhan qua get_current_patient_id()
    (backend/api/security.py) khong the uu tien patient_id cua chinh JWT.

Code da sua (backend/api/auth_routes.py::oauth_google) chi va cho lan dang
nhap SAU. Script nay don cac tai khoan da o trang thai loi tu truoc, dung
DUNG cac ham service cua app (khong tu sinh ID bang tay) de ID sinh ra khong
lech dinh dang / khong dung so voi generate_next_patient_id().

CHAY LAI DUOC (idempotent): chi cham vao account THAT SU con thieu
patient_id, khong bao gio ghi de patient_id da co.

Usage:
    # mac dinh: doc DATABASE_URL cua moi truong hien tai (backend/config.py)
    python scripts/backfill_missing_patient_id.py --dry-run
    python scripts/backfill_missing_patient_id.py

    # production: tro DATABASE_URL sang DB that (KHONG hardcode trong file nay)
    DATABASE_URL="postgresql://..." python scripts/backfill_missing_patient_id.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account  # noqa: E402
from backend.services.doctor_watch import auto_watch_new_patient  # noqa: E402
from backend.services.patient_id import generate_next_patient_id  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chi in ra tai khoan se duoc cap patient_id, KHONG ghi gi vao DB.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        thieu = (
            db.query(Account)
            .filter(Account.role == "patient", Account.patient_id.is_(None))
            .order_by(Account.created_at)
            .all()
        )
        if not thieu:
            print("Khong co tai khoan role=patient nao thieu patient_id.")
            return 0

        print(f"Tim thay {len(thieu)} tai khoan role=patient thieu patient_id:")
        for account in thieu:
            print(f"  - {account.email} | {account.full_name} | tao {account.created_at}")

        if args.dry_run:
            print("\n--dry-run: khong ghi gi vao DB.")
            return 0

        # Import muon: chi can khi that su ghi, va de --dry-run chay duoc tren
        # DB chua co bang Patient (vd DB moi chua migrate).
        from backend.db.models import Patient

        print()
        for account in thieu:
            patient_id = generate_next_patient_id(db)
            db.add(Patient(id=patient_id, full_name=account.full_name))
            account.patient_id = patient_id
            # Flush TRUOC auto_watch: DoctorWatch tham chieu patient_id, va
            # generate_next_patient_id() cua vong sau doc lai bang Patient nen
            # can thay dong vua them (neu khong, 2 tai khoan se nhan cung 1 ID).
            db.flush()
            auto_watch_new_patient(db, patient_id)
            db.commit()
            print(f"  OK {account.email} -> {patient_id}")

        print(f"\nDa cap patient_id cho {len(thieu)} tai khoan.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
