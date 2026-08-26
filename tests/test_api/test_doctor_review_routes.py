"""BUILD-44 API-level tests: /doctor/reviews/* + /agent/v2/handoff/status
authorization, the real claim/activate/message/resolve workflow, and real
Postgres claim-concurrency, through the actual HTTP routes.

Real Postgres via the same account_client-factory pattern
tests/test_api/test_admin_safety_routes.py already established.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, DoctorReviewMessage, DoctorReviewRequest, Patient  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402
from backend.services.doctor_handoff import (  # noqa: E402
    HandoffCreateCommand,
    MessageSenderRole,
    VerifiedContextRef,
    VerifiedContextSource,
    activate_doctor_review_request,
    claim_doctor_review_request,
    create_doctor_review_request,
    get_active_takeover,
    record_doctor_review_message,
    resolve_doctor_review_request,
)

NOW = datetime(2026, 8, 26, tzinfo=UTC)


@pytest_asyncio.fixture
async def account_client():
    created_account_ids: list[str] = []
    clients: list[AsyncClient] = []
    db = SessionLocal()

    async def _make(role: str, *, patient_id: str | None = None, doctor_id: str | None = None) -> AsyncClient:
        account_id = f"test-{role}-{uuid.uuid4().hex[:10]}"
        db.add(
            Account(
                id=account_id, full_name=f"Test {role}", email=f"{account_id}@example.local",
                password_hash="not-a-real-hash", role=role, status="active",
                patient_id=patient_id, doctor_id=doctor_id,
            )
        )
        db.commit()
        created_account_ids.append(account_id)
        token = create_access_token(sub=account_id, role=role, patient_id=patient_id, doctor_id=doctor_id)
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"})
        clients.append(client)
        client._test_account_id = account_id  # type: ignore[attr-defined]
        return client

    try:
        yield _make
    finally:
        for client in clients:
            await client.aclose()
        db.query(Account).filter(Account.id.in_(created_account_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture
def real_patient():
    db = SessionLocal()
    patient_id = f"build44-patient-{uuid.uuid4().hex[:8]}"
    db.add(Patient(id=patient_id, full_name="BUILD-44 Test Patient", doctor_id=None))
    db.commit()
    try:
        yield patient_id
    finally:
        db.query(DoctorReviewMessage).filter(DoctorReviewMessage.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoctorReviewRequest).filter(DoctorReviewRequest.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def _pending_uncertainty(patient_id: str, *, key_suffix: str = "") -> DoctorReviewRequest:
    """A real PENDING row -- no treating doctor -- via the real domain
    service (same idempotency/creation path BUILD-42's own Answerability
    Gate uses), not a raw INSERT."""
    db = SessionLocal()
    try:
        result = create_doctor_review_request(
            db,
            command=HandoffCreateCommand(
                patient_id=patient_id,
                actor_id=f"account-{patient_id}",
                patient_question="Tôi bị đau đầu.",
                reason_code="REPEATED_CLARIFICATION",
                risk_disposition="UNCERTAINTY_HANDOFF",
                idempotency_key=f"build44-key-{patient_id}{key_suffix}-{uuid.uuid4().hex[:6]}",
                verified_context_refs=(
                    VerifiedContextRef(VerifiedContextSource.ANSWERABILITY_GATE, "reason", "provenance"),
                ),
            ),
            created_at=NOW,
        )
        db.commit()
        db.refresh(result.request)
        return result.request
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_and_caregiver_denied_every_doctor_queue_route(account_client, real_patient):
    handoff = _pending_uncertainty(real_patient)
    for role, kwargs in (
        ("patient", {"patient_id": real_patient}),
        ("caregiver", {}),
    ):
        client = await account_client(role, **kwargs)
        for method, path in (
            ("GET", "/api/v1/doctor/reviews"),
            ("GET", f"/api/v1/doctor/reviews/{handoff.id}"),
            ("POST", f"/api/v1/doctor/reviews/{handoff.id}/claim"),
            ("POST", f"/api/v1/doctor/reviews/{handoff.id}/activate"),
            ("POST", f"/api/v1/doctor/reviews/{handoff.id}/resolve"),
        ):
            resp = await client.request(method, path)
            assert resp.status_code == 403, f"{role} should be denied {method} {path}"


@pytest.mark.asyncio
async def test_unauthenticated_denied(real_patient):
    handoff = _pending_uncertainty(real_patient)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/doctor/reviews/{handoff.id}")
        assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_doctor_allowed_to_view_queue(account_client, real_patient):
    _pending_uncertainty(real_patient)
    doctor = await account_client("doctor", doctor_id=f"doc-{uuid.uuid4().hex[:8]}")
    resp = await doctor.get("/api/v1/doctor/reviews")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_cross_doctor_cannot_activate_another_doctors_claim(account_client, real_patient):
    handoff = _pending_uncertainty(real_patient)
    doctor_a = await account_client("doctor", doctor_id=f"doc-a-{uuid.uuid4().hex[:8]}")
    doctor_b = await account_client("doctor", doctor_id=f"doc-b-{uuid.uuid4().hex[:8]}")

    claim_resp = await doctor_a.post(f"/api/v1/doctor/reviews/{handoff.id}/claim")
    assert claim_resp.status_code == 200
    assert claim_resp.json()["status"] == "ASSIGNED"

    forbidden = await doctor_b.post(f"/api/v1/doctor/reviews/{handoff.id}/activate")
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_cross_patient_status_isolation(account_client, real_patient):
    other_patient_id = f"build44-other-patient-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    db.add(Patient(id=other_patient_id, full_name="Other Patient", doctor_id=None))
    db.commit()
    db.close()
    try:
        patient_client = await account_client("patient", patient_id=real_patient)
        resp = await patient_client.get("/api/v1/agent/v2/handoff/status", params={"patient_id": other_patient_id})
        assert resp.status_code == 403
    finally:
        db = SessionLocal()
        db.query(Patient).filter(Patient.id == other_patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Real end-to-end workflow through the actual HTTP routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_claim_activate_message_resolve_workflow(account_client, real_patient):
    handoff = _pending_uncertainty(real_patient)
    doctor = await account_client("doctor", doctor_id=f"doc-{uuid.uuid4().hex[:8]}")
    patient_client = await account_client("patient", patient_id=real_patient)

    claim = await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/claim")
    assert claim.status_code == 200 and claim.json()["status"] == "ASSIGNED"

    # ASSIGNED does not yet suppress the bot / allow messaging.
    pre_activate_message = await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/messages", json={"content": "xin chao"})
    assert pre_activate_message.status_code == 409

    activate = await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/activate")
    assert activate.status_code == 200 and activate.json()["status"] == "ACTIVE"

    status_resp = await patient_client.get("/api/v1/agent/v2/handoff/status", params={"patient_id": real_patient})
    assert status_resp.status_code == 200
    assert status_resp.json()["has_active_handoff"] is True
    assert status_resp.json()["status"] == "ACTIVE"

    doctor_message = await doctor.post(
        f"/api/v1/doctor/reviews/{handoff.id}/messages", json={"content": "Chào bạn, tôi là bác sĩ, bạn đang thấy sao rồi?"}
    )
    assert doctor_message.status_code == 200
    detail = doctor_message.json()
    assert any(m["sender_role"] == "DOCTOR" and m["content"].startswith("Chào bạn") for m in detail["messages"])

    resolve = await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/resolve")
    assert resolve.status_code == 200 and resolve.json()["status"] == "RESOLVED"

    # Idempotent repeat resolve by the same doctor.
    resolve_again = await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/resolve")
    assert resolve_again.status_code == 200 and resolve_again.json()["status"] == "RESOLVED"

    status_after = await patient_client.get("/api/v1/agent/v2/handoff/status", params={"patient_id": real_patient})
    assert status_after.json()["has_active_handoff"] is False


@pytest.mark.asyncio
async def test_sequential_duplicate_claim_retry_rejected_not_crashed(account_client, real_patient):
    """SS26-D: a SEQUENTIAL (not concurrent) second claim attempt on an
    already-ASSIGNED request -- e.g. a client retrying a claim call whose
    response it never saw -- must come back as a clean 409, never a crash,
    and must never reassign/duplicate the handoff to a different doctor."""
    handoff = _pending_uncertainty(real_patient)
    doctor_a = await account_client("doctor", doctor_id=f"doc-a-{uuid.uuid4().hex[:8]}")
    doctor_b = await account_client("doctor", doctor_id=f"doc-b-{uuid.uuid4().hex[:8]}")

    first = await doctor_a.post(f"/api/v1/doctor/reviews/{handoff.id}/claim")
    assert first.status_code == 200 and first.json()["status"] == "ASSIGNED"
    assigned_to = first.json()["assigned_doctor_id"]

    # A retry by the SAME doctor (e.g. a lost-response retry).
    retry_same = await doctor_a.post(f"/api/v1/doctor/reviews/{handoff.id}/claim")
    assert retry_same.status_code == 409

    # A different doctor attempting to claim the already-claimed request.
    retry_other = await doctor_b.post(f"/api/v1/doctor/reviews/{handoff.id}/claim")
    assert retry_other.status_code == 409

    db = SessionLocal()
    try:
        row = db.get(DoctorReviewRequest, handoff.id)
        assert row.status == "ASSIGNED"
        assert row.assigned_doctor_id == assigned_to
    finally:
        db.close()


@pytest.mark.asyncio
async def test_repeated_activate_is_idempotent(account_client, real_patient):
    handoff = _pending_uncertainty(real_patient)
    doctor = await account_client("doctor", doctor_id=f"doc-{uuid.uuid4().hex[:8]}")
    await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/claim")
    first = await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/activate")
    second = await doctor.post(f"/api/v1/doctor/reviews/{handoff.id}/activate")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Real Postgres claim concurrency (SS6/SS26-A)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_doctors_claiming_the_same_request_concurrently_exactly_one_succeeds(account_client, real_patient):
    handoff = _pending_uncertainty(real_patient)
    doctor_id_a, doctor_id_b = f"doc-a-{uuid.uuid4().hex[:8]}", f"doc-b-{uuid.uuid4().hex[:8]}"
    doctor_a = await account_client("doctor", doctor_id=doctor_id_a)
    doctor_b = await account_client("doctor", doctor_id=doctor_id_b)

    resp_a, resp_b = await asyncio.gather(
        doctor_a.post(f"/api/v1/doctor/reviews/{handoff.id}/claim"),
        doctor_b.post(f"/api/v1/doctor/reviews/{handoff.id}/claim"),
    )
    statuses = sorted([resp_a.status_code, resp_b.status_code])
    assert statuses == [200, 409], f"exactly one claim should succeed, got {[resp_a.status_code, resp_b.status_code]}"

    db = SessionLocal()
    try:
        row = db.get(DoctorReviewRequest, handoff.id)
        assert row.status == "ASSIGNED"
        assert row.assigned_doctor_id in (doctor_id_a, doctor_id_b)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Real Postgres resolve/patient-message concurrency (SS26-B)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_doctor_resolve_and_patient_message_persist_concurrently_no_corruption(real_patient):
    """SS26-B: a doctor resolving and a patient's in-flight message hitting
    the same ACTIVE handoff at the same wall-clock time must never crash,
    corrupt state, or silently drop the patient's message.

    Exercises the exact same two calls
    ``agent_v2_routes.py::_respond_with_doctor_takeover_active`` itself
    makes (``get_active_takeover`` then ``record_doctor_review_message``)
    directly against real Postgres, via ``asyncio.to_thread`` so both sides
    run in genuinely parallel OS threads rather than cooperative
    interleaving -- without going through the full HTTP orchestrate route,
    so this test needs no model gateway / network call regardless of which
    ordering wins the race.

    Both legitimate outcomes are asserted for internally-consistent state;
    neither outcome may lose the patient's message or leave the handoff in
    anything but RESOLVED once both sides finish.
    """
    handoff = _pending_uncertainty(real_patient)
    doctor_id = f"doc-resolve-{uuid.uuid4().hex[:8]}"

    db_setup = SessionLocal()
    try:
        claim_doctor_review_request(db_setup, request_id=handoff.id, doctor_id=doctor_id, claimed_at=NOW)
        db_setup.commit()
        activate_doctor_review_request(db_setup, request_id=handoff.id, doctor_id=doctor_id, activated_at=NOW)
        db_setup.commit()
    finally:
        db_setup.close()

    def _patient_message_attempt() -> bool:
        """True iff this call observed the handoff as ACTIVE (and
        therefore persisted a PATIENT message instead of falling through
        to normal bot orchestration, as the real route would)."""
        db = SessionLocal()
        try:
            active = get_active_takeover(db, patient_id=real_patient)
            if active is None:
                return False
            record_doctor_review_message(
                db,
                handoff_id=active.id,
                patient_id=real_patient,
                sender_role=MessageSenderRole.PATIENT,
                actor_id=f"account-{real_patient}",
                content="Tin nhan trong luc bac si co the dang resolve",
                created_at=NOW,
            )
            db.commit()
            return True
        finally:
            db.close()

    def _doctor_resolve() -> None:
        db = SessionLocal()
        try:
            resolve_doctor_review_request(db, request_id=handoff.id, doctor_id=doctor_id, resolved_at=NOW)
            db.commit()
        finally:
            db.close()

    saw_active, _ = await asyncio.gather(
        asyncio.to_thread(_patient_message_attempt),
        asyncio.to_thread(_doctor_resolve),
    )

    db = SessionLocal()
    try:
        row = db.get(DoctorReviewRequest, handoff.id)
        assert row.status == "RESOLVED"
        assert row.resolved_by_doctor_id == doctor_id

        messages = db.execute(
            select(DoctorReviewMessage).where(DoctorReviewMessage.handoff_id == handoff.id)
        ).scalars().all()
        if saw_active:
            # This side's read won the race before resolve committed -- its
            # message must be durably persisted; resolve must not silently
            # drop it.
            assert len(messages) == 1
            assert messages[0].sender_role == "PATIENT"
        else:
            # Resolve won the race -- the patient's request saw no active
            # takeover and (in the real route) would fall through to
            # normal Agent V2 orchestration instead; nothing should have
            # been written to DoctorReviewMessage by this path.
            assert len(messages) == 0
    finally:
        db.close()
