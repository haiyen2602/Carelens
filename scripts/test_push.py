#!/usr/bin/env python3
"""Ban thu 1 Web Push toi benh nhan - de test tay, KHONG phai code chay that.

Dung de kiem tra ca chuoi VAPID -> dich vu day cua trinh duyet -> Service
Worker -> thong bao he thong, ma khong phai ngoi cho toi gio uong thuoc.

    python scripts/test_push.py                 # gui cho MOI benh nhan da dang ky
    python scripts/test_push.py <patient_id>    # gui cho 1 benh nhan
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import PushSubscription  # noqa: E402
from backend.services.push import push_is_configured, send_push_to_patient  # noqa: E402


def main() -> int:
    if not push_is_configured():
        print("LOI: chua cau hinh VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY trong .env")
        return 1

    db = SessionLocal()
    try:
        rows = db.query(PushSubscription).all()
        if not rows:
            print("Chua co thiet bi nao dang ky push.")
            print("  -> Vao http://localhost:3000/patient, bam avatar goc phai,")
            print("     bam 'Bat thong bao', roi chay lai script nay.")
            return 1

        print(f"Co {len(rows)} thiet bi da dang ky:")
        for r in rows:
            print(f"  - patient_id={r.patient_id}  ({(r.user_agent or '')[:50]})")

        muc_tieu = sys.argv[1] if len(sys.argv) > 1 else None
        patient_ids = [muc_tieu] if muc_tieu else sorted({r.patient_id for r in rows})

        print()
        for pid in patient_ids:
            n = send_push_to_patient(
                db,
                pid,
                "CapyMedi (thu)",
                "Day la thong bao thu - neu ban thay dong nay tuc la push da chay.",
            )
            print(f"  {pid}: gui thanh cong toi {n} thiet bi")
        db.commit()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
