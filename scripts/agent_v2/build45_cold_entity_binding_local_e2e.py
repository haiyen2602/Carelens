"""BUILD-45 Candidate A: real local E2E for cold drug entity binding.

Real Postgres, real HTTP-equivalent route call, real model calls -- NO
seeded ConversationState (unlike BUILD-43's own production validation,
which HAD to seed state because this exact cold-binding gap was still
open at the time). This script's whole point is to prove the natural
flow now works end to end without that workaround.

Usage:

    python scripts/agent_v2/build45_cold_entity_binding_local_e2e.py
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
from backend.services.agent_conversation_state import AgentConversationStateStore  # noqa: E402

get_settings.cache_clear()

PATIENT_ID = "agent-v2-staging-patient-1"
ACTOR_ID = "agent-v2-staging-patient1-account"
RUN_TAG = uuid.uuid4().hex[:8]
CONV_ID = f"build45-coldentity-{RUN_TAG}"
FAILURES: list[str] = []


def _actor() -> CurrentUser:
    return CurrentUser(id=ACTOR_ID, role="patient", patient_id=PATIENT_ID, doctor_id=None)


def _orchestrate(message: str):
    db = SessionLocal()
    try:
        request = AgentV2OrchestrateRequest(patient_id=PATIENT_ID, message=message, conversation_id=CONV_ID)
        return run_agent_orchestration(request, db=db, actor=_actor())
    finally:
        db.close()


def _check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{label}: {detail}")


def main() -> int:
    print(f"BUILD-45 Candidate A local E2E -- real Postgres, real model, conversation_id={CONV_ID}\n")

    # "Berocca Bayer" -- a real catalog entry confirmed (via a random sample
    # of the real catalog, not assumed) to resolve UNIQUELY under this
    # build's stricter uniqueness floor -- unlike a bare, popular ingredient
    # name like "Paracetamol", which genuinely has multiple real SKUs in
    # this catalog (different manufacturers/forms) and correctly stays
    # unresolved even after this fix. This E2E deliberately uses a case the
    # fix is designed to help, not a case that was always going to fail
    # safely either way.
    print("=== Step 1: fresh conversation, cold drug question (real, natural phrasing) ===")
    turn1 = _orchestrate("Thuốc Berocca Bayer dùng để làm gì?")
    print(f"  status={turn1.status} intent={turn1.intent} tools={turn1.tools}")
    print(f"  reply={turn1.reply!r}")
    _check("turn completed", turn1.status == "COMPLETED", turn1.status)

    db = SessionLocal()
    try:
        state = AgentConversationStateStore().load(db, actor_id=ACTOR_ID, patient_id=PATIENT_ID, conversation_id=CONV_ID)
    finally:
        db.close()
    print(f"  persisted active_entity = {state.active_entity}")
    _check(
        "active_entity established on the FIRST turn (the fix)",
        state.active_entity is not None and state.active_entity.type == "drug",
        str(state.active_entity),
    )
    if state.active_entity is not None:
        _check(
            "active_entity has a real display name, not a raw id",
            state.active_entity.display_name is not None and state.active_entity.display_name != state.active_entity.id,
            state.active_entity.display_name,
        )

    print("\n=== Step 2: natural pronoun/attribute follow-up (no button, no re-naming the drug) ===")
    turn2 = _orchestrate("Tác dụng phụ thì sao?")
    print(f"  status={turn2.status} intent={turn2.intent} tools={turn2.tools}")
    print(f"  reply={turn2.reply!r}")
    _check("turn completed", turn2.status == "COMPLETED", turn2.status)
    _check(
        "TRUE_FOLLOWUP inherited the entity -- reply is actually about the drug, not a generic decline",
        bool(turn2.reply) and "berocca" in turn2.reply.lower(),
        turn2.reply,
    )
    _check(
        "no GROUNDING_FAILURE on the inherited-entity turn",
        turn2.status != "FAILED" and (turn2.citations or turn2.tools),
        f"citations={turn2.citations} tools={turn2.tools}",
    )

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} FAILURE(S)")
        for item in FAILURES:
            print(f"  - {item}")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
