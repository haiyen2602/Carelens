"""BUILD-36 API-level tests: /admin/monitoring/* authorization + a real
end-to-end read through the actual HTTP routes, and the expected-count
verification the spec's own §21/§22 asks for (seed N real rows, dashboard
must report exactly N, not just HTTP 200).

Real Postgres via the same account_client-factory pattern
tests/test_api/test_admin_safety_routes.py already established.
"""

from __future__ import annotations

import datetime
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, AgentFeedbackTicket, AgentRun, AgentSafetyEvent  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402

_MONITORING_ROUTES = (
    "/api/v1/admin/monitoring/overview",
    "/api/v1/admin/monitoring/quality",
    "/api/v1/admin/monitoring/retrieval",
    "/api/v1/admin/monitoring/performance",
    "/api/v1/admin/monitoring/cost",
    "/api/v1/admin/monitoring/errors",
    "/api/v1/admin/monitoring/judge",
    "/api/v1/admin/monitoring/golden",
    "/api/v1/admin/monitoring/versions/filters",
    "/api/v1/admin/monitoring/traces",
)


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
            )
        )
        db.commit()
        created_account_ids.append(account_id)
        token = create_access_token(sub=account_id, role=role, patient_id=patient_id, doctor_id=doctor_id)
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"})
        clients.append(client)
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
def real_run_ticket_and_safety_event():
    """3 real, committed AgentRun rows (2 plain, 1 with a safety event + a
    ticket) -- used both for authz tests and the expected-count assertion."""

    db = SessionLocal()
    run_ids = [f"build36-authz-run-{uuid.uuid4().hex[:8]}" for _ in range(3)]
    trace_id = f"build36-authz-trace-{uuid.uuid4().hex[:8]}"
    for i, rid in enumerate(run_ids):
        # run_ids[0] is the one carrying the real trace_id (matches the
        # safety event/ticket below) -- trace_detail() looks up AgentRun by
        # trace_id, so this must actually be set, not left None (a real
        # bug in an earlier version of this fixture: the safety event/
        # ticket had trace_id, the AgentRun row itself never did).
        db.add(AgentRun(
            id=rid, status="COMPLETED", started_at=datetime.datetime.now(datetime.UTC), model="gpt-5.4-mini",
            trace_id=trace_id if i == 0 else None,
        ))
    db.commit()

    event = AgentSafetyEvent(
        agent_run_id=run_ids[0], trace_id=trace_id, conversation_id="conv-authz", patient_id="patient-authz",
        actor_id="actor-authz", outcome="HANDOFF_REQUIRED", reason_code="ACUTE_DANGER_DETECTED",
        severity="CRITICAL", severity_source="reason_code_mapped",
    )
    ticket = AgentFeedbackTicket(
        id=f"build36-authz-ticket-{uuid.uuid4().hex[:8]}", actor_id="actor-authz", patient_id="patient-authz",
        conversation_id="conv-authz", agent_run_id=run_ids[0], trace_id=trace_id,
        user_message="q", assistant_message="a", reason="WRONG_ANSWER", priority="P2",
    )
    db.add(event)
    db.add(ticket)
    db.commit()
    try:
        yield run_ids, event, ticket
    finally:
        db.query(AgentFeedbackTicket).filter(AgentFeedbackTicket.id == ticket.id).delete(synchronize_session=False)
        db.query(AgentSafetyEvent).filter(AgentSafetyEvent.agent_run_id == run_ids[0]).delete(synchronize_session=False)
        db.query(AgentRun).filter(AgentRun.id.in_(run_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_doctor_caregiver_denied_every_monitoring_route(account_client):
    for role, kwargs in (
        ("patient", {"patient_id": "patient-monitoring-authz-1"}),
        ("doctor", {"doctor_id": "doctor-monitoring-authz-1"}),
        ("caregiver", {}),
    ):
        client = await account_client(role, **kwargs)
        for path in _MONITORING_ROUTES:
            resp = await client.get(path)
            assert resp.status_code == 403, f"{role} should be denied {path}"


@pytest.mark.asyncio
async def test_admin_allowed_on_every_monitoring_route(account_client):
    admin = await account_client("admin")
    for path in _MONITORING_ROUTES:
        resp = await admin.get(path)
        assert resp.status_code == 200, f"admin should be allowed {path}"


@pytest.mark.asyncio
async def test_non_admin_denied_trace_and_session_detail(account_client):
    patient = await account_client("patient", patient_id="patient-monitoring-authz-2")
    resp = await patient.get("/api/v1/admin/monitoring/traces/does-not-exist")
    assert resp.status_code == 403
    resp = await patient.get("/api/v1/admin/monitoring/sessions/does-not-exist")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Real end-to-end read through the actual HTTP routes + expected-count check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_reads_real_overview_through_http(account_client, real_run_ticket_and_safety_event):
    run_ids, event, ticket = real_run_ticket_and_safety_event
    admin = await account_client("admin")

    resp = await admin.get("/api/v1/admin/monitoring/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["total_requests"] >= 3


@pytest.mark.asyncio
async def test_admin_traces_list_shows_real_markers_through_http(account_client, real_run_ticket_and_safety_event):
    run_ids, event, ticket = real_run_ticket_and_safety_event
    admin = await account_client("admin")

    resp = await admin.get("/api/v1/admin/monitoring/traces", params={"limit": 200})
    assert resp.status_code == 200
    body = resp.json()
    marked = next((item for item in body["items"] if item["agent_run_id"] == run_ids[0]), None)
    assert marked is not None
    assert marked["has_ticket"] is True
    assert marked["has_safety_event"] is True


@pytest.mark.asyncio
async def test_admin_trace_detail_real_correlation_through_http(account_client, real_run_ticket_and_safety_event):
    run_ids, event, ticket = real_run_ticket_and_safety_event
    admin = await account_client("admin")

    resp = await admin.get(f"/api/v1/admin/monitoring/traces/{event.trace_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_run_id"] == run_ids[0]
    assert body["safety"] is not None
    assert body["safety"]["reason_code"] == "ACUTE_DANGER_DETECTED"
    assert body["ticket"] is not None
    assert body["ticket"]["ticket_id"] == ticket.id


@pytest.mark.asyncio
async def test_unknown_trace_id_returns_404(account_client):
    admin = await account_client("admin")
    resp = await admin.get("/api/v1/admin/monitoring/traces/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_golden_run_detail_unknown_id_returns_404(account_client):
    admin = await account_client("admin")
    resp = await admin.get("/api/v1/admin/monitoring/golden/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ticket_detail_now_returns_judge_evaluation_safety_fields(account_client, real_run_ticket_and_safety_event):
    """BUILD-36 audit finding regression test: GET /admin/tickets/{id}
    previously returned `judge` but the field was computed and silently
    correct while `evaluation`/`safety` were entirely absent from the
    correlation chain. Confirms all 3 keys are now present in the real
    HTTP response shape (None is a valid, honest value when no row exists
    -- the point is the KEY is no longer missing)."""

    run_ids, event, ticket = real_run_ticket_and_safety_event
    admin = await account_client("admin")

    resp = await admin.get(f"/api/v1/admin/tickets/{ticket.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "judge" in body
    assert "evaluation" in body
    assert "safety" in body
    assert body["safety"] is not None
    assert body["safety"]["reason_code"] == "ACUTE_DANGER_DETECTED"
