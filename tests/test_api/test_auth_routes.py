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

from backend.api.security import INTERNAL_SECRET_HEADER  # noqa: E402
from backend.config import get_settings  # noqa: E402
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

    # SUA 2026-08-14 (thiet ke ID benh nhan, yeu cau PM kem anh chup man
    # hinh that): account_id (UUID, tra ve trong body["user"]["id"]) KHONG
    # con duoc dung lam patient_id nua - patient_id phai dang BNxxxxx (khop
    # du lieu cu vd "BN00002"), khong phai UUID. UserOut khong tra
    # patient_id truc tiep (xem docstring UserOut) - doc lai tu Account.
    account_id = body["user"]["id"]
    db = SessionLocal()
    account = db.query(Account).filter(Account.id == account_id).first()
    assert account is not None
    assert account.patient_id is not None
    assert account.patient_id != account_id  # KHONG con dung chung UUID
    assert _PATIENT_ID_RE.match(account.patient_id), (
        f"patient_id {account.patient_id!r} khong dung dang BNxxxxx"
    )
    patient_id = account.patient_id

    # Dong bo hoa (yeu cau PM): duong tu dang ky PHAI tao dong Patient that
    # dang sau patient_id, khong chi gan chuoi ID vao Account.
    patient = db.get(Patient, patient_id)
    assert patient is not None
    assert patient.full_name == "Nguyễn Đăng Ký"

    # Clean up DB after test - xoa CA Account, Patient LAN DoctorWatch (moi
    # register() tu dong tao 1 dong DoctorWatch/bac si dang co, xem
    # test_register_auto_watches_new_patient_for_existing_doctors ben duoi -
    # sot lai khong anh huong dung/sai cua test nay nhung van don dep).
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
    db.query(DoctorWatch).filter(DoctorWatch.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_register_auto_watches_new_patient_for_existing_doctors(unauthenticated_client):
    """Yeu cau PM 2026-08-14: benh nhan MOI mac dinh duoc TAT CA bac si dang
    co theo doi ngay - sua bug "Cảnh báo mới nhất" luon rong vi benh nhan moi
    khong ai theo doi. Seed 1 bac si that truoc, dang ky 1 benh nhan moi, xac
    nhan co dung 1 dong DoctorWatch noi bac si do toi benh nhan moi."""
    db = SessionLocal()
    doctor_account_id = f"test-doctor-{uuid.uuid4().hex[:8]}"
    db.add(
        Account(
            id=doctor_account_id,
            full_name="BS Test AutoWatch",
            email=f"{doctor_account_id}@example.local",
            password_hash="not-a-real-hash",
            role="doctor",
            status="active",
            doctor_id=doctor_account_id,
        )
    )
    db.commit()
    db.close()

    reg_email = f"test-reg-{uuid.uuid4().hex[:8]}@example.com"
    reg_payload = {
        "full_name": "Bệnh Nhân AutoWatch",
        "email": reg_email,
        "password": "register-test-pass-123",
        "role": "patient",
    }
    response = await unauthenticated_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 201
    account_id = response.json()["user"]["id"]

    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        patient_id = account.patient_id

        watch = (
            db.query(DoctorWatch)
            .filter(DoctorWatch.doctor_id == doctor_account_id, DoctorWatch.patient_id == patient_id)
            .first()
        )
        assert watch is not None, "Bác sĩ đang có sẵn phải tự động theo dõi bệnh nhân mới đăng ký"
    finally:
        db.query(Account).filter(Account.id.in_([account_id, doctor_account_id])).delete(
            synchronize_session=False
        )
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.query(DoctorWatch).filter(DoctorWatch.patient_id == patient_id).delete(synchronize_session=False)
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
async def test_register_rejects_doctor_role(unauthenticated_client):
    """Yeu cau PM 2026-08-17: khong cho tu dang ky tai khoan bac si - chi admin
    tao duoc qua account-api. Pydantic Literal["patient"] tra 422."""
    reg_payload = {
        "full_name": "BS Tu Dang Ky",
        "email": f"test-reg-doctor-{uuid.uuid4().hex[:8]}@example.com",
        "password": "register-test-pass-123",
        "role": "doctor",
    }
    response = await unauthenticated_client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 422

    db = SessionLocal()
    try:
        assert db.query(Account).filter(Account.email == reg_payload["email"]).first() is None
    finally:
        db.close()


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
    patient_id = acc_updated.patient_id

    # Clean up DB - xoa CA Account LAN Patient (register() vong 2026-08-14 tao
    # them dong Patient that voi ID BNxxxxx rieng, khong con dung chung UUID
    # cua account - de sot lai se anh huong so dem cua generate_next_patient_id()).
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    if patient_id:
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.query(DoctorWatch).filter(DoctorWatch.patient_id == patient_id).delete(synchronize_session=False)
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

    # Verify me works with original token
    me_before = await unauthenticated_client.get("/api/v1/auth/me", headers=headers)
    assert me_before.status_code == 200

    import asyncio
    await asyncio.sleep(1.1)

    new_pass = "changed-password-789"
    change_res = await unauthenticated_client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": demo_account["password"], "new_password": new_pass},
    )
    assert change_res.status_code == 200
    body = change_res.json()
    assert body["detail"] == "Đổi mật khẩu thành công"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"

    new_token = body["access_token"]

    # Verify old token is now revoked (should return 401)
    me_old_token = await unauthenticated_client.get("/api/v1/auth/me", headers=headers)
    assert me_old_token.status_code == 401

    # Verify new token works (should return 200)
    me_new_token = await unauthenticated_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert me_new_token.status_code == 200

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


