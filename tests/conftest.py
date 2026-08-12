from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.api.security import INTERNAL_SECRET_HEADER
from backend.config import get_settings
from backend.main import app
from backend.services.auth import create_access_token

# TASK-010: JWT cua fixture `client` dung role=caregiver (KHONG phai
# patient) - vi get_current_patient_id() (backend/api/security.py) chi tin
# request.patient_id trong body cho role != patient (patient bi khoa vao
# patient_id cua chinh JWT). Cac test hien co (test_chat_routes.py,
# test_rate_limit.py, test_drug_confirmation_e2e.py...) deu tu sinh
# patient_id ngau nhien MOI test roi truyen qua body - can role duoc phep
# "goi ho benh nhan" de khong phai vi lai toan bo bo test nay (mint 1
# Account that/JWT rieng cho tung patient_id ngau nhien) trong pham vi
# TASK-010. Test rieng cho hanh vi role=patient xem test_get_current_patient_id.py.
_TEST_CALLER_ID = "test-caregiver-conftest"


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints. Gui san:
    - `X-Internal-Secret` (rao tam CON LAI cho escalation_routes.py - chua
      thuoc pham vi TASK-010, xem tasks/TASK-010-auth-api.md muc "Ghi chu").
    - `Authorization: Bearer <JWT>` (role=caregiver, TASK-010) cho
      /api/v1/chat va cac route dung get_current_user.
    Test nao can mo phong nguoi goi khac (role khac, thieu token...) tu tao
    client rieng (xem test_chat_security_gate.py)."""
    transport = ASGITransport(app=app)
    settings = get_settings()
    token = create_access_token(sub=_TEST_CALLER_ID, role="caregiver")
    headers = {
        INTERNAL_SECRET_HEADER: settings.internal_auth_secret,
        "Authorization": f"Bearer {token}",
    }
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
