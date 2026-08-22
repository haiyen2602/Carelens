"""Mint a fresh JWT for the already-seeded BUILD-27B/27C canary patient
(agent-v2-timeaware-canary-patient-1) -- no DATABASE_URL needed, this is a
pure signing operation. Only JWT_SECRET (production) is required.

Usage:
    JWT_SECRET="<production>" python scripts/agent_v2/mint_time_aware_canary_jwt.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.auth import create_access_token  # noqa: E402

ACCOUNT_ID = "agent-v2-timeaware-canary-patient1-account"
PATIENT_ID = "agent-v2-timeaware-canary-patient-1"

if __name__ == "__main__":
    jwt = create_access_token(sub=ACCOUNT_ID, role="patient", patient_id=PATIENT_ID)
    print(f"PATIENT_JWT={jwt}")
