"""Kiểm chứng vòng đời phác đồ trên Postgres thật.

Cần DB có bảng `drug` đã nạp (python scripts/seed_drug_catalog.py) và bảng
`patient` tồn tại (python scripts/seed_photo_patients.py, hoặc tự tạo bệnh
nhân trong fixture — ở đây tự tạo để test không phụ thuộc script khác).

Không cần webcam, không cần mạng ngoài — chỉ SQL.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.config import get_settings
from backend.db.base import SessionLocal, engine
from backend.db.models import (
    DoseEvent,
    DoseOccurrence,
    MedicationPlan,
    Patient,
    Prescription,
    PrescriptionItem,
    ScheduleRule,
    ScheduleRuleCycle,
    ScheduleRuleTime,
)
from backend.services.drug_knowledge.v2_agent import get_v2_agent_knowledge_service
from backend.services.prescription import (
    KhongTimThayError,
    TrangThaiKhongHopLeError,
    ViPhamNghiepVuError,
    dung_phac_do,
    duyet_phac_do,
    lay_phac_do,
    liet_ke_phac_do,
    sua_phac_do,
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
    v2_item_ids = [row[0] for row in db.query(PrescriptionItem.id).filter(PrescriptionItem.patient_id == p.id).all()]
    plan_ids = [row[0] for row in db.query(MedicationPlan.id).filter(MedicationPlan.patient_id == p.id).all()]
    rule_ids = (
        [row[0] for row in db.query(ScheduleRule.id).filter(ScheduleRule.medication_plan_id.in_(plan_ids)).all()]
        if plan_ids
        else []
    )
    if rule_ids:
        db.query(ScheduleRuleTime).filter(ScheduleRuleTime.schedule_rule_id.in_(rule_ids)).delete(
            synchronize_session=False
        )
        db.query(ScheduleRuleCycle).filter(ScheduleRuleCycle.schedule_rule_id.in_(rule_ids)).delete(
            synchronize_session=False
        )
        db.query(ScheduleRule).filter(ScheduleRule.id.in_(rule_ids)).delete(synchronize_session=False)
    if v2_item_ids:
        db.query(PrescriptionItem).filter(PrescriptionItem.id.in_(v2_item_ids)).delete(synchronize_session=False)
    if plan_ids:
        db.query(MedicationPlan).filter(MedicationPlan.id.in_(plan_ids)).delete(synchronize_session=False)
    db.query(DoseOccurrence).filter(DoseOccurrence.patient_id == p.id).delete(synchronize_session=False)
    db.query(DoseEvent).filter(DoseEvent.patient_id == p.id).delete(synchronize_session=False)
    db.query(Prescription).filter(Prescription.patient_id == p.id).delete(synchronize_session=False)
    db.query(Patient).filter(Patient.id == p.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def thuoc_that(db):
    """Một thuốc thật bất kỳ trong danh mục — không quan tâm tên cụ thể."""
    del db
    return get_v2_agent_knowledge_service().catalog_items[0]


# "Ngày mai" tính động: sinh_dose_event() cố ý bỏ liều đã trôi qua giờ hẹn
# (xem generator.py), nên duyệt một phác đồ bắt đầu "hôm nay" mà giờ hẹn đã
# qua trong ngày sẽ sinh RA ÍT LIỀU HƠN mong đợi tuỳ giờ chạy test. Không phải
# lỗi của service — hardcode ngày cụ thể mới là lỗi ăn may lúc viết test.
NGAY_MAI = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()


def _item(thuoc, so_vien=1, gio=("08:00",)):
    return {"drug_id": thuoc.id, "ten_thuoc": thuoc.ten_thuoc, "lieu_dung": f"{so_vien} đơn vị",
            "so_vien_moi_lan": so_vien, "gio_nhac": list(gio)}


def _set_prescription_v2_mode(monkeypatch, mode: str) -> None:
    monkeypatch.setenv("PRESCRIPTION_V2_MODE", mode)
    get_settings.cache_clear()


def _restore_prescription_v2_mode() -> None:
    get_settings.cache_clear()


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


def test_thuoc_go_tay_khong_co_drug_id_bi_tu_choi(db, benh_nhan):
    """FB-14: danh mục là allowlist đóng. Trước 2026-08-20 `drug_id` rỗng vẫn
    kê được, nên gõ được tên bất kỳ — kể cả chất gây nghiện — vào đơn thuốc."""
    with pytest.raises(ViPhamNghiepVuError):
        tao_phac_do(
            db, patient_id=benh_nhan.id, doctor_id="bs1",
            items=[{"ten_thuoc": "Heroin", "lieu_dung": "1v", "gio_nhac": ["08:00"]}],
        )


def test_ten_thuoc_lay_tu_danh_muc_khong_lay_chu_bac_si_go(db, benh_nhan, thuoc_that):
    """FB-14, lỗ hổng thứ hai: chọn một thuốc hợp lệ rồi sửa lại ô tên thì
    `drug_id` vẫn trỏ thuốc cũ nhưng `ten_thuoc` mang chữ vừa gõ — và đó là
    tên bệnh nhân nhìn thấy. Danh mục phải thắng."""
    item = _item(thuoc_that)
    item["ten_thuoc"] = "Heroin"

    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[item])

    assert presc.items[0]["ten_thuoc"] == thuoc_that.ten_thuoc
    assert presc.items[0]["dang_thuoc"] == thuoc_that.dang_thuoc
    assert presc.items[0]["duong_dung"] == thuoc_that.duong_dung


def test_shadow_mode_writes_resolved_v2_sidecar_and_stops_intent(db, benh_nhan, thuoc_that, monkeypatch, caplog):
    _set_prescription_v2_mode(monkeypatch, "shadow")
    monkeypatch.setenv("DOSE_RUNTIME_MODE", "shadow")
    get_settings.cache_clear()
    try:
        caplog.set_level(logging.INFO, logger="backend.services.prescription.service")
        item = _item(thuoc_that, gio=("08:00", "20:00"))
        item.update({"doses_per_day": 2, "thoi_diem_dung": "Sau \u0103n"})
        presc = tao_phac_do(
            db,
            patient_id=benh_nhan.id,
            doctor_id="bs1",
            items=[item],
            duration_days=2,
            start_date=NGAY_MAI,
        )
        sidecar = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == presc.id).one()
        assert sidecar.drug_product_id is not None
        assert sidecar.status == "DRAFT"
        assert sidecar.end_date.isoformat() == (datetime.fromisoformat(NGAY_MAI) + timedelta(days=1)).date().isoformat()
        assert any(
            "prescription_v2_shadow" in record.getMessage()
            and "mismatch=False" in record.getMessage()
            and presc.id in record.getMessage()
            for record in caplog.records
        )

        duyet_phac_do(db, presc.id, doctor_id="bs_duyet")
        assert db.query(MedicationPlan).filter(MedicationPlan.prescription_item_id == sidecar.id).one().status == "ACTIVE"
        assert db.query(DoseOccurrence).filter(DoseOccurrence.prescription_item_id == sidecar.id).count() == 4

        da_dung, _ = dung_phac_do(db, presc.id, doctor_id="bs_duyet")
        assert da_dung.status == "stopped"
        assert db.query(MedicationPlan).filter(MedicationPlan.prescription_item_id == sidecar.id).one().status == "STOPPED"
        assert {row.status for row in db.query(DoseOccurrence).filter(DoseOccurrence.prescription_item_id == sidecar.id)} == {"CANCELLED"}
    finally:
        _restore_prescription_v2_mode()


# GO 2026-08-20 (FB-14): test_shadow_mode_keeps_unresolved_drug_in_review_required
# da bi xoa khoi day. No ke mot thuoc go tay (`drug_id` rong) roi assert sidecar
# V2 nam o REVIEW_REQUIRED - duong vao do gio bi chan han, xem
# test_thuoc_go_tay_khong_co_drug_id_bi_tu_choi o tren.
#
# Nhanh REVIEW_REQUIRED VAN CON THAT nhung khong con vao duoc tu tao_phac_do:
# lay_thuoc() mac dinh phan giai qua catalog V2 (xem drug_knowledge/__init__.py),
# nen mot drug_id da qua duoc cua allowlist thi cung luon resolve duoc sang
# drug_product. Trang thai do gio chi con y nghia voi du lieu cu/backfill.
#
# CHUA CO TEST THAY THE. Cho dung cho no la unit test cua
# services/scheduling/write_path.py::sync_prescription_schedule - goi thang voi
# mot item khong resolve duoc, khong di qua cua allowlist cua phac do.
# TODO(FB-14): bo sung test do.




def test_shadow_edit_supersedes_only_future_v2_occurrences(db, benh_nhan, thuoc_that, monkeypatch):
    _set_prescription_v2_mode(monkeypatch, "shadow")
    monkeypatch.setenv("DOSE_RUNTIME_MODE", "shadow")
    get_settings.cache_clear()
    try:
        original = _item(thuoc_that, gio=("08:00",))
        original["thoi_diem_dung"] = "Sau \u0103n"
        presc = tao_phac_do(
            db,
            patient_id=benh_nhan.id,
            doctor_id="bs1",
            items=[original],
            duration_days=1,
            start_date=NGAY_MAI,
        )
        duyet_phac_do(db, presc.id, doctor_id="bs_duyet")
        replacement = _item(thuoc_that, gio=("20:00",))
        replacement["thoi_diem_dung"] = "Sau \u0103n"

        sua_phac_do(db, presc.id, doctor_id="bs_duyet", items=[replacement])

        occurrences = db.query(DoseOccurrence).filter(DoseOccurrence.patient_id == benh_nhan.id).all()
        assert {occurrence.status for occurrence in occurrences} == {"CANCELLED", "SCHEDULED"}
        assert len({occurrence.generation_key for occurrence in occurrences}) == 2
    finally:
        _restore_prescription_v2_mode()


def test_legacy_mode_does_not_write_v2_sidecar(db, benh_nhan, thuoc_that, monkeypatch):
    _set_prescription_v2_mode(monkeypatch, "legacy")
    try:
        presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])
        assert db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == presc.id).count() == 0
    finally:
        _restore_prescription_v2_mode()


def test_shadow_approve_resyncs_legacy_created_prescription(db, benh_nhan, thuoc_that, monkeypatch):
    _set_prescription_v2_mode(monkeypatch, "legacy")
    try:
        item = _item(thuoc_that)
        item["thoi_diem_dung"] = "Sau \u0103n"
        presc = tao_phac_do(
            db,
            patient_id=benh_nhan.id,
            doctor_id="bs1",
            items=[item],
            duration_days=1,
            start_date=NGAY_MAI,
        )
        _set_prescription_v2_mode(monkeypatch, "shadow")
        duyet_phac_do(db, presc.id, doctor_id="bs_duyet")
        assert db.query(MedicationPlan).filter(MedicationPlan.patient_id == benh_nhan.id).one().status == "ACTIVE"
    finally:
        _restore_prescription_v2_mode()


def test_shadow_create_rolls_back_legacy_write_when_sidecar_fails(db, benh_nhan, thuoc_that, monkeypatch):
    _set_prescription_v2_mode(monkeypatch, "shadow")

    def fail_sync(*_args, **_kwargs):
        raise RuntimeError("sidecar write failure")

    monkeypatch.setattr("backend.services.prescription.service.sync_prescription_schedule", fail_sync)
    try:
        with pytest.raises(RuntimeError, match="sidecar write failure"):
            tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])
        assert db.query(Prescription).filter(Prescription.patient_id == benh_nhan.id).count() == 0
        assert db.query(PrescriptionItem).filter(PrescriptionItem.patient_id == benh_nhan.id).count() == 0
    finally:
        _restore_prescription_v2_mode()


def test_mutation_lock_blocks_a_second_postgres_session(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)])
    locker = SessionLocal()
    contender = SessionLocal()
    try:
        lay_phac_do(locker, presc.id, for_update=True)
        contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(OperationalError):
            lay_phac_do(contender, presc.id, for_update=True)
    finally:
        contender.rollback()
        contender.close()
        locker.rollback()
        locker.close()


def test_shadow_stop_cancels_future_v2_occurrence(db, benh_nhan, thuoc_that, monkeypatch):
    _set_prescription_v2_mode(monkeypatch, "shadow")
    try:
        item = _item(thuoc_that)
        item["thoi_diem_dung"] = "Sau \u0103n"
        presc = tao_phac_do(
            db,
            patient_id=benh_nhan.id,
            doctor_id="bs1",
            items=[item],
            duration_days=1,
            start_date=NGAY_MAI,
        )
        duyet_phac_do(db, presc.id, doctor_id="bs_duyet")
        sidecar = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == presc.id).one()
        plan = db.query(MedicationPlan).filter(MedicationPlan.prescription_item_id == sidecar.id).one()
        occurrence = DoseOccurrence(
                medication_plan_id=plan.id,
                prescription_item_id=sidecar.id,
                patient_id=benh_nhan.id,
                drug_product_id=sidecar.drug_product_id,
                legacy_drug_id=sidecar.legacy_drug_id,
                scheduled_at=datetime.now(UTC) + timedelta(days=1),
                generation_key=f"test-stop-conflict-{uuid.uuid4()}",
                status="SCHEDULED",
        )
        db.add(occurrence)
        db.commit()

        da_dung, _ = dung_phac_do(db, presc.id, doctor_id="bs_duyet")
        db.refresh(presc)
        assert da_dung.status == "stopped"
        assert presc.status == "stopped"
        assert db.query(DoseOccurrence).filter(DoseOccurrence.id == occurrence.id).one().status == "CANCELLED"
    finally:
        _restore_prescription_v2_mode()


# ---------------------------------------------------------------------------
# Duyệt (ADR-0010, BR-1.1, BR-1.5)
# ---------------------------------------------------------------------------
def test_duyet_sinh_lieu_va_ghi_lai_ai_duyet(db, benh_nhan, thuoc_that):
    presc = tao_phac_do(
        db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)],
        duration_days=2, start_date=NGAY_MAI,
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

    presc = tao_phac_do(
        db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)],
        duration_days=1, start_date=NGAY_MAI,
    )
    duyet_phac_do(db, presc.id, doctor_id="bs1")

    sinh_dose_event(db, presc)  # gọi thẳng lần 2, mô phỏng lỗi tầng trên
    db.commit()

    con_lai = db.query(DoseEvent).filter(DoseEvent.prescription_id == presc.id).count()
    assert con_lai == 1


def test_duyet_lai_khong_dung_den_lieu_da_dong(db, benh_nhan, thuoc_that):
    """Liều TAKEN là lịch sử y tế — sinh lại lịch không được viết đè (BR-1.3)."""
    from backend.services.scheduling import sinh_dose_event

    presc = tao_phac_do(
        db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)],
        duration_days=1, start_date=NGAY_MAI,
    )
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
    presc = tao_phac_do(
        db, patient_id=benh_nhan.id, doctor_id="bs1", items=[_item(thuoc_that)],
        duration_days=3, start_date=NGAY_MAI,
    )
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