# ---------------------------------------------------------------------------
# "Login with Google" - POST /api/v1/auth/oauth/google (api-contracts.md §1).
# Endpoint nay KHONG public: no khong co mat khau nao de kiem tra, toan bo niem
# tin nam o cho "nguoi goi (Route Handler cua Next.js) da xac thuc Google giup
# roi" -> chan bang X-Internal-Secret. Cac test duoi day khoa dung nhung tinh
# chat an toan do lai.
# ---------------------------------------------------------------------------


def _internal_headers() -> dict[str, str]:
    return {INTERNAL_SECRET_HEADER: get_settings().internal_auth_secret}


def _delete_account_cascade(email: str) -> None:
    db = SessionLocal()
    account = db.query(Account).filter(Account.email == email).first()
    if account is not None:
        patient_id = account.patient_id
        db.query(Account).filter(Account.id == account.id).delete(synchronize_session=False)
        if patient_id:
            db.query(DoctorWatch).filter(DoctorWatch.patient_id == patient_id).delete(
                synchronize_session=False
            )
            db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_oauth_google_without_internal_secret_returns_401(unauthenticated_client):
    """Rao can require_internal_secret phai duoc wire that su. Neu quen, bat ky
    ai cung POST duoc mot email tuy y vao day va nhan lai JWT cua chu email do."""
    res = await unauthenticated_client.post(
        "/api/v1/auth/oauth/google",
        json={
            "email": f"test-oauth-nosecret-{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Kẻ Gọi Lạ",
            "provider_account_id": "google-sub-attacker",
        },
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_oauth_google_first_login_creates_patient_account(unauthenticated_client):
    email = f"test-oauth-new-{uuid.uuid4().hex[:8]}@example.com"
    try:
        res = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={
                "email": email,
                "full_name": "Nguyễn Văn Google",
                "provider_account_id": "google-sub-1234567890",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["user"]["role"] == "patient"
        assert body["user"]["full_name"] == "Nguyễn Văn Google"

        db = SessionLocal()
        account = db.query(Account).filter(Account.email == email).first()
        assert account is not None
        assert account.auth_provider == "google"
        assert account.is_email_verified is True
        # Giong het duong /auth/register: patient_id dang BNxxxxx + dong Patient
        # that dang sau no (khong chi gan chuoi ID vao Account).
        assert account.patient_id is not None
        assert _PATIENT_ID_RE.match(account.patient_id)
        assert db.get(Patient, account.patient_id) is not None
        db.close()
    finally:
        _delete_account_cascade(email)


@pytest.mark.asyncio
async def test_oauth_google_cannot_login_with_password(unauthenticated_client):
    """Tai khoan tao qua Google co password_hash la bcrypt cua 1 chuoi ngau
    nhien khong luu o dau -> POST /auth/login phai luon 401, va KHONG duoc 500
    (verify_password voi hash rong se nem loi)."""
    email = f"test-oauth-nopass-{uuid.uuid4().hex[:8]}@example.com"
    try:
        create = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={"email": email, "full_name": "Không Mật Khẩu", "provider_account_id": "g-sub-2"},
        )
        assert create.status_code == 200

        for guess in ("", "password", "123456789"):
            res = await unauthenticated_client.post(
                "/api/v1/auth/login", json={"email": email, "password": guess}
            )
            assert res.status_code in (401, 422), f"mat khau {guess!r} -> {res.status_code}"
    finally:
        _delete_account_cascade(email)


@pytest.mark.asyncio
async def test_oauth_google_unverified_email_returns_400(unauthenticated_client):
    """Fail-closed: Google noi email chua xac thuc -> khong duoc dung no de nhan
    danh chu tai khoan cung email (duong chiem tai khoan)."""
    email = f"test-oauth-unverified-{uuid.uuid4().hex[:8]}@example.com"
    try:
        res = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={
                "email": email,
                "full_name": "Chưa Xác Thực",
                "provider_account_id": "g-sub-3",
                "email_verified": False,
            },
        )
        assert res.status_code == 400
        db = SessionLocal()
        assert db.query(Account).filter(Account.email == email).first() is None
        db.close()
    finally:
        _delete_account_cascade(email)


