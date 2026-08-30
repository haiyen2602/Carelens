"""BUILD-46 Fix B: real local E2E for handoff dedup type isolation
(spec scenarios D, E, F).

Real Postgres, real ``run_agent_orchestration`` calls -- the exact
production shape that produced the live bug (BUILD-44's own production
validation): a real SAFETY trigger, followed by a real USER_REQUEST
trigger, must never reuse/mislabel the SAFETY row.

Usage:

    python scripts/agent_v2/build46_handoff_type_isolation_local_e2e.py
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

from sqlalchemy import select  # noqa: E402

from backend.agents.v2.answerability import MAX_CLARIFICATION_ATTEMPTS, HandoffType, handoff_type_for  # noqa: E402
from backend.agents.v2.conversation_state import ConversationState  # noqa: E402
from backend.api.agent_v2_routes import run_agent_orchestration  # noqa: E402
from backend.api.security import CurrentUser  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import AgentRun, DoctorReviewRequest, Patient  # noqa: E402
from backend.models.schemas import AgentV2OrchestrateRequest  # noqa: E402
from backend.services.agent_conversation_state import AgentConversationStateStore  # noqa: E402

get_settings.cache_clear()

RUN_TAG = uuid.uuid4().hex[:8]
FAILURES: list[str] = []


def _check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _new_patient(prefix: str) -> str:
    patient_id = f"build46-e2e-{prefix}-{RUN_TAG}"
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name=f"BUILD-46 E2E {prefix}"))
        db.commit()
    finally:
        db.close()
    return patient_id


def _actor(patient_id: str) -> CurrentUser:
    return CurrentUser(id=f"account-{patient_id}", role="patient", patient_id=patient_id, doctor_id=None)


def _orchestrate(patient_id: str, message: str, conversation_id: str):
    db = SessionLocal()
    try:
        request = AgentV2OrchestrateRequest(patient_id=patient_id, message=message, conversation_id=conversation_id)
        return run_agent_orchestration(request, db=db, actor=_actor(patient_id))
    finally:
        db.close()


def _seed_repeated_clarification_state(patient_id: str, conversation_id: str) -> None:
    """Same decoupling recipe BUILD-44's own local E2E already established
    and proved (0 model calls): a synthetic AgentRun carrying
    answerability_attempt_count=MAX_CLARIFICATION_ATTEMPTS."""
    db = SessionLocal()
    try:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        run = AgentRun(
            id=str(uuid.uuid4()), conversation_id=conversation_id, patient_id=patient_id,
            status="COMPLETED", started_at=now, completed_at=now, metadata_json={},
        )
        db.add(run)
        db.flush()
        state = ConversationState(conversation_id=conversation_id, answerability_attempt_count=MAX_CLARIFICATION_ATTEMPTS)
        AgentConversationStateStore().save(
            db, agent_run_id=run.id, actor_id=f"account-{patient_id}", patient_id=patient_id, state=state,
        )
        db.commit()
    finally:
        db.close()


def _handoffs_for(patient_id: str) -> list[DoctorReviewRequest]:
    db = SessionLocal()
    try:
        return list(
            db.execute(
                select(DoctorReviewRequest)
                .where(DoctorReviewRequest.patient_id == patient_id)
                .order_by(DoctorReviewRequest.created_at)
            ).scalars()
        )
    finally:
        db.close()


def _derived_type(row: DoctorReviewRequest) -> HandoffType:
    return handoff_type_for(reason_code=row.reason_code, risk_disposition=row.risk_disposition)


def main() -> int:
    print(f"BUILD-46 Fix B local E2E -- real Postgres, real model, run_tag={RUN_TAG}\n")

    # === Scenario D: SAFETY handoff open, then a real USER_REQUEST trigger
    # === must NOT reuse/mislabel it -- the exact production defect.
    print("=== Scenario D: SAFETY open, then USER_REQUEST -- must not reuse/mislabel ===")
    patient_d = _new_patient("d")
    conv_d = f"conv-d-{RUN_TAG}"
    r1 = _orchestrate(patient_d, "Tôi vừa nôn ra máu", conv_d)
    print(f"  turn1 (safety trigger) status={r1.status} handoff_required={r1.handoff_required} handoff_type={r1.handoff_type}")
    _check("safety turn completed with a real handoff", r1.handoff_required is True, str(r1.handoff_required))
    _check("safety turn's own handoff_type is SAFETY", r1.handoff_type == HandoffType.SAFETY.value, str(r1.handoff_type))

    r2 = _orchestrate(patient_d, "Tôi muốn nói chuyện với bác sĩ.", conv_d)
    print(f"  turn2 (user_request trigger) status={r2.status} handoff_required={r2.handoff_required} handoff_type={r2.handoff_type} id={r2.handoff_id}")
    _check("user_request turn completed with a real handoff", r2.handoff_required is True, str(r2.handoff_required))
    _check(
        "user_request turn's own reported handoff_type is USER_REQUEST, not SAFETY",
        r2.handoff_type == HandoffType.USER_REQUEST.value,
        str(r2.handoff_type),
    )
    _check(
        "user_request turn got a DIFFERENT handoff_id than the safety turn (no reuse)",
        r2.handoff_id != r1.handoff_id,
        f"safety={r1.handoff_id} user_request={r2.handoff_id}",
    )
    rows_d = _handoffs_for(patient_d)
    _check("exactly 2 durable DoctorReviewRequest rows for this patient", len(rows_d) == 2, str(len(rows_d)))
    for row in rows_d:
        print(f"    durable row: id={row.id} reason_code={row.reason_code} risk_disposition={row.risk_disposition} derived_type={_derived_type(row)}")
    safety_rows = [row for row in rows_d if _derived_type(row) == HandoffType.SAFETY]
    user_request_rows = [row for row in rows_d if _derived_type(row) == HandoffType.USER_REQUEST]
    _check("exactly 1 durable SAFETY-type row, still its own type", len(safety_rows) == 1, str(len(safety_rows)))
    _check("exactly 1 durable USER_REQUEST-type row, never merged with SAFETY", len(user_request_rows) == 1, str(len(user_request_rows)))

    # === Scenario E: repeated USER_REQUEST -- must reuse the SAME row. ===
    print("\n=== Scenario E: repeated USER_REQUEST -- compatible reuse ===")
    r3 = _orchestrate(patient_d, "Cho tôi gặp bác sĩ với.", conv_d)
    print(f"  turn3 (repeated user_request) status={r3.status} handoff_id={r3.handoff_id}")
    _check(
        "repeated USER_REQUEST reuses the SAME row as turn2 (not a 3rd row)",
        r3.handoff_id == r2.handoff_id,
        f"turn2={r2.handoff_id} turn3={r3.handoff_id}",
    )
    rows_d_after = _handoffs_for(patient_d)
    _check("still exactly 2 durable rows after the repeated USER_REQUEST", len(rows_d_after) == 2, str(len(rows_d_after)))

    # === Scenario F: a genuine UNCERTAINTY trigger -- correct type, and
    # === must not cross-reuse the SAFETY or USER_REQUEST rows either.
    print("\n=== Scenario F: UNCERTAINTY trigger -- correct type, no cross-reuse ===")
    patient_f = _new_patient("f")
    conv_f = f"conv-f-{RUN_TAG}"
    r1f = _orchestrate(patient_f, "Tôi vừa nôn ra máu", conv_f)
    _check("scenario F: safety turn completed", r1f.handoff_required is True, str(r1f.handoff_required))
    _seed_repeated_clarification_state(patient_f, conv_f)
    r2f = _orchestrate(patient_f, "Tôi bị đau đầu", conv_f)
    print(f"  turn2 (uncertainty trigger) status={r2f.status} handoff_required={r2f.handoff_required} handoff_type={r2f.handoff_type} id={r2f.handoff_id}")
    _check("uncertainty turn completed with a real handoff", r2f.handoff_required is True, str(r2f.handoff_required))
    _check("uncertainty turn's own reported type is UNCERTAINTY, not SAFETY", r2f.handoff_type == HandoffType.UNCERTAINTY.value, str(r2f.handoff_type))
    _check("uncertainty turn got a DIFFERENT id than the safety turn (no reuse)", r2f.handoff_id != r1f.handoff_id, f"safety={r1f.handoff_id} uncertainty={r2f.handoff_id}")
    rows_f = _handoffs_for(patient_f)
    _check("exactly 2 durable rows for this patient", len(rows_f) == 2, str(len(rows_f)))

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
