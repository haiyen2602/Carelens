"""BUILD-18: synthetic-only staging test data for Agent V2 live E2E.

Creates exactly the accounts/patients/prescription needed to drive the 9
BUILD-17/18 live HTTP scenarios, and nothing else. Every identifier is a
fixed, obviously-synthetic string (``agent-v2-staging-*``) so it can never be
confused with real production data, and this script must only ever be run
against a staging DATABASE_URL. It creates NO PHI beyond what is invented
here (no import from production, no copy of any real patient).

Idempotent: safe to re-run (deletes and recreates its own fixed IDs only).

Usage (DATABASE_URL, JWT_SECRET point at the staging service's own values)::

    DATABASE_URL="<staging>" JWT_SECRET="<staging>" \
        python scripts/agent_v2/seed_staging_agent_v2_data.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete, select  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, CaregiverLink, DoseOccurrence, Patient, Prescription, PrescriptionItem  # noqa: E402
from backend.services.auth import create_access_token, hash_password  # noqa: E402
from backend.services.prescription.service import duyet_phac_do, tao_phac_do  # noqa: E402
from backend.services.scheduling.runtime_adapter import list_v2_dose_groups  # noqa: E402

DOCTOR_ACCOUNT_ID = "agent-v2-staging-doctor-account"
DOCTOR_ID = "agent-v2-staging-doctor"
CAREGIVER_ACCOUNT_ID = "agent-v2-staging-caregiver-account"
PATIENT1_ACCOUNT_ID = "agent-v2-staging-patient1-account"
PATIENT1_ID = "agent-v2-staging-patient-1"
PATIENT2_ID = "agent-v2-staging-patient-2"  # deliberately NOT linked to the caregiver above

# Confirmed present and query-real in BUILD-7D's own live retrieval smoke.
SEED_DRUG_ID = "paracetamol-kabi-1000mg-frensenius-kabi-48-chai-x-100ml"


def _reset(db) -> None:
    # BUILD-22: also clean up DB Architecture V2 shadow-mode sidecar rows
    # (PrescriptionItem/DoseOccurrence) -- left behind by every prior re-run,
    # these silently doubled (tripled, ...) the dose data the Agent V2 dose
    # tools see and can push token-budget-sensitive scenarios over budget.
    # See report 27-build-22, "Batch A / stale canary data finding" (found on
    # production's equivalent script; fixed here too since staging accumulates
    # the same way across every BUILD-17/18/19/20 re-run).
    db.execute(delete(CaregiverLink).where(CaregiverLink.caregiver_account_id == CAREGIVER_ACCOUNT_ID))
    db.execute(delete(DoseOccurrence).where(DoseOccurrence.patient_id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.execute(delete(PrescriptionItem).where(PrescriptionItem.patient_id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.execute(delete(Prescription).where(Prescription.patient_id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.execute(delete(Account).where(Account.id.in_((DOCTOR_ACCOUNT_ID, CAREGIVER_ACCOUNT_ID, PATIENT1_ACCOUNT_ID))))
    db.execute(delete(Patient).where(Patient.id.in_((PATIENT1_ID, PATIENT2_ID))))
    db.commit()


def main() -> int:
    db = SessionLocal()
    try:
        _reset(db)

        db.add_all(
            [
                Account(
                    id=DOCTOR_ACCOUNT_ID, full_name="Agent V2 Staging Doctor",
                    email="agent-v2-staging-doctor@example.invalid", password_hash=hash_password("staging-only-not-a-real-login"),
                    role="doctor", doctor_id=DOCTOR_ID, status="active",
                ),
                Account(
                    id=CAREGIVER_ACCOUNT_ID, full_name="Agent V2 Staging Caregiver",
                    email="agent-v2-staging-caregiver@example.invalid", password_hash=hash_password("staging-only-not-a-real-login"),
                    role="caregiver", status="active",
                ),
                Account(
                    id=PATIENT1_ACCOUNT_ID, full_name="Agent V2 Staging Patient One",
                    email="agent-v2-staging-patient1@example.invalid", password_hash=hash_password("staging-only-not-a-real-login"),
                    role="patient", patient_id=PATIENT1_ID, status="active",
                ),
                Patient(id=PATIENT1_ID, full_name="Agent V2 Staging Patient One", doctor_id=DOCTOR_ID),
                Patient(id=PATIENT2_ID, full_name="Agent V2 Staging Patient Two (unlinked)", doctor_id=DOCTOR_ID),
                CaregiverLink(
                    id="agent-v2-staging-caregiver-link-1", caregiver_account_id=CAREGIVER_ACCOUNT_ID,
                    patient_id=PATIENT1_ID, relationship="Nguoi than (staging test)", status="accepted",
                ),
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
                    # Must exactly match one of write_path.py's MEAL_CODES
                    # keys (Vietnamese diacritics required) or the V2 shadow
                    # item is left REVIEW_REQUIRED instead of ACTIVE and no
                    # dose occurrence is generated.
                    "thoi_diem_dung": "Sau ăn",
                    "so_vien_moi_lan": 1,
                    "gio_nhac": ["08:00", "20:00"],
                    "doses_per_day": 2,
                }
            ],
            note="BUILD-18 synthetic staging prescription (no real patient data).",
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

        # JWTs are minted here (not returned by any HTTP endpoint) purely for
        # this synthetic staging smoke run; they encode only synthetic ids.
        doctor_jwt = create_access_token(sub=DOCTOR_ACCOUNT_ID, role="doctor", doctor_id=DOCTOR_ID)
        caregiver_jwt = create_access_token(sub=CAREGIVER_ACCOUNT_ID, role="caregiver")
        patient_jwt = create_access_token(sub=PATIENT1_ACCOUNT_ID, role="patient", patient_id=PATIENT1_ID)

        # Printed to stderr with an unambiguous marker line so a caller can
        # redirect/filter this exact block into an env file without this
        # script needing to guess a writable temp path across platforms.
        print("BEGIN_TOKENS_ENV", file=sys.stderr)
        print(f"DOCTOR_JWT={doctor_jwt}", file=sys.stderr)
        print(f"CAREGIVER_JWT={caregiver_jwt}", file=sys.stderr)
        print(f"PATIENT_JWT={patient_jwt}", file=sys.stderr)
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