@pytest.mark.asyncio
async def test_oauth_google_existing_password_account_keeps_role_and_provider(
    unauthenticated_client, demo_account
):
    """Tai khoan da co (dang nhap bang mat khau) lien ket Google: dang nhap
    duoc, nhung KHONG bi ha thanh "khong co mat khau" - `auth_provider` giu
    nguyen "password" de /auth/change-password van hoat dong."""
    res = await unauthenticated_client.post(
        "/api/v1/auth/oauth/google",
        headers=_internal_headers(),
        json={
            "email": demo_account["email"],
            "full_name": "Tên Từ Google",
            "provider_account_id": "g-sub-4",
        },
    )
    assert res.status_code == 200
    assert res.json()["access_token"]

    db = SessionLocal()
    account = db.query(Account).filter(Account.id == demo_account["id"]).first()
    assert account is not None
    assert account.auth_provider == "password"
    assert account.role == "patient"
    db.close()

    # Mat khau cu VAN dung sau khi lien ket Google.
    login_res = await unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": demo_account["email"], "password": demo_account["password"]},
    )
    assert login_res.status_code == 200


@pytest.mark.asyncio
async def test_oauth_google_locked_account_returns_403(unauthenticated_client, demo_account):
    """Nut "khoa tai khoan" cua admin (account.status) khong duoc di duong
    OAuth de lach qua."""
    db = SessionLocal()
    account = db.query(Account).filter(Account.id == demo_account["id"]).first()
    account.status = "locked"
    db.commit()
    db.close()

    res = await unauthenticated_client.post(
        "/api/v1/auth/oauth/google",
        headers=_internal_headers(),
        json={
            "email": demo_account["email"],
            "full_name": "Bị Khoá",
            "provider_account_id": "g-sub-5",
        },
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_change_password_on_google_account_returns_400(unauthenticated_client):
    """Tai khoan Google chua he co mat khau nguoi dung -> /auth/change-password
    phai bao ro dieu do thay vi "mat khau hien tai khong chinh xac"."""
    email = f"test-oauth-chpass-{uuid.uuid4().hex[:8]}@example.com"
    try:
        create = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={"email": email, "full_name": "Google User", "provider_account_id": "g-sub-6"},
        )
        assert create.status_code == 200
        token = create.json()["access_token"]

        res = await unauthenticated_client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "bat-ky-gi", "new_password": "new-password-789"},
        )
        assert res.status_code == 400
        assert "Google" in res.json()["detail"]
    finally:
        _delete_account_cascade(email)


@pytest.mark.asyncio
async def test_me_exposes_auth_provider(unauthenticated_client, demo_account):
    """Frontend can `auth_provider` de biet hien "Đặt mật khẩu" hay "Đổi mật
    khẩu" TRUOC khi mo dialog (components/account-settings.tsx)."""
    login_res = await unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": demo_account["email"], "password": demo_account["password"]},
    )
    token = login_res.json()["access_token"]
    me_res = await unauthenticated_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_res.status_code == 200
    assert me_res.json()["auth_provider"] == "password"


