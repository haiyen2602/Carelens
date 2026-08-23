"""GET /api/v1/audit-logs/me (THEM 2026-08-23) - nhat ky THAO TAC cua chinh
nguoi dang dang nhap, cho trang "Lịch sử" cua bac si.

Diem quan trong nhat can khoa lai bang test: `actor_id` lay tu JWT chu KHONG
tu query param - neu nhan tu client thi doi mot tham so tren URL la doc duoc
nhat ky cua bac si khac.

Cung khuon voi test_escalation_ack.py (TestClient that, DB that).
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, Patient, SystemAuditLog  # noqa: E402
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


def _seed_doctor(suffix: str) -> tuple[str, str]:
    """Tra ve (account_id, token) cua 1 bac si that trong DB."""
    account_id = f"test-audit-doc-{suffix}"
    db = SessionLocal()
    try:
        db.add(
            Account(
                id=account_id,
                full_name=f"BS Kiem Thu {suffix}",
                email=f"{account_id}@example.local",
                password_hash=hash_password("x"),
                role="doctor",
                doctor_id=account_id,
                status="active",
            )
        )
        db.commit()
    finally:
        db.close()
    return account_id, create_access_token(sub=account_id, role="doctor", doctor_id=account_id)


def _seed_log(actor_id: str, action: str, target: str | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(
            SystemAuditLog(
                actor_id=actor_id,
                actor_name="BS Kiem Thu",
                actor_role="doctor",
                action=action,
                target=target,
            )
        )
        db.commit()
    finally:
        db.close()


def _cleanup(*actor_ids: str) -> None:
    db = SessionLocal()
    try:
        for actor_id in actor_ids:
            db.query(SystemAuditLog).filter(SystemAuditLog.actor_id == actor_id).delete(
                synchronize_session=False
            )
            db.query(Account).filter(Account.id == actor_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_only_returns_own_actions():
    """Hai bac si, moi nguoi 1 thao tac - moi nguoi chi duoc thay cua minh."""
    a_id, a_token = _seed_doctor(uuid.uuid4().hex[:8])
    b_id, b_token = _seed_doctor(uuid.uuid4().hex[:8])
    _seed_log(a_id, "Duyệt phác đồ", "Bệnh nhân A")
    _seed_log(b_id, "Từ chối phác đồ", "Bệnh nhân B")

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_a = await client.get(
                "/api/v1/audit-logs/me", headers={"Authorization": f"Bearer {a_token}"}
            )
            r_b = await client.get(
                "/api/v1/audit-logs/me", headers={"Authorization": f"Bearer {b_token}"}
            )

        assert r_a.status_code == 200
        actions_a = [i["action"] for i in r_a.json()["items"]]
        assert actions_a == ["Duyệt phác đồ"]

        assert r_b.status_code == 200
        actions_b = [i["action"] for i in r_b.json()["items"]]
        assert actions_b == ["Từ chối phác đồ"]
    finally:
        _cleanup(a_id, b_id)


@pytest.mark.asyncio
async def test_search_filters_by_action_and_target():
    actor_id, token = _seed_doctor(uuid.uuid4().hex[:8])
    _seed_log(actor_id, "Duyệt phác đồ", "Nguyen Van A (p-1)")
    _seed_log(actor_id, "Bật theo dõi bệnh nhân", "Tran Thi B (p-2)")

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(
                "/api/v1/audit-logs/me",
                params={"q": "theo dõi"},
                headers={"Authorization": f"Bearer {token}"},
            )
            r_target = await client.get(
                "/api/v1/audit-logs/me",
                params={"q": "Nguyen Van A"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert [i["action"] for i in r.json()["items"]] == ["Bật theo dõi bệnh nhân"]
        assert [i["action"] for i in r_target.json()["items"]] == ["Duyệt phác đồ"]
    finally:
        _cleanup(actor_id)


@pytest.mark.asyncio
async def test_without_auth_header_is_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/audit-logs/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_watch_toggle_writes_a_log_entry():
    """Kiem chung DAU->CUOI: bam "Theo dõi" that su de lai dong nhat ky, va
    bam lai lan nua (da theo doi roi) KHONG ghi them dong trung."""
    actor_id, token = _seed_doctor(uuid.uuid4().hex[:8])
    patient_id = f"test-audit-bn-{uuid.uuid4().hex[:8]}"

    db = SessionLocal()
    db.add(Patient(id=patient_id, full_name="Benh Nhan Nhat Ky"))
    db.commit()
    db.close()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token}"}
            r1 = await client.patch(
                f"/api/v1/reporting/patients/{patient_id}/watch",
                json={"watch": True},
                headers=headers,
            )
            r2 = await client.patch(
                f"/api/v1/reporting/patients/{patient_id}/watch",
                json={"watch": True},
                headers=headers,
            )
            logs = await client.get("/api/v1/audit-logs/me", headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        items = logs.json()["items"]
        assert len(items) == 1, "bam lai khi da theo doi khong duoc ghi them dong nhat ky"
        assert items[0]["action"] == "Bật theo dõi bệnh nhân"
        assert "Benh Nhan Nhat Ky" in items[0]["target"]
    finally:
        db = SessionLocal()
        # DoctorWatch khong co FK - xoa tay theo doctor_id de khong bo lai rac.
        db.execute(
            text("DELETE FROM doctor_watch WHERE doctor_id = :d"), {"d": actor_id}
        )
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()
        _cleanup(actor_id)
