import pytest
from httpx import ASGITransport, AsyncClient
from backend.db.base import SessionLocal
from backend.db.models import Account
from backend.main import app
from backend.services.auth import create_access_token, hash_password


@pytest.fixture
def auth_tokens():
    db = SessionLocal()
    # Tạo 1 super_admin, 1 admin thường, 1 doctor
    super_admin = Account(
        id="sa-01",
        full_name="Super Administrator",
        email="superadmin@test.dev",
        password_hash=hash_password("SuperSecret123"),
        role="super_admin",
        status="active",
    )
    regular_admin = Account(
        id="adm-01",
        full_name="Regular Admin",
        email="regularadmin@test.dev",
        password_hash=hash_password("RegularSecret123"),
        role="admin",
        status="active",
    )
    doctor = Account(
        id="doc-01",
        full_name="Dr. Test",
        email="doctor@test.dev",
        password_hash=hash_password("DoctorSecret123"),
        role="doctor",
        doctor_id="doc-01",
        status="active",
    )
    # Xoá nếu đã có
    db.query(Account).filter(Account.id.in_(["sa-01", "adm-01", "doc-01"])).delete(synchronize_session=False)
    db.commit()

    db.add_all([super_admin, regular_admin, doctor])
    db.commit()

    sa_token = create_access_token(sub=super_admin.id, role=super_admin.role)
    adm_token = create_access_token(sub=regular_admin.id, role=regular_admin.role)
    doc_token = create_access_token(sub=doctor.id, role=doctor.role)

    tokens = {
        "super_admin_token": sa_token,
        "admin_token": adm_token,
        "doctor_token": doc_token,
        "super_admin_id": super_admin.id,
        "admin_id": regular_admin.id,
        "doctor_id": doctor.id,
    }
    yield tokens

    db.query(Account).filter(
        Account.id.in_(["sa-01", "adm-01", "doc-01"]) | Account.email.like("%@test.dev")
    ).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_super_admin_can_create_admin_and_super_admin(auth_tokens):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Super admin tạo admin
        res1 = await client.post(
            "/api/v1/accounts",
            json={
                "email": "new_admin@test.dev",
                "password": "Password123",
                "full_name": "New Admin",
                "role": "admin",
            },
            headers={"Authorization": f"Bearer {auth_tokens['super_admin_token']}"},
        )
        assert res1.status_code == 201
        assert res1.json()["role"] == "admin"

        # Super admin tạo super_admin
        res2 = await client.post(
            "/api/v1/accounts",
            json={
                "email": "new_sa@test.dev",
                "password": "Password123",
                "full_name": "New Super Admin",
                "role": "super_admin",
            },
            headers={"Authorization": f"Bearer {auth_tokens['super_admin_token']}"},
        )
        assert res2.status_code == 201
        assert res2.json()["role"] == "super_admin"


@pytest.mark.asyncio
async def test_regular_admin_cannot_create_admin_or_super_admin(auth_tokens):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Admin thường cố tạo admin -> 403 Forbidden
        res1 = await client.post(
            "/api/v1/accounts",
            json={
                "email": "blocked_admin@test.dev",
                "password": "Password123",
                "full_name": "Blocked Admin",
                "role": "admin",
            },
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res1.status_code == 403
        assert "Chỉ super_admin" in res1.json()["detail"]

        # Admin thường cố tạo super_admin -> 403 Forbidden
        res2 = await client.post(
            "/api/v1/accounts",
            json={
                "email": "blocked_sa@test.dev",
                "password": "Password123",
                "full_name": "Blocked Super Admin",
                "role": "super_admin",
            },
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res2.status_code == 403


@pytest.mark.asyncio
async def test_regular_admin_can_create_and_manage_doctor(auth_tokens):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Admin thường tạo doctor -> 201 OK
        res = await client.post(
            "/api/v1/accounts",
            json={
                "email": "allowed_doc@test.dev",
                "password": "Password123",
                "full_name": "Allowed Doctor",
                "role": "doctor",
            },
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res.status_code == 201
        doc_id = res.json()["id"]

        # Admin thường sửa thông tin doctor -> 200 OK
        res_update = await client.patch(
            f"/api/v1/accounts/{doc_id}",
            json={"full_name": "Allowed Doctor Updated"},
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res_update.status_code == 200
        assert res_update.json()["full_name"] == "Allowed Doctor Updated"

        # Admin thường khoá doctor -> 200 OK
        res_lock = await client.patch(
            f"/api/v1/accounts/{doc_id}/status",
            json={"status": "locked"},
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res_lock.status_code == 200
        assert res_lock.json()["status"] == "locked"


@pytest.mark.asyncio
async def test_regular_admin_cannot_edit_or_lock_admin_or_super_admin(auth_tokens):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Admin thường cố sửa thông tin Super Admin -> 403 Forbidden
        res1 = await client.patch(
            f"/api/v1/accounts/{auth_tokens['super_admin_id']}",
            json={"full_name": "Hacked SA Name"},
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res1.status_code == 403
        assert "Chỉ super_admin" in res1.json()["detail"]

        # Admin thường cố khoá Super Admin -> 403 Forbidden
        res2 = await client.patch(
            f"/api/v1/accounts/{auth_tokens['super_admin_id']}/status",
            json={"status": "locked"},
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res2.status_code == 403

        # Admin thường cố sửa thông tin Admin khác -> 403 Forbidden
        res3 = await client.patch(
            f"/api/v1/accounts/{auth_tokens['admin_id']}",
            json={"full_name": "Hacked Admin Name"},
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res3.status_code == 403

        # Admin thường cố khoá Admin khác -> 403 Forbidden
        res4 = await client.patch(
            f"/api/v1/accounts/{auth_tokens['admin_id']}/status",
            json={"status": "locked"},
            headers={"Authorization": f"Bearer {auth_tokens['admin_token']}"},
        )
        assert res4.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_edit_and_lock_admin(auth_tokens):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Super Admin sửa Admin -> 200 OK
        res1 = await client.patch(
            f"/api/v1/accounts/{auth_tokens['admin_id']}",
            json={"full_name": "Super Updated Admin"},
            headers={"Authorization": f"Bearer {auth_tokens['super_admin_token']}"},
        )
        assert res1.status_code == 200
        assert res1.json()["full_name"] == "Super Updated Admin"

        # Super Admin khoá Admin -> 200 OK
        res2 = await client.patch(
            f"/api/v1/accounts/{auth_tokens['admin_id']}/status",
            json={"status": "locked"},
            headers={"Authorization": f"Bearer {auth_tokens['super_admin_token']}"},
        )
        assert res2.status_code == 200
        assert res2.json()["status"] == "locked"
