"""POST /api/v1/escalations/{id}/ack (api-contracts.md §6, vong 2 muc 13) -
test qua FastAPI TestClient that, DB that."""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, CaregiverLink, Escalation, Patient  # noqa: E402
from backend.services.auth import create_access_token, hash_password  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_open_escalation(patient_id: str) -> str:
    db = SessionLocal()
    try:
        row = Escalation(
            patient_id=patient_id,
            dose_event_id=None,
            severity="HIGH",
            trigger="safety_redflag",
            raw_utterance="test",
            reason="test escalation for ack endpoint",
            status="OPEN",
            notified=["caregiver", "doctor"],
            reminder_count=2,
            last_reminder_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ack_marks_escalation_resolved(client):
    # `client` fixture (conftest.py) dang nhap role=caregiver, Account.full_name
    # = "Test caregiver caller" - resolved_by gio doc THANG tu JWT/Account
    # (SUA 2026-08-20), khong con nhan tu request body nua.
    patient_id = f"test-ack-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    response = await client.post(f"/api/v1/escalations/{esc_id}/ack")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RESOLVED"
    assert body["resolved_by"] == "Test caregiver caller"

    db = SessionLocal()
    try:
        row = db.get(Escalation, esc_id)
        assert row.status == "RESOLVED"
        assert row.resolved_by == "Test caregiver caller"
        assert row.resolved_at is not None
    finally:
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_ack_nonexistent_escalation_returns_404(client):
    response = await client.post(f"/api/v1/escalations/{uuid.uuid4().hex}/ack")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ack_is_idempotent_when_called_twice(client):
    patient_id = f"test-ack-twice-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        r1 = await client.post(f"/api/v1/escalations/{esc_id}/ack")
        r2 = await client.post(f"/api/v1/escalations/{esc_id}/ack")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["resolved_by"] == "Test caregiver caller", "goi lai lan 2 khong loi, van cap nhat lai resolved_at/resolved_by"
    finally:
        db = SessionLocal()
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_ack_without_auth_header_is_rejected(client):
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    patient_id = f"test-ack-noauth-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as unauthenticated_client:
            response = await unauthenticated_client.post(f"/api/v1/escalations/{esc_id}/ack")
        assert response.status_code == 401
    finally:
        db = SessionLocal()
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_patient_acting_as_caregiver_can_ack_with_accepted_link(client):
    """SUA 2026-08-20 - truoc day require_role("doctor","caregiver","admin")
    chan nham truong hop pho bien nhat: 1 tai khoan role=patient dang xem NHU
    nguoi than cua benh nhan khac (patient/family/[id]/page.tsx). Gio phai
    cho phep neu co CaregiverLink accepted, tu choi (403) neu chua co link."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    other_patient_id = f"test-ack-other-{uuid.uuid4().hex[:8]}"
    caregiver_account_id = f"test-ack-cgacct-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(other_patient_id)

    db = SessionLocal()
    db.add(Patient(id=other_patient_id, full_name="Benh nhan duoc theo doi"))
    db.add(
        Account(
            id=caregiver_account_id,
            full_name="Nguoi than (tai khoan patient)",
            email=f"{caregiver_account_id}@example.local",
            password_hash=hash_password("x"),
            role="patient",
            patient_id=f"self-{caregiver_account_id}",
            status="active",
        )
    )
    db.commit()
    db.close()

    token = create_access_token(sub=caregiver_account_id, role="patient", patient_id=f"self-{caregiver_account_id}")

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as unlinked_client:
            no_link_resp = await unlinked_client.post(
                f"/api/v1/escalations/{esc_id}/ack", headers={"Authorization": f"Bearer {token}"}
            )
        assert no_link_resp.status_code == 403

        db = SessionLocal()
        db.add(
            CaregiverLink(
                caregiver_account_id=caregiver_account_id,
                patient_id=other_patient_id,
                relationship="Con gái",
                status="accepted",
            )
        )
        db.commit()
        db.close()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as linked_client:
            linked_resp = await linked_client.post(
                f"/api/v1/escalations/{esc_id}/ack", headers={"Authorization": f"Bearer {token}"}
            )
        assert linked_resp.status_code == 200
        assert linked_resp.json()["resolved_by"] == "Nguoi than (tai khoan patient)"
    finally:
        db = SessionLocal()
        db.query(Escalation).filter(Escalation.patient_id == other_patient_id).delete(synchronize_session=False)
        db.query(CaregiverLink).filter(CaregiverLink.patient_id == other_patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == other_patient_id).delete(synchronize_session=False)
        db.query(Account).filter(Account.id == caregiver_account_id).delete(synchronize_session=False)
        db.commit()
        db.close()
