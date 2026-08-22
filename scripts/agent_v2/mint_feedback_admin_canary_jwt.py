"""Mint a fresh JWT for the BUILD-29 canary admin account (must already be
seeded via seed_feedback_admin_canary.py). No DATABASE_URL needed -- this is
a pure signing operation, only JWT_SECRET (production) is required.

Usage:
    JWT_SECRET="<production>" python scripts/agent_v2/mint_feedback_admin_canary_jwt.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.auth import create_access_token  # noqa: E402

ACCOUNT_ID = "agent-v2-feedback-canary-admin-1"

if __name__ == "__main__":
    jwt = create_access_token(sub=ACCOUNT_ID, role="admin")
    print(f"ADMIN_JWT={jwt}")
