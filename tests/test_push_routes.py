"""GET /push/vapid-public-key + POST/DELETE /push/subscribe
(backend/api/push_routes.py) - test qua FastAPI TestClient that, DB that.
Cung pattern voi tests/test_nudge_routes.py."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, Patient, PushSubscription  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest_asyncio.fixture
async def patient_token():
    patient_id = f"test-push-{uuid.uuid4().hex[:8]}"
    account_id = f"test-push-acc-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    db.add(Patient(id=patient_id, full_name="Benh nhan push test"))
    db.add(
        Account(
            id=account_id,
            full_name="Benh nhan push test",
            email=f"{account_id}@example.local",
            password_hash="not-a-real-hash",
            role="patient",
            patient_id=patient_id,
            status="active",
        )
    )
    db.commit()
    db.close()

    yield patient_id, create_access_token(sub=account_id, role="patient", patient_id=patient_id)

    db = SessionLocal()
    db.query(PushSubscription).filter(PushSubscription.patient_id == patient_id).delete(
        synchronize_session=False
    )
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_vapid_public_key_endpoint_tra_ve_chuoi(client):
    """Khong assert gia tri cu the - moi moi truong 1 cap khoa rieng. Chi can
    endpoint song va tra dung shape; rong = chua cau hinh, van hop le."""
    response = await client.get("/api/v1/push/vapid-public-key")
    assert response.status_code == 200
    assert isinstance(response.json()["public_key"], str)


@pytest.mark.asyncio
async def test_subscribe_roi_unsubscribe(client, patient_token):
    patient_id, token = patient_token
    headers = {"Authorization": f"Bearer {token}"}
    endpoint = f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}"
    body = {"endpoint": endpoint, "keys": {"p256dh": "khoa-p256dh", "auth": "khoa-auth"}}

    resp = await client.post("/api/v1/push/subscribe", json=body, headers=headers)
    assert resp.status_code == 204

    db = SessionLocal()
    rows = db.query(PushSubscription).filter(PushSubscription.patient_id == patient_id).all()
    assert len(rows) == 1
    assert rows[0].endpoint == endpoint
    db.close()

    resp = await client.delete(
        "/api/v1/push/subscribe", params={"endpoint": endpoint}, headers=headers
    )
    assert resp.status_code == 204

    db = SessionLocal()
    assert db.query(PushSubscription).filter(PushSubscription.patient_id == patient_id).count() == 0
    db.close()


@pytest.mark.asyncio
async def test_subscribe_lai_cung_endpoint_thi_upsert_khong_tao_dong_thu_2(client, patient_token):
    """1 thiet bi = 1 dong. Neu tao dong thu 2 thi moi lan nhac se ban 2 lan
    vao cung 1 may - dung lo hong da chan bang UNIQUE tren endpoint."""
    patient_id, token = patient_token
    headers = {"Authorization": f"Bearer {token}"}
    endpoint = f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}"

    await client.post(
        "/api/v1/push/subscribe",
        json={"endpoint": endpoint, "keys": {"p256dh": "cu", "auth": "cu"}},
        headers=headers,
    )
    await client.post(
        "/api/v1/push/subscribe",
        json={"endpoint": endpoint, "keys": {"p256dh": "moi", "auth": "moi"}},
        headers=headers,
    )

    db = SessionLocal()
    rows = db.query(PushSubscription).filter(PushSubscription.patient_id == patient_id).all()
    assert len(rows) == 1, "subscribe lai phai UPSERT, khong duoc tao dong thu 2"
    assert rows[0].p256dh == "moi", "phai cap nhat khoa moi nhat"
    db.close()


@pytest.mark.asyncio
async def test_role_khong_phai_patient_bi_tu_choi(client):
    """`client` fixture dang nhap voi role=caregiver - khong co danh tinh
    benh nhan nen khong tu dang ky thiet bi cho ai duoc."""
    resp = await client.post(
        "/api/v1/push/subscribe",
        json={"endpoint": "https://example.com/x", "keys": {"p256dh": "a", "auth": "b"}},
    )
    assert resp.status_code == 403
