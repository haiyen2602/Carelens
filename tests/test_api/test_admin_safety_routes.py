"""BUILD-34 API-level tests: /admin/safety/* authorization + a real
end-to-end read through the actual HTTP routes.

Real Postgres via the same account_client-factory pattern
tests/test_api/test_agent_feedback_routes.py already established.
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
from backend.db.models import Account, AgentRun, AgentSafetyEvent  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402

_SAFETY_ROUTES = (
    "/api/v1/admin/safety/summary",
    "/api/v1/admin/safety/events",
    "/api/v1/admin/safety/judge-review-signals",
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
def real_safety_event():
    """A real, committed AgentRun + AgentSafetyEvent row -- cleaned up after."""

    db = SessionLocal()
    run_id = f"build34-authz-run-{uuid.uuid4().hex[:8]}"
    trace_id = f"build34-authz-trace-{uuid.uuid4().hex[:8]}"
    db.add(AgentRun(id=run_id, status="HANDOFF_CREATED", started_at=datetime.datetime.now(datetime.UTC)))
    event = AgentSafetyEvent(
        agent_run_id=run_id, trace_id=trace_id, conversation_id="conv-authz", patient_id="patient-authz",
        actor_id="actor-authz", outcome="HANDOFF_REQUIRED", reason_code="ACUTE_DANGER_DETECTED",
        severity="CRITICAL", severity_source="reason_code_mapped", safety_path="SAFETY",
        provenance="agent-orchestrator:acute-danger", handoff_required=True, handoff_created=False,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    try:
        yield event
    finally:
        db.query(AgentSafetyEvent).filter(AgentSafetyEvent.agent_run_id == run_id).delete(synchronize_session=False)
        db.query(AgentRun).filter(AgentRun.id == run_id).delete(synchronize_session=False)
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_doctor_caregiver_denied_every_safety_route(account_client):
    for role, kwargs in (
        ("patient", {"patient_id": "patient-safety-authz-1"}),
        ("doctor", {"doctor_id": "doctor-safety-authz-1"}),
        ("caregiver", {}),
    ):
        client = await account_client(role, **kwargs)
        for path in _SAFETY_ROUTES:
            resp = await client.get(path)
            assert resp.status_code == 403, f"{role} should be denied {path}"


@pytest.mark.asyncio
async def test_admin_allowed_on_every_safety_route(account_client):
    admin = await account_client("admin")
    for path in _SAFETY_ROUTES:
        resp = await admin.get(path)
        assert resp.status_code == 200, f"admin should be allowed {path}"


@pytest.mark.asyncio
async def test_non_admin_denied_event_detail(account_client, real_safety_event):
    patient = await account_client("patient", patient_id="patient-safety-authz-2")
    resp = await patient.get(f"/api/v1/admin/safety/events/{real_safety_event.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Real end-to-end read through the actual HTTP routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_reads_real_safety_event_through_summary_list_and_detail(account_client, real_safety_event):
    admin = await account_client("admin")

    summary_resp = await admin.get("/api/v1/admin/safety/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["available"] is True
    assert summary["safety_trigger_count"] >= 1
    assert summary["severity_distribution"].get("CRITICAL", 0) >= 1

    list_resp = await admin.get("/api/v1/admin/safety/events", params={"severity": "CRITICAL"})
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert any(item["id"] == real_safety_event.id for item in body["items"])

    detail_resp = await admin.get(f"/api/v1/admin/safety/events/{real_safety_event.id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["agent_run_id"] == real_safety_event.agent_run_id
    assert detail["reason_code"] == "ACUTE_DANGER_DETECTED"
    assert detail["conversation_id"] == "conv-authz"


@pytest.mark.asyncio
async def test_unknown_event_id_returns_404(account_client):
    admin = await account_client("admin")
    resp = await admin.get("/api/v1/admin/safety/events/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_legacy_rag_safety_endpoint_still_works_and_carries_agent_v2_block(account_client):
    """BUILD-34 §6: the pre-existing /admin/rag/safety endpoint keeps working
    unchanged, and now additionally carries a real, separate agent_v2_safety
    block (never blended into the legacy `incidents`/`critical_safety_
    failures` fields already there)."""

    admin = await account_client("admin")
    resp = await admin.get("/api/v1/admin/rag/safety")
    assert resp.status_code == 200
    body = resp.json()
    assert "incidents" in body  # pre-existing field, untouched
    assert "agent_v2_safety" in body
    assert body["agent_v2_safety"] is None or "safety_trigger_count" in body["agent_v2_safety"]
