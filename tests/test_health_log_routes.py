"""POST /api/v1/health-log (backend/api/health_log_routes.py) - benh nhan tu
ghi nhat ky suc khoe, muc "mid"/"high" tao Escalation that cho nguoi than
thay. Test qua FastAPI TestClient that, DB that - cung pattern voi
tests/test_caregiver_routes.py."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, Escalation, Patient  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token, hash_password  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest_asyncio.fixture
async def patient_client():
    """Client dang nhap role=patient THAT (khac fixture `client` cua
    conftest.py dung role=caregiver) - endpoint nay chi cho benh nhan tu ghi
    nhat ky cho chinh minh."""
    patient_id = f"test-hl-{uuid.uuid4().hex[:8]}"
    account_id = f"test-hl-acct-{uuid.uuid4().hex[:8]}"

    db = SessionLocal()
    db.add(Patient(id=patient_id, full_name="Benh nhan health log test"))
    db.add(
        Account(
            id=account_id,
            full_name="Benh nhan health log test",
            email=f"{account_id}@example.local",
            password_hash=hash_password("x"),
            role="patient",
            patient_id=patient_id,
            status="active",
        )
    )
    db.commit()
    db.close()

    token = create_access_token(sub=account_id, role="patient", patient_id=patient_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as ac:
        yield ac, patient_id

    db = SessionLocal()
    db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


def _escalations_of(patient_id: str) -> list[Escalation]:
    db = SessionLocal()
    try:
        return db.query(Escalation).filter(Escalation.patient_id == patient_id).all()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_low_level_does_not_create_escalation(patient_client):
    ac, patient_id = patient_client
    response = await ac.post("/api/v1/health-log", json={"text": "hơi mệt chút", "level": "low"})
    assert response.status_code == 200
    assert response.json()["escalation_id"] is None
    assert _escalations_of(patient_id) == []


@pytest.mark.asyncio
async def test_mid_level_creates_medium_escalation(patient_client):
    ac, patient_id = patient_client
    response = await ac.post(
        "/api/v1/health-log", json={"text": "chóng mặt, buồn nôn", "level": "mid"}
    )
    assert response.status_code == 200
    assert response.json()["escalation_id"] is not None

    rows = _escalations_of(patient_id)
    assert len(rows) == 1
    assert rows[0].severity == "MEDIUM"
    assert rows[0].trigger == "patient_reported"
    assert rows[0].reason == "chóng mặt, buồn nôn"
    assert rows[0].status == "OPEN"
    assert "caregiver" in rows[0].notified


@pytest.mark.asyncio
async def test_high_level_creates_high_escalation(patient_client):
    ac, patient_id = patient_client
    response = await ac.post("/api/v1/health-log", json={"text": "", "level": "high"})
    assert response.status_code == 200

    rows = _escalations_of(patient_id)
    assert len(rows) == 1
    assert rows[0].severity == "HIGH"
    # text rong -> dung mac dinh, khop health/page.tsx::guiBaoVanDe()
    assert rows[0].reason == "Không mô tả chi tiết"


@pytest.mark.asyncio
async def test_non_patient_role_is_rejected(client):
    """`client` cua conftest.py dung role=caregiver - khong duoc tu ghi nhat
    ky suc khoe (endpoint nay danh cho benh nhan tu bao ve chinh minh)."""
    response = await client.post("/api/v1/health-log", json={"text": "x", "level": "mid"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_invalid_level_is_rejected(patient_client):
    ac, _ = patient_client
    response = await ac.post("/api/v1/health-log", json={"text": "x", "level": "khong-hop-le"})
    assert response.status_code == 422
