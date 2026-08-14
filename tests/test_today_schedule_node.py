"""Vong 3, muc 5 (chatbot-rag-design.md muc 10 #26/#27, viet lai hoan toan tu
Phase 6) - build_today_schedule_node(): chi loc HOM NAY, loc theo buoi, format
lai + ghep thoi_diem_dung. Can Postgres that."""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.conversation_nodes import NO_SCHEDULE_TODAY_MESSAGE, build_today_schedule_node  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import DoseEvent, Prescription  # noqa: E402

VN_TZ = timezone(timedelta(hours=7))


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _make_prescription(db, patient_id, items):
    presc = Prescription(
        patient_id=patient_id,
        doctor_id="doc-1",
        status="approved",
        items=items,
        start_date="2026-08-01",
        duration_days=30,
    )
    db.add(presc)
    db.commit()
    return presc


def _make_dose_event(db, presc, patient_id, scheduled_at, status, expected_items):
    dose = DoseEvent(
        prescription_id=presc.id,
        patient_id=patient_id,
        scheduled_at=scheduled_at,
        window_start=scheduled_at,
        window_end=scheduled_at,
        status=status,
        expected_items=expected_items,
    )
    db.add(dose)
    db.commit()
    return dose


def _cleanup(db, patient_id):
    db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
    db.query(Prescription).filter(Prescription.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_only_lists_dose_events_scheduled_today_not_yesterday():
    """Vong 3 sua bug: ban truoc tra ve TOAN BO lich su, khong loc ngay."""
    db = SessionLocal()
    patient_id = f"test-sched-{uuid.uuid4().hex[:8]}"
    try:
        presc = _make_prescription(db, patient_id, [])
        today_8h = datetime.now(VN_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
        yesterday_8h = today_8h - timedelta(days=1)
        _make_dose_event(db, presc, patient_id, today_8h, "PENDING", [{"drug_id": "d1", "ten_thuoc": "Panadol"}])
        _make_dose_event(
            db, presc, patient_id, yesterday_8h, "PENDING", [{"drug_id": "d2", "ten_thuoc": "Thuốc Hôm Qua"}]
        )

        node = build_today_schedule_node(db)
        result = await node({"patient_id": patient_id, "intent": "today_schedule", "utterance": "hôm nay uống thuốc gì", "trace": []})

        assert "Panadol" in result["response"]
        assert "Thuốc Hôm Qua" not in result["response"], "khong duoc lo lich cua NGAY KHAC"
        assert result["trace"][-1]["dose_event_count"] == 1
    finally:
        _cleanup(db, patient_id)


@pytest.mark.asyncio
async def test_no_events_gives_explicit_message_not_empty_string():
    db = SessionLocal()
    patient_id = f"test-sched-empty-{uuid.uuid4().hex[:8]}"
    try:
        node = build_today_schedule_node(db)
        result = await node({"patient_id": patient_id, "intent": "today_schedule", "utterance": "x", "trace": []})
        assert result["response"] == NO_SCHEDULE_TODAY_MESSAGE
        assert result["trace"][-1]["dose_event_count"] == 0
    finally:
        db.close()


@pytest.mark.asyncio
async def test_timezone_shows_the_real_vn_hour_not_shifted_7_hours():
    """Muc 5.5 - case timezone bat buoc: xac nhan scheduled_at hien thi
    dung gio VN that (khong lech 7 tieng, dung y bug goc muc 5.1)."""
    db = SessionLocal()
    patient_id = f"test-sched-tz-{uuid.uuid4().hex[:8]}"
    try:
        presc = _make_prescription(db, patient_id, [])
        today_8h_vn = datetime.now(VN_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
        _make_dose_event(db, presc, patient_id, today_8h_vn, "TAKEN", [{"drug_id": "d1", "ten_thuoc": "Panadol"}])

        node = build_today_schedule_node(db)
        result = await node({"patient_id": patient_id, "intent": "today_schedule", "utterance": "hôm nay uống thuốc gì", "trace": []})

        assert "8 giờ" in result["response"], f"phai hien dung 8 gio VN, khong phai lech: {result['response']!r}"
        assert "15 giờ" not in result["response"], "dau hieu bug lech UTC/VN cu (8h VN = 15h neu bi tinh nham UTC)"
        assert "Buổi sáng" in result["response"]
    finally:
        _cleanup(db, patient_id)


@pytest.mark.asyncio
async def test_asking_for_a_specific_buoi_only_returns_that_buoi():
    """Muc 5.3/5.5 - hoi "buổi sáng" chi tra buoi sang, khong lan buoi khac."""
    db = SessionLocal()
    patient_id = f"test-sched-buoi-{uuid.uuid4().hex[:8]}"
    try:
        presc = _make_prescription(
            db,
            patient_id,
            [
                {"drug_id": "d1", "ten_thuoc": "Panadol", "thoi_diem_dung": "trước bữa sáng"},
                {"drug_id": "d2", "ten_thuoc": "Vitamin C", "thoi_diem_dung": "sau bữa tối"},
            ],
        )
        now = datetime.now(VN_TZ)
        morning = now.replace(hour=8, minute=0, second=0, microsecond=0)
        evening = now.replace(hour=20, minute=0, second=0, microsecond=0)
        _make_dose_event(db, presc, patient_id, morning, "PENDING", [{"drug_id": "d1", "ten_thuoc": "Panadol"}])
        _make_dose_event(db, presc, patient_id, evening, "PENDING", [{"drug_id": "d2", "ten_thuoc": "Vitamin C"}])

        node = build_today_schedule_node(db)
        result = await node(
            {"patient_id": patient_id, "intent": "today_schedule", "utterance": "buổi sáng tôi cần uống thuốc gì", "trace": []}
        )

        assert "Panadol" in result["response"]
        assert "Vitamin C" not in result["response"], "khong duoc lan buoi toi vao khi chi hoi buoi sang"
        assert result["trace"][-1]["requested_buoi"] == "sang"
    finally:
        _cleanup(db, patient_id)


@pytest.mark.asyncio
async def test_same_hour_same_thoi_diem_dung_merges_into_one_sentence():
    """Muc 5.4/5.5 - nhieu thuoc cung gio, CUNG thoi_diem_dung -> gop 1 cau."""
    db = SessionLocal()
    patient_id = f"test-sched-merge-{uuid.uuid4().hex[:8]}"
    try:
        presc = _make_prescription(
            db,
            patient_id,
            [
                {"drug_id": "d1", "ten_thuoc": "Panadol 500mg", "thoi_diem_dung": "trước bữa ăn sáng"},
                {"drug_id": "d2", "ten_thuoc": "Vitamin C 500mg", "thoi_diem_dung": "trước bữa ăn sáng"},
            ],
        )
        morning = datetime.now(VN_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
        _make_dose_event(
            db,
            presc,
            patient_id,
            morning,
            "PENDING",
            [{"drug_id": "d1", "ten_thuoc": "Panadol 500mg"}, {"drug_id": "d2", "ten_thuoc": "Vitamin C 500mg"}],
        )

        node = build_today_schedule_node(db)
        result = await node(
            {"patient_id": patient_id, "intent": "today_schedule", "utterance": "buổi sáng tôi cần uống thuốc gì", "trace": []}
        )

        response = result["response"]
        assert "Panadol 500mg, Vitamin C 500mg" in response or "Vitamin C 500mg, Panadol 500mg" in response
        assert response.count("trước bữa ăn sáng") == 1, "phai gop 1 cau, khong lap lai thoi_diem_dung cho tung thuoc"
    finally:
        _cleanup(db, patient_id)


@pytest.mark.asyncio
async def test_same_hour_different_thoi_diem_dung_lists_separately():
    """Muc 5.4/5.5 - nhieu thuoc cung gio, KHAC thoi_diem_dung -> liet rieng tung dong."""
    db = SessionLocal()
    patient_id = f"test-sched-split-{uuid.uuid4().hex[:8]}"
    try:
        presc = _make_prescription(
            db,
            patient_id,
            [
                {"drug_id": "d1", "ten_thuoc": "Panadol 500mg", "thoi_diem_dung": "trước bữa ăn sáng"},
                {"drug_id": "d2", "ten_thuoc": "Vitamin C 500mg", "thoi_diem_dung": "sau bữa ăn sáng"},
            ],
        )
        morning = datetime.now(VN_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
        _make_dose_event(
            db,
            presc,
            patient_id,
            morning,
            "PENDING",
            [{"drug_id": "d1", "ten_thuoc": "Panadol 500mg"}, {"drug_id": "d2", "ten_thuoc": "Vitamin C 500mg"}],
        )

        node = build_today_schedule_node(db)
        result = await node(
            {"patient_id": patient_id, "intent": "today_schedule", "utterance": "buổi sáng tôi cần uống thuốc gì", "trace": []}
        )

        response = result["response"]
        assert "- Panadol 500mg, trước bữa ăn sáng." in response
        assert "- Vitamin C 500mg, sau bữa ăn sáng." in response
    finally:
        _cleanup(db, patient_id)


@pytest.mark.asyncio
async def test_missing_thoi_diem_dung_does_not_show_dangling_text():
    """Muc 5.4/5.5 - thuoc KHONG co thoi_diem_dung trong don -> bo han phan
    do cho thuoc do, khong hien cho trong/cut nghia."""
    db = SessionLocal()
    patient_id = f"test-sched-missing-{uuid.uuid4().hex[:8]}"
    try:
        # KHONG co thoi_diem_dung trong item don thuoc.
        presc = _make_prescription(db, patient_id, [{"drug_id": "d1", "ten_thuoc": "Panadol 500mg"}])
        morning = datetime.now(VN_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
        _make_dose_event(db, presc, patient_id, morning, "PENDING", [{"drug_id": "d1", "ten_thuoc": "Panadol 500mg"}])

        node = build_today_schedule_node(db)
        result = await node(
            {"patient_id": patient_id, "intent": "today_schedule", "utterance": "buổi sáng tôi cần uống thuốc gì", "trace": []}
        )

        response = result["response"]
        assert "- Panadol 500mg." in response
        assert "None" not in response
        assert ", ." not in response
    finally:
        _cleanup(db, patient_id)


@pytest.mark.asyncio
async def test_full_day_format_matches_pm_example_shape():
    """Muc 5.4 - format ca ngay dung 4 thanh phan: header ngay thang, "Buổi
    X, H giờ bạn cần uống:", ten thuoc rut gon, trang thai (đã/chưa uống)."""
    db = SessionLocal()
    patient_id = f"test-sched-fullday-{uuid.uuid4().hex[:8]}"
    try:
        presc = _make_prescription(db, patient_id, [])
        morning = datetime.now(VN_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
        _make_dose_event(
            db, presc, patient_id, morning, "TAKEN", [{"drug_id": "d1", "ten_thuoc": "Solufemo 100mg Hataphar 20 ỐNG"}]
        )

        node = build_today_schedule_node(db)
        result = await node({"patient_id": patient_id, "intent": "today_schedule", "utterance": "hôm nay uống thuốc gì", "trace": []})

        response = result["response"]
        assert response.startswith("Dạ, hôm nay, ngày")
        assert "Buổi sáng, 8 giờ bạn cần uống:" in response
        assert "Solufemo 100mg" in response
        assert "Hataphar" not in response, "ten rut gon phai bo hang san xuat"
        assert "20 ỐNG" not in response, "ten rut gon phai bo quy cach dong goi"
        assert "(đã uống)" in response
    finally:
        _cleanup(db, patient_id)
