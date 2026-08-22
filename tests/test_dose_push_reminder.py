"""backend/services/dose_push_reminder.py - job quet lieu toi gio roi day
Web Push. Tach 2 tang giong escalation_reminder: tinh_moc() la ham THUAN
(test truc tiep, khong can DB), quet_va_day_nhac() can DB that."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import DoseEvent, Escalation, PushReminderSent  # noqa: E402
from backend.services.dose_push_reminder import (  # noqa: E402
    HET_HAN_NHAC_PHUT,
    MOC_GOI,
    MOC_NHAC_LAN_2,
    quet_va_day_nhac,
    tinh_moc,
)

# --- Tang 1: ham thuan, khong can DB ---------------------------------------

@pytest.mark.parametrize(
    ("phut_qua", "mong_doi"),
    [
        (-5, None),          # chua toi gio
        (0, 0),              # dung gio
        (14.9, 0),
        (MOC_NHAC_LAN_2, MOC_NHAC_LAN_2),
        (29, MOC_NHAC_LAN_2),
        (MOC_GOI, MOC_GOI),
        (HET_HAN_NHAC_PHUT, MOC_GOI),
        (HET_HAN_NHAC_PHUT + 1, None),   # qua han - khong nhac nua
        (22 * 60, None),                 # lieu ton dong tu hom truoc
    ],
)
def test_tinh_moc(phut_qua, mong_doi):
    assert tinh_moc(phut_qua) == mong_doi


# --- Tang 2: quet DB that --------------------------------------------------

def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


db_required = pytest.mark.skipif(
    not _db_available(), reason="Can Postgres that (docker compose up -d db)"
)


def _seed_dose(db, patient_id: str, scheduled_at: datetime, ten_thuoc: str) -> DoseEvent:
    row = DoseEvent(
        prescription_id="presc-test-push",
        patient_id=patient_id,
        scheduled_at=scheduled_at,
        window_start=scheduled_at - timedelta(minutes=30),
        window_end=scheduled_at + timedelta(minutes=30),
        status="PENDING",
        expected_items=[{"drug_id": "x", "ten_thuoc": ten_thuoc, "so_vien": 1}],
    )
    db.add(row)
    return row


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
    db.query(PushReminderSent).filter(PushReminderSent.patient_id == patient_id).delete(
        synchronize_session=False
    )
    db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@db_required
def test_gop_nhieu_thuoc_cung_khung_gio_thanh_1_luot_nhac():
    """2 thuoc cung hen 1 gio la 2 dong DoseEvent nhung chi la 1 lan uong -
    nhac tung dong se thanh 2 thong bao lien tiep (bug that da sua o client)."""
    patient_id = f"test-dpr-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    slot = now - timedelta(minutes=2)

    db = SessionLocal()
    try:
        _seed_dose(db, patient_id, slot, "Thuoc A")
        _seed_dose(db, patient_id, slot, "Thuoc B")
        db.commit()

        assert quet_va_day_nhac(db, now=now) == 1, "2 lieu cung gio = 1 luot nhac"

        rows = db.query(PushReminderSent).filter(PushReminderSent.patient_id == patient_id).all()
        assert len(rows) == 1
        assert rows[0].moc == 0
    finally:
        db.close()
        _cleanup(patient_id)


@db_required
def test_khong_day_trung_khi_chay_lai():
    """Job chay moi 60s - lan chay thu 2 trong cung 1 moc khong duoc nhac lai."""
    patient_id = f"test-dpr-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        _seed_dose(db, patient_id, now - timedelta(minutes=2), "Thuoc A")
        db.commit()

        assert quet_va_day_nhac(db, now=now) == 1
        assert quet_va_day_nhac(db, now=now + timedelta(seconds=60)) == 0
    finally:
        db.close()
        _cleanup(patient_id)


@db_required
def test_moc_30_tao_canh_bao_cho_nguoi_than():
    patient_id = f"test-dpr-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        _seed_dose(db, patient_id, now - timedelta(minutes=31), "Thuoc A")
        db.commit()

        assert quet_va_day_nhac(db, now=now) == 1

        canh_bao = db.query(Escalation).filter(Escalation.patient_id == patient_id).all()
        assert len(canh_bao) == 1
        assert canh_bao[0].severity == "MEDIUM"
        assert canh_bao[0].trigger == "dose_unconfirmed"
        assert canh_bao[0].status == "OPEN"
        assert "caregiver" in canh_bao[0].notified
    finally:
        db.close()
        _cleanup(patient_id)


@db_required
def test_bo_qua_lieu_ton_dong_qua_han():
    """Lieu tu hom truoc con PENDING (khong ai doi thanh MISSED) khong duoc
    lam benh nhan bi day 1 loat thong bao cu khi job chay."""
    patient_id = f"test-dpr-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        _seed_dose(db, patient_id, now - timedelta(hours=22), "Thuoc cu")
        db.commit()

        assert quet_va_day_nhac(db, now=now) == 0
        assert db.query(Escalation).filter(Escalation.patient_id == patient_id).count() == 0
    finally:
        db.close()
        _cleanup(patient_id)


@db_required
def test_lieu_da_uong_khong_bi_nhac():
    patient_id = f"test-dpr-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    db = SessionLocal()
    try:
        row = _seed_dose(db, patient_id, now - timedelta(minutes=5), "Thuoc A")
        row.status = "TAKEN"
        db.commit()

        assert quet_va_day_nhac(db, now=now) == 0
    finally:
        db.close()
        _cleanup(patient_id)
