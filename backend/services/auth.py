"""TASK-010 (api-contracts.md muc 1, auth-api) - hash mat khau + tao/giai ma
JWT. Tach rieng khoi backend/api/security.py (dependency FastAPI, doc header)
va backend/api/auth_routes.py (route) - file nay CHI la logic thuan, khong
dung FastAPI/DB, de test/tai su dung de dang (dung pattern da ap dung cho cac
service khac trong backend/services/)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenError(Exception):
    """Raise khi JWT thieu, sai chu ky, het han, hoac sai payload - ranh
    gioi ro rang de backend/api/security.py chi can bat 1 exception type roi
    map sang HTTP 401, khong phai doan tung loai loi cua thu vien jose."""


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _create_token(sub: str, role: str, expires_delta: timedelta, extra_claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + expires_delta,
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    sub: str, role: str, patient_id: str | None = None, doctor_id: str | None = None
) -> str:
    """`patient_id`/`doctor_id`: claim MO RONG ngoai `sub`+`role` ma
    api-contracts.md §1 quy dinh (contract khong cam them claim) - dung de
    get_current_patient_id() (backend/api/security.py) doc duoc patient_id
    cua chinh nguoi dang dang nhap ma KHONG can query lai DB tren moi request."""
    settings = get_settings()
    extra = {"patient_id": patient_id, "doctor_id": doctor_id}
    return _create_token(sub, role, timedelta(minutes=settings.access_token_expire_minutes), extra)


def create_refresh_token(sub: str, role: str) -> str:
    settings = get_settings()
    return _create_token(sub, role, timedelta(days=settings.refresh_token_expire_days), {"type": "refresh"})


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
