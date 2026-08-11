from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.api.security import INTERNAL_SECRET_HEADER
from backend.config import get_settings
from backend.main import app


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints. Gui san header cua rao
    can tam (X-Internal-Secret, xem backend/api/security.py) voi dung gia tri
    dang cau hinh trong settings hien tai - test luon "duoc uy quyen" du
    secret la gia tri mac dinh local dev hay 1 gia tri that duoc dat qua
    env var, khong can moi test tu them header rieng."""
    transport = ASGITransport(app=app)
    settings = get_settings()
    headers = {INTERNAL_SECRET_HEADER: settings.internal_auth_secret}
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
