"""Vong 2 (chatbot-rag-design.md muc 12.4) - rate limiter theo patient_id.
Phan 1: unit test SlidingWindowRateLimiter thuan (clock injectable, khong
can sleep() that). Phan 2: integration qua /api/v1/chat that (DB that, LLM
fake), xac nhan 429 + thong bao lich su, khong phai loi 500."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.api.rate_limit import RATE_LIMIT_MESSAGE, SlidingWindowRateLimiter, reset_default_limiter_for_tests  # noqa: E402


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_allows_requests_under_the_limit():
    clock = _FakeClock()
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.check("patient-a")  # khong raise


def test_blocks_the_request_that_exceeds_the_limit():
    clock = _FakeClock()
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.check("patient-a")

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("patient-a")
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == RATE_LIMIT_MESSAGE


def test_different_patients_have_independent_limits():
    clock = _FakeClock()
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60, clock=clock)
    limiter.check("patient-a")  # dung het quota cua patient-a

    limiter.check("patient-b")  # patient-b khong bi anh huong, khong raise


def test_old_requests_outside_window_are_forgotten():
    clock = _FakeClock()
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60, clock=clock)
    limiter.check("patient-a")

    with pytest.raises(HTTPException):
        limiter.check("patient-a")

    clock.advance(61)  # qua khoi window
    limiter.check("patient-a")  # khong raise - request cu da het han


# ---------------------------------------------------------------------------
# Integration - qua /api/v1/chat that (DB that, LLM fake)
# ---------------------------------------------------------------------------


def _db_available() -> bool:
    from backend.db.base import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.fixture(autouse=True)
def _reset_limiter_and_overrides():
    reset_default_limiter_for_tests()
    yield
    reset_default_limiter_for_tests()
    from backend.main import app

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_exceeding_rate_limit_returns_429_not_500(client, monkeypatch):
    from backend.api.chat_deps import ChatServices, get_chat_services
    from backend.config import get_settings
    from backend.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_max_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60.0)

    app.dependency_overrides[get_chat_services] = lambda: ChatServices(
        classify_intent=lambda u: ("drug_info", 0.95),
        classify_dose=lambda u: ("TAKEN", 0.95),
        generate_answer=lambda u, r: "Câu trả lời giả lập.",
        classify_severity=lambda combined_text: None,
        embed_query=lambda t: [0.0] * 1536,
        safety_check=__import__("backend.agents.orchestrator", fromlist=["default_safety_check"]).default_safety_check,
    )

    patient_id = f"test-ratelimit-{uuid.uuid4().hex[:8]}"
    payload = {"patient_id": patient_id, "message": "qzxjklmwvbpfgh_ratelimit_test"}

    r1 = await client.post("/api/v1/chat", json=payload)
    r2 = await client.post("/api/v1/chat", json=payload)
    r3 = await client.post("/api/v1/chat", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429, "cau thu 3 phai bi chan (nguong = 2/window)"
    assert r3.json()["detail"] == RATE_LIMIT_MESSAGE