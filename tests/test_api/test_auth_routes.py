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


@pytest.mark.asyncio
async def test_register_creates_account_and_returns_jwt(unauthenticated_client):
    reg_email = f"test-reg-{uuid.uuid4().hex[:8]}@example.com"
    reg_payload = {
        "full_name": "Nguyễn Đăng Ký",
        "email": reg_email,
        "password": "register-test-pass-123",
        "role": "patient",
    }
    response = await unauthenticated_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["full_name"] == "Nguyễn Đăng Ký"
    assert body["user"]["role"] == "patient"

    # Clean up DB after test
    account_id = body["user"]["id"]
    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(unauthenticated_client, demo_account):
    reg_payload = {
        "full_name": "Trùng Email",
        "email": demo_account["email"],
        "password": "register-test-pass-123",
        "role": "patient",
    }
    response = await unauthenticated_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "Email đã được sử dụng"


@pytest.mark.asyncio
async def test_verify_email_flow(unauthenticated_client):
    reg_email = f"test-verify-{uuid.uuid4().hex[:8]}@example.com"
    reg_payload = {
        "full_name": "Nguyễn Xác Minh",
        "email": reg_email,
        "password": "register-test-pass-123",
        "role": "patient",
    }
    reg_res = await unauthenticated_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    account_id = reg_res.json()["user"]["id"]

    # Retrieve verification token from DB
    db = SessionLocal()
    acc = db.query(Account).filter(Account.id == account_id).first()
    assert acc is not None
    assert acc.is_email_verified is False
    token = acc.email_verification_token
    assert token is not None
    db.close()

    # Call verify-email endpoint
    verify_res = await unauthenticated_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verify_res.status_code == 200
    assert verify_res.json()["detail"] == "Xác minh email thành công"

    # Verify DB updated
    db = SessionLocal()
    acc_updated = db.query(Account).filter(Account.id == account_id).first()
    assert acc_updated.is_email_verified is True
    assert acc_updated.email_verification_token is None

    # Clean up DB
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_verify_email_invalid_token_returns_400(unauthenticated_client):
    res = await unauthenticated_client.post("/api/v1/auth/verify-email", json={"token": "invalid-token-123"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Mã xác minh không hợp lệ"


@pytest.mark.asyncio
async def test_forgot_password_and_reset_password_flow(unauthenticated_client, demo_account):
    # 1. Trigger forgot password
    forgot_res = await unauthenticated_client.post(
        "/api/v1/auth/forgot-password", json={"email": demo_account["email"]}
    )
    assert forgot_res.status_code == 200
    assert "gửi hướng dẫn" in forgot_res.json()["detail"]

    # 2. Retrieve token from DB
    db = SessionLocal()
    acc = db.query(Account).filter(Account.id == demo_account["id"]).first()
    assert acc is not None
    reset_token = acc.password_reset_token
    assert reset_token is not None
    db.close()

    # 3. Call reset-password with new password
    new_pass = "new-secure-password-456"
    reset_res = await unauthenticated_client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": new_pass}
    )
    assert reset_res.status_code == 200

    # 4. Login with old password fails
    old_login = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    assert old_login.status_code == 401

    # 5. Login with new password succeeds
    new_login = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": new_pass}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_invalid_token_returns_400(unauthenticated_client):
    res = await unauthenticated_client.post(
        "/api/v1/auth/reset-password", json={"token": "invalid-reset-token", "new_password": "new-pass-12345"}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Mã đặt lại mật khẩu không hợp lệ"


@pytest.mark.asyncio
async def test_change_password_success(unauthenticated_client, demo_account):
    # Login to get JWT access token
    login_res = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    new_pass = "changed-password-789"
    change_res = await unauthenticated_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": demo_account["password"], "new_password": new_pass},
    )
    assert change_res.status_code == 200
    assert change_res.json()["detail"] == "Đổi mật khẩu thành công"

    # Verify old password fails
    fail_res = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    assert fail_res.status_code == 401

    # Verify new password succeeds
    succ_res = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": new_pass}
    )
    assert succ_res.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current_returns_400(unauthenticated_client, demo_account):
    login_res = await unauthenticated_client.post(
        "/api/v1/auth/login", json={"email": demo_account["email"], "password": demo_account["password"]}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    change_res = await unauthenticated_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "wrong-current-pass", "new_password": "new-password-789"},
    )
    assert change_res.status_code == 400
    assert change_res.json()["detail"] == "Mật khẩu hiện tại không chính xác"


@pytest.mark.asyncio
async def test_change_password_unauthenticated_returns_401(unauthenticated_client):
    res = await unauthenticated_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "pass", "new_password": "new-pass-12345"},
    )
    assert res.status_code == 401




