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
from backend.models.schemas import AccountCreateRequest, AccountOut, AccountStatusUpdateRequest
from backend.services.auth import hash_password
from backend.services.doctor_watch import auto_watch_new_patient
from backend.services.patient_id import generate_next_patient_id

account_router = APIRouter()


@account_router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> Account:
    if db.query(Account).filter(Account.email == body.email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email đã có tài khoản")

    # SUA 2026-08-14: dong bo voi auth_routes.py::register() - truoc do
    # patient_id o day la chuoi TU DO admin go tay, khong tung tao dong
    # `Patient` that dang sau (benh nhan "co ID nhung khong co ho so"),
    # va khong theo dinh dang BNxxxxx cua du lieu cu (vd "BN00002").
    #
    # - Khong go patient_id (role=patient) -> tu sinh BNxxxxx ke tiep VA tao
    #   dong Patient that, giong het duong tu dang ky.
    # - CO go patient_id (vd link toi du lieu demo co san nhu
    #   "demo-patient-01", dung y goc cua field nay - xem docstring
    #   AccountCreateRequest) -> giu nguyen ID do (KHONG ep ve BNxxxxx, vi
    #   day la lien ket toi ID DA CO TU TRUOC), chi tao dong Patient neu
    #   THAT SU chua co (tranh de trong hop lai khong co ho so that).
    patient_id = body.patient_id
    if body.role == "patient":
        if not patient_id:
            patient_id = generate_next_patient_id(db)
        if db.get(Patient, patient_id) is None:
            db.add(Patient(id=patient_id, full_name=body.full_name))
            # THEM 2026-08-14 (yeu cau PM) - CHI khi THAT SU vua tao Patient
            # moi (khong goi khi patient_id la lien ket toi ho so DA CO SAN,
            # vi do khong phai "benh nhan moi tao"): tu dong theo doi boi
            # TAT CA bac si dang co, cung logic voi auth_routes.py::register().
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
    db.commit()
    db.refresh(account)
    return account


@account_router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_role("admin"))
) -> list[Account]:
    return db.query(Account).order_by(Account.created_at.desc()).all()


@account_router.patch("/accounts/{account_id}/status", response_model=AccountOut)
async def update_account_status(
    account_id: str,
    body: AccountStatusUpdateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài khoản không tồn tại")

    account.status = body.status
    db.commit()
    db.refresh(account)
    return account
