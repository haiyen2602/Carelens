"""BUILD-22: additive canary-expansion fixture (batch 2 and batch 3).

Extends BUILD-21's ``seed_production_canary_data.py`` (which remains the
source of the doctor + patient-1 + bare patient-2 identities) with two more
small, obviously-synthetic batches, so ``AGENT_CANARY_ALLOWLIST`` can be
expanded incrementally with real accounts to monitor rather than growing by
guesswork:

  batch 2: two more patient accounts (agent-v2-canary-patient3/4)
  batch 3: one more doctor account (agent-v2-canary-doctor2), with
           patient-4 reassigned to them, to exercise a second treating
           doctor's own authorization path.

Every identifier is a fixed, obviously-synthetic string
(``agent-v2-canary-*``), same convention as BUILD-21. Idempotent: safe to
re-run (deletes and recreates its own fixed IDs only). Must only ever be run
against a PRODUCTION DATABASE_URL as part of this same controlled canary.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, DoctorWatch, DoseOccurrence, Patient, Prescription, PrescriptionItem  # noqa: E402
from backend.services.auth import create_access_token, hash_password  # noqa: E402
from backend.services.prescription.service import duyet_phac_do, tao_phac_do  # noqa: E402

DOCTOR_ID = "agent-v2-canary-doctor"  # BUILD-21's doctor, reused as batch 2's treating doctor
DOCTOR2_ACCOUNT_ID = "agent-v2-canary-doctor2-account"
DOCTOR2_ID = "agent-v2-canary-doctor2"

PATIENT3_ACCOUNT_ID = "agent-v2-canary-patient3-account"
PATIENT3_ID = "agent-v2-canary-patient-3"
PATIENT4_ACCOUNT_ID = "agent-v2-canary-patient4-account"
PATIENT4_ID = "agent-v2-canary-patient-4"

SEED_DRUG_ID = "paracetamol-kabi-1000mg-frensenius-kabi-48-chai-x-100ml"

ALL_PATIENT_IDS = (PATIENT3_ID, PATIENT4_ID)
ALL_ACCOUNT_IDS = (DOCTOR2_ACCOUNT_ID, PATIENT3_ACCOUNT_ID, PATIENT4_ACCOUNT_ID)


def _reset(db) -> None:
    # BUILD-22: also delete DoseOccurrence/PrescriptionItem (V2 shadow-mode
    # sidecar rows) -- see seed_production_canary_data.py's _reset() for why.
    db.execute(delete(DoseOccurrence).where(DoseOccurrence.patient_id.in_(ALL_PATIENT_IDS)))
    db.execute(delete(PrescriptionItem).where(PrescriptionItem.patient_id.in_(ALL_PATIENT_IDS)))
    db.execute(delete(Prescription).where(Prescription.patient_id.in_(ALL_PATIENT_IDS)))
    db.execute(delete(DoctorWatch).where(DoctorWatch.patient_id.in_(ALL_PATIENT_IDS)))
    db.execute(delete(Account).where(Account.id.in_(ALL_ACCOUNT_IDS)))
    db.execute(delete(Patient).where(Patient.id.in_(ALL_PATIENT_IDS)))
    db.commit()


def _prescribe(db, *, patient_id: str, doctor_id: str) -> str:
    today = datetime.now(UTC).date().isoformat()
    presc = tao_phac_do(
        db,
        patient_id=patient_id,
        doctor_id=doctor_id,
        items=[
            {
                "drug_id": SEED_DRUG_ID,
                "lieu_dung": "1 vien/lan",
                "thoi_diem_dung": "Sau ăn",  # MUST match write_path.py's MEAL_CODES exactly (with the "ă"
                # diacritic) -- a plain-ASCII "Sau an" silently fails meal-text validation, which silently
                # marks the item REVIEW_REQUIRED instead of ACTIVE, which silently excludes it from V2
                # dose-occurrence generation. Found live in BUILD-22 batch 2 (see report 27-build-22,
                # "Batch B / seed script diacritics bug"): legacy dose_event generation is not gated the
                # same way, so `doses_generated=N` printed successfully while zero V2 occurrences existed.
                "so_vien_moi_lan": 1,
                "gio_nhac": ["08:00", "20:00"],
                "doses_per_day": 2,
            }
        ],
        note="BUILD-22 synthetic production-canary-expansion prescription (no real patient data).",
        start_date=today,
        duration_days=3,
    )
    presc, so_lieu = duyet_phac_do(db, presc.id, doctor_id=doctor_id)
    print(f"PRESCRIPTION[{patient_id}]: id={presc.id} status={presc.status} doses_generated={so_lieu}")
    return presc.id


def main() -> int:
    db = SessionLocal()
    try:
        _reset(db)

        db.add_all(
            [
                Account(
                    id=DOCTOR2_ACCOUNT_ID, full_name="Agent V2 Canary Doctor Two",
                    email="agent-v2-canary-doctor2@example.invalid", password_hash=hash_password("canary-only-not-a-real-login"),
                    role="doctor", doctor_id=DOCTOR2_ID, status="active",
                ),
                Account(
                    id=PATIENT3_ACCOUNT_ID, full_name="Agent V2 Canary Patient Three",
                    email="agent-v2-canary-patient3@example.invalid", password_hash=hash_password("canary-only-not-a-real-login"),
                    role="patient", patient_id=PATIENT3_ID, status="active",
                ),
                Account(
                    id=PATIENT4_ACCOUNT_ID, full_name="Agent V2 Canary Patient Four",
                    email="agent-v2-canary-patient4@example.invalid", password_hash=hash_password("canary-only-not-a-real-login"),
                    role="patient", patient_id=PATIENT4_ID, status="active",
                ),
                # batch 2: treated by BUILD-21's existing canary doctor
                Patient(id=PATIENT3_ID, full_name="Agent V2 Canary Patient Three", doctor_id=DOCTOR_ID),
                # batch 3: treated by the NEW second canary doctor
                Patient(id=PATIENT4_ID, full_name="Agent V2 Canary Patient Four", doctor_id=DOCTOR2_ID),
            ]
        )
        db.commit()

        # BUILD-22: Agent V2's own read-authorization boundary
        # (backend/services/agent_authorization.py) checks DoctorWatch, which
        # is deliberately a DIFFERENT, opt-in relationship from
        # Patient.doctor_id (the "responsible doctor") -- a doctor is not
        # automatically granted Agent V2 read access to every patient they
        # are responsible for; they must be explicitly watching. Without this
        # row, doctor2 was found live (BUILD-22 batch 3) to be denied even
        # for their own patient -- correct fail-closed behavior given an
        # incomplete fixture, not a product defect, but this line is needed
        # to exercise the POSITIVE "doctor reads their watched patient" path
        # at all (every prior canary doctor query had been a denial case).
        db.add(DoctorWatch(doctor_id=DOCTOR2_ID, patient_id=PATIENT4_ID))
        db.commit()

        _prescribe(db, patient_id=PATIENT3_ID, doctor_id=DOCTOR_ID)
        _prescribe(db, patient_id=PATIENT4_ID, doctor_id=DOCTOR2_ID)

        patient3_jwt = create_access_token(sub=PATIENT3_ACCOUNT_ID, role="patient", patient_id=PATIENT3_ID)
        patient4_jwt = create_access_token(sub=PATIENT4_ACCOUNT_ID, role="patient", patient_id=PATIENT4_ID)
        doctor2_jwt = create_access_token(sub=DOCTOR2_ACCOUNT_ID, role="doctor", doctor_id=DOCTOR2_ID)

        print("BEGIN_TOKENS_ENV", file=sys.stderr)
        print(f"PATIENT3_JWT={patient3_jwt}", file=sys.stderr)
        print(f"PATIENT4_JWT={patient4_jwt}", file=sys.stderr)
        print(f"DOCTOR2_JWT={doctor2_jwt}", file=sys.stderr)
        print(f"PATIENT3_ACCOUNT_ID={PATIENT3_ACCOUNT_ID}", file=sys.stderr)
        print(f"PATIENT4_ACCOUNT_ID={PATIENT4_ACCOUNT_ID}", file=sys.stderr)
        print(f"DOCTOR2_ACCOUNT_ID={DOCTOR2_ACCOUNT_ID}", file=sys.stderr)
        print("END_TOKENS_ENV", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
