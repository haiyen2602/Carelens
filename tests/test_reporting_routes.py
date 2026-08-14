"""GET/PATCH /api/v1/reporting/patients, GET /api/v1/escalations, GET
/api/v1/audit-log (backend/api/reporting_routes.py) - test qua FastAPI
TestClient that, DB that. Cung pattern voi tests/test_escalation_ack.py."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import AuditLog, DoseEvent, Escalation, Patient  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_patient(*, watch: bool = False) -> str:
    patient_id = f"test-report-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name="Bệnh nhân báo cáo", watch=watch))
        db.commit()
    finally:
        db.close()
    return patient_id


def _seed_due_dose(patient_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        db.add(
            DoseEvent(
                prescription_id="presc-x",
                patient_id=patient_id,
                scheduled_at=now - timedelta(hours=2),
                window_start=now - timedelta(hours=2, minutes=30),
                window_end=now - timedelta(hours=1, minutes=30),
                status=status,
                expected_items=[],
            )
        )
        db.commit()
    finally:
        db.close()


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_list_reporting_patients_includes_adherence_and_watch(client):
    patient_id = _seed_patient(watch=False)
    _seed_due_dose(patient_id, "TAKEN")
    _seed_due_dose(patient_id, "MISSED")
    try:
        response = await client.get("/api/v1/reporting/patients")
        assert response.status_code == 200
        row = next(p for p in response.json() if p["id"] == patient_id)
        assert row["watch"] is False
        assert row["adherence_pct"] == 50.0
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_patient_with_no_due_doses_has_null_adherence(client):
    patient_id = _seed_patient()
    try:
        response = await client.get("/api/v1/reporting/patients")
        row = next(p for p in response.json() if p["id"] == patient_id)
        assert row["adherence_pct"] is None
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_update_patient_watch(client):
    patient_id = _seed_patient(watch=False)
    try:
        response = await client.patch(f"/api/v1/reporting/patients/{patient_id}/watch", json={"watch": True})
        assert response.status_code == 200
        assert response.json() == {"id": patient_id, "watch": True}

        db = SessionLocal()
        try:
            assert db.get(Patient, patient_id).watch is True
        finally:
            db.close()
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_update_watch_for_unknown_patient_returns_404(client):
    response = await client.patch(
        "/api/v1/reporting/patients/does-not-exist/watch", json={"watch": True}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_escalations_filters_by_patient_and_status(client):
    patient_id = _seed_patient()
    db = SessionLocal()
    try:
        db.add(
            Escalation(
                patient_id=patient_id,
                severity="HIGH",
                trigger="missed_dose",
                reason="test open",
                status="OPEN",
            )
        )
        db.add(
            Escalation(
                patient_id=patient_id,
                severity="LOW",
                trigger="missed_dose",
                reason="test resolved",
                status="RESOLVED",
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        response = await client.get("/api/v1/escalations", params={"patient_id": patient_id, "status": "OPEN"})
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["status"] == "OPEN"
        assert rows[0]["reason"] == "test open"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_list_audit_log_filters_by_patient(client):
    patient_id = _seed_patient()
    db = SessionLocal()
    try:
        db.add(
            AuditLog(
                patient_id=patient_id,
                utterance="test utterance",
                trace=[],
                final_response="test response",
                total_duration_ms=123.4,
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        response = await client.get("/api/v1/audit-log", params={"patient_id": patient_id})
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["utterance"] == "test utterance"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_reporting_endpoints_require_internal_secret():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as unauthenticated_client:
        response = await unauthenticated_client.get("/api/v1/reporting/patients")
    assert response.status_code == 401
