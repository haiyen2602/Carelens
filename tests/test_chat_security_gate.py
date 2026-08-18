"""TASK-010: /api/v1/chat gio doi hoi Authorization: Bearer <JWT> that
(get_current_user, backend/api/security.py) thay vi rao tam
X-Internal-Secret (require_internal_secret da bi go khoi route nay - xem
chat_routes.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.agents.orchestrator import default_safety_check  # noqa: E402
from backend.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import Account  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


@pytest_asyncio.fixture
async def unauthorized_client():
    """Client KHONG gan header Authorization - ngươc lai voi fixture
    `client` dung chung o conftest.py (co gan san Bearer JWT hop le)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_missing_authorization_header_is_rejected_with_401(unauthorized_client):
    response = await unauthorized_client.post(
        "/api/v1/chat", json={"patient_id": "p1", "message": "test"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_garbage_bearer_token_is_rejected_with_401(unauthorized_client):
    response = await unauthorized_client.post(
        "/api/v1/chat",
        json={"patient_id": "p1", "message": "test"},
        headers={"Authorization": "Bearer definitely-not-a-real-jwt"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_bearer_authorization_scheme_is_rejected_with_401(unauthorized_client):
    response = await unauthorized_client.post(
        "/api/v1/chat",
        json={"patient_id": "p1", "message": "test"},
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_valid_bearer_token_is_not_rejected_by_the_gate(unauthorized_client):
    """Khong assert 200 (endpoint that co the tra loi khac vi ly do khac) -
    chi assert KHONG PHAI 401, tuc rao can xac thuc cho qua dung, loi (neu
    co) la o tang khac. Fake toan bo ChatServices - test rao can bao mat
    KHONG duoc goi OpenAI that. Dinh tuyen sang today_schedule (khong DB
    vector/lexical search 14k+ chunk)."""
    app.dependency_overrides[get_chat_services] = lambda: ChatServices(
        classify_intent=lambda u: ("today_schedule", 0.95),
        classify_dose=lambda u: ("TAKEN", 0.95),
        generate_answer=lambda u, r: "fake",
        classify_severity=lambda t: None,
        embed_query=lambda t: [0.0] * 1536,
        safety_check=default_safety_check,
    )

    account_id = "test-caregiver-gate"
    db = SessionLocal()
    try:
        db.add(
            Account(
                id=account_id,
                full_name="Chat security test caregiver",
                email="test-caregiver-gate@example.local",
                password_hash="not-a-real-hash",
                role="caregiver",
                status="active",
            )
        )
        db.commit()
        token = create_access_token(sub=account_id, role="caregiver")
        response = await unauthorized_client.post(
            "/api/v1/chat",
            json={"patient_id": "p1", "message": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code != 401
    finally:
        db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
        db.commit()
        db.close()
