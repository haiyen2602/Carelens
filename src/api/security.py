"""Rao can TAM cho endpoint cham vao du lieu benh nhan, cho toi khi auth-api
that co (chatbot-rag-design.md muc 10 #10 - RUI RO BAO MAT CHAN PRODUCTION).

KHONG PHAI auth that - khong co khai niem user/role, khong biet request tu
ai, chi biet co dung 1 chuoi bi mat (shared secret) hay khong. Muc dich DUY
NHAT: chan truy cap tu NGOAI pham vi thu nghiem noi bo (Architect, mentor,
BTC) trong luc auth-api chua co timeline - khong phai giai phap phan quyen
cuoi cung.

XOA dependency nay khoi route NGAY khi auth-api (JWT that, api-contracts.md
§1) duoc xay - day la rao can tam, gan vao 1 diem duy nhat (route) de de
xoa, khong rai rac nhieu noi."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.config import get_settings

INTERNAL_SECRET_HEADER = "X-Internal-Secret"


async def require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias=INTERNAL_SECRET_HEADER),
) -> None:
    """FastAPI dependency - chan request thieu hoac sai header
    `X-Internal-Secret` (gia tri dung dat qua env var `INTERNAL_AUTH_SECRET`,
    KHONG hardcode gia tri that trong code - xem src/config.py). FAIL-CLOSED
    co y: neu secret chua duoc cau hinh (van con gia tri mac dinh ro rang la
    khong that), request van bi tu choi trong moi truong khong khop, khong
    am tham cho qua - phong ve ky thuat dang tin hon viec dua vao moi nguoi
    lien quan deu nho dung chinh sach da ghi trong tai lieu."""
    settings = get_settings()
    if x_internal_secret is None or x_internal_secret != settings.internal_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Internal-Secret header (temp auth gate - chatbot-rag-design.md mục 10 #10)",
        )
