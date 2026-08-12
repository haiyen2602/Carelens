"""Vong 3 (phan hoi review - can test THAT qua DB, khong chi unit test voi
fake escalate_fn) - xac nhan _maybe_medium_acknowledge() (orchestrator.py)
thuc su ghi dung 1 dong Escalation qua build_db_escalate_fn(db) THAT, khong
chi goi 1 ham gia lap ghi log. Dung y "verify o dung choke-point" da ap
dung nhieu lan trong du an (escalate_fn optional, HNSW ef_search wiring)."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.orchestrator import run_conversation  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Escalation  # noqa: E402
from backend.services.escalation import build_db_escalate_fn  # noqa: E402
from backend.services.safety import SafetyFlag  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


async def _medium_self_harm_check(utterance: str) -> SafetyFlag:
    return SafetyFlag(
        is_redflag=False,
        matched_group=None,
        matched_keyword=None,
        source="llm",
        level="Trung bình",
        llm_category="self_harm",
        llm_reasoning="test that qua DB",
    )


async def _medium_wrong_drug_check(utterance: str) -> SafetyFlag:
    return SafetyFlag(
        is_redflag=False,
        matched_group=None,
        matched_keyword=None,
        source="llm",
        level="Trung bình",
        llm_category="wrong_drug",
        llm_reasoning="test that qua DB",
    )


async def _set_response_node(state: dict) -> dict:
    return {"response": "Câu trả lời bình thường.", "trace": [*state.get("trace", []), {"step": "x"}]}


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_medium_self_harm_writes_real_escalation_row_family_only():
    """Case self_harm THUOC pham vi escalate (a) - phai co 1 dong Escalation
    THAT, severity=MEDIUM, urgent tuong duong False, CHI notified=["caregiver"]
    (KHONG co "doctor" - dung chinh sach (b))."""
    patient_id = f"test-medium-escalate-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        escalate_fn = build_db_escalate_fn(db)
        result = await run_conversation(
            {"patient_id": patient_id, "dose_event_id": None, "utterance": "test", "trace": []},
            nodes=[_set_response_node],
            safety_check=_medium_self_harm_check,
            escalate_fn=escalate_fn,
        )
        assert "Capy đã ghi nhận" in result["response"]

        row = db.execute(select(Escalation).where(Escalation.patient_id == patient_id)).scalar_one_or_none()
        assert row is not None, "phai co dung 1 dong Escalation duoc ghi THAT vao Postgres"
        assert row.severity == "MEDIUM"
        assert row.notified == ["caregiver"], "CHI kenh family (caregiver) - khong duoc co 'doctor'"
        assert row.status == "OPEN"
    finally:
        db.close()
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_medium_wrong_drug_does_not_write_escalation_row_but_still_acknowledges():
    """Case wrong_drug KHONG thuoc pham vi escalate (a) - KHONG duoc co dong
    Escalation nao, nhung response VAN phai co cau ghi nhan (c, da sua bug
    gop nham dieu kien)."""
    patient_id = f"test-medium-escalate-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        escalate_fn = build_db_escalate_fn(db)
        result = await run_conversation(
            {"patient_id": patient_id, "dose_event_id": None, "utterance": "test", "trace": []},
            nodes=[_set_response_node],
            safety_check=_medium_wrong_drug_check,
            escalate_fn=escalate_fn,
        )
        assert "Capy đã ghi nhận" in result["response"]

        row = db.execute(select(Escalation).where(Escalation.patient_id == patient_id)).scalar_one_or_none()
        assert row is None, "wrong_drug khong thuoc pham vi escalate (a) - khong duoc ghi Escalation"
    finally:
        db.close()
        _cleanup(patient_id)
