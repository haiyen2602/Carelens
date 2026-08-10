"""Rao can TAM cho /api/v1/chat (chatbot-rag-design.md muc 10 #10) - xac
nhan bang request THAT (khong qua fixture `client` da tu gan header dung),
chung minh dependency require_internal_secret THAT SU chan duoc, khong chi
ton tai trong code ma chua bao gio duoc goi that."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.agents.orchestrator import default_safety_check  # noqa: E402
from src.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from src.api.security import INTERNAL_SECRET_HEADER  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.main import app  # noqa: E402


@pytest_asyncio.fixture
async def unauthorized_client():
    """Client KHONG gan header X-Internal-Secret - ngược lai voi fixture
    `client` dung chung o conftest.py (co gan san header dung)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_missing_header_is_rejected_with_401(unauthorized_client):
    response = await unauthorized_client.post(
        "/api/v1/chat", json={"patient_id": "p1", "message": "test"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wrong_header_value_is_rejected_with_401(unauthorized_client):
    response = await unauthorized_client.post(
        "/api/v1/chat",
        json={"patient_id": "p1", "message": "test"},
        headers={INTERNAL_SECRET_HEADER: "definitely-not-the-real-secret"},
    )
    assert response.status_code == 401


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_correct_header_value_is_not_rejected_by_the_gate(unauthorized_client):
    """Khong assert 200 (endpoint that co the tra loi khac vi ly do khac) -
    chi assert KHONG PHAI 401, tuc rao can tam da cho qua dung, loi (neu co)
    la o tang khac. Fake toan bo ChatServices - test rao can bao mat KHONG
    duoc goi OpenAI that (giu dung nguyen tac cost-consciousness xuyen suot
    du an, xem tests/test_chat_routes.py). Dinh tuyen sang today_schedule
    (khong DB vector/lexical search 14k+ chunk) - test nay chi can biet rao
    can bao mat cho qua, khong can di het pipeline drug_info."""
    app.dependency_overrides[get_chat_services] = lambda: ChatServices(
        classify_intent=lambda u: ("today_schedule", 0.95),
        classify_dose=lambda u: ("TAKEN", 0.95),
        generate_answer=lambda u, r: "fake",
        classify_severity=lambda t: None,
        embed_query=lambda t: [0.0] * 1536,
        safety_check=default_safety_check,
    )

    settings = get_settings()
    response = await unauthorized_client.post(
        "/api/v1/chat",
        json={"patient_id": "p1", "message": "test"},
        headers={INTERNAL_SECRET_HEADER: settings.internal_auth_secret},
    )
    assert response.status_code != 401
