#!/usr/bin/env python3
"""TASK-010 (api-contracts.md muc 1, auth-api) - tao 1 tai khoan `admin`
dau tien trong bang `account`. KHONG co endpoint dang ky cong khai (dung y -
user-roles.md: chi `admin` duoc quan ly tai khoan), nen can 1 script chay
tay 1 lan (local hoac qua `railway run`) de co tai khoan admin dau tien,
tu do dang nhap va tao cac tai khoan khac qua giao dien quan ly (khi da co).

Idempotent theo email: neu email da ton tai, bao loi ro rang thay vi tao
trung (unique constraint tren Account.email se chan o tang DB, nhung kiem
tra truoc de thong bao de hieu hon 1 IntegrityError tho).

Usage:
    python scripts/create_admin.py --email admin@vmec04.dev --password "<mat khau that>" --full-name "Admin VMEC-04"

LUU Y: POST /api/v1/auth/login dung pydantic EmailStr (email-validator) -
domain ".local" (vd admin@vmec.local) bi TU CHOI vi la special-use domain
(RFC 6762), du script nay tao Account thanh cong (khong validate format).
Dung domain that (vd .dev/.com nam ban quan ly) de dam bao dang nhap duoc
sau khi tao - xac nhan bang test that 2026-08-12.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account  # noqa: E402
from backend.services.auth import hash_password  # noqa: E402
from backend.services.email_identity import find_account_by_email, normalize_email  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True, help="Mat khau that - KHONG go thang vao shell history dung/CI log")
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--role", default="super_admin", choices=["super_admin", "admin"], help="Role cua tai khoan (mac dinh super_admin)")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("LOI: mat khau qua ngan (toi thieu 8 ky tu).")
        return 1

    db = SessionLocal()
    try:
        # Script nay KHONG di qua pydantic schema nen phai tu chuan hoa email
        # (route thi da co NormalizedEmail lo viec do) - neu khong, admin tao
        # bang tay voi "Admin@vmec04.dev" se khong dang nhap duoc bang
        # "admin@vmec04.dev" va se vi pham unique index
        # `ux_account_email_normalized` neu email chuan da ton tai.
        email = normalize_email(args.email)

        existing = find_account_by_email(db, email)
        if existing is not None:
            print(f"LOI: email {email!r} da co tai khoan (role={existing.role}).")
            return 1

        account = Account(
            full_name=args.full_name,
            email=email,
            password_hash=hash_password(args.password),
            role=args.role,
        )
        db.add(account)
        db.commit()

        print(f"Da tao tai khoan {args.role}:")
        print(f"  id    = {account.id}")
        print(f"  email = {account.email}")
        print(f"  role  = {account.role}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
