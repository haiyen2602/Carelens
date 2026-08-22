"""POST /api/v1/health-log - benh nhan tu ghi nhat ky suc khoe
(frontend/src/app/patient/health/page.tsx::guiBaoVanDe()). THEM 2026-08-20.

Truoc day hanh dong nay chi ghi vao state cuc bo trong trinh duyet
(frontend/src/lib/proto-store.tsx::reportHealth()) - benh nhan bao "cam thay
om yeu" mien khong bao gio toi duoc nguoi than/bac si that. Endpoint nay noi
no vao CUNG 1 bang Escalation ma chatbot dang dung (backend/services/
escalation.py::escalate_fn), de nguoi than thay qua tab "Canh bao"
(backend/api/caregiver_routes.py::_list_monitored_patients) va thua huong
luon co che nhac lai cho muc HIGH (backend/services/escalation_reminder.py) -
khong tach rieng 1 duong du lieu song song.

KHONG tai dung truc tiep escalate_fn - ham do la closure gan voi vong doi 1
lan chay LangGraph agent (tao moi qua factory moi request chat), khong hop
de goi tu 1 REST route thuong; insert Escalation truc tiep o day, cung
khuon du lieu."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.db.base import get_db
from backend.models.schemas import HealthLogCreateRequest, HealthLogCreateResponse
from backend.services.caregiver_escalation import tao_canh_bao_cho_nguoi_than

health_log_router = APIRouter()

_LEVEL_TO_SEVERITY = {"mid": "MEDIUM", "high": "HIGH"}


@health_log_router.post("/health-log", response_model=HealthLogCreateResponse)
def create_health_log(
    body: HealthLogCreateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> HealthLogCreateResponse:
    if current_user.role != "patient" or not current_user.patient_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Chỉ bệnh nhân mới tự ghi nhật ký sức khỏe cho chính mình",
        )

    severity = _LEVEL_TO_SEVERITY.get(body.level)
    if severity is None:
        # level="low" - chi la nhat ky rieng, KHONG dang bao dong nguoi than -
        # khop toast hien tai o health/page.tsx: "Da ghi nhat ky, theo doi 48h".
        return HealthLogCreateResponse(escalation_id=None)

    row = tao_canh_bao_cho_nguoi_than(
        db,
        patient_id=current_user.patient_id,
        severity=severity,
        trigger="patient_reported",
        reason=body.text.strip() or "Không mô tả chi tiết",
    )
    db.commit()
    db.refresh(row)

    return HealthLogCreateResponse(escalation_id=row.id)
