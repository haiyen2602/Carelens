"""account-api (follow-up sau TASK-010, xem specs/api-contracts.md muc them
sau §1 va tasks/TASK-010-auth-api.md) - admin tao/list/khoa tai khoan
doctor|patient|caregiver|admin. Day la cach DUY NHAT de co tai khoan
doctor/patient that (khong co dang ky cong khai - user-roles.md: chi admin
duoc quan ly tai khoan). `scripts/create_admin.py` (CLI) van con de bootstrap
tai khoan admin DAU TIEN (chua co admin nao thi khong ai goi duoc route nay
- require_role("admin"))."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.db.base import get_db
from backend.db.models import Account, Patient
from backend.models.schemas import (
    AccountCreateRequest,
    AccountOut,
    AccountStatusUpdateRequest,
    AccountUpdateRequest,
)
from backend.services.audit import get_actor_display_name, log_system_event
from backend.services.auth import hash_password
from backend.services.doctor_watch import auto_watch_new_patient
from backend.services.email_identity import find_account_by_email
from backend.services.patient_id import generate_next_patient_id

account_router = APIRouter()

ROLE_LABELS = {
    "doctor": "Bác sĩ",
    "admin": "Quản trị",
    "super_admin": "Quản trị cấp cao",
    "patient": "Bệnh nhân",
    "caregiver": "Người thân",
}


def get_account_target(account: Account) -> str:
    return account.patient_id or account.doctor_id or account.email


@account_router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin", "super_admin")),
) -> Account:
    if body.role in ("admin", "super_admin") and _admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ super_admin mới có quyền tạo tài khoản quản trị",
        )

    if find_account_by_email(db, body.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email đã có tài khoản")

    patient_id = body.patient_id
    if body.role == "patient":
        if not patient_id:
            patient_id = generate_next_patient_id(db)
        if db.get(Patient, patient_id) is None:
            db.add(Patient(id=patient_id, full_name=body.full_name))
            auto_watch_new_patient(db, patient_id)

    account = Account(
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        patient_id=patient_id,
        doctor_id=body.doctor_id,
    )
    db.add(account)
    db.flush()

    role_vn = ROLE_LABELS.get(account.role, account.role)
    target_id = get_account_target(account)
    actor_name = get_actor_display_name(db, _admin.id, _admin.role)
    log_system_event(
        db,
        actor_id=_admin.id,
        actor_name=actor_name,
        actor_role=_admin.role,
        action=f"Cấp tài khoản mới {role_vn} {account.full_name} ({account.email})",
        target=target_id,
    )

    db.commit()
    db.refresh(account)
    return account


@account_router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_role("admin", "super_admin"))
) -> list[Account]:
    return db.query(Account).order_by(Account.created_at.desc()).all()


@account_router.patch("/accounts/{account_id}/status", response_model=AccountOut)
async def update_account_status(
    account_id: str,
    body: AccountStatusUpdateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin", "super_admin")),
) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài khoản không tồn tại")

    if account.role in ("admin", "super_admin") and _admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ super_admin mới có quyền thay đổi trạng thái tài khoản quản trị",
        )

    account.status = body.status
    action_text = "Khoá tài khoản" if body.status == "locked" else "Mở khoá tài khoản"
    target_id = get_account_target(account)
    actor_name = get_actor_display_name(db, _admin.id, _admin.role)

    log_system_event(
        db,
        actor_id=_admin.id,
        actor_name=actor_name,
        actor_role=_admin.role,
        action=f"{action_text} {target_id} ({account.full_name})",
        target=target_id,
    )

    db.commit()
    db.refresh(account)
    return account


@account_router.patch("/accounts/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: str,
    body: AccountUpdateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin", "super_admin")),
) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài khoản không tồn tại")

    if account.role in ("admin", "super_admin") and _admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ super_admin mới có quyền chỉnh sửa tài khoản quản trị",
        )

    if body.email is not None and body.email != account.email:
        existing = find_account_by_email(db, body.email)
        if existing is not None and existing.id != account.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email đã được sử dụng")
        account.email = body.email

    if body.full_name is not None:
        account.full_name = body.full_name
        if account.patient_id:
            patient = db.get(Patient, account.patient_id)
            if patient:
                patient.full_name = body.full_name

    target_id = get_account_target(account)
    actor_name = get_actor_display_name(db, _admin.id, _admin.role)
    log_system_event(
        db,
        actor_id=_admin.id,
        actor_name=actor_name,
        actor_role=_admin.role,
        action=f"Cập nhật thông tin tài khoản {account.full_name} ({account.email})",
        target=target_id,
    )

    db.commit()
    db.refresh(account)
    return account



