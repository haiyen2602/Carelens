"""Phase 5 - test bat buoc (rui ro that, khong phai ly thuyet, xem trao doi
truoc khi code Phase 5): 2 ben nhan rieng biet, moi nguoi co don thuoc/lich
uong RIENG - goi tool cho benh nhan A khong bao gio duoc tra ve du lieu cua
benh nhan B. Day la integration test, can Postgres that (docker compose up -d
db), khong can OpenAI (2 tool nay khong goi LLM/embedding).
"""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from src.agents.tools.personal_tools import (  # noqa: E402
    tra_cuu_don_thuoc_ca_nhan,
    tra_cuu_lich_uong_ca_nhan,
)
from src.db.base import SessionLocal, engine  # noqa: E402
from src.db.models import DoseEvent, Prescription  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.fixture
def two_patients_with_own_data():
    """Seed 2 benh nhan doc lap, moi nguoi 1 prescription + 1 dose_event
    RIENG, chua 1 thuoc khac nhau va thoi_diem_dung khac nhau - de phat hien
    duoc ngay neu co nhamlan cheo."""
    db = SessionLocal()
    patient_a = f"test-patient-a-{uuid.uuid4().hex[:8]}"
    patient_b = f"test-patient-b-{uuid.uuid4().hex[:8]}"

    presc_a = Prescription(
        patient_id=patient_a,
        doctor_id="doc-1",
        status="approved",
        items=[
            {
                "ten_thuoc": "Thuốc CỦA A",
                "drug_id": "drug-a-only",
                "lieu_dung": "1 viên/lần",
                "duong_dung": "Uống",
                "thoi_diem_dung": "sau ăn sáng CỦA A",
                "gio_nhac": ["08:00"],
            }
        ],
        start_date="2026-08-01",
        duration_days=7,
    )
    presc_b = Prescription(
        patient_id=patient_b,
        doctor_id="doc-1",
        status="approved",
        items=[
            {
                "ten_thuoc": "Thuốc CỦA B",
                "drug_id": "drug-b-only",
                "lieu_dung": "2 viên/lần",
                "duong_dung": "Uống",
                "thoi_diem_dung": "trước ăn tối CỦA B",
                "gio_nhac": ["18:00"],
            }
        ],
        start_date="2026-08-01",
        duration_days=7,
    )
    db.add_all([presc_a, presc_b])
    db.commit()

    now = datetime.now(UTC)
    dose_a = DoseEvent(
        prescription_id=presc_a.id,
        patient_id=patient_a,
        scheduled_at=now,
        window_start=now,
        window_end=now,
        status="PENDING",
        expected_items=[{"drug_id": "drug-a-only", "ten_thuoc": "Thuốc CỦA A", "so_vien": 1}],
    )
    dose_b = DoseEvent(
        prescription_id=presc_b.id,
        patient_id=patient_b,
        scheduled_at=now,
        window_start=now,
        window_end=now,
        status="PENDING",
        expected_items=[{"drug_id": "drug-b-only", "ten_thuoc": "Thuốc CỦA B", "so_vien": 2}],
    )
    db.add_all([dose_a, dose_b])
    db.commit()

    yield {"patient_a": patient_a, "patient_b": patient_b}

    db.query(DoseEvent).filter(DoseEvent.patient_id.in_([patient_a, patient_b])).delete(synchronize_session=False)
    db.query(Prescription).filter(Prescription.patient_id.in_([patient_a, patient_b])).delete(
        synchronize_session=False
    )
    db.commit()
    db.close()


def test_tra_cuu_lich_uong_ca_nhan_never_leaks_other_patient(two_patients_with_own_data):
    patient_a = two_patients_with_own_data["patient_a"]
    patient_b = two_patients_with_own_data["patient_b"]

    db = SessionLocal()
    try:
        result_a = tra_cuu_lich_uong_ca_nhan(db, patient_a)
        result_b = tra_cuu_lich_uong_ca_nhan(db, patient_b)
    finally:
        db.close()

    assert len(result_a) == 1
    assert result_a[0]["expected_items"][0]["drug_id"] == "drug-a-only"
    assert all("drug-b-only" not in str(r) for r in result_a), "Lich cua A bi lo du lieu cua B"

    assert len(result_b) == 1
    assert result_b[0]["expected_items"][0]["drug_id"] == "drug-b-only"
    assert all("drug-a-only" not in str(r) for r in result_b), "Lich cua B bi lo du lieu cua A"


def test_tra_cuu_don_thuoc_ca_nhan_never_leaks_other_patient(two_patients_with_own_data):
    patient_a = two_patients_with_own_data["patient_a"]

    db = SessionLocal()
    try:
        # A hoi ve thuoc cua CHINH MINH -> phai thay
        own_drug = tra_cuu_don_thuoc_ca_nhan(db, patient_a, "drug-a-only")
        # A hoi ve thuoc cua B (gia su biet duoc drug_id do bang cach nao do)
        # -> KHONG duoc thay, vi A khong co don nao chua thuoc do
        other_drug = tra_cuu_don_thuoc_ca_nhan(db, patient_a, "drug-b-only")
    finally:
        db.close()

    assert own_drug is not None
    assert own_drug["thoi_diem_dung"] == "sau ăn sáng CỦA A"

    assert other_drug is None, (
        "LO DU LIEU: benh nhan A tra ve duoc thoi_diem_dung cua thuoc chi co trong don cua benh nhan B"
    )


def test_tra_cuu_don_thuoc_ca_nhan_cross_check_both_directions(two_patients_with_own_data):
    """Kiem tra chieu nguoc lai (B hoi ve thuoc cua A) de chac chan khong
    phai ngau nhien pass 1 chieu - phai sai o CA HAI chieu neu co bug."""
    patient_b = two_patients_with_own_data["patient_b"]

    db = SessionLocal()
    try:
        b_asks_for_a_drug = tra_cuu_don_thuoc_ca_nhan(db, patient_b, "drug-a-only")
        b_own_drug = tra_cuu_don_thuoc_ca_nhan(db, patient_b, "drug-b-only")
    finally:
        db.close()

    assert b_asks_for_a_drug is None
    assert b_own_drug is not None
    assert b_own_drug["thoi_diem_dung"] == "trước ăn tối CỦA B"
