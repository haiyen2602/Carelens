"""Service ghi và truy vấn nhật ký kiểm toán hệ thống (System Audit Logs).

APPEND-ONLY (Ràng buộc an toàn): Không cung cấp hàm sửa/xóa log.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.db.models import Account, SystemAuditLog


def get_actor_display_name(db: Session, user_id: str | None, default_role: str = "admin") -> str:
    """Lấy tên hiển thị của actor từ DB hoặc fallback về tên mặc định theo role."""
    if user_id:
        acc = db.get(Account, user_id)
        if acc and acc.full_name:
            return acc.full_name
    return "Quản trị viên" if default_role == "admin" else default_role



def log_system_event(
    db: Session,
    *,
    actor_name: str,
    actor_role: str,
    action: str,
    target: str | None = None,
    actor_id: str | None = None,
) -> SystemAuditLog:
    """Tạo mới 1 bản ghi nhật ký kiểm toán trong transaction hiện tại."""
    entry = SystemAuditLog(
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role=actor_role,
        action=action,
        target=target,
    )
    db.add(entry)
    return entry


def list_system_audit_logs(
    db: Session,
    *,
    q: str | None = None,
    role: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Truy vấn danh sách audit log có phân trang, tìm kiếm và lọc theo vai trò."""
    query = db.query(SystemAuditLog)

    if role and role != "all":
        query = query.filter(SystemAuditLog.actor_role == role)

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                SystemAuditLog.actor_name.ilike(term),
                SystemAuditLog.action.ilike(term),
                SystemAuditLog.target.ilike(term),
            )
        )

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 0

    items = (
        query.order_by(SystemAuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
