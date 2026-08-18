"""GET /api/v1/escalations/current (vong 2 muc 4 y 4, chot shape 2026-08-12)
- test qua FastAPI TestClient that, DB that."""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, Escalation  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_escalation(patient_id: str, status: str = "OPEN") -> str:
    db = SessionLocal()
    try:
        row = Escalation(
            patient_id=patient_id,
            dose_event_id=None,
            severity="HIGH",
            trigger="safety_redflag",
            raw_utterance="test",
            reason="test escalation for /escalations/current",
            status=status,
            notified=["caregiver"],
            reminder_count=2,
            last_reminder_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _cleanup(escalation_id: str) -> None:
    db = SessionLocal()
    try:
        row = db.get(Escalation, escalation_id)
        if row is not None:
            db.delete(row)
            db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _seed_authenticated_accounts():
    """JWT subjects must refer to persisted active accounts on clean PostgreSQL."""

    db = SessionLocal()
    account_ids = ("test-caregiver-escalation-status", "test-patient-escalation-status")
    try:
        db.add_all(
            [
                Account(
                    id=account_ids[0],
                    full_name="Escalation status caregiver",
                    email="test-caregiver-escalation-status@example.local",
                    password_hash="not-a-real-hash",
                    role="caregiver",
                    status="active",
                ),
                Account(
                    id=account_ids[1],
                    full_name="Escalation status patient",
                    email="test-patient-escalation-status@example.local",
                    password_hash="not-a-real-hash",
                    role="patient",
                    status="active",
                    patient_id="test-escstatus-own-placeholder",
                ),
            ]
        )
        db.commit()
        yield
    finally:
        db.query(Account).filter(Account.id.in_(account_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_missing_authorization_header_is_rejected_with_401():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/escalations/current", params={"patient_id": "p1"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_patient_role_without_patient_id_query_param_is_400():
    token = create_access_token(sub="test-caregiver-escalation-status", role="caregiver")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as ac:
        response = await ac.get("/api/v1/escalations/current")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_returns_null_when_no_open_escalation():
    patient_id = f"test-escstatus-{uuid.uuid4().hex[:8]}"
    token = create_access_token(sub="test-caregiver-escalation-status", role="caregiver")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as ac:
        response = await ac.get("/api/v1/escalations/current", params={"patient_id": patient_id})
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_returns_open_escalation_fields():
    patient_id = f"test-escstatus-{uuid.uuid4().hex[:8]}"
    escalation_id = _seed_escalation(patient_id, status="OPEN")
    token = create_access_token(sub="test-caregiver-escalation-status", role="caregiver")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
        ) as ac:
            response = await ac.get("/api/v1/escalations/current", params={"patient_id": patient_id})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "OPEN"
        assert body["severity"] == "HIGH"
        assert body["reminder_count"] == 2
        assert body["created_at"]
    finally:
        _cleanup(escalation_id)


@pytest.mark.asyncio
async def test_resolved_escalation_is_not_returned():
    patient_id = f"test-escstatus-{uuid.uuid4().hex[:8]}"
    escalation_id = _seed_escalation(patient_id, status="RESOLVED")
    token = create_access_token(sub="test-caregiver-escalation-status", role="caregiver")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
        ) as ac:
            response = await ac.get("/api/v1/escalations/current", params={"patient_id": patient_id})
        assert response.status_code == 200
        assert response.json() is None
    finally:
        _cleanup(escalation_id)


@pytest.mark.asyncio
async def test_patient_role_cannot_read_another_patients_escalation_via_query_param():
    """Dung 1 cho noi get_current_patient_id() - role=patient LUON dung
    patient_id cua chinh JWT, bo qua query string du co truyen gi vao."""
    own_patient_id = f"test-escstatus-own-{uuid.uuid4().hex[:8]}"
    other_patient_id = f"test-escstatus-other-{uuid.uuid4().hex[:8]}"
    escalation_id = _seed_escalation(other_patient_id, status="OPEN")
    token = create_access_token(sub="test-patient-escalation-status", role="patient", patient_id=own_patient_id)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
        ) as ac:
            # Tu go patient_id cua NGUOI KHAC vao query string.
            response = await ac.get("/api/v1/escalations/current", params={"patient_id": other_patient_id})
        assert response.status_code == 200
        # Phai tra ve None (khong co escalation OPEN cua own_patient_id),
        # KHONG PHAI escalation cua other_patient_id.
        assert response.json() is None
    finally:
        _cleanup(escalation_id)
