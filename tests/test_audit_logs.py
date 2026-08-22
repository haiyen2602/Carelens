"""Unit and integration tests for System Audit Logs and Admin activity logging."""

from collections.abc import AsyncIterator
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.api import audit_routes
from backend.api.security import CurrentUser, get_current_user
from backend.db.base import SessionLocal, get_db
from backend.db.models import Account, DrugProduct, SystemAuditLog
from backend.main import app
from backend.models.schemas import SystemAuditLogListResponse, SystemAuditLogOut
from backend.services.audit import list_system_audit_logs, log_system_event


async def _mock_admin() -> CurrentUser:
    return CurrentUser(
        id="admin-001",
        role="admin",
        patient_id=None,
        doctor_id=None,
    )


async def _mock_doctor() -> CurrentUser:
    return CurrentUser(
        id="doc-001",
        role="doctor",
        patient_id=None,
        doctor_id="BS001",
    )



@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def db():
    session = SessionLocal()
    admin_acc = session.get(Account, "admin-001")
    if not admin_acc:
        admin_acc = Account(
            id="admin-001",
            full_name="Nguyễn Hải Yến",
            email="admin@vinmec.com",
            password_hash="fakehash",
            role="admin",
            status="active",
        )
        session.add(admin_acc)
        session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()



@pytest.mark.asyncio
async def test_audit_logs_requires_admin(client: AsyncClient):
    app.dependency_overrides[get_current_user] = _mock_doctor
    try:
        response = await client.get("/api/v1/admin/audit-logs")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_audit_logs_endpoint_mock_service(client: AsyncClient, monkeypatch):
    app.dependency_overrides[get_current_user] = _mock_admin
    try:
        expected = {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
        }
        monkeypatch.setattr(audit_routes, "list_system_audit_logs", Mock(return_value=expected))

        response = await client.get("/api/v1/admin/audit-logs", params={"q": "thuoc", "role": "admin"})
        assert response.status_code == 200
        assert response.json()["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_log_system_event_and_list(db):
    """Test service helper functions directly with real DB session."""
    log1 = log_system_event(
        db,
        actor_id="admin-001",
        actor_name="Nguyễn Hải Yến",
        actor_role="admin",
        action="Cấp tài khoản mới Bác sĩ BS. Nguyễn Văn A (bsa@vinmec.com)",
        target="acc-test-1",
    )
    log2 = log_system_event(
        db,
        actor_id="admin-001",
        actor_name="Nguyễn Hải Yến",
        actor_role="admin",
        action="Cập nhật dữ liệu thuốc Paracetamol 500mg (v3) cho RAG",
        target="MED-001",
    )
    db.commit()

    assert log1.id is not None
    assert log2.id is not None

    res = list_system_audit_logs(db, q="Paracetamol")
    assert res["total"] >= 1
    actions = [item.action for item in res["items"]]
    assert any("Paracetamol" in act for act in actions)

    res_role = list_system_audit_logs(db, role="admin")
    assert res_role["total"] >= 2


@pytest.mark.asyncio
async def test_account_creation_writes_audit_log(client: AsyncClient, db):
    app.dependency_overrides[get_current_user] = _mock_admin
    try:
        unique_email = f"test_doctor_{SystemAuditLog.__name__.lower()}_{id(db)}@vinmec.com"
        res = await client.post(
            "/api/v1/accounts",
            json={
                "email": unique_email,
                "password": "Password123!",
                "full_name": "BS. Test Audit",
                "role": "doctor",
            },
        )
        assert res.status_code == 201
        data = res.json()

        # Verify audit log was created
        log = (
            db.query(SystemAuditLog)
            .filter(SystemAuditLog.action.contains(unique_email))
            .first()
        )
        assert log is not None
        assert log.actor_name == "Nguyễn Hải Yến"
        assert log.actor_role == "admin"
        assert "Cấp tài khoản mới Bác sĩ BS. Test Audit" in log.action
        assert log.target == unique_email

        # Clean up
        db.query(Account).filter(Account.id == data["id"]).delete()
        db.query(SystemAuditLog).filter(SystemAuditLog.id == log.id).delete()
        db.commit()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_account_status_and_update_writes_audit_log(client: AsyncClient, db):
    app.dependency_overrides[get_current_user] = _mock_admin
    try:
        # Create an account
        unique_email = f"test_user_{id(db)}@vinmec.com"
        account = Account(
            full_name="Người Dùng Test",
            email=unique_email,
            password_hash="fakehash",
            role="patient",
            patient_id=f"BN_TEST_{id(db)}",
            status="active",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        # 1. Update status -> Lock
        res_lock = await client.patch(
            f"/api/v1/accounts/{account.id}/status",
            json={"status": "locked"},
        )
        assert res_lock.status_code == 200
        lock_log = (
            db.query(SystemAuditLog)
            .filter(SystemAuditLog.action.contains(f"Khoá tài khoản {account.patient_id}"))
            .first()
        )
        assert lock_log is not None

        # 2. Update user info
        res_update = await client.patch(
            f"/api/v1/accounts/{account.id}",
            json={"full_name": "Người Dùng Test Đã Sửa"},
        )
        assert res_update.status_code == 200
        update_log = (
            db.query(SystemAuditLog)
            .filter(SystemAuditLog.action.contains("Cập nhật thông tin tài khoản Người Dùng Test Đã Sửa"))
            .first()
        )
        assert update_log is not None

        # Clean up
        db.query(SystemAuditLog).filter(
            SystemAuditLog.id.in_([lock_log.id, update_log.id])
        ).delete(synchronize_session=False)
        db.query(Account).filter(Account.id == account.id).delete()
        db.commit()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_drug_update_writes_audit_log(client: AsyncClient, db):
    app.dependency_overrides[get_current_user] = _mock_admin
    try:
        # Create or find a test drug product
        product = DrugProduct(
            id=f"test-prod-{id(db)}",
            legacy_drug_id="MED-TEST-001",
            display_name="Paracetamol 500mg Test",
            dosage_form="Viên nén",
            route="Uống",
            status="ACTIVE",
        )
        db.add(product)
        db.commit()

        res = await client.patch(
            f"/api/v1/admin/drugs/{product.id}",
            json={"display_name": "Paracetamol 500mg Test (v2)"},
        )
        assert res.status_code == 200

        drug_log = (
            db.query(SystemAuditLog)
            .filter(SystemAuditLog.action.contains("Cập nhật dữ liệu thuốc Paracetamol 500mg Test (v2) cho RAG"))
            .first()
        )
        assert drug_log is not None
        assert drug_log.target == "MED-TEST-001"
        assert drug_log.actor_name == "Nguyễn Hải Yến"

        # Clean up
        db.query(SystemAuditLog).filter(SystemAuditLog.id == drug_log.id).delete()
        db.query(DrugProduct).filter(DrugProduct.id == product.id).delete()
        db.commit()
    finally:
        app.dependency_overrides.clear()

