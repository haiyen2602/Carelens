"""Kiểm chứng `xoa_anh_het_han` trên Postgres thật — cần `docker compose up -d db`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.config import Settings
from backend.db.base import SessionLocal, engine
from backend.db.models import PhotoVerification
from backend.services.photo_cleanup import xoa_anh_het_han
from backend.services.photo_verification.matcher import KetQua
from backend.services.photo_verification.verifier import (
    TRANG_THAI_DANG_XU_LY,
    TRANG_THAI_DO_TIN_CAY_THAP,
    TRANG_THAI_LOI_HE_THONG,
)


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Cần Postgres thật (docker compose up -d db)")

_SETTINGS = Settings(
    photo_retention_days_khop=14,
    photo_retention_days_lech=90,
    photo_retention_days_stuck=3,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _tao_dong(db, tmp_path, *, ket_qua: str, tuoi_ngay: int, co_file: bool = True) -> PhotoVerification:
    duong_dan = None
    if co_file:
        p = tmp_path / f"{uuid.uuid4().hex}.jpg"
        p.write_bytes(b"\xff\xd8\xff" + b"0" * 10)
        duong_dan = str(p)

    row = PhotoVerification(
        id=uuid.uuid4().hex,
        dose_event_id=f"dose-{uuid.uuid4().hex[:8]}",
        patient_id=f"patient-{uuid.uuid4().hex[:8]}",
        attempt=1,
        ket_qua=ket_qua,
        thong_bao="test",
        image_path=duong_dan,
        created_at=datetime.now(UTC) - timedelta(days=tuoi_ngay),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture(autouse=True)
def don_dep(db):
    yield
    db.query(PhotoVerification).filter(PhotoVerification.dose_event_id.like("dose-%")).delete(synchronize_session=False)
    db.commit()


def test_khop_qua_han_bi_xoa(db, tmp_path):
    row = _tao_dong(db, tmp_path, ket_qua=KetQua.KHOP.value, tuoi_ngay=15)

    so_xoa = xoa_anh_het_han(db, settings=_SETTINGS)

    db.refresh(row)
    assert so_xoa == 1
    assert row.image_path is None
    assert not (tmp_path / "khong-dung").exists()  # sanity: thư mục tmp vẫn hoạt động


def test_khop_trong_han_khong_bi_dong(db, tmp_path):
    row = _tao_dong(db, tmp_path, ket_qua=KetQua.KHOP.value, tuoi_ngay=5)
    duong_dan_cu = row.image_path

    so_xoa = xoa_anh_het_han(db, settings=_SETTINGS)

    db.refresh(row)
    assert so_xoa == 0
    assert row.image_path == duong_dan_cu


def test_lech_giu_lau_hon_khop_dung_tang_rieng(db, tmp_path):
    """20 ngày: đã quá hạn 'khop' (14) nhưng chưa quá hạn 'lech' (90) — dòng
    lech ở tuổi này KHÔNG được xoá, chứng minh 2 tầng độc lập nhau."""
    row = _tao_dong(db, tmp_path, ket_qua=KetQua.LECH.value, tuoi_ngay=20)
    duong_dan_cu = row.image_path

    so_xoa = xoa_anh_het_han(db, settings=_SETTINGS)

    db.refresh(row)
    assert so_xoa == 0
    assert row.image_path == duong_dan_cu


def test_lech_qua_han_bi_xoa(db, tmp_path):
    row = _tao_dong(db, tmp_path, ket_qua=KetQua.LECH.value, tuoi_ngay=91)

    so_xoa = xoa_anh_het_han(db, settings=_SETTINGS)

    db.refresh(row)
    assert so_xoa == 1
    assert row.image_path is None


@pytest.mark.parametrize(
    "ket_qua", [TRANG_THAI_DANG_XU_LY, TRANG_THAI_LOI_HE_THONG, TRANG_THAI_DO_TIN_CAY_THAP]
)
def test_ket_qua_ket_qua_han_stuck_qua_han_bi_xoa(db, tmp_path, ket_qua):
    row = _tao_dong(db, tmp_path, ket_qua=ket_qua, tuoi_ngay=4)

    so_xoa = xoa_anh_het_han(db, settings=_SETTINGS)

    db.refresh(row)
    assert so_xoa == 1
    assert row.image_path is None


def test_dong_khong_co_file_khong_bi_dong_khong_crash(db, tmp_path):
    row = _tao_dong(db, tmp_path, ket_qua=KetQua.KHOP.value, tuoi_ngay=30, co_file=False)

    so_xoa = xoa_anh_het_han(db, settings=_SETTINGS)

    db.refresh(row)
    assert so_xoa == 0
    assert row.image_path is None


def test_file_da_bi_xoa_tay_tu_truoc_khong_lam_job_crash(db, tmp_path):
    row = _tao_dong(db, tmp_path, ket_qua=KetQua.KHOP.value, tuoi_ngay=15)
    Path(row.image_path).unlink()  # giả lập file đã mất trước khi job chạy

    so_xoa = xoa_anh_het_han(db, settings=_SETTINGS)

    db.refresh(row)
    assert so_xoa == 1  # missing_ok=True vẫn tính là "đã dọn xong"
    assert row.image_path is None
