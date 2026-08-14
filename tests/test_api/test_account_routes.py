"""account-api (follow-up TASK-010, specs/api-contracts.md muc 1b) -
POST/GET/PATCH /api/v1/accounts, chi role=admin duoc goi. Dung DB that,
giong pattern test_auth_routes.py."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, DoctorWatch, Patient  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import hash_password  # noqa: E402
from backend.services.patient_id import _PATIENT_ID_RE  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_account(role: str, status: str = "active") -> dict:
    email = f"test-account-{uuid.uuid4().hex[:8]}@example.com"
    password = "a-real-test-password-123"
    db = SessionLocal()
    account = Account(
        full_name=f"Test {role}",
        email=email,
        password_hash=hash_password(password),
        role=role,
        status=status,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    account_id = account.id
    db.close()
    return {"id": account_id, "email": email, "password": password, "role": role}


def _cleanup(account_id: str) -> None:
    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


def _cleanup_with_patient(account_id: str, patient_id: str | None) -> None:
    """Nhu `_cleanup()` nhung xoa THEM dong `Patient`/`DoctorWatch` - dung
    cho test tao tai khoan role=patient (2026-08-14): create_account() gio
    co the tao dong Patient that + tu dong DoctorWatch cho moi bac si dang
    co (auto_watch_new_patient), khong chi gan patient_id vao Account nhu
    truoc."""
    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    if patient_id:
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.query(DoctorWatch).filter(DoctorWatch.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest_asyncio.fixture
async def admin_token(client):
    admin = _make_account("admin")
    resp = await client.post("/api/v1/auth/login", json={"email": admin["email"], "password": admin["password"]})
    token = resp.json()["access_token"]
    yield token
    _cleanup(admin["id"])


@pytest_asyncio.fixture
async def doctor_token(client):
    doctor = _make_account("doctor")
    resp = await client.post("/api/v1/auth/login", json={"email": doctor["email"], "password": doctor["password"]})
    token = resp.json()["access_token"]
    yield token
    _cleanup(doctor["id"])


@pytest.mark.asyncio
async def test_create_account_requires_admin_role(client, doctor_token):
    response = await client.post(
        "/api/v1/accounts",
        json={"email": "x@example.com", "password": "whatever123", "full_name": "X", "role": "patient"},
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_account_requires_authentication(client):
    response = await client.post(
        "/api/v1/accounts",
        json={"email": "x@example.com", "password": "whatever123", "full_name": "X", "role": "patient"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_creates_account_then_new_account_can_log_in(client, admin_token):
    new_email = f"test-created-{uuid.uuid4().hex[:8]}@example.com"
    create_response = await client.post(
        "/api/v1/accounts",
        json={
            "email": new_email,
            "password": "a-real-test-password-123",
            "full_name": "BS Test",
            "role": "doctor",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert "password_hash" not in created
    assert created["status"] == "active"

    try:
        login_response = await client.post(
            "/api/v1/auth/login", json={"email": new_email, "password": "a-real-test-password-123"}
        )
        assert login_response.status_code == 200
        assert login_response.json()["user"]["role"] == "doctor"
    finally:
        _cleanup(created["id"])


@pytest.mark.asyncio
async def test_create_patient_account_without_patient_id_autogenerates_bn_id(client, admin_token):
    """SUA 2026-08-14 (thiet ke ID benh nhan, yeu cau PM) - truoc do khong
    go patient_id se tao Account voi patient_id=None VA khong tung tao dong
    Patient nao (benh nhan "co tai khoan nhung khong co ho so"). Gio phai tu
    sinh dung dang BNxxxxx (khop du lieu cu vd "BN00002" cua MCK) VA tao that
    dong Patient dang sau, dong bo voi duong tu dang ky."""
    new_email = f"test-created-{uuid.uuid4().hex[:8]}@example.com"
    create_response = await client.post(
        "/api/v1/accounts",
        json={
            "email": new_email,
            "password": "a-real-test-password-123",
            "full_name": "BN Test Moi",
            "role": "patient",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    patient_id = created["patient_id"]
    assert patient_id is not None
    assert _PATIENT_ID_RE.match(patient_id), f"patient_id {patient_id!r} không đúng dạng BNxxxxx"

    try:
        db = SessionLocal()
        patient = db.get(Patient, patient_id)
        assert patient is not None
        assert patient.full_name == "BN Test Moi"
        db.close()
    finally:
        _cleanup_with_patient(created["id"], patient_id)


@pytest.mark.asyncio
async def test_create_patient_account_with_explicit_patient_id_keeps_it_and_creates_patient_row(
    client, admin_token
):
    """Van giu duoc cach link toi 1 patient_id CO SAN (dung y goc cua field
    nay - vd du lieu demo "demo-patient-01", xem docstring
    AccountCreateRequest) - KHONG bi ep ve dang BNxxxxx. Nhung PHAI tao dong
    Patient that neu chua co (sua bug cu: truoc day khong bao gio tao)."""
    new_email = f"test-created-{uuid.uuid4().hex[:8]}@example.com"
    explicit_patient_id = f"demo-patient-{uuid.uuid4().hex[:8]}"
    create_response = await client.post(
        "/api/v1/accounts",
        json={
            "email": new_email,
            "password": "a-real-test-password-123",
            "full_name": "BN Link San",
            "role": "patient",
            "patient_id": explicit_patient_id,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["patient_id"] == explicit_patient_id  # giu nguyen, khong doi sang BNxxxxx

    try:
        db = SessionLocal()
        patient = db.get(Patient, explicit_patient_id)
        assert patient is not None
        assert patient.full_name == "BN Link San"
        db.close()
    finally:
        _cleanup_with_patient(created["id"], explicit_patient_id)


@pytest.mark.asyncio
async def test_create_account_with_duplicate_email_returns_409(client, admin_token):
    existing = _make_account("patient")
    try:
        response = await client.post(
            "/api/v1/accounts",
            json={
                "email": existing["email"],
                "password": "another-password-123",
                "full_name": "Dup",
                "role": "patient",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409
    finally:
        _cleanup(existing["id"])


@pytest.mark.asyncio
async def test_list_accounts_requires_admin_role(client, doctor_token):
    response = await client.get("/api/v1/accounts", headers={"Authorization": f"Bearer {doctor_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_accounts_returns_created_account(client, admin_token):
    account = _make_account("patient")
    try:
        response = await client.get("/api/v1/accounts", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        ids = [a["id"] for a in response.json()]
        assert account["id"] in ids
    finally:
        _cleanup(account["id"])


@pytest.mark.asyncio
async def test_locking_account_blocks_login(client, admin_token):
    account = _make_account("patient")
    try:
        lock_response = await client.patch(
            f"/api/v1/accounts/{account['id']}/status",
            json={"status": "locked"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert lock_response.status_code == 200
        assert lock_response.json()["status"] == "locked"

        login_response = await client.post(
            "/api/v1/auth/login", json={"email": account["email"], "password": account["password"]}
        )
        assert login_response.status_code == 403
    finally:
        _cleanup(account["id"])


@pytest.mark.asyncio
async def test_update_status_of_unknown_account_returns_404(client, admin_token):
    response = await client.patch(
        "/api/v1/accounts/does-not-exist/status",
        json={"status": "locked"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404
