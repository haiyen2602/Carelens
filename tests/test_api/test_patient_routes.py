"""GET /api/v1/patients/me (backend/api/patient_routes.py::get_my_patient_profile) -
phan hoi review 2026-08-14: patient/health/page.tsx tung goi list_patients()
(chi doctor/admin) de tim ho so chinh minh, luon 403 voi role=patient nen
"tuoi/ghi chu" tren UI luon rong du DB co du lieu that (xac nhan qua DB
production, benh nhan BN-0000). Route rieng nay doc patient_id tu JWT
(current_user.patient_id), khong nhan id tu client - test day du seed
Account/Patient rieng, khong phu thuoc seed ben ngoai (self-hosted runner)."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, Patient  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_patient_account(role: str = "patient", with_patient_link: bool = True) -> tuple[str, str | None]:
    """Tra ve (account_id, patient_id) - patient_id la None neu with_patient_link=False."""
    db = SessionLocal()
    account_id = f"test-acct-{uuid.uuid4().hex[:8]}"
    patient_id: str | None = None
    try:
        if with_patient_link:
            patient_id = f"test-patient-{uuid.uuid4().hex[:8]}"
            db.add(
                Patient(
                    id=patient_id,
                    full_name="Bệnh nhân test route /me",
                    year_of_birth=1990,
                    note="Ghi chú test",
                )
            )
        db.add(
            Account(
                id=account_id,
                full_name="Test Account",
                email=f"{account_id}@example.local",
                password_hash="not-a-real-hash",
                role=role,
                status="active",
                patient_id=patient_id,
            )
        )
        db.commit()
    finally:
        db.close()
    return account_id, patient_id


def _cleanup(account_id: str, patient_id: str | None) -> None:
    db = SessionLocal()
    try:
        db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
        if patient_id:
            db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_patient_can_read_own_profile(client):
    account_id, patient_id = _seed_patient_account()
    token = create_access_token(sub=account_id, role="patient", patient_id=patient_id)

    try:
        response = await client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == patient_id
        assert body["full_name"] == "Bệnh nhân test route /me"
        assert body["year_of_birth"] == 1990
        assert body["note"] == "Ghi chú test"
    finally:
        _cleanup(account_id, patient_id)


@pytest.mark.asyncio
async def test_account_without_patient_link_gets_403(client):
    """Role co the la patient nhung tai khoan chua gan patient_id nao (hiem,
    du lieu chua dong bo) - hoac bat ky role khac (doctor/caregiver) tu goi
    nham route nay - deu phai 403, khong duoc tra ho so cua ai ca."""
    account_id, patient_id = _seed_patient_account(role="caregiver", with_patient_link=False)
    token = create_access_token(sub=account_id, role="caregiver", patient_id=None)

    try:
        response = await client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
    finally:
        _cleanup(account_id, patient_id)


@pytest.mark.asyncio
async def test_patient_cannot_see_another_patients_profile_via_this_route(client):
    """IDOR check - route khong nhan patient_id tu client (khong co tham so
    nao de gia mao), luon tra dung ho so gan voi JWT cua chinh nguoi goi."""
    account_a, patient_a = _seed_patient_account()
    account_b, patient_b = _seed_patient_account()
    token_a = create_access_token(sub=account_a, role="patient", patient_id=patient_a)

    try:
        response = await client.get("/api/v1/patients/me", headers={"Authorization": f"Bearer {token_a}"})
        assert response.status_code == 200
        assert response.json()["id"] == patient_a
        assert response.json()["id"] != patient_b
    finally:
        _cleanup(account_a, patient_a)
        _cleanup(account_b, patient_b)
