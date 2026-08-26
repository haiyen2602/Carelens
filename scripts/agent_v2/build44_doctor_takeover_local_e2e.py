"""BUILD-44 sections 27-30: real local E2E for the Doctor Chat Queue &
Takeover workflow (Core / Safety / Uncertainty / Explicit User Request).

Real Postgres, real ``run_agent_orchestration`` calls for every patient-side
turn (same direct-call convention ``build36_admin_monitoring_local_e2e.py``
already established for this script family), real domain-function calls for
every doctor-side action (``claim_doctor_review_request`` /
``activate_doctor_review_request`` / ``record_doctor_review_message`` /
``resolve_doctor_review_request`` -- the exact functions the real HTTP
routes in ``doctor_review_routes.py`` call, already covered at the HTTP/auth
layer by ``tests/test_api/test_doctor_review_routes.py``, so this script's
job is the full cross-module DATA FLOW, not re-proving auth).

BUILD-44 consumes handoff decisions BUILD-42/43 already produce; it does not
re-validate their own trigger mechanism (that is BUILD-42's own report's
job). The CORE/UNCERTAINTY scenario below therefore seeds
``ConversationState.answerability_attempt_count`` directly via a synthetic
``AgentRun`` + ``AgentConversationStateStore.save`` -- the SAME decoupling
technique the BUILD-43 production-validation session already used, and the
exact ``answerability_attempt_count=MAX_CLARIFICATION_ATTEMPTS`` + "toi bi
dau dau" recipe already proven (0 model calls) in
``tests/test_agent_v2_build42_answerability.py::test_e_repeated_clarification_unresolved_escalates_to_doctor``.

Usage:

    python scripts/agent_v2/build44_doctor_takeover_local_e2e.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if __name__ == "__main__":
    os.environ.setdefault("AGENT_RUNTIME_ENABLED", "true")
    # Windows console default codepage (cp1252) crashes on Vietnamese
    # diacritics in print() -- same fix already established by
    # staging_performance_batch.py / uat_staging_scenarios.py in this same
    # script family, not a product bug.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from backend.agents.v2.answerability import MAX_CLARIFICATION_ATTEMPTS, HandoffType, handoff_type_for  # noqa: E402
from backend.agents.v2.conversation_state import ConversationState  # noqa: E402
from backend.api.agent_v2_routes import run_agent_orchestration  # noqa: E402
from backend.api.security import CurrentUser  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import AgentRun, AgentSafetyEvent, DoctorReviewRequest, Patient  # noqa: E402
from backend.models.schemas import AgentV2OrchestrateRequest  # noqa: E402
from backend.services.agent_conversation_state import AgentConversationStateStore  # noqa: E402
from backend.services.doctor_handoff import (  # noqa: E402
    MessageSenderRole,
    activate_doctor_review_request,
    claim_doctor_review_request,
    get_active_takeover,
    list_doctor_review_messages,
    record_doctor_review_message,
    resolve_doctor_review_request,
)

get_settings.cache_clear()

RUN_TAG = uuid.uuid4().hex[:8]
# BUILD-44 lesson (found via this script's own first real run): every
# doctor-side action below happens at a genuinely later wall-clock moment
# than the one before it -- a single frozen timestamp reused across calls
# put a later real action (e.g. the patient's ACTIVE-turn message, which
# the real route stamps live) BEFORE an earlier script call in
# ``created_at`` order, failing the thread-order assertion for a reason
# that was this script's bug, not the product's (SS19: the real route
# always stamps a fresh server timestamp per call; a test script emulating
# multiple separate "server calls" must do the same). ``_SEED_TIME`` below
# is the one deliberate exception -- it represents a genuinely earlier,
# already-completed turn.
_SEED_TIME = datetime.now(UTC)
FAILURES: list[str] = []


def _now() -> datetime:
    return datetime.now(UTC)


def _check(label: str, condition: bool, detail: str = "") -> None:
    mark = "OK" if condition else "FAIL"
    print(f"    [{mark}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _new_patient(prefix: str) -> str:
    patient_id = f"build44-e2e-{prefix}-{RUN_TAG}"
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name=f"BUILD-44 E2E {prefix}"))
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
    """A synthetic, real ``AgentRun`` row carrying
    ``answerability_attempt_count=MAX_CLARIFICATION_ATTEMPTS`` -- decoupling
    this scenario from natural multi-turn drift (not this build's object of
    testing; see module docstring)."""
    db = SessionLocal()
    try:
        run = AgentRun(
            id=str(uuid.uuid4()), conversation_id=conversation_id, patient_id=patient_id,
            status="COMPLETED", started_at=_SEED_TIME, completed_at=_SEED_TIME, metadata_json={},
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


def _handoff_row(handoff_id: str) -> DoctorReviewRequest:
    db = SessionLocal()
    try:
        return db.get(DoctorReviewRequest, handoff_id)
    finally:
        db.close()


def _run_id_row(run_id: str) -> AgentRun:
    db = SessionLocal()
    try:
        return db.get(AgentRun, run_id)
    finally:
        db.close()


def _safety_event_count(patient_id: str) -> int:
    db = SessionLocal()
    try:
        return len(db.execute(select(AgentSafetyEvent).where(AgentSafetyEvent.patient_id == patient_id)).scalars().all())
    finally:
        db.close()


def _active_takeover(patient_id: str) -> DoctorReviewRequest | None:
    db = SessionLocal()
    try:
        return get_active_takeover(db, patient_id=patient_id)
    finally:
        db.close()


def _messages(handoff_id: str):
    db = SessionLocal()
    try:
        return list_doctor_review_messages(db, handoff_id=handoff_id)
    finally:
        db.close()


def _doctor_side_pass(handoff_id: str, doctor_id: str, patient_id: str, *, respond: bool) -> None:
    """Shared claim -> activate -> (optional message) -> resolve pass, real
    domain-function calls, same as the real HTTP route layer uses."""
    db = SessionLocal()
    try:
        claim_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, claimed_at=_now())
        db.commit()
    finally:
        db.close()
    row = _handoff_row(handoff_id)
    _check("doctor claim -> ASSIGNED", row.status == "ASSIGNED", row.status)

    db = SessionLocal()
    try:
        activate_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, activated_at=_now())
        db.commit()
    finally:
        db.close()
    row = _handoff_row(handoff_id)
    _check("doctor activate -> ACTIVE", row.status == "ACTIVE", row.status)

    if respond:
        db = SessionLocal()
        try:
            record_doctor_review_message(
                db, handoff_id=handoff_id, patient_id=patient_id, sender_role=MessageSenderRole.DOCTOR,
                actor_id=f"account-{doctor_id}", content="Chao ban, bac si day, ban dang thay the nao?",
                created_at=_now(),
            )
            db.commit()
        finally:
            db.close()

    db = SessionLocal()
    try:
        resolve_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, resolved_at=_now())
        db.commit()
    finally:
        db.close()
    row = _handoff_row(handoff_id)
    _check("doctor resolve -> RESOLVED", row.status == "RESOLVED", row.status)


def scenario_core_uncertainty() -> None:
    """Sections 27-28: the 15-step core scenario, uncertainty-triggered."""
    print("\n[CORE / UNCERTAINTY] 15-step queue -> claim -> activate -> message -> resolve -> resume")
    patient_id = _new_patient("core")
    conversation_id = f"build44-core-{RUN_TAG}"
    doctor_id = f"doc-core-{RUN_TAG}"

    # 1-3: seed attempt_count, trigger NEED_DOCTOR (0 model calls -- proven path).
    _seed_repeated_clarification_state(patient_id, conversation_id)
    trigger = _orchestrate(patient_id, "Tôi bị đau đầu", conversation_id)
    _check("trigger -> handoff_required", trigger.handoff_required is True, str(trigger.model_dump()))
    _check("trigger -> handoff_type UNCERTAINTY", trigger.handoff_type == "UNCERTAINTY", trigger.handoff_type)
    handoff_id = trigger.handoff_id

    # 4: durable row correctness.
    row = _handoff_row(handoff_id)
    _check("handoff row PENDING", row is not None and row.status == "PENDING", row.status if row else "MISSING")
    _check(
        "handoff_type_for matches response",
        handoff_type_for(reason_code=row.reason_code, risk_disposition=row.risk_disposition) is HandoffType.UNCERTAINTY,
        f"{row.reason_code}/{row.risk_disposition}",
    )

    # 5: queue -- exactly one open item for this patient.
    active_now = _active_takeover(patient_id)
    _check("not yet ACTIVE before doctor acts", active_now is None, str(active_now))

    # 6-7: claim + activate.
    db = SessionLocal()
    try:
        claim_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, claimed_at=_now())
        db.commit()
    finally:
        db.close()
    db = SessionLocal()
    try:
        activate_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, activated_at=_now())
        db.commit()
    finally:
        db.close()
    row = _handoff_row(handoff_id)
    _check("claim+activate -> ACTIVE", row.status == "ACTIVE", row.status)

    # 8: patient message during ACTIVE -- 0 model calls, persisted, ack reply.
    during = _orchestrate(patient_id, "Tác dụng phụ thì sao?", conversation_id)
    _check("patient msg during ACTIVE -> DOCTOR_ACTIVE", during.status == "DOCTOR_ACTIVE", during.status)
    _check("patient msg during ACTIVE -> handoff_id matches", during.handoff_id == handoff_id, during.handoff_id)
    run_row = _run_id_row(during.agent_run_id)
    _check("patient msg during ACTIVE -> 0 model calls", run_row is not None and run_row.model_calls == 0, str(run_row.model_calls if run_row else None))

    # 9: doctor reads.
    messages = _messages(handoff_id)
    _check("doctor sees 1 PATIENT message", len(messages) == 1 and messages[0].sender_role == "PATIENT", str(len(messages)))

    # 10: doctor responds (never routed through the Main Model -- verbatim persist).
    db = SessionLocal()
    try:
        record_doctor_review_message(
            db, handoff_id=handoff_id, patient_id=patient_id, sender_role=MessageSenderRole.DOCTOR,
            actor_id=f"account-{doctor_id}", content="Chao ban, ban nen theo doi them 24h.", created_at=_now(),
        )
        db.commit()
    finally:
        db.close()

    # 11: patient-side read (durable thread order).
    messages = _messages(handoff_id)
    _check(
        "thread order PATIENT then DOCTOR",
        [m.sender_role for m in messages] == ["PATIENT", "DOCTOR"],
        str([m.sender_role for m in messages]),
    )

    # 12-13: resolve, gate reopens.
    db = SessionLocal()
    try:
        resolve_doctor_review_request(db, request_id=handoff_id, doctor_id=doctor_id, resolved_at=_now())
        db.commit()
    finally:
        db.close()
    row = _handoff_row(handoff_id)
    _check("resolve -> RESOLVED", row.status == "RESOLVED", row.status)
    active_after = _active_takeover(patient_id)
    _check("get_active_takeover -> None after resolve", active_after is None, str(active_after))

    # 14: bot resumes -- real orchestration turn, real model call.
    resumed = _orchestrate(patient_id, "Paracetamol dùng để làm gì?", conversation_id)
    _check("bot resumes -> status != DOCTOR_ACTIVE", resumed.status != "DOCTOR_ACTIVE", resumed.status)
    _check("bot resumes -> real non-empty reply", bool(resumed.reply and resumed.reply.strip()), repr(resumed.reply))

    # 15: no fake AgentSafetyEvent for an uncertainty handoff, ever.
    _check("no AgentSafetyEvent created for UNCERTAINTY handoff", _safety_event_count(patient_id) == 0, str(_safety_event_count(patient_id)))


def scenario_safety() -> None:
    print("\n[SAFETY] local-only -- must not interfere with the pre-existing Safety pipeline")
    patient_id = _new_patient("safety")
    conversation_id = f"build44-safety-{RUN_TAG}"
    doctor_id = f"doc-safety-{RUN_TAG}"
    before = _safety_event_count(patient_id)

    trigger = _orchestrate(patient_id, "Tôi vừa nôn ra máu", conversation_id)
    _check("safety trigger -> handoff_required", trigger.handoff_required is True, str(trigger.model_dump()))
    _check("safety trigger -> handoff_type SAFETY", trigger.handoff_type == "SAFETY", trigger.handoff_type)
    handoff_id = trigger.handoff_id
    if handoff_id is None:
        print("    [SKIP] no handoff_id returned -- cannot continue this scenario's doctor-side pass")
        return

    row = _handoff_row(handoff_id)
    _check(
        "handoff_type_for matches response (SAFETY)",
        handoff_type_for(reason_code=row.reason_code, risk_disposition=row.risk_disposition) is HandoffType.SAFETY,
        f"{row.reason_code}/{row.risk_disposition}",
    )
    after_trigger = _safety_event_count(patient_id)
    _check("a real AgentSafetyEvent WAS recorded for the safety trigger", after_trigger > before, str(after_trigger))

    _doctor_side_pass(handoff_id, doctor_id, patient_id, respond=True)
    after_workflow = _safety_event_count(patient_id)
    _check(
        "claim/activate/resolve created no ADDITIONAL AgentSafetyEvent rows",
        after_workflow == after_trigger,
        f"before-doctor-workflow={after_trigger} after-doctor-workflow={after_workflow}",
    )


def scenario_explicit_user_request() -> None:
    print("\n[EXPLICIT USER REQUEST] 'Tôi muốn nói chuyện với bác sĩ.' -> USER_REQUEST, 0 model calls")
    patient_id = _new_patient("userreq")
    conversation_id = f"build44-userreq-{RUN_TAG}"
    doctor_id = f"doc-userreq-{RUN_TAG}"

    trigger = _orchestrate(patient_id, "Tôi muốn nói chuyện với bác sĩ.", conversation_id)
    _check("explicit request -> handoff_required", trigger.handoff_required is True, str(trigger.model_dump()))
    _check("explicit request -> handoff_type USER_REQUEST", trigger.handoff_type == "USER_REQUEST", trigger.handoff_type)
    run_row = _run_id_row(trigger.agent_run_id)
    _check("explicit request -> 0 model calls", run_row is not None and run_row.model_calls == 0, str(run_row.model_calls if run_row else None))
    _check("no fake AgentSafetyEvent for USER_REQUEST handoff", _safety_event_count(patient_id) == 0, str(_safety_event_count(patient_id)))

    handoff_id = trigger.handoff_id
    row = _handoff_row(handoff_id)
    _check(
        "handoff_type_for matches response (USER_REQUEST)",
        handoff_type_for(reason_code=row.reason_code, risk_disposition=row.risk_disposition) is HandoffType.USER_REQUEST,
        f"{row.reason_code}/{row.risk_disposition}",
    )
    _doctor_side_pass(handoff_id, doctor_id, patient_id, respond=False)


def main() -> int:
    print(f"BUILD-44 local E2E -- real Postgres, RUN_TAG={RUN_TAG}")
    scenario_core_uncertainty()
    scenario_safety()
    scenario_explicit_user_request()

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
