"""Vong 3, muc 7 (chatbot-rag-design.md muc 10 #26) - e2e qua /api/v1/chat
that (DB that, LLM fake qua dependency override) - xac nhan wiring THAT
trong chat_routes.py, khong chi logic don le."""

import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import ChatMessage  # noqa: E402
from backend.main import app  # noqa: E402

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
        "classify_intent": lambda u: ("greeting", 0.95),
        "classify_dose": lambda u: ("TAKEN", 0.95),
        "generate_answer": lambda u, r: f"Câu trả lời giả lập cho: {u}",
        "classify_severity": lambda combined_text: None,
        "embed_query": lambda t: _UNRELATED_EMBEDDING,
        "safety_check": None,
    }
    defaults.update(fakes)
    from backend.agents.orchestrator import default_safety_check

    if defaults["safety_check"] is None:
        async def _clean(utterance: str):
            from backend.services.safety import SafetyFlag

            return SafetyFlag(is_redflag=False, matched_group=None, matched_keyword=None, source="keyword")

        defaults["safety_check"] = _clean

    app.dependency_overrides[get_chat_services] = lambda: ChatServices(**defaults)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _cleanup(patient_id):
    db = SessionLocal()
    db.query(ChatMessage).filter(ChatMessage.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_chat_turn_saves_both_patient_and_assistant_messages(client):
    patient_id = f"test-chathist-e2e-{uuid.uuid4().hex[:8]}"
    _override_services()
    try:
        resp = await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": "xin chào"})
        assert resp.status_code == 200

        history_resp = await client.post("/api/v1/chat/history", json={"patient_id": patient_id})
        assert history_resp.status_code == 200
        messages = history_resp.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "patient"
        assert messages[0]["content"] == "xin chào"
        assert messages[1]["role"] == "assistant"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_hide_history_endpoint_clears_display_not_audit(client):
    patient_id = f"test-chathist-e2e-{uuid.uuid4().hex[:8]}"
    _override_services()
    try:
        await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": "xin chào"})

        hide_resp = await client.post("/api/v1/chat/history/hide", json={"patient_id": patient_id})
        assert hide_resp.status_code == 200
        assert hide_resp.json()["hidden_count"] == 2

        history_resp = await client.post("/api/v1/chat/history", json={"patient_id": patient_id})
        assert history_resp.json()["messages"] == []

        # Idempotent - goi lai lan 2 khong loi.
        hide_resp2 = await client.post("/api/v1/chat/history/hide", json={"patient_id": patient_id})
        assert hide_resp2.json()["hidden_count"] == 0
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_recent_context_is_threaded_into_intent_classification(client):
    """Muc 7.2 - xac nhan THAT cua so 15 phut duoc ghep vao utterance truoc
    khi goi classify_intent (khong chi logic thuan, day la wiring THAT qua
    chat_routes.py -> build_intent_classification_node(db=db))."""
    patient_id = f"test-chathist-e2e-{uuid.uuid4().hex[:8]}"
    received_utterances = []

    def recording_classify_intent(u: str):
        received_utterances.append(u)
        return ("greeting", 0.95)

    _override_services(classify_intent=recording_classify_intent)
    try:
        await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": "câu đầu tiên"})
        await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": "câu thứ hai"})

        assert len(received_utterances) == 2
        # Luot 1: chua co lich su gi truoc do -> utterance KHONG bi ghep prefix.
        assert received_utterances[0] == "câu đầu tiên"
        # Luot 2: da co 2 tin nhan tu luot 1 (patient + assistant) trong 15
        # phut gan day -> utterance PHAI duoc ghep them ngu canh.
        assert "Ngữ cảnh hội thoại gần đây" in received_utterances[1]
        assert "câu đầu tiên" in received_utterances[1]
        assert received_utterances[1].endswith("Câu hỏi hiện tại: câu thứ hai")
    finally:
        _cleanup(patient_id)
