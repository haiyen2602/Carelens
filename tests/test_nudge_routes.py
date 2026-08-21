"""POST /api/v1/nudges + GET /api/v1/nudges/unseen (backend/api/nudge_routes.py)
- test qua FastAPI TestClient that, DB that. Cung pattern voi
tests/test_caregiver_routes.py."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, CaregiverLink, Nudge, Patient  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_patient() -> str:
    patient_id = f"test-nudge-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name="Bệnh nhân nudge test"))
        db.commit()
    finally:
        db.close()
    return patient_id


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(Nudge).filter(Nudge.patient_id == patient_id).delete(synchronize_session=False)
        db.query(CaregiverLink).filter(CaregiverLink.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest_asyncio.fixture
async def patient_token(client):
    patient_id = _seed_patient()
    account_id = f"test-nudge-account-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    db.add(
        Account(
            id=account_id,
            full_name="Bệnh nhân nudge test",
            email=f"{account_id}@example.local",
            password_hash="not-a-real-hash",
            role="patient",
            patient_id=patient_id,
            status="active",
        )
    )
    db.commit()
    db.close()

    token = create_access_token(sub=account_id, role="patient", patient_id=patient_id)
    yield patient_id, token

    _cleanup(patient_id)
    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_send_nudge_requires_accepted_link(client, patient_token):
    # `client` fixture (conftest.py) dang nhap voi role=caregiver nhung CHUA
    # co CaregiverLink toi patient_id nay - phai bi tu choi.
    patient_id, _ = patient_token
    response = await client.post("/api/v1/nudges", json={"patient_id": patient_id, "message": "Đến giờ uống thuốc rồi nha"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_send_nudge_then_patient_polls_unseen(client, patient_token):
    patient_id, token = patient_token
    db = SessionLocal()
    db.add(
        CaregiverLink(
            caregiver_account_id="test-caregiver-conftest",
            patient_id=patient_id,
            relationship="Con gái",
            status="accepted",
        )
    )
    db.commit()
    db.close()

    send_resp = await client.post(
        "/api/v1/nudges", json={"patient_id": patient_id, "message": "Đừng quên thuốc nhé"}
    )
    assert send_resp.status_code == 201
    body = send_resp.json()
    assert body["message"] == "Đừng quên thuốc nhé"
    assert body["caregiver_name"] == "Test caregiver caller"

    poll_resp = await client.get(
        "/api/v1/nudges/unseen", headers={"Authorization": f"Bearer {token}"}
    )
    assert poll_resp.status_code == 200
    unseen = poll_resp.json()
    assert len(unseen) == 1
    assert unseen[0]["message"] == "Đừng quên thuốc nhé"

    # Lan poll thu 2 phai rong - dong da bi danh dau seen_at o lan truoc.
    second_poll = await client.get(
        "/api/v1/nudges/unseen", headers={"Authorization": f"Bearer {token}"}
    )
    assert second_poll.status_code == 200
    assert second_poll.json() == []


@pytest.mark.asyncio
async def test_unknown_patient_returns_404(client):
    response = await client.post(
        "/api/v1/nudges", json={"patient_id": "khong-ton-tai", "message": "hi"}
    )
    assert response.status_code == 404
