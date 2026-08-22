"""BUILD-29: a fixed, obviously-synthetic admin Account for production
verification of the new /admin/tickets* endpoints and the _require_admin
security fix -- same convention as BUILD-27B's
``seed_production_time_aware_canary.py`` (fixed, unmistakably-synthetic ID,
idempotent delete+recreate, no real PHI).

This account has no linked patient/doctor -- it exists only to mint a real
admin-role JWT for verification, never to log in through the actual UI.

Usage (run inside the production environment, e.g. via
``railway run --service VMEC-04/BE --environment production python
scripts/agent_v2/seed_feedback_admin_canary.py`` -- this injects
DATABASE_URL server-side; the script itself never prints it)::

    python scripts/agent_v2/seed_feedback_admin_canary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account  # noqa: E402
from backend.services.auth import hash_password  # noqa: E402

ACCOUNT_ID = "agent-v2-feedback-canary-admin-1"


def main() -> int:
    db = SessionLocal()
    try:
        db.execute(delete(Account).where(Account.id == ACCOUNT_ID))
        db.commit()
        db.add(
            Account(
                id=ACCOUNT_ID, full_name="BUILD-29 Canary Admin (synthetic)",
                email="agent-v2-feedback-canary-admin1@example.invalid",
                password_hash=hash_password("canary-only-not-a-real-login"),
                role="admin", status="active",
            )
        )
        db.commit()
        print(f"Seeded canary admin account: {ACCOUNT_ID}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
