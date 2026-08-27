"""BUILD-45 Candidate B: real local E2E for topic persistence coverage.

Real Postgres, real HTTP-equivalent route call, real model calls -- no
seeded ConversationState. Proves the natural flow: a disease/topic
question persists active_topic, a pronoun follow-up inherits it, and
switching to a drug question correctly clears the stale topic.

Usage:

    python scripts/agent_v2/build45_topic_persistence_local_e2e.py
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
CONV_ID = f"build45-topic-{RUN_TAG}"
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


def _state():
    db = SessionLocal()
    try:
        return AgentConversationStateStore().load(db, actor_id=ACTOR_ID, patient_id=PATIENT_ID, conversation_id=CONV_ID)
    finally:
        db.close()


def _check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{label}: {detail}")


def main() -> int:
    print(f"BUILD-45 Candidate B local E2E -- real Postgres, real model, conversation_id={CONV_ID}\n")

    print("=== Step 1: fresh conversation, explicit disease/topic question ===")
    turn1 = _orchestrate("Viêm gan B là bệnh gì?")
    print(f"  status={turn1.status} intent={turn1.intent}")
    _check("turn completed", turn1.status == "COMPLETED", turn1.status)
    state = _state()
    print(f"  persisted active_topic = {state.active_topic}")
    _check(
        "active_topic established on the first turn (the fix -- 'la benh gi' tail shape)",
        state.active_topic is not None,
        str(state.active_topic),
    )

    print("\n=== Step 2: pronoun follow-up, no button, no re-naming the disease ===")
    turn2 = _orchestrate("Triệu chứng của nó là gì?")
    print(f"  status={turn2.status} intent={turn2.intent}")
    print(f"  reply={turn2.reply!r}")
    _check("turn completed", turn2.status == "COMPLETED", turn2.status)
    _check(
        "TRUE_FOLLOWUP inherited the topic -- reply is actually about viêm gan B",
        bool(turn2.reply) and ("gan" in turn2.reply.lower() or "viêm" in turn2.reply.lower()),
        turn2.reply,
    )
    state = _state()
    topic_name = state.active_topic.canonical_name if state.active_topic else None
    _check("active_topic still set after the follow-up", state.active_topic is not None, str(state.active_topic))
    _check(
        "active_topic is still the ORIGINAL disease, not corrupted by the "
        "pronoun+filler tail of this compound follow-up question",
        topic_name == "Viêm gan B",
        f"expected 'Viêm gan B', got {topic_name!r} "
        "(a real bug found here: 'Triệu chứng của nó là gì?' used to "
        "corrupt active_topic to literally 'nó là gì')",
    )

    print("\n=== Step 3: switch to an unrelated drug question -- stale topic must clear ===")
    turn3 = _orchestrate("Paracetamol dùng để làm gì?")
    print(f"  status={turn3.status} intent={turn3.intent} tools={turn3.tools}")
    _check("turn completed", turn3.status == "COMPLETED", turn3.status)
    state = _state()
    print(f"  active_topic={state.active_topic} active_entity={state.active_entity}")
    _check(
        "stale disease topic cleared on real topic switch",
        state.active_topic is None,
        str(state.active_topic),
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
