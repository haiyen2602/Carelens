"""Kiểm chứng vòng đời phác đồ trên Postgres thật.

Cần DB có bảng `drug` đã nạp (python scripts/seed_drug_catalog.py) và bảng
`patient` tồn tại (python scripts/seed_photo_patients.py, hoặc tự tạo bệnh
nhân trong fixture — ở đây tự tạo để test không phụ thuộc script khác).

Không cần webcam, không cần mạng ngoài — chỉ SQL.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.db.base import SessionLocal, engine
from backend.db.models import DoseEvent, Drug, Patient, Prescription
from backend.services.prescription import (
    KhongTimThayError,
    TrangThaiKhongHopLeError,
    ViPhamNghiepVuError,
    dung_phac_do,
    duyet_phac_do,
    lay_phac_do,
    liet_ke_phac_do,
    tao_phac_do,
    tu_choi_phac_do,
)


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM drug LIMIT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="Cần Postgres + bảng drug đã nạp (python scripts/seed_drug_catalog.py)"
)


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
    """Một bệnh nhân riêng cho mỗi test, dọn sạch sau khi xong."""
    p = Patient(id=f"test-{uuid.uuid4().hex[:8]}", full_name="Bệnh nhân test")
    db.add(p)
    db.commit()
    yield p
    db.query(DoseEvent).filter(DoseEvent.patient_id == p.id).delete(synchronize_session=False)
    db.query(Prescription).filter(Prescription.patient_id == p.id).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == p.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def thuoc_that(db):
    """Một thuốc thật bất kỳ trong danh mục — không quan tâm tên cụ thể."""
    return db.query(Drug).first()


def _item(thuoc, so_vien=1, gio=("08:00",)):
    return {"drug_id": thuoc.id, "ten_thuoc": thuoc.ten_thuoc, "lieu_dung": f"{so_vien} đơn vị",
            "so_vien_moi_lan": so_vien, "gio_nhac": list(gio)}


# ---------------------------------------------------------------------------
# Tạo phác đồ
# ---------------------------------------------------------------------------
def test_tao_moi_luon_o_draft_khong_sinh_lieu_nao(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])

    assert presc.status == "draft"
    assert liet_ke_phac_do(db, patient_id=benh_nhan.id) == [presc]
    assert db.query(DoseEvent).filter(DoseEvent.prescription_id == presc.id).count() == 0


def test_tao_lay_dang_thuoc_tu_danh_muc_khong_tin_trinh_duyet(db, benh_nhan, thuoc_that):
    """Trình duyệt gửi dang_thuoc sai lệch — backend phải ghi đè bằng danh mục."""
    item = _item(thuoc_that)
    item["dang_thuoc"] = "Thuốc tiêm giả mạo"  # cố tình sai

    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[item])

    assert presc.items[0]["dang_thuoc"] == thuoc_that.dang_thuoc


def test_benh_nhan_khong_ton_tai_bi_tu_choi(db, thuoc_that):
    with pytest.raises(KhongTimThayError):
        tao_phac_do(db, patient_id="khong-ton-tai-chac-chan", doctor_id="bs1", items=[_item(thuoc_that)])


def test_thuoc_khong_ton_tai_bi_tu_choi(db, benh_nhan):
    with pytest.raises(ViPhamNghiepVuError):
        tao_phac_do(
            db, patient_id=benh_nhan.id, doctor_id="bs1",
            items=[{"drug_id": "khong-ton-tai", "ten_thuoc": "x", "lieu_dung": "1v", "gio_nhac": ["08:00"]}],
        )


def test_don_rong_bi_tu_choi(db, benh_nhan):
    with pytest.raises(ViPhamNghiepVuError):
        tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[])


def test_bac_si_tu_go_thuoc_khong_co_trong_danh_muc_van_ke_duoc(db, benh_nhan):
    """drug_id rỗng vẫn hợp lệ — không chặn bác sĩ kê thuốc chưa vào danh mục,
    chỉ là liều đó sau này sẽ không xác minh được bằng ảnh."""
    presc = tao_phac_do(
        db, patient_id=benh_nhan.id, doctor_id="bs1",
        items=[{"ten_thuoc": "Thuốc lạ chưa có trong danh mục", "lieu_dung": "1v", "gio_nhac": ["08:00"]}],
    )

    assert presc.items[0]["drug_id"] == ""


# ---------------------------------------------------------------------------
# Duyệt (ADR-0010, BR-1.1, BR-1.5)
# ---------------------------------------------------------------------------
def test_duyet_sinh_lieu_va_ghi_lai_ai_duyet(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(
        db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)], duration_days=2
    )

    da_duyet, so_lieu = duyet_phac_do(db, presc.id, doctor_id="bs_duyet")

    assert da_duyet.status == "active"
    assert da_duyet.approved_by == "bs_duyet"  # BR-1.5
    assert da_duyet.approved_at is not None
    assert so_lieu == 2


def test_duyet_lai_phac_do_da_duyet_bao_409(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])
    duyet_phac_do(db, presc.id, doctor_id="bs1")

    with pytest.raises(TrangThaiKhongHopLeError):
        duyet_phac_do(db, presc.id, doctor_id="bs1")


def test_duyet_khong_tao_lieu_trung_khi_goi_lai(db, benh_nhan, thuoc_that):
    """BR-2.3: idempotent. Không gọi trực tiếp duyệt 2 lần (đã bị chặn 409) mà
    kiểm tra tầng dưới — sinh_dose_event không nhân đôi nếu lỡ được gọi lại."""
    from backend.services.scheduling import sinh_dose_event

    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)], duration_days=1)
    duyet_phac_do(db, presc.id, doctor_id="bs1")

    sinh_dose_event(db, presc)  # gọi thẳng lần 2, mô phỏng lỗi tầng trên
    db.commit()

    con_lai = db.query(DoseEvent).filter(DoseEvent.prescription_id == presc.id).count()
    assert con_lai == 1


def test_duyet_lai_khong_dung_den_lieu_da_dong(db, benh_nhan, thuoc_that):
    """Liều TAKEN là lịch sử y tế — sinh lại lịch không được viết đè (BR-1.3)."""
    from backend.services.scheduling import sinh_dose_event

    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)], duration_days=1)
    duyet_phac_do(db, presc.id, doctor_id="bs1")

    lieu = db.query(DoseEvent).filter(DoseEvent.prescription_id == presc.id).first()
    lieu.status = "TAKEN"
    db.commit()
    lieu_id = lieu.id

    sinh_dose_event(db, presc)
    db.commit()

    van_con = db.get(DoseEvent, lieu_id)
    assert van_con is not None, "liều đã TAKEN không được xoá khi sinh lại"
    assert van_con.status == "TAKEN"


# ---------------------------------------------------------------------------
# Từ chối
# ---------------------------------------------------------------------------
def test_tu_choi_khong_sinh_lieu_nao(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])

    da_tu_choi = tu_choi_phac_do(db, presc.id, doctor_id="bs1")

    assert da_tu_choi.status == "rejected"
    assert db.query(DoseEvent).filter(DoseEvent.prescription_id == presc.id).count() == 0


def test_khong_tu_choi_duoc_phac_do_da_duyet(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])
    duyet_phac_do(db, presc.id, doctor_id="bs1")

    with pytest.raises(TrangThaiKhongHopLeError):
        tu_choi_phac_do(db, presc.id, doctor_id="bs1")


# ---------------------------------------------------------------------------
# Dừng phác đồ (BR-1.4)
# ---------------------------------------------------------------------------
def test_dung_phac_do_huy_lieu_pending_chua_toi_han(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)], duration_days=3)
    duyet_phac_do(db, presc.id, doctor_id="bs1")

    da_dung, so_huy = dung_phac_do(db, presc.id, doctor_id="bs1")

    assert da_dung.status == "stopped"
    assert so_huy == 3
    trang_thai = {d.status for d in db.query(DoseEvent).filter(DoseEvent.prescription_id == presc.id)}
    assert trang_thai == {"CANCELLED"}


def test_khong_dung_duoc_phac_do_chua_duyet(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])

    with pytest.raises(TrangThaiKhongHopLeError):
        dung_phac_do(db, presc.id, doctor_id="bs1")


# ---------------------------------------------------------------------------
# Tra cứu
# ---------------------------------------------------------------------------
def test_lay_phac_do_khong_ton_tai_bao_404(db):
    with pytest.raises(KhongTimThayError):
        lay_phac_do(db, "khong-ton-tai-chac-chan")


def test_liet_ke_loc_theo_trang_thai(db, benh_nhan, thuoc_that):
    """Hàng đợi duyệt = gọi với status='draft'."""
    draft = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])
    active = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])
    duyet_phac_do(db, active.id, doctor_id="bs1")

    hang_doi = liet_ke_phac_do(db, patient_id=benh_nhan.id, status="draft")

    assert [p.id for p in hang_doi] == [draft.id]
