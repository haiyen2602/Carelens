"""Phase 5b - nhanh 'Xac nhan lieu' (CLASSIFY -> SEVERITY -> LEVEL) bo sung
sau khi phat hien kickoff prompt Phase 5 liet thieu nhanh nay (chi co
drug_info). 3 nhom test:

  1. CLASSIFY (thuan, khong DB): confidence < 0.7 -> hoi lai, khong doan.
  2. SEVERITY (can Postgres that): dung dung 2 chunk cong_dung+tac_dung_phu
     CUA DUNG thuoc trong dose_event, khong dung rag_results cua nhanh khac.
  3. LEVEL (thuan, khong DB): 3 nhanh hanh dong + test do thoi gian THAT
     chung minh escalate family/doctor chay SONG SONG (khong xep hang).
"""

import asyncio
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.dose_confirmation_nodes import (  # noqa: E402
    ASK_AGAIN_MESSAGE,
    HIGH_ACTION,
    LOW_ACTION,
    LOW_ACTION_RESPONSE,
    MEDIUM_ACTION,
    MEDIUM_ACTION_RESPONSE,
    TAKEN_RESPONSE,
    build_classify_node,
    build_level_action_node,
    build_severity_node,
)
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import DoseEvent, DrugChunk, Prescription  # noqa: E402
from backend.services.drug_knowledge.v2_agent import SAFE_DEFAULT_SEVERITY, SeveritySource  # noqa: E402
from backend.services.escalation import MISSED_DOSE_OVERLAY_MESSAGE, SIDE_EFFECT_OVERLAY_MESSAGE  # noqa: E402

# ---------------------------------------------------------------------------
# Nhom 1 - CLASSIFY node, thuan, khong can DB.
# ---------------------------------------------------------------------------


def _base_state(**overrides) -> dict:
    state = {"patient_id": "p1", "dose_event_id": "dose-1", "utterance": "tôi quên uống thuốc sáng nay", "trace": []}
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_classify_high_confidence_uses_label_directly():
    node = build_classify_node(classify_fn=lambda u: ("MISSED", 0.92))
    result = await node(_base_state())

    assert result["classification"] == "MISSED"
    assert result["classification_confidence"] == 0.92
    assert "response" not in result
    entry = result["trace"][-1]
    assert entry["raw_result"] == "MISSED"
    assert entry["result"] == "MISSED"
    assert entry["low_confidence"] is False


@pytest.mark.asyncio
async def test_classify_low_confidence_asks_again_instead_of_guessing():
    """Diem bat buoc: confidence < 0.7 -> KHONG dung nhan da doan duoc, phai
    hoi lai - dung ca cau vi du chinh trong chatbot-rag-design.md muc 8."""
    node = build_classify_node(classify_fn=lambda u: ("DELAYED", 0.55))
    result = await node(_base_state())

    assert result["classification"] is None, "confidence thap khong duoc dung nhan da doan"
    assert result["response"] == ASK_AGAIN_MESSAGE
    entry = result["trace"][-1]
    assert entry["low_confidence"] is True
    assert entry["raw_result"] == "DELAYED", "van phai audit duoc LLM thuc te doan gi, du he thong khong dung"
    assert entry["result"] is None


@pytest.mark.asyncio
async def test_classify_confidence_exactly_at_threshold_is_not_low_confidence():
    node = build_classify_node(classify_fn=lambda u: ("TAKEN", 0.7))
    result = await node(_base_state())
    assert result["classification"] == "TAKEN"
    assert "response" not in result


# ---------------------------------------------------------------------------
# Nhom 2 - SEVERITY node, can Postgres that (docker compose up -d db).
# ---------------------------------------------------------------------------


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


def _fake_embedding() -> list[float]:
    return [0.0] * 1536


def _v2_severity_source(_db, drug_id: str) -> SeveritySource:
    return SeveritySource(
        drug_id,
        "Thu\u1ed1c d\u00f9ng \u0111\u1ec3 h\u1ea1 s\u1ed1t, gi\u1ea3m \u0111au th\u00f4ng th\u01b0\u1eddng.\n\nC\u00f3 th\u1ec3 g\u00e2y bu\u1ed3n n\u00f4n nh\u1eb9.",
        SAFE_DEFAULT_SEVERITY,
        "REVIEW_REQUIRED",
        ("INDICATION", "ADVERSE_EFFECT"),
    )

