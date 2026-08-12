"""Vong 3, muc 6 - build_greeting_node() tra loi co dinh (khong LLM) khi
intent=="greeting", chi 1 truy van DB don gian de ca nhan hoa ten (#21).
Duong SKIP da co o tests/test_intent_self_guards.py, file nay chi test
duong CHAY THAT."""

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.agents.nodes.conversation_nodes import (  # noqa: E402
    GREETING_QUICK_REPLIES,
    GREETING_RESPONSE,
    build_greeting_node,
)
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Patient  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _state(intent, patient_id="p-khong-ton-tai"):
    return {"patient_id": patient_id, "dose_event_id": None, "utterance": "xin chao", "trace": [], "intent": intent}


@pytest.mark.asyncio
async def test_greeting_node_returns_fixed_response_when_no_patient_row():
    """patient_id khong khop dong Patient nao (vd du lieu test cu, hoac
    Patient.id chua co FK bat buoc voi patient_id dung noi khac - xem
    docstring class Patient) - fallback ve ban chao khong ten, khong loi."""
    db = SessionLocal()
    try:
        node = build_greeting_node(db)
        result = await node(_state("greeting"))

        assert result["response"] == GREETING_RESPONSE
        assert result["quick_replies"] == GREETING_QUICK_REPLIES
        assert result["trace"][-1]["step"] == "greeting"
        assert result["trace"][-1]["personalized"] is False
        assert "skipped" not in result["trace"][-1]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_greeting_node_personalizes_when_patient_row_exists():
    """#21 - Patient.full_name that (migration 0009) dung de ca nhan hoa
    cau chao khi co san."""
    db = SessionLocal()
    patient_id = f"test-greeting-{uuid4().hex[:8]}"
    try:
        db.add(Patient(id=patient_id, full_name="Nguyễn Thị Test"))
        db.commit()

        node = build_greeting_node(db)
        result = await node(_state("greeting", patient_id=patient_id))

        assert "Nguyễn Thị Test" in result["response"]
        assert result["response"] != GREETING_RESPONSE
        assert result["quick_replies"] == GREETING_QUICK_REPLIES
        assert result["trace"][-1]["personalized"] is True
    finally:
        db.query(Patient).filter(Patient.id == patient_id).delete()
        db.commit()
        db.close()
