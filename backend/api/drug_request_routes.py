"""Yeu cau bo sung thuoc ngoai danh muc (FB-14).

Hai nhom endpoint tren cung mot resource, tach prefix theo NGUOI DUNG chu
khong theo hanh dong:

  /drug-requests        -> bac si: gui yeu cau, xem yeu cau CUA CHINH MINH
  /admin/drug-requests  -> admin: xem ca hang doi, duyet/tu choi

Vi sao khong gop lam mot prefix roi phan nhanh theo role: hai nhom co pham vi
du lieu khac han (cua minh vs tat ca), va gop lai thi moi endpoint deu phai tu
nho loc theo doctor_id - quen mot cho la bac si doc duoc yeu cau cua nguoi
khac. Tach prefix khien `require_role` lam viec do mot lan.

CHI ADMIN DUYET - khop ma tran quyen trong specs/user-roles.md ("Nap/sua du
lieu thuoc cho RAG" = admin). Cho bac si tu duyet yeu cau cua chinh minh thi
lo hong FB-14 quay lai nguyen ven, chi them vai cu bam.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.db.base import get_db
from backend.models.drug_request_schemas import (
    DrugRequestApprove,
    DrugRequestCreate,
    DrugRequestListResponse,
    DrugRequestOut,
    DrugRequestReject,
    DrugRequestStatus,
)
from backend.services.drug_requests import (
    duyet_yeu_cau,
    liet_ke_yeu_cau,
    tao_yeu_cau,
    tu_choi_yeu_cau,
)
from backend.services.prescription.errors import VmecError

drug_request_router = APIRouter(prefix="/drug-requests", tags=["drug-requests"])
admin_drug_request_router = APIRouter(prefix="/admin/drug-requests", tags=["admin-drug-requests"])


def _http(exc: VmecError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail=exc.to_contract()["error"])


def _doctor_id(current_user: CurrentUser) -> str:
    """`doctor_id` trong JWT, roi ve `id` neu token chua co claim do.

    Token cu (phat truoc khi them claim) van dung duoc thay vi bat dang nhap
    lai - cung cach xu ly voi get_current_doctor_id o prescription_routes.py.
    """
    return current_user.doctor_id or current_user.id


@drug_request_router.post("", response_model=DrugRequestOut, status_code=201)
def create_drug_request(
    payload: DrugRequestCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor")),
) -> DrugRequestOut:
    try:
        yeu_cau = tao_yeu_cau(
            db,
            doctor_id=_doctor_id(current_user),
            ten_thuoc=payload.ten_thuoc,
            dang_thuoc=payload.dang_thuoc,
            duong_dung=payload.duong_dung,
            ham_luong=payload.ham_luong,
            tong_so_luong=payload.tong_so_luong,
            ly_do=payload.ly_do,
        )
    except VmecError as exc:
        raise _http(exc) from exc
    return DrugRequestOut.model_validate(yeu_cau)


@drug_request_router.get("", response_model=DrugRequestListResponse)
def list_my_drug_requests(
    status: DrugRequestStatus | None = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor")),
) -> DrugRequestListResponse:
    """CHI yeu cau cua chinh bac si dang dang nhap - `doctor_id` lay tu JWT,
    khong nhan tu query param (nhan tu ngoai la doc duoc cua nguoi khac)."""
    rows = liet_ke_yeu_cau(db, doctor_id=_doctor_id(current_user), status=status)
    return DrugRequestListResponse(items=[DrugRequestOut.model_validate(r) for r in rows])


@admin_drug_request_router.get("", response_model=DrugRequestListResponse)
def list_all_drug_requests(
    status: Annotated[DrugRequestStatus | None, Query()] = None,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin", "super_admin")),
) -> DrugRequestListResponse:
    rows = liet_ke_yeu_cau(db, status=status)
    return DrugRequestListResponse(items=[DrugRequestOut.model_validate(r) for r in rows])


@admin_drug_request_router.post("/{request_id}/approve", response_model=DrugRequestOut)
def approve_drug_request(
    request_id: str,
    payload: DrugRequestApprove,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_role("admin", "super_admin")),
) -> DrugRequestOut:
    try:
        yeu_cau = duyet_yeu_cau(db, request_id, admin_account_id=admin.id, note=payload.note)
    except VmecError as exc:
        raise _http(exc) from exc
    return DrugRequestOut.model_validate(yeu_cau)


@admin_drug_request_router.post("/{request_id}/reject", response_model=DrugRequestOut)
def reject_drug_request(
    request_id: str,
    payload: DrugRequestReject,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_role("admin", "super_admin")),
) -> DrugRequestOut:
    try:
        yeu_cau = tu_choi_yeu_cau(db, request_id, admin_account_id=admin.id, note=payload.note)
    except VmecError as exc:
        raise _http(exc) from exc
    return DrugRequestOut.model_validate(yeu_cau)