@pytest.fixture
def severity_fixture():
    """1 benh nhan, 1 thuoc rieng (drug_id ngau nhien) co du 4 chunk, trong
    do muc_nghiem_trong (fallback) co dinh la 'Nhẹ' - de test invariant
    'khong ha' bang cach cho RAG tra ve cao hon."""
    if not _db_available():
        pytest.skip("Can Postgres that (docker compose up -d db)")

    db = SessionLocal()
    patient_id = f"test-severity-patient-{uuid.uuid4().hex[:8]}"
    drug_id = f"test-severity-drug-{uuid.uuid4().hex[:8]}"

    chunks = [
        DrugChunk(
            drug_id=drug_id,
            ten_thuoc="Thuốc Test Severity",
            danh_muc="Danh mục test",
            muc_nghiem_trong="Nhẹ",
            field_group=fg,
            noi_dung=noi_dung,
            noi_dung_unaccent=noi_dung,
            ten_thuoc_unaccent="thuoc test severity",
            embedding=_fake_embedding(),
        )
        for fg, noi_dung in [
            ("cong_dung", "Thuốc dùng để hạ sốt, giảm đau thông thường."),
            ("tac_dung_phu", "Có thể gây buồn nôn nhẹ, hiếm khi dị ứng nặng."),
            ("cach_dung", "Uống 1 viên mỗi 6 giờ."),  # KHONG duoc dua vao combined_text
            ("bao_quan", "Bảo quản nơi khô ráo."),
        ]
    ]
    db.add_all(chunks)

    presc = Prescription(
        patient_id=patient_id,
        doctor_id="doc-1",
        status="approved",
        items=[{"ten_thuoc": "Thuốc Test Severity", "drug_id": drug_id, "lieu_dung": "1 viên", "duong_dung": "Uống"}],
        start_date="2026-08-01",
        duration_days=7,
    )
    db.add(presc)
    db.commit()

    now = datetime.now(UTC)
    dose_event = DoseEvent(
        prescription_id=presc.id,
        patient_id=patient_id,
        scheduled_at=now,
        window_start=now,
        window_end=now,
        status="PENDING",
        expected_items=[{"drug_id": drug_id, "ten_thuoc": "Thuốc Test Severity", "so_vien": 1}],
    )
    db.add(dose_event)
    db.commit()

    yield {"patient_id": patient_id, "drug_id": drug_id, "dose_event_id": dose_event.id}

    db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
    db.query(Prescription).filter(Prescription.patient_id == patient_id).delete(synchronize_session=False)
    db.query(DrugChunk).filter(DrugChunk.drug_id == drug_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_severity_node_skips_when_classification_not_applicable(severity_fixture):
    db = SessionLocal()
    try:
        node = build_severity_node(db, classify_severity_fn=lambda text: "Nguy hiểm", source_fn=_v2_severity_source)
        state = _base_state(
            patient_id=severity_fixture["patient_id"],
            dose_event_id=severity_fixture["dose_event_id"],
            classification="TAKEN",
        )
        result = await node(state)
    finally:
        db.close()

    assert "severity" not in result
    entry = result["trace"][-1]
    assert entry["skipped"] is True


@pytest.mark.asyncio
async def test_severity_node_never_downgrades_below_rag_result(severity_fixture):
    """Invariant o muc node, khong chi ham thuan: fallback (muc_nghiem_trong)
    trong fixture la 'Nhẹ', nhung classify_severity_fn (RAG) tra ve
    'Nguy hiểm' -> ket qua cuoi PHAI la 'Nguy hiểm', khong duoc ha theo
    fallback thap hon."""
    db = SessionLocal()
    try:
        node = build_severity_node(db, classify_severity_fn=lambda text: "Nguy hiểm", source_fn=_v2_severity_source)
        state = _base_state(
            patient_id=severity_fixture["patient_id"],
            dose_event_id=severity_fixture["dose_event_id"],
            classification="MISSED",
        )
        result = await node(state)
    finally:
        db.close()

    assert result["severity"] == "Nguy hiểm"
    entry = result["trace"][-1]
    assert entry["fallback_severity"] == SAFE_DEFAULT_SEVERITY
    assert entry["rag_severity"] == "Nguy hiểm"
    assert entry["result"] == "Nguy hiểm"


@pytest.mark.asyncio
async def test_severity_node_combines_cong_dung_and_tac_dung_phu_only(severity_fixture):
    """Nguon RAG phai gom CA 2 chunk cong_dung + tac_dung_phu gop lai (quyet
    dinh 2026-08-08), va KHONG duoc lan noi dung chunk cach_dung/bao_quan vao
    - kiem tra bang spy ghi lai dung text nhan duoc."""
    captured: dict = {}

    def spy_classify(combined_text: str) -> str | None:
        captured["text"] = combined_text
        return None

    db = SessionLocal()
    try:
        node = build_severity_node(db, classify_severity_fn=spy_classify, source_fn=_v2_severity_source)
        state = _base_state(
            patient_id=severity_fixture["patient_id"],
            dose_event_id=severity_fixture["dose_event_id"],
            classification="SIDE_EFFECT",
        )
        await node(state)
    finally:
        db.close()

    assert "hạ sốt" in captured["text"], "thieu noi dung chunk cong_dung"
    assert "buồn nôn" in captured["text"], "thieu noi dung chunk tac_dung_phu"
    assert "6 giờ" not in captured["text"], "khong duoc lan noi dung chunk cach_dung vao severity"
    assert "khô ráo" not in captured["text"], "khong duoc lan noi dung chunk bao_quan vao severity"


@pytest.mark.asyncio
async def test_severity_node_uses_dose_event_drug_not_rag_results_from_other_branch(severity_fixture):
    """2 nhanh (drug_info va dose_confirmation) doc lap - neu state con
    rag_results cua 1 cau hoi thuoc chung KHONG lien quan (vd tu 1 luot hoi
    truoc do trong cung phien), SEVERITY van phai dung dung thuoc cua
    dose_event dang xu ly, khong bi nham lan qua rag_results."""
    from backend.services.retrieval import DrugInfoResult

    unrelated_result = DrugInfoResult(
        drug_id="drug-hoan-toan-khac",
        ten_thuoc="Thuốc Khác",
        field_group="cong_dung",
        noi_dung="không liên quan",
        danh_muc="x",
        muc_nghiem_trong="Nguy hiểm",
        source="cong_dung — Thuốc Khác",
        vector_score=0.9,
        lexical_score=None,
        rrf_score=0.02,
        rank=1,
    )

    def spy_classify(combined_text: str) -> str | None:
        return None

    db = SessionLocal()
    try:
        node = build_severity_node(db, classify_severity_fn=spy_classify, source_fn=_v2_severity_source)
        state = _base_state(
            patient_id=severity_fixture["patient_id"],
            dose_event_id=severity_fixture["dose_event_id"],
            classification="MISSED",
            rag_results=[unrelated_result],
        )
        result = await node(state)
    finally:
        db.close()

    entry = result["trace"][-1]
    assert entry["drug_id"] == severity_fixture["drug_id"], (
        "SEVERITY dung nham drug_id tu rag_results cua nhanh khac thay vi dose_event"
    )
    assert entry["drug_id"] != "drug-hoan-toan-khac"


# ---------------------------------------------------------------------------
# Nhom 3 - LEVEL node, thuan, khong can DB. escalate_fn injectable.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_level_taken_logs_only_no_escalation():
    calls: list = []

    async def spy_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append(target)

    node = build_level_action_node(escalate_fn=spy_escalate)
    result = await node(_base_state(classification="TAKEN", severity=None))

    assert calls == []
    entry = result["trace"][-1]
    assert entry["action"] == "log_only"
    assert result["response"], (
        "TAKEN khong duoc tra ve response rong - phat hien 2026-08-08 qua 1 lan chay that: "
        "benh nhan bao 'da uong roi' ma nhan ve im lang tuyet doi, khong phan biet duoc voi app loi"
    )
    assert result["response"] == TAKEN_RESPONSE


@pytest.mark.asyncio
async def test_level_nhe_logs_and_monitors_no_escalation():
    calls: list = []

    async def spy_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append(target)

    node = build_level_action_node(escalate_fn=spy_escalate)
    result = await node(_base_state(classification="MISSED", severity="Nhẹ"))

    assert calls == []
    entry = result["trace"][-1]
    assert entry["action"] == LOW_ACTION
    assert result["response"] == LOW_ACTION_RESPONSE, "Nhẹ khong duoc de trong response - cung 1 lo hong voi TAKEN"


@pytest.mark.asyncio
async def test_level_trung_binh_escalates_family_and_doctor():
    calls: list = []

    async def spy_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append((target, urgent))

    node = build_level_action_node(escalate_fn=spy_escalate)
    result = await node(_base_state(classification="MISSED", severity="Trung bình"))

    assert set(t for t, _ in calls) == {"family", "doctor"}
    assert all(urgent is False for _, urgent in calls)
    entry = result["trace"][-1]
    assert entry["action"] == MEDIUM_ACTION
    assert set(entry["escalated_to"]) == {"family", "doctor"}
    # Phat hien 2026-08-08 qua 1 lan chay that: ban truoc day assert
    # "response" not in result o day - dung, nhung khong ai hoi nguoc lai
    # "vay benh nhan thay gi" - hoa ra la KHONG THAY GI CA (chuoi rong).
    # Danh dau lai dung invariant MOI: Trung binh PHAI co response (khac
    # overlay cap cuu Nguy hiem).
    assert result["response"] == MEDIUM_ACTION_RESPONSE
    assert result["response"] != MISSED_DOSE_OVERLAY_MESSAGE, "Trung binh khong duoc dung chung cau voi Nguy hiem"


@pytest.mark.asyncio
async def test_level_nguy_hiem_escalates_urgent_and_sets_overlay_response():
    calls: list = []

    async def spy_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append((target, urgent))

    node = build_level_action_node(escalate_fn=spy_escalate)
    result = await node(_base_state(classification="MISSED", severity="Nguy hiểm"))

    assert set(t for t, _ in calls) == {"family", "doctor"}
    assert all(urgent is True for _, urgent in calls)
    entry = result["trace"][-1]
    assert entry["action"] == HIGH_ACTION
    assert result["response"] == MISSED_DOSE_OVERLAY_MESSAGE, "classification=MISSED -> trigger=missed_dose"


@pytest.mark.asyncio
async def test_level_nguy_hiem_side_effect_uses_side_effect_overlay_not_missed_dose():
    """Vong 2 (chatbot-rag-design.md muc 7.1) - classification=SIDE_EFFECT +
    severity=Nguy hiem PHAI dung SIDE_EFFECT_OVERLAY_MESSAGE, khac han nhanh
    MISSED (test truoc do) du ca 2 cung urgent=True - truoc vong 2 ca 2
    duong dung chung 1 HIGH_OVERLAY_MESSAGE, gio phai tach dung theo trigger."""
    async def spy_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        return None

    node = build_level_action_node(escalate_fn=spy_escalate)
    result = await node(_base_state(classification="SIDE_EFFECT", severity="Nguy hiểm"))

    entry = result["trace"][-1]
    assert entry["action"] == HIGH_ACTION
    assert result["response"] == SIDE_EFFECT_OVERLAY_MESSAGE
    assert result["response"] != MISSED_DOSE_OVERLAY_MESSAGE


@pytest.mark.asyncio
async def test_level_partial_escalation_failure_is_visible_in_trace_not_hidden():
    """Code review 2026-08-08: cung invariant voi orchestrator - 1 kenh loi
    khong duoc bien mat khoi trace, phai hien ro kenh nao/vi sao."""

    async def family_fails(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        if target == "family":
            raise RuntimeError("push family that bai (mo phong)")

    node = build_level_action_node(escalate_fn=family_fails)
    result = await node(_base_state(classification="MISSED", severity="Nguy hiểm"))

    entry = result["trace"][-1]
    assert entry["escalated_to"] == ["doctor"], "doctor thanh cong khong duoc bi an di"
    assert "family" in entry["escalation_failed"]


@pytest.mark.asyncio
async def test_level_no_severity_and_not_taken_takes_no_action():
    calls: list = []

    async def spy_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append(target)

    node = build_level_action_node(escalate_fn=spy_escalate)
    # vd: CLASSIFY confidence thap -> classification=None, severity chua chay
    result = await node(_base_state(classification=None, severity=None))

    assert calls == []
    entry = result["trace"][-1]
    assert entry["action"] == "none"


@pytest.mark.asyncio
async def test_escalation_to_family_and_doctor_runs_in_parallel_not_sequential():
    """Diem bat buoc thu 3 cua Phase 5b: do THOI GIAN THAT (khong doan) de
    chung minh escalate family/doctor chay SONG SONG (BR-3.5 "khong xep hang
    cho nguoi than xu ly truoc"), khong phai goi lan luot. Neu chay tuan tu,
    2 lan delay 0.3s se cong don thanh ~0.6s; neu song song, tong thoi gian
    phai gan bang 1 lan delay (~0.3s), khong phai 2 lan.

    Day cung la co so uoc luong kha nang dat SLA < 2 phut (business-rules.md
    §3, HIGH) - mo phong o day (escalate_fn gia lap delay 0.3s cho moi kenh),
    KHONG phai do tren ha tang push that (chi la tin hieu kien truc dung
    huong, khong phai benchmark production)."""
    delay_s = 0.3

    async def slow_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        await asyncio.sleep(delay_s)

    node = build_level_action_node(escalate_fn=slow_escalate)

    t0 = time.monotonic()
    result = await node(_base_state(classification="MISSED", severity="Nguy hiểm"))
    wall_clock_elapsed_s = time.monotonic() - t0

    assert wall_clock_elapsed_s < delay_s * 1.8, (
        f"escalate family/doctor co ve chay TUAN TU (mat {wall_clock_elapsed_s:.3f}s cho 2 lan delay "
        f"{delay_s}s), khong phai song song qua asyncio.gather"
    )

    entry = result["trace"][-1]
    assert entry["duration_ms"] < 2 * 60 * 1000, "vuot qua SLA 2 phut cho muc Nguy hiem (business-rules.md §3)"
    assert entry["parallel"] is True
