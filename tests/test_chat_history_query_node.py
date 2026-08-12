"""Vong 3, muc 7.3(a) - build_chat_history_query_node() (backend/agents/
nodes/conversation_nodes.py). Can Postgres that (doc chat_messages that)."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.conversation_nodes import build_chat_history_query_node  # noqa: E402
from backend.agents.tools.chat_history_tool import save_chat_message  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import ChatMessage  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _state(intent, patient_id):
    return {"patient_id": patient_id, "dose_event_id": None, "utterance": "test", "trace": [], "intent": intent}


@pytest.mark.asyncio
async def test_skips_when_intent_is_not_chat_history_query():
    db = SessionLocal()
    node = build_chat_history_query_node(db)
    result = await node(_state("drug_info", "p1"))
    assert result["trace"][-1]["skipped"] is True
    db.close()


@pytest.mark.asyncio
async def test_recaps_recent_patient_messages():
    db = SessionLocal()
    patient_id = f"test-histquery-{uuid.uuid4().hex[:8]}"
    try:
        save_chat_message(db, patient_id, "patient", "cefixim dùng sao")
        save_chat_message(db, patient_id, "assistant", "trả lời giả lập")
        save_chat_message(db, patient_id, "patient", "daflavon dùng sao")

        node = build_chat_history_query_node(db)
        result = await node(_state("chat_history_query", patient_id))

        assert "cefixim dùng sao" in result["response"]
        assert "daflavon dùng sao" in result["response"]
        assert result["trace"][-1]["step"] == "chat_history_query"
        assert result["trace"][-1]["message_count"] == 2
    finally:
        db.query(ChatMessage).filter(ChatMessage.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_no_history_gives_fallback_message():
    db = SessionLocal()
    patient_id = f"test-histquery-empty-{uuid.uuid4().hex[:8]}"
    node = build_chat_history_query_node(db)
    result = await node(_state("chat_history_query", patient_id))
    assert "chưa thấy lịch sử" in result["response"]
    db.close()
