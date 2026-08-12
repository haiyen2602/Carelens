"""Rate limiter theo `patient_id` (vong 2, chatbot-rag-design.md muc 12.4) -
KHONG theo IP, vi nhieu benh nhan co the chung 1 mang nha/benh vien (rate
limit theo IP se chan nham nhieu nguoi dung hop le cung mang).

Sliding-window log don gian, luu trong memory (KHONG dung Redis/queue rieng -
dung quy mo hien tai cua du an, giong tinh than "khong them dependency moi
neu chua can" da ap dung cho lua chon APScheduler o muc 13). Chi phu hop
single-process deployment - neu sau nay scale nhieu instance, can chuyen
sang store dung chung (Redis) de dem dung across-process, ghi lai o day
lam TODO cho nguoi doc sau.

Vuot nguong -> HTTPException 429 (thong bao lich su), KHONG phai loi 500."""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from backend.api.security import CurrentUser, get_current_patient_id, get_current_user
from backend.config import get_settings
from backend.models.schemas import ConversationChatRequest

RATE_LIMIT_MESSAGE = "Bạn đang gửi tin nhắn quá nhanh, vui lòng thử lại sau ít phút."


class SlidingWindowRateLimiter:
    """`clock` injectable (mac dinh `time.monotonic`) - de test duoc gia lap
    thoi gian ma khong can `sleep()` that (cung tinh than da dung cho
    escalation reminder o muc 13)."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._requests_by_key: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        """Raise HTTPException(429) neu `key` (patient_id) da vuot
        `max_requests` trong `window_seconds` gan nhat. KHONG raise (ghi
        nhan request nay) neu con trong nguong."""
        now = self._clock()
        cutoff = now - self._window_seconds
        timestamps = self._requests_by_key.setdefault(key, [])

        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= self._max_requests:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=RATE_LIMIT_MESSAGE)

        timestamps.append(now)


_default_limiter: SlidingWindowRateLimiter | None = None


def _get_default_limiter() -> SlidingWindowRateLimiter:
    """Lazy singleton - doc settings luc GOI DAU TIEN (khong phai luc import
    module), de test co the doi settings truoc khi limiter duoc tao."""
    global _default_limiter
    if _default_limiter is None:
        settings = get_settings()
        _default_limiter = SlidingWindowRateLimiter(
            max_requests=settings.rate_limit_max_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
    return _default_limiter


def reset_default_limiter_for_tests() -> None:
    """CHI dung trong test - xoa singleton de test sau khong bi anh huong
    boi state cua test truoc (nhieu test co the dung chung patient_id)."""
    global _default_limiter
    _default_limiter = None


async def rate_limit_check(
    request: ConversationChatRequest, current_user: CurrentUser = Depends(get_current_user)
) -> None:
    """FastAPI dependency - dat trong `dependencies=[...]` cua route. Nhan
    `request` (Pydantic model) lam tham so - FastAPI se merge voi tham so
    `request` cua route handler chinh, KHONG parse body 2 lan. TASK-010:
    them `current_user` (Depends(get_current_user)) - FastAPI cache ket qua
    dependency theo request nen get_current_user() chi chay 1 lan du duoc
    khai bao o ca day va o route handler chinh (chat_routes.py)."""
    patient_id = get_current_patient_id(request, current_user)
    _get_default_limiter().check(patient_id)
