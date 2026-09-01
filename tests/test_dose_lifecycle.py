"""backend/services/dose_lifecycle.py - job chot cac lieu con PENDING sau khi
da sang ngay moi thanh MISSED.

Tach 2 tang giong test_dose_push_reminder.py: qua_ngay_moi() la ham THUAN
(test truc tiep, khong can DB), chot_lieu_qua_han() can DB that.

Vi sao job nay ton tai: truoc day KHONG co gi chuyen PENDING -> MISSED (xem
comment cu o dose_push_reminder.py va verifier.py), nen lieu benh nhan im
lang khong dung toi nam PENDING vinh vien. Ca hai man hinh thong ke deu loai
PENDING khoi mau so, nen ty le tuan thu bi thoi phong (do that: 88% hien thi
vs 23% that tren pat_002).
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
from backend.db.models import DoseEvent  # noqa: E402
from backend.services.dose_lifecycle import (  # noqa: E402
    chot_lieu_qua_han,
    chot_nhan_xac_nhan,
    qua_ngay_moi,
)

# 07:00 UTC = 14:00 gio VN - gio "giua ngay" o ca hai mui, dung lam moc goc
# cho cac phep cong/tru ben duoi de khong vo tinh nhay ngay.
GIUA_NGAY_VN = datetime(2026, 8, 20, 7, 0, tzinfo=UTC)


# --- Tang 1: ham thuan, khong can DB ---------------------------------------


@pytest.mark.parametrize(
    ("mo_ta", "scheduled_at", "now", "mong_doi"),
    [
        (
            "cung ngay, chua qua window - chua chot",
            GIUA_NGAY_VN,
            GIUA_NGAY_VN + timedelta(minutes=10),
            False,
        ),
        (
            "cung ngay, DA qua window 3 tieng - VAN chua chot (con co hoi xac nhan muon)",
            GIUA_NGAY_VN,
            GIUA_NGAY_VN + timedelta(hours=3),
            False,
        ),
        (
            "sang ngay moi gio VN - chot",
            GIUA_NGAY_VN,
            GIUA_NGAY_VN + timedelta(hours=11),  # 14:00 -> 01:00 hom sau gio VN
            True,
        ),
        (
            "lieu 23:30 VN, xac nhan 00:10 hom sau - DA sang ngay moi",
            datetime(2026, 8, 20, 16, 30, tzinfo=UTC),  # 23:30 VN 20/08
            datetime(2026, 8, 20, 17, 10, tzinfo=UTC),  # 00:10 VN 21/08
            True,
        ),
        (
            "BAY MUI GIO: lieu 06:00 VN luu thanh 23:00 UTC HOM TRUOC, "
            "23:00 VN cung ngay VN do van la CUNG ngay - khong duoc chot",
            datetime(2026, 8, 19, 23, 0, tzinfo=UTC),  # 06:00 VN 20/08
            datetime(2026, 8, 20, 16, 0, tzinfo=UTC),  # 23:00 VN 20/08
            False,
        ),
    ],
)
def test_qua_ngay_moi(mo_ta, scheduled_at, now, mong_doi):
    assert qua_ngay_moi(scheduled_at, now) is mong_doi, mo_ta


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


def _seed_dose(db, patient_id: str, scheduled_at: datetime, status: str) -> DoseEvent:
    row = DoseEvent(
        prescription_id="presc-test-closeout",
        patient_id=patient_id,
        scheduled_at=scheduled_at,
        window_start=scheduled_at - timedelta(minutes=30),
        window_end=scheduled_at + timedelta(minutes=30),
        status=status,
        expected_items=[{"drug_id": "x", "ten_thuoc": "Thuoc A", "so_vien": 1}],
    )
    db.add(row)
    return row


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@db_required
def test_chot_lieu_pending_cua_hom_qua():
    patient_id = f"test-closeout-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        hom_qua = _seed_dose(db, patient_id, now - timedelta(days=1), "PENDING")
        db.commit()

        assert chot_lieu_qua_han(db, now=now) == 1

        db.refresh(hom_qua)
        assert hom_qua.status == "MISSED"
    finally:
        db.close()
        _cleanup(patient_id)


@db_required
def test_khong_dung_toi_lieu_cua_hom_nay():
    """Lieu hom nay da qua window van con co hoi xac nhan muon (DELAYED) -
    job KHONG duoc cuop mat co hoi do."""
    patient_id = f"test-closeout-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        # Lui 90 phut de chac chan da qua window (+-30 phut) nhung van trong
        # ngay VN - tru khi job chay sat nua dem, xem assert phong ve ben duoi.
        hom_nay = _seed_dose(db, patient_id, now - timedelta(minutes=90), "PENDING")
        db.commit()

        from backend.services.reward_ledger import ngay_vn

        if ngay_vn(hom_nay.scheduled_at) != ngay_vn(now):
            pytest.skip("Chay sat nua dem gio VN - moc ngay da doi, test khong con y nghia")

        assert chot_lieu_qua_han(db, now=now) == 0
        db.refresh(hom_nay)
        assert hom_nay.status == "PENDING"
    finally:
        db.close()
        _cleanup(patient_id)


@db_required
@pytest.mark.parametrize("status", ["TAKEN", "DELAYED", "MISSED", "CANCELLED", "AWAITING_CAREGIVER"])
def test_khong_dung_toi_trang_thai_da_chot(status):
    """AWAITING_CAREGIVER co trong danh sach nay theo quyet dinh san pham
    2026-08-31: lieu ket o do la vi NGUOI THAN chua duyet, khong phai benh
    nhan bo thuoc - chot thanh MISSED se phat nham nguoi."""
    patient_id = f"test-closeout-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        row = _seed_dose(db, patient_id, now - timedelta(days=1), status)
        db.commit()

        assert chot_lieu_qua_han(db, now=now) == 0
        db.refresh(row)
        assert row.status == status
    finally:
        db.close()
        _cleanup(patient_id)


@db_required
def test_idempotent_chay_lai_khong_dem_lai():
    """Job chay dinh ky - lan chay thu 2 khong duoc dem lai lieu da chot."""
    patient_id = f"test-closeout-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        _seed_dose(db, patient_id, now - timedelta(days=1), "PENDING")
        _seed_dose(db, patient_id, now - timedelta(days=2), "PENDING")
        db.commit()

        assert chot_lieu_qua_han(db, now=now) == 2
        assert chot_lieu_qua_han(db, now=now) == 0
    finally:
        db.close()
        _cleanup(patient_id)


# --- chot_nhan_xac_nhan: TAKEN hay DELAYED ---------------------------------
#
# Truoc thay doi nay, PATCH /doses/{id} gan THANG `body.status` cua client vao
# cot status (dose_routes.py: `dose.status = body.status`), khong doi chieu gio
# nao ca - ma frontend thi luon gui cung mot chuoi "TAKEN". Ket qua: benh nhan
# bam "toi da uong" luc 3 gio sang cho lieu 20:00 hom truoc van duoc ghi TAKEN.
# Do la ly do man Lich su hien "0 lan xac nhan muon" du khong ai dung gio.


@pytest.mark.parametrize(
    ("mo_ta", "lech_so_voi_window_end", "mong_doi"),
    [
        ("truoc window_end", timedelta(minutes=-10), "TAKEN"),
        ("dung window_end - van tinh la trong window", timedelta(0), "TAKEN"),
        ("qua window_end 1 giay", timedelta(seconds=1), "DELAYED"),
        ("qua window_end 3 tieng", timedelta(hours=3), "DELAYED"),
    ],
)
def test_chot_nhan_xac_nhan(mo_ta, lech_so_voi_window_end, mong_doi):
    window_end = GIUA_NGAY_VN + timedelta(minutes=30)
    assert chot_nhan_xac_nhan(window_end, window_end + lech_so_voi_window_end) == mong_doi, mo_ta


def test_chot_nhan_xac_nhan_dung_chung_quy_tac_voi_duong_chup_anh():
    """verifier.py da lam DUNG viec nay tu truoc (BR-2.2) bang bieu thuc
    `"TAKEN" if now <= window_end else "DELAYED"`. Test nay khoa lai rang hai
    duong xac nhan cho ra cung ket qua, de khong ai sua lech mot ben."""
    window_end = GIUA_NGAY_VN + timedelta(minutes=30)
    for lech in (timedelta(minutes=-1), timedelta(0), timedelta(minutes=1)):
        now = window_end + lech
        cach_cu_cua_verifier = "TAKEN" if now <= window_end else "DELAYED"
        assert chot_nhan_xac_nhan(window_end, now) == cach_cu_cua_verifier


@db_required
def test_khong_tu_commit_de_nguoi_goi_giu_ranh_gioi_giao_dich():
    """Hoi quy cho review PR #181: chot_lieu_qua_han() KHONG duoc tu commit.

    Quy uoc chung cua repo (reward_ledger._award, push.py, telegram.py,
    caregiver_escalation.py): service ghi DB nhung de NGUOI GOI dong giao
    dich. Tu commit ben trong se cat doi giao dich cua nguoi goi - cu the o
    scripts/backfill_dose_closeout.py, ham nay nam chung giao dich voi buoc
    ghi file bao cao (audit trail duy nhat cua lan va du lieu do).

    Kiem bang MOT PHIEN DOC LAP: o READ COMMITTED, phien khac chi thay thay
    doi sau khi phien ghi commit - nen day la phep thu that cho "da commit
    hay chua", khong phai chi doc lai cache cua chinh phien dang ghi.
    """
    patient_id = f"test-closeout-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    db = SessionLocal()
    kiem_tra = SessionLocal()
    try:
        lieu = _seed_dose(db, patient_id, now - timedelta(days=1), "PENDING")
        db.commit()
        dose_id = lieu.id

        assert chot_lieu_qua_han(db, now=now) == 1

        van_pending = kiem_tra.get(DoseEvent, dose_id)
        assert van_pending is not None
        assert van_pending.status == "PENDING", "Ham da tu commit - vi pham quy uoc ranh gioi giao dich"

        db.commit()
        kiem_tra.expire_all()
        assert kiem_tra.get(DoseEvent, dose_id).status == "MISSED", "Sau commit cua nguoi goi phai thay MISSED"
    finally:
        db.close()
        kiem_tra.close()
        _cleanup(patient_id)
