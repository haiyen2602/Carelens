"""BUILD-22C: create a REAL, non-fabricated MISSED DoseOccurrence for the
now-REVIEWED Vitamin C safety policy, using the app's own real code paths
(tao_phac_do/duyet_phac_do for the prescription and dose generation,
transition_v2_dose_group -- the same function the real patient dose API
uses -- for the MISSED transition). No row is hand-inserted; every row here
is produced exactly the way the running application produces it.

Idempotent-ish: creates a fresh prescription each run (does not attempt to
reuse a prior one), since a MISSED transition is a one-way state change.

Usage::

    DATABASE_URL="<production, via a temporary tcp-proxy>" \
        python scripts/agent_v2/seed_safety_safe_canary_dose.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.db.base import SessionLocal  # noqa: E402
from backend.services.prescription.service import duyet_phac_do, tao_phac_do  # noqa: E402
from backend.services.scheduling.runtime_adapter import list_v2_dose_groups, transition_v2_dose_group  # noqa: E402

PATIENT_ID = "agent-v2-canary-patient-1"
DOCTOR_ID = "agent-v2-canary-doctor"
VITAMIN_C_DRUG_ID = "vitamin-c-100mg-vidipha-200v"  # legacy_drug_id for the reviewed product; see note below


def main() -> int:
    db = SessionLocal()
    try:
        today = datetime.now(UTC).date().isoformat()
        presc = tao_phac_do(
            db,
            patient_id=PATIENT_ID,
            doctor_id=DOCTOR_ID,
            items=[
                {
                    "drug_id": VITAMIN_C_DRUG_ID,
                    "lieu_dung": "1 vien/lan",
                    "thoi_diem_dung": "Sau ăn",
                    "so_vien_moi_lan": 1,
                    "gio_nhac": ["08:00"],
                    "doses_per_day": 1,
                }
            ],
            note="BUILD-22C synthetic production-canary Safety SAFE test prescription (no real patient data).",
            start_date=today,
            duration_days=1,
        )
        presc, so_lieu = duyet_phac_do(db, presc.id, doctor_id=DOCTOR_ID)
        db.commit()
        print(f"PRESCRIPTION: id={presc.id} status={presc.status} doses_generated={so_lieu}")

        groups = [g for g in list_v2_dose_groups(db, patient_id=PATIENT_ID) if VITAMIN_C_DRUG_ID in str(g.expected_items)]
        if not groups:
            # legacy_drug_id may not literally appear in expected_items text; fall back to today's newest group
            groups = sorted(list_v2_dose_groups(db, patient_id=PATIENT_ID), key=lambda g: g.scheduled_at, reverse=True)[:1]
        target = groups[0]
        print(f"DOSE_GROUP: id={target.id} status={target.status} scheduled_at={target.scheduled_at.isoformat()}")

        updated = transition_v2_dose_group(
            db,
            dose_group_id=target.id,
            target_status="MISSED",
            event_at=datetime.now(UTC),
            source="BUILD22C_CANARY_SAFETY_SAFE_TEST",  # honest: this is a controlled test transition, not a real patient/system event
            actor_type="SYSTEM",
            actor_id="build-22c-canary-setup",
        )
        db.commit()
        print(f"TRANSITIONED: dose_group_id={updated.id} status={updated.status} occurrence_ids={updated.occurrence_ids}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
