"""BUILD-24: minimal synthetic accounts to directly exercise the
AGENT_ROLLOUT_PERCENTAGE bucketing mechanism, deliberately NOT on
AGENT_CANARY_ALLOWLIST -- their behavior is governed purely by the
percentage bucket, isolating that code path from the allowlist path.

Account ids were chosen offline (hashlib.sha256(id) % 100) so their bucket
assignment is known in advance:
  build24-percentage-probe-6  -> bucket 1  (inside a 5% rollout)
  build24-percentage-probe-4  -> bucket 4  (inside a 5% rollout)
  build24-percentage-probe-2  -> bucket 98 (outside a 5% rollout)

Idempotent. Synthetic only, no real patient data.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, Patient  # noqa: E402
from backend.services.auth import create_access_token, hash_password  # noqa: E402

PROBES = [
    ("build24-percentage-probe-6", "build24-percentage-probe-patient-6", 1),
    ("build24-percentage-probe-4", "build24-percentage-probe-patient-4", 4),
    ("build24-percentage-probe-2", "build24-percentage-probe-patient-2", 98),
]


def main() -> int:
    db = SessionLocal()
    try:
        account_ids = [p[0] for p in PROBES]
        patient_ids = [p[1] for p in PROBES]
        db.execute(delete(Account).where(Account.id.in_(account_ids)))
        db.execute(delete(Patient).where(Patient.id.in_(patient_ids)))
        db.commit()

        for account_id, patient_id, bucket in PROBES:
            db.add(Account(
                id=account_id, full_name=f"Build24 Rollout Probe (bucket {bucket})",
                email=f"{account_id}@example.invalid", password_hash=hash_password("probe-only-not-a-real-login"),
                role="patient", patient_id=patient_id, status="active",
            ))
            db.add(Patient(id=patient_id, full_name=f"Build24 Rollout Probe (bucket {bucket})", doctor_id=None))
        db.commit()

        for account_id, patient_id, bucket in PROBES:
            jwt = create_access_token(sub=account_id, role="patient", patient_id=patient_id)
            print(f"PROBE bucket={bucket} account={account_id} patient={patient_id}", file=sys.stderr)
            print(f"JWT_{bucket}={jwt}", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
