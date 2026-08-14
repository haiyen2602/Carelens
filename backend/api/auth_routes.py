"""TASK-010 (api-contracts.md §1, auth-api) - POST /api/v1/auth/login,
POST /api/v1/auth/refresh, GET /api/v1/auth/me. 1 bang `account` chung cho
ca 4 role (doctor|patient|caregiver|admin) - quyet dinh da chot voi PM
2026-08-12, xem tasks/TASK-010-auth-api.md."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from datetime import UTC, datetime
import uuid

from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import Account, Patient
from backend.models.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    UserOut,
)
from backend.services.auth import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_revoked_by_password_change,
    verify_password,
)


auth_router = APIRouter()


def _login_response(account: Account) -> LoginResponse:
    settings = get_settings()
    access_token = create_access_token(
        sub=account.id, role=account.role, patient_id=account.patient_id, doctor_id=account.doctor_id
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_token=create_refresh_token(sub=account.id, role=account.role),
        user=UserOut(
            id=account.id,
            full_name=account.full_name,
            role=account.role,
            is_email_verified=getattr(account, "is_email_verified", True),
        ),
    )


@auth_router.post("/auth/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    existing_account = db.query(Account).filter(Account.email == body.email).first()
    if existing_account is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email đã được sử dụng")

    account_id = str(uuid.uuid4())
    account = Account(
        id=account_id,
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        status="active",
        is_email_verified=True,
    )

    if body.role == "patient":
        patient = Patient(id=account_id, full_name=body.full_name)
        db.add(patient)
        account.patient_id = account_id
    elif body.role == "doctor":
        account.doctor_id = account_id

    db.add(account)
    db.commit()
    db.refresh(account)

    return _login_response(account)








@auth_router.post("/auth/change-password", response_model=ChangePasswordResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChangePasswordResponse:
    account = db.query(Account).filter(Account.id == current_user.id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không tồn tại")

    if not verify_password(body.current_password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu hiện tại không chính xác"
        )

    account.password_hash = hash_password(body.new_password)
    account.password_changed_at = datetime.now(UTC)
    db.commit()
    db.refresh(account)

    login_res = _login_response(account)
    return ChangePasswordResponse(
        access_token=login_res.access_token,
        token_type=login_res.token_type,
        expires_in=login_res.expires_in,
        refresh_token=login_res.refresh_token,
        user=login_res.user,
        detail="Đổi mật khẩu thành công"
    )


@auth_router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    account = db.query(Account).filter(Account.email == body.email).first()
    # Cung 1 thong bao du sai email hay sai password - khong tiet lo email
    # nao ton tai trong he thong (tranh do email that qua endpoint dang nhap).
    if account is None or not verify_password(body.password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai email hoac mat khau")
    # THEM sau TASK-010 (migration 0013, account-api) - BAT BUOC check O DAY,
    # khong chi o tang UI: neu thieu, nut "khoa tai khoan" cua admin
    # (backend/api/account_routes.py) chi la UI gia, khong chan dang nhap
    # that. 403 (khong phai 401) - mat khau DUNG, chi la tai khoan bi khoa;
    # khong ro ri gi them vi nguoi goi da chung minh biet dung credential.
    if account.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khoá")
    return _login_response(account)


@auth_router.post("/auth/refresh", response_model=LoginResponse)
async def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        payload = decode_token(body.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Thieu/het han JWT") from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token khong phai refresh token")

    account = db.query(Account).filter(Account.id == payload.get("sub")).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tai khoan khong ton tai")
    if account.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khoá")
    return _login_response(account)


@auth_router.get("/auth/me", response_model=MeResponse)
async def me(
    current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> MeResponse:
    account = db.query(Account).filter(Account.id == current_user.id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tai khoan khong ton tai")
    return MeResponse(
        id=account.id,
        full_name=account.full_name,
        email=account.email,
        role=account.role,
        is_email_verified=getattr(account, "is_email_verified", True),
        patient_id=account.patient_id,
        doctor_id=account.doctor_id,
    )


__all__ = ["auth_router"]
