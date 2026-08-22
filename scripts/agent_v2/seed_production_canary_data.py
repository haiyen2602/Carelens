"""BUILD-21: minimal synthetic-only production canary test data for Agent V2.

Creates exactly the accounts/patient/prescription needed to drive BUILD-21's
controlled canary UAT (drug info, doses, prescription, Safety SAFE/BLOCKED,
Doctor Handoff, checkpoint/idempotency, authorization/allowlist), and
nothing else. Every identifier is a fixed, obviously-synthetic string
(``agent-v2-canary-*``) so it can never be confused with a real patient, and
this script must only ever be run against a PRODUCTION DATABASE_URL as part
of a canary this deliberately controlled. It creates NO PHI beyond what is
invented here (no import from any real patient row).

Deliberately smaller than BUILD-18's ``seed_staging_agent_v2_data.py``: one
patient (the actual canary account, put on ``AGENT_CANARY_ALLOWLIST``) plus
one bare second patient (existence only, for the cross-patient authorization
check) -- "a very small allowlist", not a full staging-style fixture set.

Idempotent: safe to re-run (deletes and recreates its own fixed IDs only).

Usage (DATABASE_URL, JWT_SECRET point at PRODUCTION's own values, via a
temporary TCP proxy, deleted immediately after use)::

    DATABASE_URL="<production>" JWT_SECRET="<production>" \
        python scripts/agent_v2/seed_production_canary_data.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, DoseOccurrence, Patient, Prescription, PrescriptionItem  # noqa: E402
from backend.services.auth import create_access_token, hash_password  # noqa: E402
from backend.services.prescription.service import duyet_phac_do, tao_phac_do  # noqa: E402
from backend.services.scheduling.runtime_adapter import list_v2_dose_groups  # noqa: E402

DOCTOR_ACCOUNT_ID = "agent-v2-canary-doctor-account"
DOCTOR_ID = "agent-v2-canary-doctor"
PATIENT1_ACCOUNT_ID = "agent-v2-canary-patient1-account"
PATIENT1_ID = "agent-v2-canary-patient-1"
PATIENT2_ID = "agent-v2-canary-patient-2"  # bare row only -- cross-patient denial check

# Same drug used by BUILD-18's staging fixture; present in the canonical V2
# catalog this build just restored onto production from staging (identical
# source data, see report 26-build-21).
SEED_DRUG_ID = "paracetamol-kabi-1000mg-frensenius-kabi-48-chai-x-100ml"


def _reset(db) -> None:
    # BUILD-22 fix: the legacy ``Prescription``/``dose_event`` rows this
    # deletes are not the only schedule this fixture creates -- shadow mode
    # (PRESCRIPTION_V2_MODE=shadow) also writes DB Architecture V2 sidecar
    # rows (``PrescriptionItem``/``DoseOccurrence``) that were NOT cleaned up
    # here before. Every re-run therefore left the previous run's V2
    # occurrences orphaned but still live and still returned by
    # ``list_v2_dose_groups``/the Agent V2 dose tools -- caught when BUILD-22
    # re-ran this script and the resulting DOUBLED dose-occurrence set pushed
    # the prescription_multi_tool scenario over its token budget (see report
    # 27-build-22, "Batch A / stale canary data finding"). Deleting these
    # explicitly, in child-before-parent order, keeps every re-run genuinely
    # idempotent instead of merely appearing to be.
    db.execute(delete(DoseOccurrence).where(DoseOccurrence.patient_id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.execute(delete(PrescriptionItem).where(PrescriptionItem.patient_id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.execute(delete(Prescription).where(Prescription.patient_id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.execute(delete(Account).where(Account.id.in_((DOCTOR_ACCOUNT_ID, PATIENT1_ACCOUNT_ID))))
    db.execute(delete(Patient).where(Patient.id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.commit()


def main() -> int:
    db = SessionLocal()
    try:
        _reset(db)

        db.add_all(
            [
                Account(
                    id=DOCTOR_ACCOUNT_ID, full_name="Agent V2 Canary Doctor",
                    email="agent-v2-canary-doctor@example.invalid", password_hash=hash_password("canary-only-not-a-real-login"),
                    role="doctor", doctor_id=DOCTOR_ID, status="active",
                ),
                Account(
                    id=PATIENT1_ACCOUNT_ID, full_name="Agent V2 Canary Patient One",
                    email="agent-v2-canary-patient1@example.invalid", password_hash=hash_password("canary-only-not-a-real-login"),
                    role="patient", patient_id=PATIENT1_ID, status="active",
                ),
                Patient(id=PATIENT1_ID, full_name="Agent V2 Canary Patient One", doctor_id=DOCTOR_ID),
                Patient(id=PATIENT2_ID, full_name="Agent V2 Canary Patient Two (unlinked)", doctor_id=DOCTOR_ID),
            ]
        )
        db.commit()

        today = datetime.now(UTC).date().isoformat()
        presc = tao_phac_do(
            db,
            patient_id=PATIENT1_ID,
            doctor_id=DOCTOR_ID,
            items=[
                {
                    "drug_id": SEED_DRUG_ID,
                    "lieu_dung": "1 vien/lan",
                    "thoi_diem_dung": "Sau ăn",
                    "so_vien_moi_lan": 1,
                    "gio_nhac": ["08:00", "20:00"],
                    "doses_per_day": 2,
                }
            ],
            note="BUILD-21 synthetic production-canary prescription (no real patient data).",
            start_date=today,
            duration_days=3,
        )
        presc, so_lieu = duyet_phac_do(db, presc.id, doctor_id=DOCTOR_ID)
        print(f"PRESCRIPTION: id={presc.id} status={presc.status} doses_generated={so_lieu}")

        groups = list_v2_dose_groups(db, patient_id=PATIENT1_ID)
        today_group = next((g for g in groups if g.scheduled_at.date() == datetime.now(UTC).date()), None)
        print(f"V2_DOSE_GROUPS: total={len(groups)}")
        if today_group is not None:
            print(f"TODAY_DOSE_GROUP_ID: {today_group.id} status={today_group.status}")
        else:
            print("TODAY_DOSE_GROUP_ID: NONE")

        doctor_jwt = create_access_token(sub=DOCTOR_ACCOUNT_ID, role="doctor", doctor_id=DOCTOR_ID)
        patient_jwt = create_access_token(sub=PATIENT1_ACCOUNT_ID, role="patient", patient_id=PATIENT1_ID)

        print("BEGIN_TOKENS_ENV", file=sys.stderr)
        print(f"DOCTOR_JWT={doctor_jwt}", file=sys.stderr)
        print(f"PATIENT_JWT={patient_jwt}", file=sys.stderr)
        print(f"PATIENT1_ACCOUNT_ID={PATIENT1_ACCOUNT_ID}", file=sys.stderr)
        print(f"PATIENT1_ID={PATIENT1_ID}", file=sys.stderr)
        print(f"PATIENT2_ID={PATIENT2_ID}", file=sys.stderr)
        print(f"PRESCRIPTION_ID={presc.id}", file=sys.stderr)
        print(f"TODAY_DOSE_GROUP_ID={today_group.id if today_group else ''}", file=sys.stderr)
        print("END_TOKENS_ENV", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
