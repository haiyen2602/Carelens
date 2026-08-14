"""TASK-010 (api-contracts.md §1, auth-api) - POST /api/v1/auth/login,
POST /api/v1/auth/refresh, GET /api/v1/auth/me. 1 bang `account` chung cho
ca 4 role (doctor|patient|caregiver|admin) - quyet dinh da chot voi PM
2026-08-12, xem tasks/TASK-010-auth-api.md."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
    verify_password,
)
from backend.services.doctor_watch import auto_watch_new_patient
from backend.services.patient_id import generate_next_patient_id

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


# 5 route duoi day truoc la `async def` nhung goi thang Session dong bo cua
# SQLAlchemy (khong co await nao ben trong) - FastAPI CHI tu day sang
# threadpool cho route khai bao `def` thuong, `async def` thi chay ngay
# tren event loop chinh. Goi DB dong bo (blocking) trong `async def` do se
# chan cung event loop cua worker duy nhat (Dockerfile khong --workers),
# nghen luon CA cac request khac khong lien quan gi toi auth trong luc dang
# cho DB tra loi. Phat hien khi dieu tra "web treo khi nhieu nguoi cung 1
# tai khoan" (login/refresh bi goi don dap) - doi ve `def` de dung dung co
# che threadpool nhu 38 route con lai trong du an.
@auth_router.post("/auth/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
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
        # SUA 2026-08-14: patient_id KHONG con dung chung account_id (UUID) -
        # đó là bug khiến UI hiển thị thẳng UUID thay vì ID ngắn gọn dạng
        # BNxxxxx như dữ liệu cũ (vd "BN00002"). `Account.id` vẫn là UUID
        # riêng (dùng để đăng nhập/JWT sub), độc lập với patient_id hiển thị.
        patient_id = generate_next_patient_id(db)
        patient = Patient(id=patient_id, full_name=body.full_name)
        db.add(patient)
        account.patient_id = patient_id
        # THEM 2026-08-14 (yeu cau PM): benh nhan MOI mac dinh duoc TAT CA
        # bac si dang co theo doi ngay - khong con tinh trang "Cảnh báo mới
        # nhất" rong vi chua ai bam "Theo dõi" benh nhan nay.
        auto_watch_new_patient(db, patient_id)
    elif body.role == "doctor":
        account.doctor_id = account_id

    db.add(account)
    db.commit()
    db.refresh(account)

    return _login_response(account)








@auth_router.post("/auth/change-password", response_model=ChangePasswordResponse)
def change_password(
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
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
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
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> LoginResponse:
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
def me(
    current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> MeResponse:
    account = db.query(Account).filter(Account.id == current_user.id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tai khoan khong ton tai")

    # THEM (migration 0022) - frontend dung de biet co bat buoc redirect
    # sang /onboarding/profile hay khong. Chi tra gia tri khi role=patient
    # (con lai None - chua co onboarding tuong tu cho role khac).
    profile_completed: bool | None = None
    if account.role == "patient" and account.patient_id:
        patient = db.query(Patient).filter(Patient.id == account.patient_id).first()
        profile_completed = patient.profile_completed if patient is not None else False

    return MeResponse(
        id=account.id,
        full_name=account.full_name,
        email=account.email,
        role=account.role,
        is_email_verified=getattr(account, "is_email_verified", True),
        patient_id=account.patient_id,
        doctor_id=account.doctor_id,
        profile_completed=profile_completed,
    )


__all__ = ["auth_router"]
