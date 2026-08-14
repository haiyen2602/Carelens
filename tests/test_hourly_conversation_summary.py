"""Vong 4, muc 5 - hourly summaries chi la history data, khong phai context chat."""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.conversation_nodes import build_chat_history_query_node  # noqa: E402
from backend.agents.tools.chat_history_tool import get_hourly_summaries_for_history  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import ChatMessage, HourlyConversationSummary  # noqa: E402
from backend.services.hourly_conversation_summary import (  # noqa: E402
    completed_hour_bucket,
    create_completed_hour_summaries,
)


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT to_regclass('public.hourly_conversation_summaries')")).scalar() is not None
    except OperationalError:
        return False


def test_completed_hour_bucket_uses_previous_utc_hour():
    assert completed_hour_bucket(datetime(2026, 8, 13, 10, 17, tzinfo=UTC)) == datetime(2026, 8, 13, 9, tzinfo=UTC)


@pytest.fixture
def hourly_summary_fixture():
    if not _db_available():
        pytest.skip("Can Postgres that da apply migration 0022 (alembic upgrade head)")

    patient_id = f"test-hourly-summary-{uuid.uuid4().hex[:8]}"
    # Bucket xa trong tuong lai de job test khong tao summary cho chat data
    # local co san cua benh nhan khac (job that dung phai quet MOI patient).
    now = datetime(2099, 1, 1, 10, 5, tzinfo=UTC)
    db = SessionLocal()
    db.add_all(
        [
            ChatMessage(patient_id=patient_id, role="patient", content="Tôi buồn nôn", created_at=now - timedelta(minutes=20)),
            ChatMessage(patient_id=patient_id, role="assistant", content="Bạn theo dõi thêm nhé", created_at=now - timedelta(minutes=18)),
            ChatMessage(patient_id=patient_id, role="patient", content="Tin nhắn giờ hiện tại", created_at=now - timedelta(minutes=2)),
        ]
    )
    db.commit()
    yield db, patient_id, now
    db.rollback()
    db.query(HourlyConversationSummary).filter(HourlyConversationSummary.patient_id == patient_id).delete(
        synchronize_session=False
    )
    db.query(ChatMessage).filter(ChatMessage.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_active_patient_gets_one_independent_summary_for_completed_hour(hourly_summary_fixture):
    db, patient_id, now = hourly_summary_fixture
    received_messages: list[list[dict]] = []

    def summarize(messages: list[dict]) -> str:
        received_messages.append(messages)
        return "Bệnh nhân báo buồn nôn; trợ lý đã hướng dẫn theo dõi."

    assert await create_completed_hour_summaries(db, summarize, now=now) == 1
    assert await create_completed_hour_summaries(db, summarize, now=now) == 0

    summaries = get_hourly_summaries_for_history(db, patient_id)
    assert len(summaries) == 1
    assert summaries[0]["message_count"] == 2
    assert "Tin nhắn giờ hiện tại" not in str(received_messages[0])


@pytest.mark.asyncio
async def test_inactive_hour_creates_no_summary_and_never_calls_llm(hourly_summary_fixture):
    db, _patient_id, now = hourly_summary_fixture
    called = False

    def summarize(_messages: list[dict]) -> str:
        nonlocal called
        called = True
        return "khong duoc goi"

    assert await create_completed_hour_summaries(db, summarize, now=now + timedelta(hours=3)) == 0
    assert called is False


@pytest.mark.asyncio
async def test_history_query_prefers_hourly_summary_over_raw_messages(hourly_summary_fixture):
    db, patient_id, now = hourly_summary_fixture
    db.add(
        HourlyConversationSummary(
            patient_id=patient_id,
            hour_bucket=completed_hour_bucket(now),
            summary_text="Bệnh nhân đã hỏi về triệu chứng buồn nôn.",
            message_count=2,
        )
    )
    db.commit()

    state = {"patient_id": patient_id, "utterance": "Trước đây tôi đã hỏi gì?", "intent": "chat_history_query", "trace": []}
    result = await build_chat_history_query_node(db)(state)

    assert "Bệnh nhân đã hỏi về triệu chứng buồn nôn." in result["response"]
    assert result["trace"][-1]["source"] == "hourly_summaries"
    assert result["trace"][-1]["summary_count"] == 1
