"""GET /api/v1/reporting/dose-summary (THEM 2026-08-23) - so lieu that cho 2
bieu do o trang "Tổng quan thông tin" cua bac si.

Trong tam cua file nay la MUI GIO. DoseEvent.scheduled_at luu UTC, con bieu do
noi ve ngay va khung gio theo gio Viet Nam (UTC+7) - day la cho de sai nhat va
sai am tham nhat: mot lieu 06:00 sang gio VN nam o 23:00 UTC NGAY HOM TRUOC,
gom nhom theo UTC se day no sang cot cua hom truoc va lam bieu do "khung gio
hay bo lo" lech han 7 tieng.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Account, DoctorWatch, DoseEvent, Patient  # noqa: E402
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

_GIO_VN = timedelta(hours=7)


def _seed_doctor() -> tuple[str, str]:
    account_id = f"test-ds-doc-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(
            Account(
                id=account_id,
                full_name="BS Dose Summary",
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


def _seed_patient(doctor_id: str | None = None) -> str:
    patient_id = f"test-ds-bn-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name="BN Dose Summary"))
        if doctor_id:
            db.add(DoctorWatch(doctor_id=doctor_id, patient_id=patient_id))
        db.commit()
    finally:
        db.close()
    return patient_id


def _seed_dose(patient_id: str, scheduled_at: datetime, status: str) -> None:
    db = SessionLocal()
    try:
        db.add(
            DoseEvent(
                prescription_id=f"test-ds-presc-{uuid.uuid4().hex[:8]}",
                patient_id=patient_id,
                scheduled_at=scheduled_at,
                window_start=scheduled_at - timedelta(minutes=30),
                window_end=scheduled_at + timedelta(minutes=30),
                status=status,
                expected_items=[],
            )
        )
        db.commit()
    finally:
        db.close()


def _cleanup(*, doctor_ids: tuple[str, ...] = (), patient_ids: tuple[str, ...] = ()) -> None:
    db = SessionLocal()
    try:
        for pid in patient_ids:
            db.query(DoseEvent).filter(DoseEvent.patient_id == pid).delete(synchronize_session=False)
            db.query(Patient).filter(Patient.id == pid).delete(synchronize_session=False)
        for did in doctor_ids:
            db.query(DoctorWatch).filter(DoctorWatch.doctor_id == did).delete(
                synchronize_session=False
            )
            db.query(Account).filter(Account.id == did).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


async def _get(token: str, days: int = 7) -> dict:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/reporting/dose-summary",
            params={"days": days},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_counts_taken_delayed_missed_for_today():
    doctor_id, token = _seed_doctor()
    patient_id = _seed_patient(doctor_id)

    # Giua trua gio VN hom nay - xa ranh gioi ngay o ca hai mui gio nen khong
    # bi test lat khi chay gan nua dem.
    trua_vn = (datetime.now(UTC) + _GIO_VN).replace(hour=12, minute=0, second=0, microsecond=0)
    hom_nay = trua_vn.strftime("%Y-%m-%d")
    trua_utc = trua_vn - _GIO_VN

    _seed_dose(patient_id, trua_utc, "TAKEN")
    _seed_dose(patient_id, trua_utc, "TAKEN")
    _seed_dose(patient_id, trua_utc, "DELAYED")
    _seed_dose(patient_id, trua_utc, "MISSED")
    # PENDING khong duoc dem - chua co ket qua thi khong noi len dieu gi.
    _seed_dose(patient_id, trua_utc, "PENDING")

    try:
        data = await _get(token)
        assert len(data["daily"]) == 7, "luon du 7 dong ke ca ngay khong co lieu"
        ngay = next(d for d in data["daily"] if d["date"] == hom_nay)
        assert (ngay["taken"], ngay["delayed"], ngay["missed"]) == (2, 1, 1)
        assert ngay["total"] == 4, "PENDING khong duoc tinh vao mau"
    finally:
        _cleanup(doctor_ids=(doctor_id,), patient_ids=(patient_id,))


@pytest.mark.asyncio
async def test_early_morning_dose_lands_on_vietnam_day_not_utc_day():
    """Lieu 06:00 sang gio VN = 23:00 UTC NGAY HOM TRUOC. Neu gom theo ngay
    UTC thi no roi sang cot hom truoc - day la bug mui gio dien hinh."""
    doctor_id, token = _seed_doctor()
    patient_id = _seed_patient(doctor_id)

    sang_vn = (datetime.now(UTC) + _GIO_VN).replace(hour=6, minute=0, second=0, microsecond=0)
    ngay_vn = sang_vn.strftime("%Y-%m-%d")
    sang_utc = sang_vn - _GIO_VN
    assert sang_utc.strftime("%Y-%m-%d") != ngay_vn, "moc test phai that su vat qua nua dem UTC"

    _seed_dose(patient_id, sang_utc, "TAKEN")

    try:
        data = await _get(token)
        ngay = next(d for d in data["daily"] if d["date"] == ngay_vn)
        assert ngay["taken"] == 1, "lieu buoi sang phai nam o ngay Viet Nam, khong phai ngay UTC"
    finally:
        _cleanup(doctor_ids=(doctor_id,), patient_ids=(patient_id,))


@pytest.mark.asyncio
async def test_missed_doses_are_bucketed_by_vietnam_hour():
    doctor_id, token = _seed_doctor()
    patient_id = _seed_patient(doctor_id)

    hom_nay_vn = (datetime.now(UTC) + _GIO_VN).replace(minute=0, second=0, microsecond=0)

    def luc(gio_vn: int) -> datetime:
        return hom_nay_vn.replace(hour=gio_vn) - _GIO_VN

    _seed_dose(patient_id, luc(7), "MISSED")  # Sáng
    _seed_dose(patient_id, luc(12), "MISSED")  # Trưa
    _seed_dose(patient_id, luc(15), "MISSED")  # Chiều
    _seed_dose(patient_id, luc(20), "MISSED")  # Tối
    _seed_dose(patient_id, luc(21), "MISSED")  # Tối
    _seed_dose(patient_id, luc(20), "TAKEN")  # khong phai MISSED -> khong dem

    try:
        data = await _get(token)
        theo_khung = {w["key"]: w["missed"] for w in data["missed_by_window"]}
        assert theo_khung == {"morning": 1, "noon": 1, "afternoon": 1, "evening": 2}
        assert [w["label"] for w in data["missed_by_window"]] == ["Sáng", "Trưa", "Chiều", "Tối"]
    finally:
        _cleanup(doctor_ids=(doctor_id,), patient_ids=(patient_id,))


@pytest.mark.asyncio
async def test_only_counts_watched_patients():
    """Bac si chi thay so lieu cua benh nhan minh dang "Theo doi" - cung pham
    vi voi Hop canh bao, de hai man hinh noi ve cung mot tap benh nhan."""
    doctor_id, token = _seed_doctor()
    duoc_theo_doi = _seed_patient(doctor_id)
    khong_theo_doi = _seed_patient()  # khong tao DoctorWatch

    trua_utc = (datetime.now(UTC) + _GIO_VN).replace(
        hour=12, minute=0, second=0, microsecond=0
    ) - _GIO_VN
    _seed_dose(duoc_theo_doi, trua_utc, "TAKEN")
    _seed_dose(khong_theo_doi, trua_utc, "MISSED")
    _seed_dose(khong_theo_doi, trua_utc, "MISSED")

    try:
        data = await _get(token)
        assert data["patient_count"] == 1
        assert sum(d["taken"] for d in data["daily"]) == 1
        assert sum(d["missed"] for d in data["daily"]) == 0, (
            "lieu cua benh nhan KHONG theo doi khong duoc lot vao thong ke"
        )
        assert sum(w["missed"] for w in data["missed_by_window"]) == 0
    finally:
        _cleanup(doctor_ids=(doctor_id,), patient_ids=(duoc_theo_doi, khong_theo_doi))


@pytest.mark.asyncio
async def test_doctor_watching_nobody_gets_empty_but_valid_shape():
    """Chua theo doi ai van phai tra ve du 7 dong (so 0), khong phai loi hay
    mang rong - giao dien ve bieu do truoc khi biet co du lieu hay khong."""
    doctor_id, token = _seed_doctor()
    try:
        data = await _get(token)
        assert data["patient_count"] == 0
        assert len(data["daily"]) == 7
        assert all(d["total"] == 0 for d in data["daily"])
        assert sum(w["missed"] for w in data["missed_by_window"]) == 0
    finally:
        _cleanup(doctor_ids=(doctor_id,))


@pytest.mark.asyncio
async def test_days_param_is_bounded_and_without_auth_is_rejected():
    doctor_id, token = _seed_doctor()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            qua_lon = await client.get(
                "/api/v1/reporting/dose-summary",
                params={"days": 500},
                headers={"Authorization": f"Bearer {token}"},
            )
            khong_token = await client.get("/api/v1/reporting/dose-summary")
        assert qua_lon.status_code == 422
        assert khong_token.status_code == 401

        data = await _get(token, days=30)
        assert data["days"] == 30
        assert len(data["daily"]) == 30
    finally:
        _cleanup(doctor_ids=(doctor_id,))
