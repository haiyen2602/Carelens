"""BUILD-22C: stage a DRAFT MedicationSafetyPolicy for real clinical review.

This only ever lands the row in ``REVIEW_REQUIRED`` (see
backend/services/safety_policy_domain/review_workflow.py) -- it cannot, by
itself, unlock a SAFE disposition for any patient. It is safe to run against
production directly: the effect is inert until a real reviewer runs
``approve_safety_policy.py`` against the printed policy id.

Content in this script is drawn from an authoritative external reference
cited in --source-reference; it is NOT clinical judgment invented by this
script or by whoever runs it -- that judgment is left entirely to the real
reviewer who decides whether to approve it.

Usage::

    DATABASE_URL="<production, via a temporary tcp-proxy>" \
        python scripts/agent_v2/propose_safety_policy.py \
        --scope-type DRUG_PRODUCT --scope-id <drug_product.id> \
        --risk-type MISSED_DOSE \
        --risk-level LOW \
        --action-policy SAFE_NO_ACTION_NEEDED \
        --source-type EXTERNAL_REFERENCE \
        --source-reference "MedlinePlus Ascorbic Acid (Vitamin C) Drug Information, https://medlineplus.gov/druginfo/meds/a682583.html -- missed-dose guidance: no cause for concern, resume normal schedule, do not double dose" \
        --created-by "build-22c-draft"
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.db.base import SessionLocal  # noqa: E402
from backend.services.safety_policy_domain.review_workflow import ProposedPolicy, propose_policy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scope-type", required=True, choices=["DRUG_PRODUCT", "INGREDIENT", "CATEGORY"])
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--risk-type", required=True, choices=["MISSED_DOSE", "DELAYED_DOSE"])
    parser.add_argument("--risk-level", required=True)
    parser.add_argument("--action-policy", required=True)
    parser.add_argument("--source-type", required=True)
    parser.add_argument("--source-reference", required=True)
    parser.add_argument("--created-by", required=True)
    parser.add_argument("--policy-version", type=int, default=1)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        proposal = ProposedPolicy(
            scope_type=args.scope_type,
            scope_id=args.scope_id,
            risk_type=args.risk_type,
            risk_level=args.risk_level,
            action_policy=args.action_policy,
            source_type=args.source_type,
            source_reference=args.source_reference,
            created_by=args.created_by,
            valid_from=datetime.now(UTC),
            policy_version=args.policy_version,
        )
        policy = propose_policy(db, proposal=proposal)
        db.commit()
        print(f"PROPOSED: id={policy.id} review_status={policy.review_status}")
        print(f"  scope={policy.scope_type}:{policy.scope_id} risk_type={policy.risk_type}")
        print(f"  risk_level={policy.risk_level} action_policy={policy.action_policy}")
        print(f"  source={policy.source_type}: {policy.source_reference}")
        print("NEXT STEP: a real clinical reviewer must run approve_safety_policy.py "
              f"--policy-id {policy.id} --reviewed-by \"<real name/role>\" to activate this.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
