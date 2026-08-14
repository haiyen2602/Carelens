"""PATCH /api/v1/doses/{dose_id} (backend/api/dose_routes.py) - test qua
FastAPI TestClient that, DB that. Cung pattern voi tests/test_escalation_ack.py.

Cac nhanh phan quyen can kiem: patient tu sua duoc lieu cua chinh minh (khong
sua duoc cua nguoi khac), caregiver can co CaregiverLink toi dung benh nhan,
doctor sua duoc lieu cua BAT KY benh nhan nao (khong con rang buoc theo
Patient.doctor_id - bac si quan ly toan bo benh nhan qua tim kiem theo ID)."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import CaregiverLink, DoseEvent, Patient  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_dose(patient_id: str, doctor_id: str | None = None) -> tuple[str, str]:
    """Tra ve (patient_id, dose_id) - tao ca Patient lan DoseEvent."""
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name="Bệnh nhân dose test", doctor_id=doctor_id))
        now = datetime.now(UTC)
        dose = DoseEvent(
            prescription_id="presc-x",
            patient_id=patient_id,
            scheduled_at=now,
            window_start=now - timedelta(minutes=30),
            window_end=now + timedelta(minutes=30),
            status="PENDING",
            expected_items=[],
        )
        db.add(dose)
        db.commit()
        dose_id = dose.id
    finally:
        db.close()
    return patient_id, dose_id


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(CaregiverLink).filter(CaregiverLink.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_patient_updates_own_dose(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="acct-1", role="patient", patient_id=patient_id)

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "TAKEN"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_patient_cannot_update_others_dose(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="acct-2", role="patient", patient_id="someone-else")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_caregiver_with_link_can_update(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    caregiver_account_id = "cg-account-1"
    db = SessionLocal()
    db.add(CaregiverLink(caregiver_account_id=caregiver_account_id, patient_id=patient_id, relationship="Con gái"))
    db.commit()
    db.close()
    token = create_access_token(sub=caregiver_account_id, role="caregiver")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_caregiver_without_link_forbidden(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="cg-account-no-link", role="caregiver")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_doctor_in_charge_can_update(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    doctor_id = "doctor-account-1"
    _, dose_id = _seed_dose(patient_id, doctor_id=doctor_id)
    token = create_access_token(sub=doctor_id, role="doctor")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "MISSED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "MISSED"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_other_doctor_can_update(client):
    """Bac si khong phai doctor_id cua benh nhan van thao tac duoc - khong
    con rang buoc theo Patient.doctor_id, bat ky bac si nao cung quan ly
    duoc moi benh nhan."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id, doctor_id="doctor-account-1")
    token = create_access_token(sub="doctor-account-2", role="doctor")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "MISSED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "MISSED"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_unknown_dose_returns_404(client):
    token = create_access_token(sub="doctor-account-1", role="doctor")
    response = await client.patch(
        f"/api/v1/doses/{uuid.uuid4().hex}",
        json={"status": "TAKEN"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
