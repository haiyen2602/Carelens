"""BUILD-29 API-level tests: POST /agent/v2/feedback and /admin/tickets*,
plus the _require_admin security-fix regression on /admin/rag/*.

Real Postgres via the same SessionLocal/Account pattern as
tests/conftest.py's own `client` fixture -- each test mints its own
role-specific JWT/Account rather than reusing the shared caregiver fixture,
since this file's whole point is per-role authorization behavior.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import backend.services.telemetry as telemetry_module  # noqa: E402
from backend.api.agent_feedback_routes import reset_feedback_rate_limiter_for_tests  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, AgentFeedbackTicket  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402
from backend.services.telemetry import TelemetryService  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    reset_feedback_rate_limiter_for_tests()
    yield
    reset_feedback_rate_limiter_for_tests()


@pytest.fixture
def clean_trace_buffer():
    original = list(telemetry_module._LOCAL_TRACE_BUFFER)
    telemetry_module._LOCAL_TRACE_BUFFER.clear()
    yield telemetry_module._LOCAL_TRACE_BUFFER
    telemetry_module._LOCAL_TRACE_BUFFER.clear()
    telemetry_module._LOCAL_TRACE_BUFFER.extend(original)


def _seed_trace(*, trace_id, user_id, session_id, intent=None, message="hi", response="ok"):
    svc = TelemetryService()
    trace = svc.create_trace(
        trace_id=trace_id, session_id=session_id, user_id=user_id,
        input_data={"message": message}, metadata={"intent": intent} if intent else {},
    )
    svc.finalize_trace(trace, output_data={"response": response}, status="success")
    return trace


@pytest_asyncio.fixture
async def account_client():
    """Yields a factory: role -> AsyncClient authenticated as a freshly
    created, real Account of that role. Every created account/ticket row is
    cleaned up afterward."""
    created_account_ids: list[str] = []
    clients: list[AsyncClient] = []
    db = SessionLocal()

    async def _make(role: str, *, patient_id: str | None = None, doctor_id: str | None = None) -> AsyncClient:
        account_id = f"test-{role}-{uuid.uuid4().hex[:10]}"
        db.add(
            Account(
                id=account_id, full_name=f"Test {role}", email=f"{account_id}@example.local",
                password_hash="not-a-real-hash", role=role, status="active",
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
        db.query(AgentFeedbackTicket).filter(AgentFeedbackTicket.actor_id.in_(created_account_ids)).delete(synchronize_session=False)
        db.query(Account).filter(Account.id.in_(created_account_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


def _feedback_payload(**overrides) -> dict:
    values = dict(
        conversation_id=f"conv-{uuid.uuid4().hex[:8]}",
        trace_id=None,
        agent_run_id=f"run-{uuid.uuid4().hex[:8]}",
        user_message="tôi uống thuốc gì hôm nay",
        assistant_message="bạn chưa có đơn thuốc nào",
        reason="WRONG_ANSWER",
        user_note=None,
    )
    values.update(overrides)
    return values


# ---------------------------------------------------------------------------
# 1-2-3: patient reports own message, correct trace/conversation attached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_reports_own_assistant_message(account_client):
    patient = await account_client("patient", patient_id="patient-report-1")
    resp = await patient.post("/api/v1/agent/v2/feedback", json=_feedback_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "OPEN"
    assert body["patient_id"] == "patient-report-1"
    assert body["priority"] in ("P0", "P1", "P2", "P3")


@pytest.mark.asyncio
async def test_report_attaches_the_correct_trace_id(account_client, clean_trace_buffer):
    patient = await account_client("patient", patient_id="patient-report-2")
    _seed_trace(trace_id="trace-correct-1", user_id=patient._test_account_id, session_id="conv-x")
    resp = await patient.post("/api/v1/agent/v2/feedback", json=_feedback_payload(trace_id="trace-correct-1"))
    assert resp.status_code == 201
    assert resp.json()["trace_id"] == "trace-correct-1"


@pytest.mark.asyncio
async def test_report_attaches_the_correct_conversation_id(account_client):
    patient = await account_client("patient", patient_id="patient-report-3")
    resp = await patient.post("/api/v1/agent/v2/feedback", json=_feedback_payload(conversation_id="conv-specific-abc"))
    assert resp.status_code == 201
    assert resp.json()["conversation_id"] == "conv-specific-abc"


# ---------------------------------------------------------------------------
# 4: duplicate submit -> no duplicate ticket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_submit_does_not_create_a_duplicate_ticket(account_client):
    patient = await account_client("patient", patient_id="patient-report-4")
    payload = _feedback_payload(agent_run_id="run-dup-http")
    first = await patient.post("/api/v1/agent/v2/feedback", json=payload)
    second = await patient.post("/api/v1/agent/v2/feedback", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


# ---------------------------------------------------------------------------
# 5: cross-patient report attempt -> denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_patient_report_attempt_is_denied(account_client, clean_trace_buffer):
    victim = await account_client("patient", patient_id="patient-victim")
    attacker = await account_client("patient", patient_id="patient-attacker")
    _seed_trace(trace_id="trace-victim-1", user_id=victim._test_account_id, session_id="conv-victim")

    resp = await attacker.post("/api/v1/agent/v2/feedback", json=_feedback_payload(trace_id="trace-victim-1"))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6-7: role gating on the admin ticket API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_cannot_read_admin_ticket_api(account_client):
    patient = await account_client("patient", patient_id="patient-report-5")
    resp = await patient.get("/api/v1/admin/tickets")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_doctor_cannot_read_admin_trace_explorer(account_client):
    doctor = await account_client("doctor", doctor_id="doctor-1")
    resp = await doctor.get("/api/v1/admin/rag/traces")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_caregiver_cannot_read_admin_ticket_api(account_client):
    caregiver = await account_client("caregiver")
    resp = await caregiver.get("/api/v1/admin/tickets")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 8-9-10-11: admin reads ticket / session / linked trace / updates status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_reads_ticket_opens_session_and_linked_trace(account_client, clean_trace_buffer):
    patient = await account_client("patient", patient_id="patient-report-6")
    admin = await account_client("admin")

    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    _seed_trace(trace_id="trace-admin-1", user_id=patient._test_account_id, session_id=conv_id, message="q1", response="a1")
    _seed_trace(trace_id="trace-admin-2", user_id=patient._test_account_id, session_id=conv_id, message="q2", response="a2")

    create_resp = await patient.post(
        "/api/v1/agent/v2/feedback",
        json=_feedback_payload(conversation_id=conv_id, trace_id="trace-admin-2"),
    )
    assert create_resp.status_code == 201
    ticket_id = create_resp.json()["id"]

    # admin reads ticket -> PASS
    detail_resp = await admin.get(f"/api/v1/admin/tickets/{ticket_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["ticket"]["id"] == ticket_id
    assert detail["trace"]["found"] is True
    assert detail["trace"]["final_response"] == "a2"

    # admin opens session -> PASS, sees both turns in the same conversation
    session_resp = await admin.get(f"/api/v1/admin/tickets/{ticket_id}/session")
    assert session_resp.status_code == 200
    session = session_resp.json()
    assert session["conversation_id"] == conv_id
    assert {item["trace_id"] for item in session["items"]} == {"trace-admin-1", "trace-admin-2"}

    # admin opens the linked trace via the existing Trace Explorer -> PASS
    trace_resp = await admin.get("/api/v1/admin/rag/traces/trace-admin-2")
    assert trace_resp.status_code == 200

    # ticket status update -> PASS
    update_resp = await admin.patch(f"/api/v1/admin/tickets/{ticket_id}", json={"status": "INVESTIGATING"})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "INVESTIGATING"

    resolved_resp = await admin.patch(f"/api/v1/admin/tickets/{ticket_id}", json={"status": "FIXED", "admin_note": "da sua"})
    assert resolved_resp.status_code == 200
    resolved = resolved_resp.json()
    assert resolved["status"] == "FIXED"
    assert resolved["admin_note"] == "da sua"
    assert resolved["resolved_at"] is not None


@pytest.mark.asyncio
async def test_admin_can_list_and_filter_tickets(account_client):
    patient = await account_client("patient", patient_id="patient-report-7")
    admin = await account_client("admin")
    await patient.post("/api/v1/agent/v2/feedback", json=_feedback_payload(reason="UNSAFE_OR_INAPPROPRIATE", trace_id=None))

    resp = await admin.get("/api/v1/admin/tickets", params={"priority": "P0"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(item["priority"] == "P0" for item in body["items"])


# ---------------------------------------------------------------------------
# 12: security-fix regression -- _require_admin now actually checks role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_admin_fix_blocks_every_non_admin_role_on_rag_routes(account_client):
    for role, kwargs in (("patient", {"patient_id": "patient-security-1"}), ("doctor", {"doctor_id": "doctor-security-1"}), ("caregiver", {})):
        client = await account_client(role, **kwargs)
        resp = await client.get("/api/v1/admin/rag/health")
        assert resp.status_code == 403, f"{role} should be denied /admin/rag/health"


@pytest.mark.asyncio
async def test_admin_role_still_reads_rag_health(account_client):
    admin = await account_client("admin")
    resp = await admin.get("/api/v1/admin/rag/health")
    assert resp.status_code == 200
