"""Kiểm chứng state machine ADR-0011 trên Postgres thật.

`dem_thuoc_trong_anh` (gọi mạng thật, 26-265 giây) bị thay bằng hàm giả — bài
test này kiểm chứng STATE MACHINE (đủ lượt chưa, escalate khi nào, dose_event
đổi trạng thái ra sao), không kiểm chứng lại mô hình đếm (đã có
test_vlm_bridge.py riêng).

Cần DB có bảng `drug` đã nạp (python scripts/seed_drug_catalog.py).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.db.base import SessionLocal, engine
from backend.db.models import DoseEvent, Escalation, Patient, PhotoVerification
from backend.services.photo_verification import KetQuaDemVlm
from backend.services.photo_verification.matcher import KetQua
from backend.services.photo_verification.verifier import (
    MAX_ATTEMPTS,
    MAX_LAN_DO_TIN_CAY_THAP,
    NEXT_ACTION_CAREGIVER_REVIEW,
    NEXT_ACTION_NONE,
    NEXT_ACTION_RETAKE,
    TRANG_THAI_DANG_XU_LY,
    TRANG_THAI_DO_TIN_CAY_THAP,
    TRANG_THAI_LOI_HE_THONG,
    HanMucVuotQuaError,
    KhongXacMinhDuocError,
    dem_lan_do_tin_cay_thap,
    dem_luot_da_dung,
    hoan_tat_xac_minh,
    khoi_tao_xac_minh,
    xac_dinh_next_action,
)
from backend.services.vlm_telemetry import get_vlm_local_traces


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Cần Postgres thật (docker compose up -d db)")


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def benh_nhan(db):
    p = Patient(id=f"test-verifier-{uuid.uuid4().hex[:8]}", full_name="Bệnh nhân test verifier")
    db.add(p)
    db.commit()
    yield p
    db.query(Escalation).filter(Escalation.patient_id == p.id).delete(synchronize_session=False)
    db.query(PhotoVerification).filter(PhotoVerification.patient_id == p.id).delete(synchronize_session=False)
    db.query(DoseEvent).filter(DoseEvent.patient_id == p.id).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == p.id).delete(synchronize_session=False)
    db.commit()


def _dose_event(patient_id: str, expected_items: list[dict]) -> DoseEvent:
    gio = datetime.now(UTC)
    return DoseEvent(
        prescription_id="presc-gia",
        patient_id=patient_id,
        scheduled_at=gio,
        window_start=gio - timedelta(minutes=30),
        window_end=gio + timedelta(minutes=30),
        status="PENDING",
        expected_items=expected_items,
    )


def _lieu_xac_minh_duoc(db, patient_id) -> DoseEvent:
    """1 liều 2 viên nén — EXACT, đối chiếu được ngay."""
    d = _dose_event(patient_id, [{
        "drug_id": "d1", "ten_thuoc": "Thuốc test", "dang_thuoc": "Viên nén",
        "duong_dung": "Uống", "so_vien": 2,
    }])
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _lieu_khong_xac_minh_duoc(db, patient_id) -> DoseEvent:
    """1 liều toàn thuốc tiêm — SKIP, không thuốc nào đối chiếu được."""
    d = _dose_event(patient_id, [{
        "drug_id": "d2", "ten_thuoc": "Insulin", "dang_thuoc": "Dung dịch tiêm",
        "duong_dung": "Tiêm", "so_vien": 1,
    }])
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _gia_vlm(monkeypatch, do_tin_cay="cao", **so_dem) -> None:
    """Thay `dem_thuoc_trong_anh` bằng hàm trả về kết quả lập trình sẵn — patch
    đúng chỗ verifier.py đã `from ... import`, không phải nơi định nghĩa gốc.
    `so_dem` (vd `vien_nen=2`) đổ vào `counts`, không phải field cấp cao nhất."""
    counts = dict.fromkeys(("vien_nang", "vien_nen", "tuyp_thuoc", "lo_thuoc", "hop_thuoc", "goi_thuoc"), 0)
    counts.update(so_dem)
    ket_qua = KetQuaDemVlm(ok=True, counts=counts, do_tin_cay=do_tin_cay)
    monkeypatch.setattr("backend.services.photo_verification.verifier.dem_thuoc_trong_anh", lambda *_a, **_kw: ket_qua)


def _gia_vlm_loi(monkeypatch, thong_bao="mất mạng") -> None:
    ket_qua = KetQuaDemVlm(ok=False, error=thong_bao)
    monkeypatch.setattr("backend.services.photo_verification.verifier.dem_thuoc_trong_anh", lambda *_a, **_kw: ket_qua)


def _gia_doc_anh(monkeypatch, tmp_path) -> str:
    """Ảnh giả trên đĩa thật — `hoan_tat_xac_minh` tự mở lại file bằng đường dẫn."""
    duong_dan = tmp_path / "anh_gia.jpg"
    duong_dan.write_bytes(b"\xff\xd8\xff" + b"0" * 20)
    return str(duong_dan)


# ---------------------------------------------------------------------------
# Hàm thuần — không cần DB
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "ket_qua,attempt,mong_doi",
    [
        (KetQua.KHOP, 1, NEXT_ACTION_NONE),
        (KetQua.KHOP, 3, NEXT_ACTION_NONE),
        (KetQua.LECH, 1, NEXT_ACTION_RETAKE),
        (KetQua.LECH, 2, NEXT_ACTION_RETAKE),
        (KetQua.LECH, 3, NEXT_ACTION_CAREGIVER_REVIEW),
        (KetQua.KHONG_XAC_MINH_DUOC, 1, NEXT_ACTION_NONE),
    ],
)
def test_xac_dinh_next_action(ket_qua, attempt, mong_doi):
    assert xac_dinh_next_action(ket_qua, attempt) == mong_doi


# ---------------------------------------------------------------------------
# Khởi tạo — chặn TRƯỚC khi tốn thời gian gọi mô hình
# ---------------------------------------------------------------------------
def test_lieu_khong_xac_minh_duoc_bi_chan_ngay_khong_tao_dong(db, benh_nhan):
    dose = _lieu_khong_xac_minh_duoc(db, benh_nhan.id)

    with pytest.raises(KhongXacMinhDuocError):
        khoi_tao_xac_minh(db, dose, "/tmp/khong-dung-toi.jpg")

    assert db.query(PhotoVerification).filter(PhotoVerification.dose_event_id == dose.id).count() == 0


def test_khoi_tao_thanh_cong_tao_dong_dang_xu_ly(db, benh_nhan):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)

    ket_qua = khoi_tao_xac_minh(db, dose, "/tmp/anh1.jpg")

    row = db.get(PhotoVerification, ket_qua.id)
    assert row.ket_qua == TRANG_THAI_DANG_XU_LY
    assert row.attempt == 1
    assert row.expected_by_form == {"vien_nen": 2}


def test_het_luot_bi_chan(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm(monkeypatch, vien_nen=999)  # luôn lệch, để đi hết cả 3 lượt

    for _ in range(MAX_ATTEMPTS):
        ket_qua = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
        hoan_tat_xac_minh(ket_qua.id)

    with pytest.raises(HanMucVuotQuaError):
        khoi_tao_xac_minh(db, dose, "/tmp/lan-thu-4.jpg")


# ---------------------------------------------------------------------------
# Hoàn tất — đường khớp
# ---------------------------------------------------------------------------
def test_khop_thi_dose_event_chuyen_taken(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm(monkeypatch, vien_nen=2)
    xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))

    hoan_tat_xac_minh(xac_minh.id)

    row = db.get(PhotoVerification, xac_minh.id)
    assert row.ket_qua == KetQua.KHOP.value
    # detected_by_form lưu ĐỦ 6 khoá (kể cả 0) — phục vụ audit (BR-4.2), không
    # chỉ khoá khác 0.
    assert row.detected_by_form["vien_nen"] == 2
    assert row.detected_by_form["vien_nang"] == 0
    db.refresh(dose)
    assert dose.status == "TAKEN"


def test_khop_nhung_qua_window_thi_delayed_khong_phai_taken(db, benh_nhan, monkeypatch, tmp_path):
    """BR-2.2: xác nhận sau window_end không được tính là TAKEN."""
    dose = _dose_event(benh_nhan.id, [{
        "drug_id": "d1", "ten_thuoc": "Thuốc test", "dang_thuoc": "Viên nén",
        "duong_dung": "Uống", "so_vien": 2,
    }])
    dose.window_end = datetime.now(UTC) - timedelta(minutes=5)  # cửa sổ đã đóng
    db.add(dose)
    db.commit()
    db.refresh(dose)

    _gia_vlm(monkeypatch, vien_nen=2)
    xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
    hoan_tat_xac_minh(xac_minh.id)

    row = db.get(PhotoVerification, xac_minh.id)
    assert row.ket_qua == KetQua.KHOP.value, "vẫn khớp đúng đơn thuốc"
    db.refresh(dose)
    assert dose.status == "DELAYED", "khớp nhưng trễ cửa sổ không được ghi TAKEN"


# ---------------------------------------------------------------------------
# Hoàn tất — đường lệch, chưa hết lượt
# ---------------------------------------------------------------------------
def test_lech_lan_dau_khong_dung_den_dose_event(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm(monkeypatch, vien_nen=1)  # đơn cần 2
    xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))

    hoan_tat_xac_minh(xac_minh.id)

    row = db.get(PhotoVerification, xac_minh.id)
    assert row.ket_qua == KetQua.LECH.value
    assert "thiếu" in row.thong_bao.lower()
    db.refresh(dose)
    assert dose.status == "PENDING", "chưa hết lượt thì chưa động vào dose_event"
    assert db.query(Escalation).filter(Escalation.dose_event_id == dose.id).count() == 0


# ---------------------------------------------------------------------------
# Hoàn tất — hết lượt: escalate + AWAITING_CAREGIVER
# ---------------------------------------------------------------------------
def test_het_luot_ma_van_lech_thi_escalate_va_cho_nguoi_than(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm(monkeypatch, vien_nen=1)  # luôn thiếu 1 viên

    for _ in range(MAX_ATTEMPTS):
        xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
        hoan_tat_xac_minh(xac_minh.id)

    db.refresh(dose)
    assert dose.status == "AWAITING_CAREGIVER"

    esc = db.query(Escalation).filter(Escalation.dose_event_id == dose.id).one()
    assert esc.trigger == "photo_mismatch"
    assert esc.severity == "MEDIUM"
    assert set(esc.notified) == {"caregiver", "doctor"}


# ---------------------------------------------------------------------------
# Hoàn tất — lỗi hệ thống không trừ lượt
# ---------------------------------------------------------------------------
def test_loi_he_thong_khong_tinh_vao_han_muc(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm_loi(monkeypatch)

    xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
    hoan_tat_xac_minh(xac_minh.id)

    row = db.get(PhotoVerification, xac_minh.id)
    assert row.ket_qua == TRANG_THAI_LOI_HE_THONG
    assert dem_luot_da_dung(db, dose.id) == 0, "lỗi mạng/model không phải lỗi của bệnh nhân"

    # Gọi lại vẫn được attempt=1, không phải attempt=2 — chứng minh không mất lượt.
    xac_minh_2 = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
    assert xac_minh_2.attempt == 1


def test_doc_anh_hong_bao_loi_he_thong_khong_lam_chet_task(db, benh_nhan, monkeypatch):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    xac_minh = khoi_tao_xac_minh(db, dose, "/duong/dan/khong/ton/tai.jpg")

    hoan_tat_xac_minh(xac_minh.id)  # không được ném exception ra ngoài

    row = db.get(PhotoVerification, xac_minh.id)
    assert row.ket_qua == TRANG_THAI_LOI_HE_THONG


def test_verification_id_khong_ton_tai_khong_lam_chet_task():
    hoan_tat_xac_minh("khong-ton-tai-chac-chan")  # chỉ log, không raise


# ---------------------------------------------------------------------------
# Telemetry VLM (THEM 2026-08-22, backend/services/vlm_telemetry.py) - moi
# lan goi hoan_tat_xac_minh phai ghi duoc 1 trace vao buffer, KE CA khi VLM
# loi (try/finally trong _hoan_tat_xac_minh) - test khong can key Langfuse
# that, buffer in-memory hoat dong doc lap voi client.
# ---------------------------------------------------------------------------
def test_hoan_tat_xac_minh_ghi_trace_khi_khop(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm(monkeypatch, vien_nen=2)
    xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))

    hoan_tat_xac_minh(xac_minh.id)

    trace = next((t for t in get_vlm_local_traces() if t.id == xac_minh.id), None)
    assert trace is not None
    assert trace.status == "success"
    assert trace.scores["match_result"] == 1.0
    assert any(o.name == "vlm.model_call" for o in trace.observations)
    assert any(o.name == "vlm.compare_prescription" for o in trace.observations)


def test_hoan_tat_xac_minh_ghi_trace_loi_khi_vlm_that_bai(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm_loi(monkeypatch)
    xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))

    hoan_tat_xac_minh(xac_minh.id)

    trace = next((t for t in get_vlm_local_traces() if t.id == xac_minh.id), None)
    assert trace is not None
    assert trace.status == "error"


# ---------------------------------------------------------------------------
# do_tin_cay="thap" (THEM 2026-08-23, sau khi chay golden set that thay do_tin_cay
# "thap" chi dung 14% - eval/eval_vlm/): coi nhu loi model chua chac chan, xin
# chup lai KHONG tru luot that (dem_luot_da_dung chi dem KHOP/LECH) - nhung co
# gioi han RIENG (MAX_LAN_DO_TIN_CAY_THAP) de khong lap vo han.
# ---------------------------------------------------------------------------
def test_do_tin_cay_thap_khong_tru_luot(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)
    _gia_vlm(monkeypatch, do_tin_cay="thap", vien_nen=2)
    xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))

    hoan_tat_xac_minh(xac_minh.id)

    row = db.get(PhotoVerification, xac_minh.id)
    assert row.ket_qua == TRANG_THAI_DO_TIN_CAY_THAP
    assert dem_luot_da_dung(db, dose.id) == 0
    assert dem_lan_do_tin_cay_thap(db, dose.id) == 1

    # Chup lai lan nua - KHONG bi tinh la attempt 2, vi lan truoc khong tru luot that.
    xac_minh_2 = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
    assert xac_minh_2.attempt == 1

    trace = next((t for t in get_vlm_local_traces() if t.id == xac_minh.id), None)
    assert trace is not None
    assert trace.status == "retry_low_confidence"


def test_do_tin_cay_thap_qua_gioi_han_thi_chay_that(db, benh_nhan, monkeypatch, tmp_path):
    dose = _lieu_xac_minh_duoc(db, benh_nhan.id)

    # Dung het MAX_LAN_DO_TIN_CAY_THAP luot mien phi.
    for _ in range(MAX_LAN_DO_TIN_CAY_THAP):
        _gia_vlm(monkeypatch, do_tin_cay="thap", vien_nen=2)
        xac_minh = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
        hoan_tat_xac_minh(xac_minh.id)
        row = db.get(PhotoVerification, xac_minh.id)
        assert row.ket_qua == TRANG_THAI_DO_TIN_CAY_THAP

    assert dem_lan_do_tin_cay_thap(db, dose.id) == MAX_LAN_DO_TIN_CAY_THAP
    assert dem_luot_da_dung(db, dose.id) == 0

    # Lan tiep theo van "thap" nhung HET ve mien phi - phai chay xuong so
    # sanh THAT (dem sai don -> LECH that, tru luot that).
    _gia_vlm(monkeypatch, do_tin_cay="thap", vien_nen=999)
    xac_minh_3 = khoi_tao_xac_minh(db, dose, _gia_doc_anh(monkeypatch, tmp_path))
    hoan_tat_xac_minh(xac_minh_3.id)

    row_3 = db.get(PhotoVerification, xac_minh_3.id)
    assert row_3.ket_qua == KetQua.LECH.value
    assert dem_luot_da_dung(db, dose.id) == 1
