"""POST/DELETE/GET /api/v1/caregiver-links (backend/api/caregiver_routes.py)
- test qua FastAPI TestClient that, DB that. Cung pattern voi
tests/test_escalation_ack.py va tests/test_api/test_account_routes.py (admin
role qua JWT that)."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, CaregiverLink, DoseEvent, Escalation, Patient  # noqa: E402
from backend.services.auth import hash_password  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest_asyncio.fixture
async def admin_token(client):
    email = f"test-admin-{uuid.uuid4().hex[:8]}@example.com"
    password = "a-real-test-password-123"
    db = SessionLocal()
    account = Account(full_name="Admin test", email=email, password_hash=hash_password(password), role="admin")
    db.add(account)
    db.commit()
    account_id = account.id
    db.close()

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    yield token

    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


def _seed_patient() -> str:
    patient_id = f"test-cg-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name="Bệnh nhân caregiver test"))
        db.commit()
    finally:
        db.close()
    return patient_id


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(CaregiverLink).filter(CaregiverLink.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_create_link_requires_admin_role(client):
    response = await client.post(
        "/api/v1/caregiver-links",
        json={"caregiver_account_id": "cg1", "patient_id": "p1", "relationship": "Con gái"},
    )
    # client fixture (conftest.py) dung JWT role=caregiver, khong phai admin.
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_creates_and_deletes_link(client, admin_token):
    patient_id = _seed_patient()
    try:
        create_resp = await client.post(
            "/api/v1/caregiver-links",
            json={"caregiver_account_id": "cg-1", "patient_id": patient_id, "relationship": "Con gái"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert create_resp.status_code == 201
        link_id = create_resp.json()["id"]
        assert create_resp.json()["relationship"] == "Con gái"

        delete_resp = await client.delete(
            f"/api/v1/caregiver-links/{link_id}", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert delete_resp.status_code == 204
        assert delete_resp.content == b""

        db = SessionLocal()
        assert db.get(CaregiverLink, link_id) is None
        db.close()
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_delete_unknown_link_returns_404(client, admin_token):
    response = await client.delete(
        f"/api/v1/caregiver-links/{uuid.uuid4().hex}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_requires_exactly_one_query_param(client):
    missing_both = await client.get("/api/v1/caregiver-links")
    assert missing_both.status_code == 400

    both = await client.get(
        "/api/v1/caregiver-links", params={"patient_id": "p1", "caregiver_account_id": "cg1"}
    )
    assert both.status_code == 400


@pytest.mark.asyncio
async def test_list_links_for_patient_includes_caregiver_name(client, admin_token):
    patient_id = _seed_patient()
    caregiver_email = f"test-cg-{uuid.uuid4().hex[:8]}@example.com"
    db = SessionLocal()
    caregiver_account = Account(
        full_name="Nguoi than test",
        email=caregiver_email,
        password_hash=hash_password("x"),
        role="caregiver",
    )
    db.add(caregiver_account)
    db.commit()
    caregiver_id = caregiver_account.id
    db.close()

    try:
        await client.post(
            "/api/v1/caregiver-links",
            json={"caregiver_account_id": caregiver_id, "patient_id": patient_id, "relationship": "Vợ"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        response = await client.get("/api/v1/caregiver-links", params={"patient_id": patient_id})
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["caregiver_name"] == "Nguoi than test"
        assert rows[0]["relationship"] == "Vợ"
    finally:
        _cleanup(patient_id)
        db = SessionLocal()
        db.query(Account).filter(Account.id == caregiver_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_list_monitored_patients_for_caregiver(client, admin_token):
    patient_id = _seed_patient()
    caregiver_account_id = f"test-cg-monitor-{uuid.uuid4().hex[:8]}"

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    db = SessionLocal()
    try:
        # Liều hôm nay: 1 TAKEN, 1 PENDING.
        db.add(
            DoseEvent(
                prescription_id="presc-x",
                patient_id=patient_id,
                scheduled_at=today_start + timedelta(hours=8),
                window_start=today_start + timedelta(hours=7, minutes=30),
                window_end=today_start + timedelta(hours=8, minutes=30),
                status="TAKEN",
                expected_items=[],
            )
        )
        db.add(
            DoseEvent(
                prescription_id="presc-x",
                patient_id=patient_id,
                scheduled_at=today_start + timedelta(hours=20),
                window_start=today_start + timedelta(hours=19, minutes=30),
                window_end=today_start + timedelta(hours=20, minutes=30),
                status="PENDING",
                expected_items=[],
            )
        )
        db.add(
            Escalation(
                patient_id=patient_id,
                severity="HIGH",
                trigger="missed_dose",
                # Reason THAT trong san xuat la chuoi ky thuat (audit/bac si,
                # xem dose_confirmation_nodes.py) - co y KHONG dung 1 cau de
                # doc nhu truoc, de bai test nay chung minh duoc `title` tra
                # ve KHONG con la `reason` nguyen van nua (xem assertion duoi).
                reason="SEVERITY=Nguy hiểm tu classification='MISSED' (BR-3.1-3.6)",
                status="OPEN",
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        await client.post(
            "/api/v1/caregiver-links",
            json={
                "caregiver_account_id": caregiver_account_id,
                "patient_id": patient_id,
                "relationship": "Con trai",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        response = await client.get(
            "/api/v1/caregiver-links", params={"caregiver_account_id": caregiver_account_id}
        )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["patient_id"] == patient_id
        assert row["relationship"] == "Con trai"
        assert row["dose_taken_today"] == 1
        assert row["dose_total_today"] == 2
        assert len(row["open_escalations"]) == 1
        # title phai la tieu de NGAN, DE HIEU (friendly_escalation_title) -
        # KHONG con la `reason` ky thuat nguyen van nhu truoc (bug da sua
        # 2026-08-14, xem backend/services/escalation.py).
        assert row["open_escalations"][0]["title"] == "Bỏ lỡ liều thuốc – mức nguy hiểm"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_list_for_unknown_caregiver_returns_empty(client):
    response = await client.get(
        "/api/v1/caregiver-links", params={"caregiver_account_id": "nobody-has-this-id"}
    )
    assert response.status_code == 200
    assert response.json() == []
