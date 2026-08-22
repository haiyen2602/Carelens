"""BUILD-30 API-level tests: GET /agent/v2/traces/{trace_id}/activity.

Covers the DB-row-based authorization path with fabricated rows (fast, no
external dependency) plus one REAL end-to-end run through the actual
POST /agent/v2/orchestrate route (a BUILD-28 schedule-deterministic query,
so it makes zero OpenAI calls) to prove the write path really persists what
build_activity_timeline() says it should, and that the read path serves it
back correctly through real HTTP.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account, AgentActivitySnapshot, Patient  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


@pytest_asyncio.fixture
async def account_client():
    created_account_ids: list[str] = []
    created_patient_ids: list[str] = []
    clients: list[AsyncClient] = []
    db = SessionLocal()

    async def _make(role: str, *, patient_id: str | None = None) -> AsyncClient:
        account_id = f"test-{role}-{uuid.uuid4().hex[:10]}"
        if patient_id and db.get(Patient, patient_id) is None:
            db.add(Patient(id=patient_id, full_name=f"Test patient {patient_id}"))
            created_patient_ids.append(patient_id)
        db.add(
            Account(
                id=account_id, full_name=f"Test {role}", email=f"{account_id}@example.local",
                password_hash="not-a-real-hash", role=role, status="active", patient_id=patient_id,
            )
        )
        db.commit()
        created_account_ids.append(account_id)
        token = create_access_token(sub=account_id, role=role, patient_id=patient_id)
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
        db.query(AgentActivitySnapshot).filter(AgentActivitySnapshot.actor_id.in_(created_account_ids)).delete(synchronize_session=False)
        db.query(Account).filter(Account.id.in_(created_account_ids)).delete(synchronize_session=False)
        for pid in created_patient_ids:
            db.query(Patient).filter(Patient.id == pid).delete(synchronize_session=False)
        db.commit()
        db.close()


def _seed_snapshot(*, patient_id: str, actor_id: str, trace_id: str, agent_run_id: str, activities: list[dict]) -> None:
    db = SessionLocal()
    try:
        db.add(
            AgentActivitySnapshot(
                agent_run_id=agent_run_id, trace_id=trace_id, patient_id=patient_id, actor_id=actor_id,
                intent="DRUG_INFORMATION", status="COMPLETED", model_calls=1, activities_json=activities,
            )
        )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Authorization: own trace / cross-patient / not found / non-patient role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_reads_their_own_trace_activity(account_client):
    patient = await account_client("patient", patient_id="patient-activity-1")
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    _seed_snapshot(
        patient_id="patient-activity-1", actor_id=patient._test_account_id, trace_id=trace_id,
        agent_run_id=f"run-{uuid.uuid4().hex[:8]}",
        activities=[{"type": "intent", "label": "Đã xác định yêu cầu", "status": "completed", "duration_ms": None}],
    )
    resp = await patient.get(f"/api/v1/agent/v2/traces/{trace_id}/activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["activities"][0]["label"] == "Đã xác định yêu cầu"


@pytest.mark.asyncio
async def test_cross_patient_trace_activity_is_denied(account_client):
    victim = await account_client("patient", patient_id="patient-activity-victim")
    attacker = await account_client("patient", patient_id="patient-activity-attacker")
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    _seed_snapshot(
        patient_id="patient-activity-victim", actor_id=victim._test_account_id, trace_id=trace_id,
        agent_run_id=f"run-{uuid.uuid4().hex[:8]}", activities=[],
    )
    resp = await attacker.get(f"/api/v1/agent/v2/traces/{trace_id}/activity")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unknown_trace_returns_available_false_not_404(account_client):
    patient = await account_client("patient", patient_id="patient-activity-2")
    resp = await patient.get("/api/v1/agent/v2/traces/does-not-exist/activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["activities"] == []


@pytest.mark.asyncio
async def test_doctor_cannot_read_patient_activity(account_client):
    doctor = await account_client("doctor")
    resp = await doctor.get("/api/v1/agent/v2/traces/whatever/activity")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Real end-to-end: /agent/v2/orchestrate actually persists what
# build_activity_timeline() says it should, served back correctly.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_orchestrate_call_persists_and_serves_real_activity(account_client, monkeypatch):
    # BUILD-28 schedule-deterministic query -- zero OpenAI calls, so this
    # stays a real, fast, free end-to-end HTTP test (real orchestrator, real
    # DB, real route), not a mock.
    enabled_settings = get_settings().model_copy(update={"agent_runtime_enabled": True, "agent_canary_allowlist": "", "agent_rollout_percentage": 0})
    monkeypatch.setattr("backend.api.agent_v2_routes.get_settings", lambda: enabled_settings)

    patient = await account_client("patient", patient_id="patient-activity-e2e")
    resp = await patient.post(
        "/api/v1/agent/v2/orchestrate",
        json={"patient_id": "patient-activity-e2e", "message": "ngày mai tôi uống thuốc gì"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "UPCOMING_DOSES"
    trace_id = body["trace_id"]

    activity_resp = await patient.get(f"/api/v1/agent/v2/traces/{trace_id}/activity")
    assert activity_resp.status_code == 200
    activity_body = activity_resp.json()
    assert activity_body["available"] is True
    labels = [a["label"] for a in activity_body["activities"]]
    assert "Đã xác định yêu cầu" in labels
    assert "Đã xác định thời gian" in labels
    assert "Đã kiểm tra lịch dùng thuốc" in labels
    assert "Đã hoàn thành câu trả lời" in labels
    # BUILD-28's own guarantee, re-verified end to end through the real HTTP
    # route: zero Main Model calls for a schedule-only query -- and BUILD-30
    # never invents a "thinking"/"called Main Model" step regardless.
    forbidden = {"Đang dùng AI suy nghĩ", "Đã gọi Main Model"}
    assert forbidden.isdisjoint(labels)
