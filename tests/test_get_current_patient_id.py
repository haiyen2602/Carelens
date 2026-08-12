"""Vong 2 (chatbot-rag-design.md muc 14, muc 10 #10) - get_current_patient_id()
la 1 CHO NOI DUY NHAT de doc patient_id cua nguoi dang goi. TASK-010 (auth-api
that): ham nay gio nhan them CurrentUser (JWT da xac thuc) - role=patient bi
khoa vao patient_id cua chinh JWT (bo qua body); role khac (doctor/caregiver/
admin) van tin request.patient_id trong body nhu truoc (chua co kiem tra lien
ket day du - xem TODO trong security.py va tasks/TASK-010-auth-api.md)."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

import backend.api.chat_routes as chat_routes  # noqa: E402
from backend.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from backend.api.security import CurrentUser, get_current_patient_id  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import AuditLog  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.schemas import ConversationChatRequest  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def test_caregiver_reads_from_request_body():
    """Role != patient (goi ho benh nhan) - van tin request.patient_id
    trong body, giu hanh vi cu (chua co kiem tra lien ket, TODO)."""
    req = ConversationChatRequest(patient_id="patient-abc", message="hello")
    caller = CurrentUser(id="caregiver-1", role="caregiver", patient_id=None, doctor_id=None)
    assert get_current_patient_id(req, caller) == "patient-abc"


def test_patient_role_ignores_body_and_uses_own_patient_id_from_token():
    """DoD chinh cua TASK-010: 1 benh nhan tu goi (role=patient) KHONG the
    gia mao patient_id cua nguoi khac qua body - ham nay phai luon tra ve
    patient_id cua chinh JWT, du body ghi gi di nua."""
    req = ConversationChatRequest(patient_id="someone-elses-id", message="hello")
    caller = CurrentUser(id="usr-patient-1", role="patient", patient_id="my-own-patient-id", doctor_id=None)
    assert get_current_patient_id(req, caller) == "my-own-patient-id"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_swapping_implementation_changes_behavior_without_touching_call_sites(client, monkeypatch):
    """DoD: monkeypatch DUNG ten `get_current_patient_id` da import vao
    chat_routes.py - request gui patient_id="original-from-body", nhung
    implementation moi luon tra ve 1 patient_id KHAC ("swapped-by-new-impl")
    - AuditLog phai duoc ghi duoi patient_id MOI, chung minh chat_routes.py
    hoan toan khong con doc thang request.patient_id o dau ca, chi di qua
    ham nay."""
    swapped_id = f"swapped-by-new-impl-{uuid.uuid4().hex[:8]}"
    original_id_in_body = f"original-from-body-{uuid.uuid4().hex[:8]}"

    monkeypatch.setattr(chat_routes, "get_current_patient_id", lambda request, current_user: swapped_id)

    app.dependency_overrides[get_chat_services] = lambda: ChatServices(
        classify_intent=lambda u: ("drug_info", 0.95),
        classify_dose=lambda u: ("TAKEN", 0.95),
        generate_answer=lambda u, r: "Câu trả lời giả lập.",
        classify_severity=lambda combined_text: None,
        embed_query=lambda t: [0.0] * 1536,
        safety_check=__import__("backend.agents.orchestrator", fromlist=["default_safety_check"]).default_safety_check,
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


@pytest.mark.asyncio
async def test_patient_role_end_to_end_ignores_body_patient_id(client, monkeypatch):
    """End-to-end qua /api/v1/chat that (khong monkeypatch get_current_patient_id)
    - client tu JWT role=patient, body co patient_id KHAC - AuditLog phai
    ghi duoi patient_id cua JWT, khong phai body."""
    from backend.api.security import get_current_user

    token_patient_id = f"jwt-patient-{uuid.uuid4().hex[:8]}"
    body_patient_id = f"body-patient-{uuid.uuid4().hex[:8]}"

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="usr-e2e-patient", role="patient", patient_id=token_patient_id, doctor_id=None
    )
    app.dependency_overrides[get_chat_services] = lambda: ChatServices(
        classify_intent=lambda u: ("today_schedule", 0.95),
        classify_dose=lambda u: ("TAKEN", 0.95),
        generate_answer=lambda u, r: "fake",
        classify_severity=lambda t: None,
        embed_query=lambda t: [0.0] * 1536,
        safety_check=__import__("backend.agents.orchestrator", fromlist=["default_safety_check"]).default_safety_check,
    )

    response = await client.post(
        "/api/v1/chat", json={"patient_id": body_patient_id, "message": "hôm nay tôi uống thuốc gì"}
    )
    assert response.status_code == 200

    db = SessionLocal()
    try:
        token_rows = db.execute(select(AuditLog).where(AuditLog.patient_id == token_patient_id)).scalars().all()
        body_rows = db.execute(select(AuditLog).where(AuditLog.patient_id == body_patient_id)).scalars().all()
        assert len(token_rows) == 1
        assert len(body_rows) == 0
    finally:
        db.query(AuditLog).filter(AuditLog.patient_id == token_patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()
