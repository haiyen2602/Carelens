"""Vong 2 (chatbot-rag-design.md muc 14, muc 10 #10) - get_current_patient_id()
la 1 CHO NOI DUY NHAT de doc patient_id cua nguoi dang goi. Definition of
done: moi cho tung doc patient_id tu body gio goi qua ham nay; test xac nhan
doi implementation cua ham KHONG can sua gi o noi goi (dung DB that + override
LLM services, giong pattern test_chat_routes.py, khong mock ham dang test)."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

import src.api.chat_routes as chat_routes  # noqa: E402
from src.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from src.api.security import get_current_patient_id  # noqa: E402
from src.db.base import SessionLocal, engine  # noqa: E402
from src.db.models import AuditLog  # noqa: E402
from src.main import app  # noqa: E402
from src.models.schemas import ConversationChatRequest  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def test_default_implementation_reads_from_request_body():
    """Hanh vi HIEN TAI (giu nguyen, khong doi ngay) - doc thang tu body."""
    req = ConversationChatRequest(patient_id="patient-abc", message="hello")
    assert get_current_patient_id(req) == "patient-abc"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_swapping_implementation_changes_behavior_without_touching_call_sites(client, monkeypatch):
    """DoD chinh: monkeypatch DUNG ten `get_current_patient_id` da import vao
    chat_routes.py (khong sua 1 dong nao trong chat_routes.py) - request gui
    patient_id="original-from-body", nhung implementation moi luon tra ve 1
    patient_id KHAC ("swapped-by-new-impl") - AuditLog phai duoc ghi duoi
    patient_id MOI, chung minh chat_routes.py hoan toan khong con doc thang
    request.patient_id o dau ca, chi di qua ham nay."""
    swapped_id = f"swapped-by-new-impl-{uuid.uuid4().hex[:8]}"
    original_id_in_body = f"original-from-body-{uuid.uuid4().hex[:8]}"

    monkeypatch.setattr(chat_routes, "get_current_patient_id", lambda request: swapped_id)

    app.dependency_overrides[get_chat_services] = lambda: ChatServices(
        classify_intent=lambda u: ("drug_info", 0.95),
        classify_dose=lambda u: ("TAKEN", 0.95),
        generate_answer=lambda u, r: "Câu trả lời giả lập.",
        classify_severity=lambda combined_text: None,
        embed_query=lambda t: [0.0] * 1536,
        safety_check=__import__("src.agents.orchestrator", fromlist=["default_safety_check"]).default_safety_check,
    )

    response = await client.post(
        "/api/v1/chat",
        json={"patient_id": original_id_in_body, "message": "qzxjklmwvbpfgh_swap_test_1234"},
    )
    assert response.status_code == 200

    db = SessionLocal()
    try:
        swapped_rows = db.execute(select(AuditLog).where(AuditLog.patient_id == swapped_id)).scalars().all()
        original_rows = db.execute(
            select(AuditLog).where(AuditLog.patient_id == original_id_in_body)
        ).scalars().all()

        assert len(swapped_rows) == 1, (
            "AuditLog phai duoc ghi duoi patient_id MOI tra ve boi implementation da doi - "
            "chung minh chat_routes.py chi doc patient_id qua get_current_patient_id(), "
            "khong con doc thang request.patient_id o dau"
        )
        assert len(original_rows) == 0, (
            "KHONG duoc con dau vet cua patient_id goc trong body - neu co nghia la van "
            "con 1 cho nao do doc thang request.patient_id, bo qua get_current_patient_id()"
        )
    finally:
        db.query(AuditLog).filter(AuditLog.patient_id == swapped_id).delete(synchronize_session=False)
        db.commit()
        db.close()