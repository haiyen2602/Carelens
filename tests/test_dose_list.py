"""GET /api/v1/doses - truong `has_photo`.

VI SAO CO TRUONG NAY (THEM 2026-08-31): man Lich su cua benh nhan can biet
lieu nao da duoc xac nhan bang anh de ghi nhan chu "xac nhan bang anh" tren
tung dong. Truoc day frontend lay thong tin do bang cach goi
GET /doses/{id}/photo-verifications cho TUNG LIEU MOT - do tren DB that ngay
2026-08-31: 147 request HTTP moi lan mo trang, de biet mot dieu ma ca DB chi
co 42 dong photo_verification. Vong lap do con chay tren TOAN BO lieu chu
khong phai lieu trong khoang dang loc, nen tab "Hom nay" hien 2 dong cung
van ban du 147 request.

Nay gop vao chinh GET /doses bang mot LEFT JOIN.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import DoseEvent, PhotoVerification  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_dose(db, patient_id: str) -> DoseEvent:
    now = datetime.now(UTC)
    dose = DoseEvent(
        prescription_id="presc-has-photo",
        patient_id=patient_id,
        scheduled_at=now,
        window_start=now - timedelta(minutes=30),
        window_end=now + timedelta(minutes=30),
        status="PENDING",
        expected_items=[],
    )
    db.add(dose)
    db.flush()
    return dose


def _seed_photo(db, dose: DoseEvent, *, image_path: str | None) -> None:
    db.add(
        PhotoVerification(
            dose_event_id=dose.id,
            patient_id=dose.patient_id,
            attempt=1,
            expected_by_form={},
            detected_by_form={},
            ket_qua="khop",
            thong_bao="test",
            image_path=image_path,
        )
    )


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(PhotoVerification).filter(PhotoVerification.patient_id == patient_id).delete(
            synchronize_session=False
        )
        db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


async def _lay_doses(client, patient_id: str) -> dict[str, dict]:
    response = await client.get(f"/api/v1/doses?patient_id={patient_id}")
    assert response.status_code == 200, response.text
    return {d["id"]: d for d in response.json()}


@pytest.mark.asyncio
async def test_lieu_co_anh_va_lieu_khong_co_anh(client):
    patient_id = f"test-hasphoto-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        co_anh = _seed_dose(db, patient_id)
        khong_anh = _seed_dose(db, patient_id)
        _seed_photo(db, co_anh, image_path="/tmp/anh-that.jpg")
        db.commit()
        ids = (co_anh.id, khong_anh.id)
        db.close()

        doses = await _lay_doses(client, patient_id)
        assert doses[ids[0]]["has_photo"] is True
        assert doses[ids[1]]["has_photo"] is False
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_anh_da_bi_don_dep_thi_khong_con_tinh_la_co_anh(client):
    """photo_cleanup.py xoa file het han va dat image_path = None, giu lai dong
    PhotoVerification lam audit trail. Dieu kien SQL phai bam theo image_path
    chu khong phai "co dong photo_verification nao khong" - neu khong, lieu da
    bi don anh van bao la co anh trong khi bam vao khong xem duoc gi."""
    patient_id = f"test-hasphoto-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        dose = _seed_dose(db, patient_id)
        _seed_photo(db, dose, image_path=None)
        db.commit()
        dose_id = dose.id
        db.close()

        doses = await _lay_doses(client, patient_id)
        assert doses[dose_id]["has_photo"] is False
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_nhieu_lan_chup_chi_can_mot_lan_co_anh(client):
    """ADR-0011 cho toi da 3 lan gui cho 1 lieu. Chi can MOT lan con anh la
    lieu do van la "da xac nhan bang anh" - va khong duoc tra ve trung dong
    lieu do vi JOIN (bug kinh dien cua LEFT JOIN 1-nhieu)."""
    patient_id = f"test-hasphoto-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        dose = _seed_dose(db, patient_id)
        _seed_photo(db, dose, image_path=None)
        _seed_photo(db, dose, image_path="/tmp/lan-2.jpg")
        db.commit()
        dose_id = dose.id
        db.close()

        response = await client.get(f"/api/v1/doses?patient_id={patient_id}")
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1, "LEFT JOIN khong duoc nhan doi dong lieu"
        assert rows[0]["id"] == dose_id
        assert rows[0]["has_photo"] is True
    finally:
        _cleanup(patient_id)
