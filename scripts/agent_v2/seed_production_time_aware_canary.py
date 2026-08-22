"""BUILD-27B: synthetic-only production canary data for time-aware schedule
verification (past history with real TAKEN/MISSED/mixed status, a no-data
day, plus today/future doses).

Every identifier is a fixed, obviously-synthetic string
(``agent-v2-timeaware-canary-*``) so it can never be confused with a real
patient -- same convention as BUILD-21/22's own
``seed_production_canary_data.py``/``seed_production_canary_batch2.py``.
Creates NO PHI beyond what is invented here.

Idempotent: safe to re-run (deletes and recreates its own fixed IDs only).

Deliberately writes DoseOccurrence rows directly with an already-past
``scheduled_at`` and an already-set TAKEN/MISSED status, rather than going
through the normal prescription-approval write path -- that path only ever
creates future SCHEDULED rows; real history only accumulates as real time
passes and real confirmations happen, which this canary cannot wait for.

Usage (DATABASE_URL, JWT_SECRET point at PRODUCTION's own values, via a
temporary TCP proxy, deleted immediately after use)::

    DATABASE_URL="<production>" JWT_SECRET="<production>" \
        python scripts/agent_v2/seed_production_time_aware_canary.py
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, DoseOccurrence, Patient, Prescription, PrescriptionItem  # noqa: E402
from backend.services.auth import create_access_token, hash_password  # noqa: E402

PATIENT_ID = "agent-v2-timeaware-canary-patient-1"
ACCOUNT_ID = "agent-v2-timeaware-canary-patient1-account"
DOCTOR_ID = "agent-v2-timeaware-canary-doctor-1"
VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _vn_dose(local_date: date, local_hour: int) -> datetime:
    return datetime.combine(local_date, time(local_hour, 0), tzinfo=VN).astimezone(UTC)


def main() -> int:
    db = SessionLocal()
    try:
        db.execute(delete(DoseOccurrence).where(DoseOccurrence.patient_id == PATIENT_ID))
        db.execute(delete(PrescriptionItem).where(PrescriptionItem.patient_id == PATIENT_ID))
        db.execute(delete(Prescription).where(Prescription.patient_id == PATIENT_ID))
        db.execute(delete(Account).where(Account.id == ACCOUNT_ID))
        db.execute(delete(Patient).where(Patient.id == PATIENT_ID))
        db.commit()

        today_vn = datetime.now(UTC).astimezone(VN).date()
        yesterday = today_vn - timedelta(days=1)
        no_data_day = today_vn - timedelta(days=3)  # deliberately left with zero doses
        mixed_day = today_vn - timedelta(days=6)

        db.add(Patient(id=PATIENT_ID, full_name="BUILD-27B Canary Patient (synthetic)", doctor_id=DOCTOR_ID))
        db.add(
            Account(
                id=ACCOUNT_ID, full_name="BUILD-27B Canary Patient (synthetic)",
                email="agent-v2-timeaware-canary-patient1@example.invalid",
                password_hash=hash_password("canary-only-not-a-real-login"),
                role="patient", patient_id=PATIENT_ID, status="active",
            )
        )
        db.add(
            Prescription(
                id="rx-timeaware-canary-1", patient_id=PATIENT_ID, doctor_id=DOCTOR_ID, status="active",
                items=[], start_date=(today_vn - timedelta(days=10)).isoformat(), duration_days=40,
            )
        )
        db.add(
            PrescriptionItem(
                id="item-timeaware-canary-1", prescription_id="rx-timeaware-canary-1", patient_id=PATIENT_ID,
                drug_display_name="Panadol Extra", status="ACTIVE",
            )
        )
        db.commit()

        occurrences: list[tuple[str, date, int]] = []
        # Yesterday: both TAKEN -> "all completed" required verification case.
        occurrences += [("TAKEN", yesterday, 8), ("TAKEN", yesterday, 20)]
        # no_data_day: deliberately nothing seeded here (see verification case 2).
        # mixed_day: one TAKEN, one MISSED -> "mixed" required verification case.
        occurrences += [("TAKEN", mixed_day, 8), ("MISSED", mixed_day, 20)]
        # today + tomorrow + day-after: ordinary SCHEDULED future/today doses.
        occurrences += [("SCHEDULED", today_vn, 8), ("SCHEDULED", today_vn, 20)]
        occurrences += [("SCHEDULED", today_vn + timedelta(days=1), 8)]
        occurrences += [("SCHEDULED", today_vn + timedelta(days=2), 8)]

        for index, (status, local_date, hour) in enumerate(occurrences):
            scheduled_at = _vn_dose(local_date, hour)
            db.add(
                DoseOccurrence(
                    id=f"occ-timeaware-canary-{index}",
                    prescription_item_id="item-timeaware-canary-1",
                    patient_id=PATIENT_ID,
                    scheduled_at=scheduled_at,
                    scheduled_local_date=local_date,
                    scheduled_local_time=time(hour, 0),
                    timezone="Asia/Ho_Chi_Minh",
                    status=status,
                    generation_key=f"gen-timeaware-canary-{index}",
                )
            )
        db.commit()

        jwt = create_access_token(sub=ACCOUNT_ID, role="patient", patient_id=PATIENT_ID)
        print(f"PATIENT_ID={PATIENT_ID}")
        print(f"TODAY_VN={today_vn.isoformat()}")
        print(f"YESTERDAY={yesterday.isoformat()} (all TAKEN)")
        print(f"NO_DATA_DAY={no_data_day.isoformat()} (zero doses, dd/mm={no_data_day.strftime('%d/%m')})")
        print(f"MIXED_DAY={mixed_day.isoformat()} (1 TAKEN + 1 MISSED, dd/mm={mixed_day.strftime('%d/%m')})")
        print("BEGIN_TOKENS_ENV", file=sys.stderr)
        print(f"PATIENT_JWT={jwt}", file=sys.stderr)
        print(f"PATIENT_ID={PATIENT_ID}", file=sys.stderr)
        print(f"NO_DATA_DAY_DDMM={no_data_day.strftime('%d/%m')}", file=sys.stderr)
        print(f"MIXED_DAY_DDMM={mixed_day.strftime('%d/%m')}", file=sys.stderr)
        print("END_TOKENS_ENV", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
