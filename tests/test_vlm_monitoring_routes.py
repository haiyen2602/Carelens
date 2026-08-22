"""GET /api/v1/admin/vlm/health - dac biet cho caregiver_override_rate (THEM
2026-08-22): ground truth lay tu quyet dinh THAT cua nguoi than sau khi xem
anh CAREGIVER_REVIEW (backend/api/dose_routes.py::update_dose_status), khong
phai model thu 2 hay golden dataset tinh."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, DoseEvent, Escalation, Patient, PhotoVerification  # noqa: E402
from backend.services.auth import hash_password  # noqa: E402
from backend.services.escalation import TRIGGER_PHOTO_MISMATCH  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Cần Postgres thật (docker compose up -d db)")


@pytest_asyncio.fixture
async def admin_token(client):
    """/admin/vlm/* doi role=admin that (require_role("admin")) - fixture
    `client` mac dinh dung JWT role=caregiver (xem tests/conftest.py), khong
    du quyen goi endpoint nay."""
    email = f"test-admin-vlm-{uuid.uuid4().hex[:8]}@example.com"
    password = "a-real-test-password-123"
    db = SessionLocal()
    account = Account(full_name="Admin test VLM", email=email, password_hash=hash_password(password), role="admin")
    db.add(account)
    db.commit()
    account_id = account.id
    db.close()

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    yield token

    db = SessionLocal()
    db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest_asyncio.fixture
async def seeded_patient(client):
    patient_id = f"test-vlm-mon-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    db.add(Patient(id=patient_id, full_name="Bệnh nhân test VLM monitoring"))
    db.commit()
    yield patient_id
    db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
    db.query(PhotoVerification).filter(PhotoVerification.patient_id == patient_id).delete(synchronize_session=False)
    db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


def _dose(patient_id: str, status: str) -> DoseEvent:
    gio = datetime.now(UTC)
    return DoseEvent(
        prescription_id="presc-gia",
        patient_id=patient_id,
        scheduled_at=gio,
        window_start=gio - timedelta(minutes=30),
        window_end=gio + timedelta(minutes=30),
        status=status,
        expected_items=[{"drug_id": "d1", "ten_thuoc": "Test", "dang_thuoc": "Viên nén", "so_vien": 2}],
    )


def _photo_row(dose: DoseEvent) -> PhotoVerification:
    return PhotoVerification(
        dose_event_id=dose.id,
        patient_id=dose.patient_id,
        attempt=3,
        expected_by_form={"vien_nen": 2},
        detected_by_form={"vien_nen": 1},
        ket_qua="lech",
        confidence="cao",
        thong_bao="test",
        image_path="/tmp/x.jpg",
    )


@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    """`client` fixture mac dinh dung JWT role=caregiver (tests/conftest.py)
    - phai bi 403, khong duoc doc du lieu xac minh anh cua benh nhan khac."""
    response = await client.get("/api/v1/admin/vlm/health")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_caregiver_override_rate_mixed_outcomes(client, admin_token, seeded_patient):
    # So sanh theo DELTA (truoc/sau khi them 2 dong test), khong hardcode %
    # tuyet doi - endpoint nay tinh TREN TOAN BO DB (khong loc theo 1 benh
    # nhan), moi truong dev co the da co du lieu photo_mismatch tu truoc.
    auth = {"Authorization": f"Bearer {admin_token}"}
    baseline = (await client.get("/api/v1/admin/vlm/health", headers=auth)).json()["kpis"]

    db = SessionLocal()
    try:
        # Ca 1: nguoi than BAC BO model (dat lai TAKEN) -> overridden.
        dose_overridden = _dose(seeded_patient, "TAKEN")
        db.add(dose_overridden)
        db.commit()
        db.refresh(dose_overridden)
        db.add(_photo_row(dose_overridden))
        db.add(Escalation(
            patient_id=seeded_patient, dose_event_id=dose_overridden.id, severity="MEDIUM",
            trigger=TRIGGER_PHOTO_MISMATCH, reason="test overridden",
        ))

        # Ca 2: nguoi than XAC NHAN model dung (dat lai MISSED) -> confirmed.
        dose_confirmed = _dose(seeded_patient, "MISSED")
        db.add(dose_confirmed)
        db.commit()
        db.refresh(dose_confirmed)
        db.add(_photo_row(dose_confirmed))
        db.add(Escalation(
            patient_id=seeded_patient, dose_event_id=dose_confirmed.id, severity="MEDIUM",
            trigger=TRIGGER_PHOTO_MISMATCH, reason="test confirmed",
        ))

        # Ca 3: CHUA ai xem (van AWAITING_CAREGIVER) -> khong tinh vao ty le.
        dose_pending = _dose(seeded_patient, "AWAITING_CAREGIVER")
        db.add(dose_pending)
        db.commit()
        db.refresh(dose_pending)
        db.add(_photo_row(dose_pending))
        db.add(Escalation(
            patient_id=seeded_patient, dose_event_id=dose_pending.id, severity="MEDIUM",
            trigger=TRIGGER_PHOTO_MISMATCH, reason="test pending",
        ))
        db.commit()

        response = await client.get("/api/v1/admin/vlm/health", headers=auth)
        assert response.status_code == 200
        kpis = response.json()["kpis"]
        # +1 overridden, +2 resolved (case pending KHONG tinh vao resolved) -
        # so voi baseline, bat ke DB dev da co du lieu tu truoc hay chua.
        assert kpis["caregiver_override_count"] == baseline["caregiver_override_count"] + 1
        assert kpis["caregiver_override_resolved_count"] == baseline["caregiver_override_resolved_count"] + 2
        assert kpis["caregiver_review_count"] >= baseline["caregiver_review_count"] + 3
    finally:
        db.close()


@pytest.mark.asyncio
async def test_caregiver_override_rate_unchanged_when_still_pending(client, admin_token, seeded_patient):
    """1 ca CAREGIVER_REVIEW chua ai xem (van AWAITING_CAREGIVER) khong duoc
    tinh vao resolved/override count - so delta voi baseline, cung ly do
    khong hardcode gia tri tuyet doi voi test tren."""
    auth = {"Authorization": f"Bearer {admin_token}"}
    baseline = (await client.get("/api/v1/admin/vlm/health", headers=auth)).json()["kpis"]

    db = SessionLocal()
    try:
        dose_pending = _dose(seeded_patient, "AWAITING_CAREGIVER")
        db.add(dose_pending)
        db.commit()
        db.refresh(dose_pending)
        db.add(_photo_row(dose_pending))
        db.add(Escalation(
            patient_id=seeded_patient, dose_event_id=dose_pending.id, severity="MEDIUM",
            trigger=TRIGGER_PHOTO_MISMATCH, reason="test pending only",
        ))
        db.commit()

        response = await client.get("/api/v1/admin/vlm/health", headers=auth)
        assert response.status_code == 200
        kpis = response.json()["kpis"]
        assert kpis["caregiver_override_count"] == baseline["caregiver_override_count"]
        assert kpis["caregiver_override_resolved_count"] == baseline["caregiver_override_resolved_count"]
        assert kpis["caregiver_review_count"] >= baseline["caregiver_review_count"] + 1
    finally:
        db.close()
