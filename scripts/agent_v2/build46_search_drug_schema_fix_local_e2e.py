"""BUILD-46 Fix A: real local E2E re-verification of the search_drug
schema fix.

Real Postgres + real model, no seeded state. Repeats the EXACT scenario
that produced a live TOOL_ERROR during BUILD-45's own production
validation ("Thuốc Berocca Bayer dùng để làm gì?" -> "Tác dụng phụ thì
sao?") N times with fresh conversations, since the underlying failure is
model tool-choice non-determinism, not a deterministic reproduction --
a single passing run proves nothing on its own.

Usage:

    python scripts/agent_v2/build46_search_drug_schema_fix_local_e2e.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if __name__ == "__main__":
    os.environ.setdefault("AGENT_RUNTIME_ENABLED", "true")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.api.agent_v2_routes import run_agent_orchestration  # noqa: E402
from backend.api.security import CurrentUser  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.models.schemas import AgentV2OrchestrateRequest  # noqa: E402

get_settings.cache_clear()

PATIENT_ID = "agent-v2-staging-patient-1"
ACTOR_ID = "agent-v2-staging-patient1-account"
N_REPEATS = 8


def _actor() -> CurrentUser:
    return CurrentUser(id=ACTOR_ID, role="patient", patient_id=PATIENT_ID, doctor_id=None)


def _orchestrate(message: str, conversation_id: str):
    db = SessionLocal()
    try:
        request = AgentV2OrchestrateRequest(patient_id=PATIENT_ID, message=message, conversation_id=conversation_id)
        return run_agent_orchestration(request, db=db, actor=_actor())
    finally:
        db.close()


def main() -> int:
    print(f"BUILD-46 Fix A local E2E -- {N_REPEATS} repeated real attempts, real Postgres, real model\n")

    tool_error_count = 0
    completed_count = 0
    other_fail_count = 0
    model_call_counts = []
    tool_call_counts = []

    for i in range(N_REPEATS):
        conv = f"build46-fixA-{uuid.uuid4().hex[:8]}"
        r1 = _orchestrate("Thuốc Berocca Bayer dùng để làm gì?", conv)
        r2 = _orchestrate("Tác dụng phụ thì sao?", conv)
        model_call_counts.append((r1.status, r2.status))
        tool_call_counts.append((r1.tools, r2.tools))

        if r2.status == "FAILED":
            other_fail_count += 1
            print(f"  run {i + 1}: turn1={r1.status}/{r1.tools}  turn2=FAILED/{r2.tools}  reply={r2.reply!r}")
        else:
            completed_count += 1
            berocca_mentioned = "berocca" in r2.reply.lower()
            print(
                f"  run {i + 1}: turn1={r1.status}/{r1.tools}  turn2={r2.status}/{r2.tools}  "
                f"berocca_mentioned={berocca_mentioned}"
            )

    print(f"\n{'=' * 60}")
    print(f"turn2 COMPLETED: {completed_count}/{N_REPEATS}")
    print(f"turn2 FAILED (any reason): {other_fail_count}/{N_REPEATS}")
    print(f"TOOL_ERROR specifically: {tool_error_count} (not distinguished from other FAILED above without a DB read)")

    if other_fail_count == 0:
        print("\nRESULT: ALL REPEATS COMPLETED -- 0 TOOL_ERROR observed post-fix")
        return 0
    print(f"\nRESULT: {other_fail_count} FAILURE(S) OUT OF {N_REPEATS} -- see per-run detail above")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
