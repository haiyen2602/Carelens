"""POST /api/v1/escalations/{id}/ack (api-contracts.md §6, vong 2 muc 13) -
test qua FastAPI TestClient that, DB that."""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Escalation  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_open_escalation(patient_id: str) -> str:
    db = SessionLocal()
    try:
        row = Escalation(
            patient_id=patient_id,
            dose_event_id=None,
            severity="HIGH",
            trigger="safety_redflag",
            raw_utterance="test",
            reason="test escalation for ack endpoint",
            status="OPEN",
            notified=["caregiver", "doctor"],
            reminder_count=2,
            last_reminder_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ack_marks_escalation_resolved(client):
    patient_id = f"test-ack-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    response = await client.post(f"/api/v1/escalations/{esc_id}/ack", json={"resolved_by": "doctor"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RESOLVED"
    assert body["resolved_by"] == "doctor"

    db = SessionLocal()
    try:
        row = db.get(Escalation, esc_id)
        assert row.status == "RESOLVED"
        assert row.resolved_by == "doctor"
        assert row.resolved_at is not None
    finally:
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_ack_nonexistent_escalation_returns_404(client):
    response = await client.post(
        f"/api/v1/escalations/{uuid.uuid4().hex}/ack", json={"resolved_by": "doctor"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ack_is_idempotent_when_called_twice(client):
    patient_id = f"test-ack-twice-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        r1 = await client.post(f"/api/v1/escalations/{esc_id}/ack", json={"resolved_by": "caregiver"})
        r2 = await client.post(f"/api/v1/escalations/{esc_id}/ack", json={"resolved_by": "doctor"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["resolved_by"] == "doctor", "lan ack thu 2 cap nhat lai resolved_by, khong loi"
    finally:
        db = SessionLocal()
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_ack_without_internal_secret_is_rejected(client):
    """Rao can require_internal_secret (muc 10 #10) phai ap dung ca cho
    endpoint moi nay, khong duoc quen wire (dung loai loi da tung xay ra)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    patient_id = f"test-ack-nosecret-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as unauthenticated_client:
            response = await unauthenticated_client.post(
                f"/api/v1/escalations/{esc_id}/ack", json={"resolved_by": "doctor"}
            )
        assert response.status_code == 401
    finally:
        db = SessionLocal()
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()
