"""POST /api/v1/escalations/{id}/ack (api-contracts.md §6, vong 2 muc 13) -
danh dau 1 escalation da duoc xu ly. Day chinh la co che DUNG nhac lai
(escalation_reminder.py::check_and_send_reminders() chi quet status="OPEN")
- KHONG them cot resolved:bool rieng, dung lai `status` da co san tren
Escalation (OPEN|ACKED|RESOLVED) chuyen sang "RESOLVED".

Idempotent co y: goi lai nhieu lan (vd 2 nguoi cung ack gan nhau) chi CAP
NHAT lai resolved_at/resolved_by, khong loi - tranh xu ly race condition
phuc tap cho 1 hanh dong vo hai (xac nhan lai)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from src.api.security import require_internal_secret
from src.db.base import get_db
from src.db.models import Escalation
from src.models.schemas import EscalationAckRequest, EscalationAckResponse

escalation_router = APIRouter()


@escalation_router.post(
    "/escalations/{escalation_id}/ack",
    response_model=EscalationAckResponse,
    dependencies=[Depends(require_internal_secret)],
)
async def ack_escalation(
    escalation_id: str, request: EscalationAckRequest, db: Session = Depends(get_db)
) -> EscalationAckResponse:
    row = db.get(Escalation, escalation_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Escalation không tồn tại")

    row.status = "RESOLVED"
    row.resolved_at = datetime.now(UTC)
    row.resolved_by = request.resolved_by
    db.commit()

    return EscalationAckResponse(
        id=row.id,
        status=row.status,
        resolved_at=row.resolved_at.isoformat(),
        resolved_by=row.resolved_by,
    )