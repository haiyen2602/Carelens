"""TASK-010 (api-contracts.md muc 1, auth-api) - POST /api/v1/auth/login,
POST /api/v1/auth/refresh, GET /api/v1/auth/me. Dung DB that (giong pattern
test_chat_routes.py) - tao/xoa 1 Account demo moi test, khong mock ORM."""

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
async def unauthenticated_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def demo_account():
    email = f"test-auth-{uuid.uuid4().hex[:8]}@example.com"
    password = "a-real-test-password-123"
    db = SessionLocal()
    account = Account(
        full_name="Nguyễn Văn Test",
        email=email,
        password_hash=hash_password(password),
        role="patient",
        patient_id="test-auth-patient-1",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    account_id = account.id
    db.close()

    yield {"id": account_id, "email": email, "password": password}

    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_login_with_correct_password_returns_jwt(unauthenticated_client, demo_account):
    response = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["id"] == demo_account["id"]
    assert body["user"]["role"] == "patient"


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(unauthenticated_client, demo_account):
    response = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_401(unauthenticated_client):
    response = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": "nobody-here@example.com", "password": "whatever123"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_bearer_token(unauthenticated_client):
    response = await unauthenticated_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_then_me_returns_account_info(unauthenticated_client, demo_account):
    login_response = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    access_token = login_response.json()["access_token"]

    me_response = await unauthenticated_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_response.status_code == 200
    body = me_response.json()
    assert body["id"] == demo_account["id"]
    assert body["email"] == demo_account["email"]
    assert body["patient_id"] == "test-auth-patient-1"


@pytest.mark.asyncio
async def test_refresh_with_access_token_is_rejected(unauthenticated_client, demo_account):
    """refresh_token va access_token KHONG hoan doi cho nhau - /auth/refresh
    phai tu choi 1 access_token that gui nham vao day (payload thieu
    type=refresh)."""
    login_response = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    access_token = login_response.json()["access_token"]

    response = await unauthenticated_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": access_token}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_valid_refresh_token_returns_new_access_token(unauthenticated_client, demo_account):
    login_response = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await unauthenticated_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]
