"""Phase 6 - POST /api/v1/chat end-to-end qua FastAPI TestClient. Dung DB
that (docker compose up -d db, da co du lieu that tu Phase 2-4) nhung FAKE
cac ham LLM/embedding qua `app.dependency_overrides[get_chat_services]`
(khong goi OpenAI that trong test - giu nguyen tinh cost-consciousness
xuyen suot du an).

Test bat buoc theo build-kickoff-prompt.md Phase 6: MOI nhanh ket thuc (ke
ca REFUSE, ke ca redflag HIGH) deu ghi du trace + audit log, khong co nhanh
nao bo sot."""

import random
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import AuditLog, DoseEvent, DrugChunk, Escalation, Prescription  # noqa: E402
from backend.main import app  # noqa: E402

# Vector "khong lien quan gi" that co y nghia - KHAC vector 0 (degenerate,
# cosine similarity voi vector 0 khong xac dinh/co the loi len sai qua
# nguong o driver/DB). 1 vector Gauss ngau nhien (seed co dinh) trong khong
# gian 1536 chieu se co cosine similarity gan 0 voi moi embedding that
# (phat hien 2026-08-08: dung [0.0]*1536 lam fake ban dau khien 5 chunk
# "trung" mot cach gia tao voi cau hoi vo nghia).
_UNRELATED_EMBEDDING = [random.Random(42).gauss(0, 1) for _ in range(1536)]


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _override_services(**fakes) -> None:
    defaults = {
        "classify_intent": lambda u: ("drug_info", 0.95),
        "classify_dose": lambda u: ("TAKEN", 0.95),
        "generate_answer": lambda u, r: "Câu trả lời giả lập.",
        "classify_severity": lambda combined_text: None,
        "embed_query": lambda t: _UNRELATED_EMBEDDING,
        "safety_check": None,  # gan default_safety_check that o duoi (keyword layer that, mien phi)
    }
    defaults.update(fakes)
    from backend.agents.orchestrator import default_safety_check

    if defaults["safety_check"] is None:
        defaults["safety_check"] = default_safety_check

    app.dependency_overrides[get_chat_services] = lambda: ChatServices(**defaults)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _latest_audit_log(patient_id: str) -> AuditLog:
    db = SessionLocal()
    try:
        return (
            db.execute(
                select(AuditLog).where(AuditLog.patient_id == patient_id).order_by(AuditLog.created_at.desc())
            )
            .scalars()
            .first()
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_drug_info_flow_returns_reply_and_sources_and_writes_audit_log(client):
    """Vong 2 (chatbot-rag-design.md muc 11): drug_info gio can 2 luot - luot
    1 hoi xac nhan danh tinh thuoc, luot 2 (xac nhan "co") moi tra loi that
    voi sources - khong con tra loi thang trong 1 luot nhu truoc."""
    patient_id = f"test-chat-druginfo-{uuid.uuid4().hex[:8]}"
    _override_services(classify_intent=lambda u: ("drug_info", 0.95))

    turn1 = await client.post(
        "/api/v1/chat",
        json={"patient_id": patient_id, "message": "Agiclovir 5% Agimexpharm dùng sao"},
    )
    assert turn1.status_code == 200
    body1 = turn1.json()
    assert "Agiclovir" in body1["reply"], "luot 1 phai hoi xac nhan, nhac lai ten thuoc tim duoc"
    assert body1["sources"] == [], "luot 1 chi hoi xac nhan, chua co sources"

    turn2 = await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": "có"})
    assert turn2.status_code == 200
    body2 = turn2.json()
    assert body2["reply"]
    assert len(body2["sources"]) > 0, "sau khi xac nhan, phai co it nhat 1 nguon"
    assert body2["safety_flag"] is False
    assert body2["classification"] is None, "drug_info khong co classification (chi dose_confirmation moi co)"

    audit = _latest_audit_log(patient_id)
    assert audit is not None, "phai ghi AuditLog cho luot xac nhan"
    steps = [e.get("step") for e in audit.trace]
    assert "drug_confirmation_reply" in steps
    assert "answer_generation" in steps
    assert audit.final_response == body2["reply"]


@pytest.mark.asyncio
async def test_drug_info_no_match_refuses_and_still_writes_audit_log(client):
    patient_id = f"test-chat-refuse-{uuid.uuid4().hex[:8]}"
    _override_services(classify_intent=lambda u: ("drug_info", 0.95))

    response = await client.post(
        # Chu y: KHONG dung tu tieng Viet that trong chuoi "vo nghia" nay (du
        # viet lien/thieu dau) - lan dau viet "..._khong_ton_tai_trong_du_
        # lieu_..." VAN khop lexical (pg_trgm) voi 50 chunk that vi cac tu
        # "khong/ton tai/trong/du lieu" la tu tieng Viet that dang ben trong.
        "/api/v1/chat",
        json={"patient_id": patient_id, "message": "qzxjklmwvbpfgh0000zzzzxxxxyyyywwww9999"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []

    audit = _latest_audit_log(patient_id)
    assert audit is not None, "nhanh khong tim duoc ung vien nao cung phai ghi AuditLog, khong duoc bo sot"
    steps = [e.get("step") for e in audit.trace]
    # Vong 4: fuzzy luon co top-5, nhung fallback khong co LLM selector phai
    # fail-closed. Ca hai result deu nghia la khong co candidate an toan de
    # hoi xac nhan, va deu tra NOT_FOUND_FINAL_MESSAGE.
    assert "drug_identity_resolution" in steps
    resolution_entry = next(e for e in audit.trace if e.get("step") == "drug_identity_resolution")
    assert resolution_entry.get("result") in {"no_candidates_at_all", "llm_no_safe_candidate"}


@pytest.mark.asyncio
async def test_today_schedule_flow_lists_dose_events_and_writes_audit_log(client):
    patient_id = f"test-chat-schedule-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        presc = Prescription(
            patient_id=patient_id, doctor_id="doc-1", status="approved", items=[],
            start_date="2026-08-01", duration_days=7,
        )
        db.add(presc)
        db.commit()
        now = datetime.now(UTC)
        dose = DoseEvent(
            prescription_id=presc.id, patient_id=patient_id, scheduled_at=now, window_start=now, window_end=now,
            status="PENDING", expected_items=[{"drug_id": "d1", "ten_thuoc": "Panadol Extra", "so_vien": 1}],
        )
        db.add(dose)
        db.commit()

        _override_services(classify_intent=lambda u: ("today_schedule", 0.9))
        response = await client.post(
            "/api/v1/chat", json={"patient_id": patient_id, "message": "hôm nay tôi uống thuốc gì"}
        )

        assert response.status_code == 200
        body = response.json()
        assert "Panadol Extra" in body["reply"]

        audit = _latest_audit_log(patient_id)
        assert audit is not None
        steps = [e.get("step") for e in audit.trace]
        assert "today_schedule" in steps
    finally:
        db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_dose_confirmation_low_confidence_sets_needs_clarification(client):
    patient_id = f"test-chat-clarify-{uuid.uuid4().hex[:8]}"
    _override_services(
        classify_intent=lambda u: ("dose_confirmation", 0.9),
        classify_dose=lambda u: ("MISSED", 0.4),  # duoi 0.7 -> hoi lai
    )

    response = await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": "ừm không biết nữa"})

    assert response.status_code == 200
    body = response.json()
    assert body["needs_clarification"] is True
    assert body["classification"] is None

    audit = _latest_audit_log(patient_id)
    assert audit is not None
    steps = [e.get("step") for e in audit.trace]
    assert "dose_classification" in steps


@pytest.mark.asyncio
async def test_dose_confirmation_missed_high_severity_sets_safety_flag_and_escalates(client):
    """severity=Nguy hiem tu SEVERITY node (KHONG phai tu safety_layer
    redflag) van phai lam FE hien overlay (safety_flag=True, BR-3.5) VA ghi
    Escalation - day la nguon HIGH thu 2, khac safety_layer. Can seed that 1
    Prescription+DoseEvent+DrugChunk de SEVERITY node phan giai duoc drug_id
    (khong thi combined_text rong, classify_severity_fn khong bao gio duoc
    goi, va ket qua se rot ve fallback "Trung bình" - da xay ra 1 lan luc
    viet test nay, khong phai bug o code that)."""
    patient_id = f"test-chat-severe-{uuid.uuid4().hex[:8]}"
    drug_id = f"test-chat-drug-{uuid.uuid4().hex[:8]}"

    db = SessionLocal()
    try:
        chunk = DrugChunk(
            drug_id=drug_id,
            ten_thuoc="Thuốc Tim Test",
            danh_muc="Danh mục test",
            muc_nghiem_trong="Nhẹ",
            field_group="cong_dung",
            noi_dung="Thuốc điều trị tim mạch.",
            noi_dung_unaccent="thuoc dieu tri tim mach",
            ten_thuoc_unaccent="thuoc tim test",
            embedding=[0.0] * 1536,
        )
        db.add(chunk)
        presc = Prescription(
            patient_id=patient_id, doctor_id="doc-1", status="approved",
            items=[{"ten_thuoc": "Thuốc Tim Test", "drug_id": drug_id}],
            start_date="2026-08-01", duration_days=7,
        )
        db.add(presc)
        db.commit()
        now = datetime.now(UTC)
        dose = DoseEvent(
            prescription_id=presc.id, patient_id=patient_id, scheduled_at=now, window_start=now, window_end=now,
            status="PENDING", expected_items=[{"drug_id": drug_id, "ten_thuoc": "Thuốc Tim Test", "so_vien": 1}],
        )
        db.add(dose)
        db.commit()
        dose_event_id = dose.id

        _override_services(
            classify_intent=lambda u: ("dose_confirmation", 0.95),
            classify_dose=lambda u: ("MISSED", 0.95),
            classify_severity=lambda combined_text: "Nguy hiểm",
        )

        response = await client.post(
            "/api/v1/chat",
            json={"patient_id": patient_id, "dose_id": dose_event_id, "message": "tôi quên uống thuốc tim sáng nay"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["severity"] == "HIGH"
        assert body["safety_flag"] is True, (
            "SEVERITY=Nguy hiem cung phai bat safety_flag cho FE, khong chi safety_layer"
        )

        rows = db.execute(select(Escalation).where(Escalation.patient_id == patient_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].severity == "HIGH"
        assert rows[0].trigger in ("missed_dose", "side_effect")
    finally:
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DrugChunk).filter(DrugChunk.drug_id == drug_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_safety_redflag_short_circuits_and_writes_audit_and_escalation(client):
    """Redflag tu khoa THAT (khong fake - safety.py keyword layer that, mien
    phi) phai cat ngang, tra ve overlay cap cuu, VA van ghi du AuditLog +
    Escalation - khong co nhanh nao (ke ca redflag) bo sot audit."""
    patient_id = f"test-chat-redflag-{uuid.uuid4().hex[:8]}"
    _override_services(classify_intent=lambda u: ("drug_info", 0.9))

    response = await client.post(
        "/api/v1/chat", json={"patient_id": patient_id, "message": "tôi thấy khó thở với đau ngực quá"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "HIGH"
    assert body["safety_flag"] is True
    assert "115" in body["reply"]

    audit = _latest_audit_log(patient_id)
    assert audit is not None, "redflag HIGH cung phai ghi AuditLog day du (build-kickoff-prompt.md Phase 6)"
    safety_entries = [e for e in audit.trace if e.get("step") == "safety_layer"]
    assert len(safety_entries) == 1
    assert safety_entries[0]["keyword_hit"] is True

    db = SessionLocal()
    try:
        rows = db.execute(select(Escalation).where(Escalation.patient_id == patient_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].trigger == "safety_redflag"
        assert set(rows[0].notified) == {"caregiver", "doctor"}
        for row in rows:
            db.delete(row)
        db.commit()
    finally:
        db.close()
