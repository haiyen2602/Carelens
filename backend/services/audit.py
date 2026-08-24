"""Service ghi và truy vấn nhật ký kiểm toán hệ thống (System Audit Logs).

APPEND-ONLY (Ràng buộc an toàn): Không cung cấp hàm sửa/xóa log.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.db.models import Account, Patient, SystemAuditLog


def patient_label(db: Session, patient_id: str | None) -> str | None:
    """Tên bệnh nhân kèm mã, dùng làm `target` cho nhật ký.

    Đọc tên NGAY lúc ghi log thay vì tra lại khi hiển thị: nhật ký là bản ghi
    của thời điểm thao tác, nếu về sau bệnh nhân đổi tên (hoặc hồ sơ bị xoá)
    thì dòng nhật ký cũ vẫn phải đọc được đúng như lúc nó xảy ra.
    """
    if not patient_id:
        return None
    patient = db.get(Patient, patient_id)
    if patient is None or not patient.full_name:
        return patient_id
    return f"{patient.full_name} ({patient_id})"


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


def log_action(
    db: Session,
    current_user: Any | None,
    action: str,
    target: str | None = None,
) -> SystemAuditLog | None:
    """Bọc log_system_event() cho các route đã có CurrentUser từ JWT.

    Trả None (KHÔNG ghi gì) khi không biết người gọi là ai - một dòng nhật ký
    không quy được trách nhiệm cho ai thì tệ hơn là không có dòng nào, vì nó
    làm người đọc tưởng đã kiểm chứng được hành động đó.

    KHÔNG commit - để nguyên trong transaction của route, đúng tinh thần
    "nhật ký ghi cùng lúc với thay đổi dữ liệu, hoặc không ghi gì cả": nếu
    route rollback thì dòng nhật ký cũng biến mất theo, không còn lại lời
    khai về một thao tác chưa từng xảy ra.
    """
    if current_user is None:
        return None
    return log_system_event(
        db,
        actor_id=current_user.id,
        actor_name=get_actor_display_name(db, current_user.id, default_role=current_user.role),
        actor_role=current_user.role,
        action=action,
        target=target,
    )


def list_system_audit_logs(
    db: Session,
    *,
    q: str | None = None,
    role: str | None = None,
    actor_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Truy vấn danh sách audit log có phân trang, tìm kiếm và lọc theo vai trò.

    `actor_id` giới hạn kết quả về đúng một người - dùng cho trang "Lịch sử"
    của bác sĩ (mỗi bác sĩ chỉ thấy thao tác của chính mình), khác màn hình
    admin xem toàn hệ thống.
    """
    query = db.query(SystemAuditLog)

    if actor_id:
        query = query.filter(SystemAuditLog.actor_id == actor_id)

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
