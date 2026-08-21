"""BUILD-22C: the ONLY way to set MedicationSafetyPolicy.review_status=REVIEWED.

Run this ONLY at the explicit direction of a real clinical reviewer, and
pass their real name/role as --reviewed-by. This script has no way to
verify clinical authority -- that responsibility belongs entirely to
whoever runs it. Never invent or default a reviewer identity.

Usage::

    DATABASE_URL="<production, via a temporary tcp-proxy>" \
        python scripts/agent_v2/approve_safety_policy.py \
        --policy-id <id printed by propose_safety_policy.py> \
        --reviewed-by "<real name/role of the human clinical reviewer>"
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.db.base import SessionLocal  # noqa: E402
from backend.services.safety_policy_domain.review_workflow import approve_policy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policy-id", required=True)
    parser.add_argument("--reviewed-by", required=True, help="Real name/role of the human clinical reviewer. Never a placeholder.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        policy = approve_policy(db, policy_id=args.policy_id, reviewed_by=args.reviewed_by, reviewed_at=datetime.now(UTC))
        db.commit()
        print(f"REVIEWED: id={policy.id} reviewed_by={policy.reviewed_by!r} reviewed_at={policy.reviewed_at.isoformat()}")
        print(f"  scope={policy.scope_type}:{policy.scope_id} risk_type={policy.risk_type}")
        print(f"  risk_level={policy.risk_level} action_policy={policy.action_policy}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