@pytest.mark.asyncio
async def test_set_password_lets_google_account_login_both_ways(unauthenticated_client):
    """Quyet dinh PM 2026-08-17: tai khoan Google DAT duoc mat khau lan dau,
    sau do dang nhap duoc CA HAI duong. Day la duong thoat duy nhat neu nguoi
    dung mat quyen truy cap Gmail (backend chua co /auth/forgot-password)."""
    email = f"test-oauth-setpass-{uuid.uuid4().hex[:8]}@example.com"
    new_password = "mat-khau-moi-dat-lan-dau-123"
    try:
        create = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={"email": email, "full_name": "Google User", "provider_account_id": "g-sub-7"},
        )
        assert create.status_code == 200
        token = create.json()["access_token"]

        set_res = await unauthenticated_client.post(
            "/api/v1/auth/set-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"new_password": new_password},
        )
        assert set_res.status_code == 200
        body = set_res.json()
        assert body["detail"] == "Đặt mật khẩu thành công"
        # Ke thua LoginResponse: tra token MOI vi dat mat khau thu hoi token cu
        # - neu chi tra `detail`, nguoi vua dat mat khau bi dang xuat ngay.
        assert body["access_token"]
        assert body["refresh_token"]

        # Duong 1: email + mat khau vua dat.
        pw_login = await unauthenticated_client.post(
            "/api/v1/auth/login", json={"email": email, "password": new_password}
        )
        assert pw_login.status_code == 200

        # Duong 2: Google van dang nhap duoc, va KHONG bi ha lai thanh "chua co
        # mat khau" (oauth_google giu nguyen auth_provider cua tai khoan da co).
        g_login = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={"email": email, "full_name": "Google User", "provider_account_id": "g-sub-7"},
        )
        assert g_login.status_code == 200

        db = SessionLocal()
        account = db.query(Account).filter(Account.email == email).first()
        assert account.auth_provider == "password"
        db.close()
    finally:
        _delete_account_cascade(email)


@pytest.mark.asyncio
async def test_set_password_is_single_use(unauthenticated_client):
    """Cong `auth_provider == "google"` chi mo duoc MOT lan. Neu khong, 1
    access_token bi lo se doi duoc mat khau ma khong can biet mat khau cu."""
    email = f"test-oauth-setpass2-{uuid.uuid4().hex[:8]}@example.com"
    try:
        create = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={"email": email, "full_name": "Google User", "provider_account_id": "g-sub-8"},
        )
        token = create.json()["access_token"]

        first = await unauthenticated_client.post(
            "/api/v1/auth/set-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"new_password": "mat-khau-lan-dau-123"},
        )
        assert first.status_code == 200
        # Dung token MOI (token cu da bi thu hoi boi password_changed_at) de
        # chac chan 400 den tu dieu kien auth_provider, khong phai tu 401.
        new_token = first.json()["access_token"]

        second = await unauthenticated_client.post(
            "/api/v1/auth/set-password",
            headers={"Authorization": f"Bearer {new_token}"},
            json={"new_password": "mat-khau-lan-hai-456"},
        )
        assert second.status_code == 400
        assert "đã có mật khẩu" in second.json()["detail"]
    finally:
        _delete_account_cascade(email)


@pytest.mark.asyncio
async def test_set_password_rejects_password_account(unauthenticated_client, demo_account):
    """Tai khoan thuong KHONG duoc di duong nay - phai qua
    /auth/change-password (co xac minh mat khau cu)."""
    login_res = await unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": demo_account["email"], "password": demo_account["password"]},
    )
    token = login_res.json()["access_token"]

    res = await unauthenticated_client.post(
        "/api/v1/auth/set-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_password": "mat-khau-cuop-tai-khoan-123"},
    )
    assert res.status_code == 400

    # Mat khau cu VAN nguyen - endpoint khong duoc doi gi truoc khi tu choi.
    still = await unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": demo_account["email"], "password": demo_account["password"]},
    )
    assert still.status_code == 200


@pytest.mark.asyncio
async def test_set_password_unauthenticated_returns_401(unauthenticated_client):
    res = await unauthenticated_client.post(
        "/api/v1/auth/set-password", json={"new_password": "khong-co-token-123"}
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_change_password_works_after_set_password(unauthenticated_client):
    """Sau khi dat mat khau, tai khoan Google dung /auth/change-password binh
    thuong (guard "đăng nhập bằng Google" khong con chan nua)."""
    email = f"test-oauth-then-ch-{uuid.uuid4().hex[:8]}@example.com"
    first_pw = "mat-khau-dat-lan-dau-123"
    second_pw = "mat-khau-doi-tiep-456"
    try:
        create = await unauthenticated_client.post(
            "/api/v1/auth/oauth/google",
            headers=_internal_headers(),
            json={"email": email, "full_name": "Google User", "provider_account_id": "g-sub-9"},
        )
        set_res = await unauthenticated_client.post(
            "/api/v1/auth/set-password",
            headers={"Authorization": f"Bearer {create.json()['access_token']}"},
            json={"new_password": first_pw},
        )
        token = set_res.json()["access_token"]

        ch_res = await unauthenticated_client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": first_pw, "new_password": second_pw},
        )
        assert ch_res.status_code == 200

        login = await unauthenticated_client.post(
            "/api/v1/auth/login", json={"email": email, "password": second_pw}
        )
        assert login.status_code == 200
    finally:
        _delete_account_cascade(email)






