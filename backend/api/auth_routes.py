"""TASK-010 (api-contracts.md §1, auth-api) - POST /api/v1/auth/login,
POST /api/v1/auth/refresh, GET /api/v1/auth/me. 1 bang `account` chung cho
ca 4 role (doctor|patient|caregiver|admin) - quyet dinh da chot voi PM
2026-08-12, xem tasks/TASK-010-auth-api.md."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_internal_secret
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import Account, Patient
from backend.models.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OAuthLoginRequest,
    RefreshRequest,
    RegisterRequest,
    SetPasswordRequest,
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
from backend.services.email_identity import find_account_by_email
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


def _provision_patient(db: Session, account: Account, full_name: str) -> None:
    """Tao ban ghi `Patient` + patient_id ngan gon (BNxxxxx) cho 1 Account
    role=patient, va cho TAT CA bac si theo doi ngay.

    Tach ra khoi register() de POST /auth/oauth/google dung DUNG khoi logic
    nay - neu copy sang do, bat ky sua doi sau nay (vd them buoc onboarding)
    se chi duoc ap dung cho 1 trong 2 duong dang ky, va benh nhan dang nhap
    bang Google se roi vao trang thai khac benh nhan dang ky bang mat khau.
    KHONG commit - nguoi goi quyet dinh ranh gioi transaction."""
    patient_id = generate_next_patient_id(db)
    db.add(Patient(id=patient_id, full_name=full_name))
    account.patient_id = patient_id
    auto_watch_new_patient(db, patient_id)


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
    # Tra cuu KHONG phan biet chu hoa/thuong (SUA 2026-08-17): neu chi so
    # `Account.email == body.email` thi "MCK@gmail.com" dang ky duoc lan 2 duoi
    # dang "mck@gmail.com" -> 2 tai khoan cho cung 1 nguoi. Xem
    # backend/services/email_identity.py.
    existing_account = find_account_by_email(db, body.email)
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
        auth_provider="password",
    )

    if body.role == "patient":
        # SUA 2026-08-14: patient_id KHONG con dung chung account_id (UUID) -
        # đó là bug khiến UI hiển thị thẳng UUID thay vì ID ngắn gọn dạng
        # BNxxxxx như dữ liệu cũ (vd "BN00002"). `Account.id` vẫn là UUID
        # riêng (dùng để đăng nhập/JWT sub), độc lập với patient_id hiển thị.
        # THEM 2026-08-14 (yeu cau PM): benh nhan MOI mac dinh duoc TAT CA
        # bac si dang co theo doi ngay - khong con tinh trang "Cảnh báo mới
        # nhất" rong vi chua ai bam "Theo dõi" benh nhan nay.
        _provision_patient(db, account, body.full_name)

    db.add(account)
    db.commit()
    db.refresh(account)

    return _login_response(account)


@auth_router.post(
    "/auth/oauth/google",
    response_model=LoginResponse,
    dependencies=[Depends(require_internal_secret)],
)
def oauth_google(body: OAuthLoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """"Login with Google" - doi danh tinh Google DA xac thuc thanh JWT cua
    chinh he thong nay (api-contracts.md §1).

    Better Auth (frontend/src/lib/better-auth.ts) chay TRONG Next.js va CHI lam
    moi gioi OAuth: no noi chuyen voi Google, xac minh chu ky, roi Route Handler
    frontend/src/app/api/auth/google-bridge/route.ts goi endpoint nay. Nguon su
    that ve danh tinh VAN LA bang `account` + JWT nay - nho vay 40 route backend
    con lai (doc role/patient_id tu JWT) khong phai doi gi.

    Chan bang `require_internal_secret` (server-to-server), KHONG public: neu mo
    public thi bat ky ai cung POST duoc mot email tuy y vao day va nhan lai JWT
    hop le cua chu email do - endpoint nay khong co mat khau nao de kiem tra,
    toan bo niem tin nam o cho "nguoi goi da xac thuc Google giup roi". Do la ly
    do `require_internal_secret` (backend/api/security.py) chua duoc xoa han."""
    if not body.email_verified:
        # Fail-closed: Google noi email nay chua xac thuc -> khong duoc phep
        # dung no de nhan danh chu tai khoan cung email trong bang `account`.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email Google chưa được xác thực, không thể dùng để đăng nhập",
        )

    # Tra cuu KHONG phan biet chu hoa/thuong - DAY la cho quan trong nhat cua
    # ban sua 2026-08-17: neu so `Account.email == body.email`, tai khoan dang
    # ky thu cong bang "MCK@gmail.com" se KHONG duoc tim thay khi Google tra ve
    # "mck@gmail.com", va nhanh `account is None` ben duoi se tao them mot tai
    # khoan THU HAI cho cung 1 nguoi (patient_id moi, ho so trong), trong khi
    # don thuoc/lich uong thuoc/canh bao van nam o tai khoan cu.
    account = find_account_by_email(db, body.email)

    if account is None:
        # Lan dau dang nhap Google -> tao tai khoan `patient` moi, giong het
        # duong /auth/register (ke ca patient_id BNxxxxx + auto-watch).
        account = Account(
            id=str(uuid.uuid4()),
            full_name=body.full_name,
            email=body.email,
            # KHONG co mat khau nguoi dung. Dat bcrypt cua 1 chuoi ngau nhien
            # 32 byte (khong luu o dau, khong ai biet) thay vi de rong: cot
            # `password_hash` NOT NULL, va quan trong hon - verify_password()
            # voi hash rong se NEM LOI thay vi tra False, bien 401 thanh 500.
            # Cach nay khien POST /auth/login bang mat khau khong bao gio vao
            # duoc tai khoan Google, du co doan trung gi.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role="patient",
            status="active",
            # Google da xac thuc email (da check email_verified o tren) - khong
            # bat nguoi dung xac thuc lai email lan hai.
            is_email_verified=True,
            auth_provider="google",
        )
        _provision_patient(db, account, body.full_name)
        db.add(account)
        db.commit()
        db.refresh(account)
        return _login_response(account)

    # Da co tai khoan cung email -> DANG NHAP vao chinh tai khoan do, giu
    # nguyen role (doctor/admin dang nhap bang Google van la doctor/admin) va
    # giu nguyen `auth_provider`: tai khoan mat khau lien ket them Google VAN
    # con mat khau cua no, khong duoc ha xuong thanh "google" (lam vay se noi
    # doi rang no chua tung dat mat khau).
    if account.status != "active":
        # Cung 403 + cung thong bao nhu /auth/login - nut "khoa tai khoan" cua
        # admin phai chan CA duong Google, neu khong no chi la UI gia.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khoá")

    # Tai khoan cu (truoc migration 0021, khi chua co luong xac thuc email)
    # hoac tao boi admin: Google vua chung minh chu email nay - danh dau da
    # xac thuc de nguoi dung khong bi chan boi buoc verify email.
    thay_doi = False
    if not account.is_email_verified:
        account.is_email_verified = True
        thay_doi = True

    # SUA 2026-08-17 (bug that tren production, phat hien khi so localhost voi
    # production): nhanh "tai khoan DA CO SAN" nay TUNG khong cap patient_id,
    # trong khi nhanh "tao moi" o tren goi _provision_patient(). Hau qua tren
    # 1 tai khoan role=patient con thieu patient_id:
    #   - header /patient hien "Bệnh nhân ·" bo trong (JWT claim patient_id =
    #     None), va MeResponse.profile_completed = None nen cong onboarding
    #     (patient/layout.tsx) khong bao gio bat -> ho so trong vinh vien;
    #   - moi endpoint doc du lieu benh nhan qua get_current_patient_id()
    #     (backend/api/security.py) roi ve patient_id cua NGUOI KHAC neu ho tu
    #     go vao body, vi role=patient chi duoc uu tien khi patient_id co that.
    # Tai khoan dang trong tinh trang nay la tai khoan tao TRUOC khi co
    # _provision_patient (dang ky som, hoac admin tao thieu buoc) - Google
    # khong sinh ra chung, nhung day la lan duy nhat ta chac chan ho la chu
    # email do, nen cap bu ngay tai day. Chi cap khi THAT SU con thieu, khong
    # bao gio ghi de patient_id da co.
    if account.role == "patient" and not account.patient_id:
        _provision_patient(db, account, account.full_name)
        thay_doi = True

    if thay_doi:
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

    # THEM (migration 0025, Login with Google): tai khoan tao qua Google KHONG
    # co mat khau nguoi dung nao. Neu de chay tiep, verify_password() se so voi
    # bcrypt cua 1 chuoi ngau nhien va tra ve "Mật khẩu hiện tại không chính
    # xác" - dung ky thuat nhung sai thong tin, nguoi dung se ngoi thu lai cac
    # mat khau ho nho. Bao dung ly do de ho biet day khong phai loi go sai.
    if account.auth_provider == "google":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản này đăng nhập bằng Google nên chưa có mật khẩu để đổi",
        )

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


@auth_router.post("/auth/set-password", response_model=ChangePasswordResponse)
def set_password(
    body: SetPasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChangePasswordResponse:
    """DAT mat khau lan dau cho tai khoan tao qua Google (api-contracts.md §1c,
    quyet dinh PM 2026-08-17).

    Vi sao KHONG dung /auth/change-password: endpoint do doi `current_password`
    va xac minh no. Tai khoan Google khong co mat khau nguoi dung nao ca
    (`password_hash` chi la bcrypt cua 1 chuoi ngau nhien khong ai biet, xem
    oauth_google), nen khong the nhap dung duoc gi.

    Vi sao no khong lam yeu he thong du KHONG doi mat khau cu: dieu kien
    `auth_provider == "google"` la mot cong CHI MO DUOC MOT LAN. Ngay sau khi
    dat mat khau, cot doi thanh "password", nen lan goi thu hai vao chinh
    endpoint nay se bi tu choi 400 - tu do tro di moi thay doi mat khau buoc
    phai di /auth/change-password (co xac minh mat khau cu). Neu thieu dieu
    kien nay, 1 access_token bi lo se doi duoc mat khau cua BAT KY tai khoan
    ma khong can biet mat khau hien tai.

    Sau khi dat: tai khoan dang nhap duoc CA HAI duong (Google va email/mat
    khau) - do la muc dich, va la duong thoat duy nhat neu nguoi dung mat
    quyen truy cap Gmail (backend chua co /auth/forgot-password)."""
    account = db.query(Account).filter(Account.id == current_user.id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không tồn tại")

    if account.auth_provider != "google":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản này đã có mật khẩu, hãy dùng chức năng đổi mật khẩu",
        )

    account.password_hash = hash_password(body.new_password)
    # Tu day tai khoan co mat khau THAT -> khong con di duong set-password nua,
    # va /auth/change-password bat dau hoat dong binh thuong. Dang nhap bang
    # Google VAN duoc: oauth_google() tim theo email va giu nguyen
    # `auth_provider` cua tai khoan da ton tai.
    account.auth_provider = "password"
    # Giong /auth/change-password: THU HOI moi token cu (migration 0018). O day
    # y nghia bao mat con ro hon - neu truoc do co phien nao khac dang mo tren
    # tai khoan chua co mat khau, chung phai bi dang xuat.
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
        detail="Đặt mật khẩu thành công",
    )


@auth_router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    # Khong phan biet chu hoa/thuong (SUA 2026-08-17): nguoi dung go
    # "MCK@gmail.com" hom nay va "mck@gmail.com" hom sau van phai vao dung 1
    # tai khoan. Xem backend/services/email_identity.py.
    account = find_account_by_email(db, body.email)
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
        auth_provider=account.auth_provider,
    )


__all__ = ["auth_router"]
