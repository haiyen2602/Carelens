"""API router cho System Audit Logs (Quản trị hệ thống)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_role
from backend.db.base import get_db
from backend.models.schemas import SystemAuditLogListResponse
from backend.services.audit import list_system_audit_logs

audit_router = APIRouter(prefix="/admin/audit-logs", tags=["admin-audit"])

# Router rieng, KHONG nam duoi /admin: day la nhat ky cua CHINH nguoi dang
# dang nhap, moi role deu goi duoc, khac han man hinh admin xem toan he thong.
my_audit_router = APIRouter(prefix="/audit-logs", tags=["audit"])


@my_audit_router.get("/me", response_model=SystemAuditLogListResponse)
def get_my_audit_logs(
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SystemAuditLogListResponse:
    """Nhat ky thao tac cua CHINH nguoi dang dang nhap (trang "Lịch sử" cua
    bac si, frontend/src/app/doctor/audit/page.tsx).

    `actor_id` lay tu JWT chu KHONG nhan tu query param - neu nhan tu client
    thi bat ky ai cung doc duoc nhat ky cua nguoi khac chi bang cach doi mot
    tham so tren URL."""
    return list_system_audit_logs(
        db, q=q, actor_id=current_user.id, page=page, page_size=page_size
    )


@audit_router.get("", response_model=SystemAuditLogListResponse)
def get_audit_logs(
    q: Annotated[str | None, Query(max_length=200)] = None,
    role: Annotated[str | None, Query(max_length=50)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> SystemAuditLogListResponse:
    """Lấy danh sách nhật ký kiểm toán hệ thống (chỉ dành cho Admin, Read-Only)."""
    return list_system_audit_logs(db, q=q, role=role, page=page, page_size=page_size)
