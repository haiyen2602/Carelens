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


def token_revoked_by_password_change(
    payload: dict[str, Any], password_changed_at: datetime | None
) -> bool:
    """True neu token nay duoc phat TRUOC lan doi mat khau gan nhat cua chu
    tai khoan -> phai coi nhu het hieu luc.

    JWT la stateless: da phat ra thi khong "xoa" duoc tu xa. Cach thu hoi duy
    nhat ma khong can bang blacklist la so claim `iat` voi 1 moc trong DB
    (`account.password_changed_at`, migration 0018). Doi mat khau => moc tang
    len => moi token cu (ke ca refresh token han 30 ngay dang nam tren thiet
    bi khac) roi vao qua khu cua moc va bi tu choi.

    So sanh o do CHINH XAC TOI GIAY (int) co y: jose encode `iat` thanh
    integer epoch (cat phan le), nen token vua phat trong cung giay voi
    `password_changed_at` co the co iat NHO HON moc vai tram ms neu so bang
    float - dieu do se tu thu hoi luon token moi vua tra cho chinh nguoi vua
    doi mat khau.

    Thieu `iat` (token khong do _create_token o day sinh ra) -> FAIL-CLOSED,
    coi la da thu hoi: khong the chung minh token duoc phat sau moc."""
    if password_changed_at is None:
        return False
    if password_changed_at.tzinfo is None:
        password_changed_at = password_changed_at.replace(tzinfo=UTC)
    iat = payload.get("iat")
    if iat is None:
        return True
    return int(iat) < int(password_changed_at.timestamp())
