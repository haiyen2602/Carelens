"""Vong 3, muc 7 (chatbot-rag-design.md muc 10 #26) - test cac ham thuan cua
chat_history_tool.py, can Postgres that (isolation theo patient_id, khong
mock)."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.tools.chat_history_tool import (  # noqa: E402
    get_chat_history_for_display,
    get_recent_context,
    hide_all_chat_messages,
    save_chat_message,
    search_chat_history,
)
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


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _cleanup(db, patient_id):
    db.query(ChatMessage).filter(ChatMessage.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()


def test_save_and_display_full_history(db):
    patient_id = f"test-chathist-{uuid.uuid4().hex[:8]}"
    try:
        save_chat_message(db, patient_id, "patient", "cefixim dùng sao")
        save_chat_message(db, patient_id, "assistant", "Cefixim uống 1 viên/lần")

        history = get_chat_history_for_display(db, patient_id)
        assert len(history) == 2
        assert history[0]["role"] == "patient"
        assert history[1]["role"] == "assistant"
        assert all(h["hidden"] is False for h in history)
    finally:
        _cleanup(db, patient_id)


def test_display_isolated_between_patients(db):
    """Cung nguyen tac isolation da ap dung xuyen suot personal_tools.py."""
    patient_a = f"test-chathist-a-{uuid.uuid4().hex[:8]}"
    patient_b = f"test-chathist-b-{uuid.uuid4().hex[:8]}"
    try:
        save_chat_message(db, patient_a, "patient", "câu hỏi của A")
        save_chat_message(db, patient_b, "patient", "câu hỏi của B")

        history_a = get_chat_history_for_display(db, patient_a)
        assert len(history_a) == 1
        assert history_a[0]["content"] == "câu hỏi của A"
    finally:
        _cleanup(db, patient_a)
        _cleanup(db, patient_b)


def test_hide_all_is_soft_delete_not_real_deletion(db):
    """#20 - "xoá đoạn chat" chỉ ẩn, không xoá thật - dòng vẫn còn trong DB
    (include_hidden=True vẫn đọc được), chỉ không xuất hiện ở display mặc định."""
    patient_id = f"test-chathist-{uuid.uuid4().hex[:8]}"
    try:
        save_chat_message(db, patient_id, "patient", "câu hỏi cũ")
        hidden_count = hide_all_chat_messages(db, patient_id)
        assert hidden_count == 1

        assert get_chat_history_for_display(db, patient_id) == []
        assert len(get_chat_history_for_display(db, patient_id, include_hidden=True)) == 1

        # Idempotent - goi lai lan 2 khong loi, tra ve 0 (khong con gi de an).
        assert hide_all_chat_messages(db, patient_id) == 0
    finally:
        _cleanup(db, patient_id)


def test_recent_context_excludes_messages_older_than_window(db):
    """Muc 7.2 - "Đã chốt: 15 phút" tuyệt đối, không phải đếm số tin nhắn."""
    patient_id = f"test-chathist-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    try:
        db.add(ChatMessage(patient_id=patient_id, role="patient", content="20 phút trước", created_at=now - timedelta(minutes=20)))
        db.add(ChatMessage(patient_id=patient_id, role="patient", content="5 phút trước", created_at=now - timedelta(minutes=5)))
        db.commit()

        context = get_recent_context(db, patient_id, now=now)
        contents = [c["content"] for c in context]
        assert "5 phút trước" in contents
        assert "20 phút trước" not in contents
    finally:
        _cleanup(db, patient_id)


def test_recent_context_excludes_hidden_messages(db):
    """Quyet dinh thiet ke: tin nhan da "xoa" (an) khong duoc ngam dung lam
    ngu canh nua - benh nhan xoa hop ly ky vong ca 2 y (khong hien + khong
    con anh huong cau tra loi sau)."""
    patient_id = f"test-chathist-{uuid.uuid4().hex[:8]}"
    try:
        save_chat_message(db, patient_id, "patient", "câu hỏi nhạy cảm")
        hide_all_chat_messages(db, patient_id)

        context = get_recent_context(db, patient_id)
        assert context == []
    finally:
        _cleanup(db, patient_id)


def test_search_chat_history_finds_substring_case_and_diacritic_sensitive(db):
    """Luu y: search_chat_history dung ILIKE (khong bo dau) - test dung dung
    dang co dau khop voi noi dung da luu, khong doi hanh vi ham de qua no."""
    patient_id = f"test-chathist-{uuid.uuid4().hex[:8]}"
    try:
        save_chat_message(db, patient_id, "patient", "cefixim dùng sao")
        save_chat_message(db, patient_id, "patient", "daflavon dùng sao")

        results = search_chat_history(db, patient_id, "cefixim")
        assert len(results) == 1
        assert "cefixim" in results[0]["content"]
    finally:
        _cleanup(db, patient_id)
