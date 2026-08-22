"""API router cho System Audit Logs (Quản trị hệ thống)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.db.base import get_db
from backend.models.schemas import SystemAuditLogListResponse
from backend.services.audit import list_system_audit_logs

audit_router = APIRouter(prefix="/admin/audit-logs", tags=["admin-audit"])


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
