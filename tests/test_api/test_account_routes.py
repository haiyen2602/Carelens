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
from backend.db.models import Account  # noqa: E402
from backend.main import app  # noqa: E402
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
