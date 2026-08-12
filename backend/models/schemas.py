from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login (api-contracts.md §1)."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class UserOut(BaseModel):
    """`user` object trong response cua /auth/login (api-contracts.md §1) -
    KHONG bao gom password_hash hay lien ket noi bo (patient_id/doctor_id),
    chi dung dung field mau trong contract."""

    id: str
    full_name: str
    role: str


class LoginResponse(BaseModel):
    """Response 200 cua POST /api/v1/auth/login - khop JSON mau
    api-contracts.md §1 (access_token/token_type/expires_in/user). Them
    `refresh_token` NGOAI mau contract - contract co dinh nghia endpoint
    POST /auth/refresh nhung KHONG noi ro client lay refresh_token dau tien
    tu dau; day la khoang trong hop ly cua ban Draft, khong phai sai lech
    contract co chu dinh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class MeResponse(BaseModel):
    """GET /api/v1/auth/me (api-contracts.md §1) - "Thong tin user hien tai
    + role + danh sach lien ket". `patient_id`/`doctor_id`: lien ket TOI
    THIEU hien co tren Account (TASK-010) - CHUA phai mo hinh lien ket day
    du bac si<->benh nhan<->nguoi than (user-roles.md, ngoai pham vi)."""

    id: str
    full_name: str
    email: str
    role: str
    patient_id: str | None = None
    doctor_id: str | None = None


AccountRole = Literal["doctor", "patient", "caregiver", "admin"]
AccountStatus = Literal["active", "locked"]


class AccountCreateRequest(BaseModel):
    """POST /api/v1/accounts (account-api, admin - xem specs/api-contracts.md
    muc them sau TASK-010). `patient_id`/`doctor_id`: lien ket TOI THIEU
    (text tu do, admin go tay khop du lieu demo co san vd 'demo-patient-01')
    - CHUA co UI chon tu danh sach, ngoai pham vi (xem tasks/TASK-010-auth-api.md)."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1)
    role: AccountRole
    patient_id: str | None = None
    doctor_id: str | None = None


class AccountStatusUpdateRequest(BaseModel):
    status: AccountStatus


class AccountOut(BaseModel):
    """KHONG BAO GIO bao gom password_hash - dung cho ca response tao moi,
    list, va update status."""

    id: str
    full_name: str
    email: str
    role: str
    status: str
    patient_id: str | None = None
    doctor_id: str | None = None
    created_at: datetime


class ConversationChatRequest(BaseModel):
    """POST /api/v1/chat (api-contracts.md §4). `patient_id` KHONG co trong
    contract goc (gia dinh lay tu JWT `sub` claim - api-contracts.md §1) -
    them tam vao body vi auth-api (§1) CHUA duoc xay trong repo nay (Draft,
    khong nam trong pham vi Phase 0-7 cua build-kickoff-prompt.md). TASK-010
    da xay auth-api that: benh nhan tu goi (role=patient) GIO DAY bi tuong
    tu tam JWT quyet dinh (get_current_patient_id bo qua field nay, xem
    backend/api/security.py) - field body chi con duoc TIN khi nguoi goi la
    doctor/caregiver/admin (goi ho benh nhan). TODO con lai: xoa han field
    nay khoi body (bat buoc moi client doc patient_id tu JWT, ke ca
    doctor/caregiver) - CHUA lam trong TASK-010 vi se pha vo bo test hien
    co dang truyen patient_id tuy y qua body (xem tests/conftest.py)."""

    patient_id: str = Field(..., min_length=1)
    dose_id: str | None = Field(default=None, description="dose_event_id neu utterance gan voi 1 lieu cu the")
    message: str = Field(..., min_length=1, max_length=5000)


class ClassificationOut(BaseModel):
    label: str  # TAKEN | MISSED | DELAYED | SIDE_EFFECT
    secondary_labels: list[str] = Field(
        default_factory=list, description="Luon rong o ban nay - chua lam multi-label classification"
    )
    confidence: float


class SourceOut(BaseModel):
    drug_id: str
    field: str  # field_group (cong_dung|tac_dung_phu|cach_dung|bao_quan)


class EscalationAckRequest(BaseModel):
    """POST /api/v1/escalations/{id}/ack (api-contracts.md §6, vong 2 muc 13).
    `resolved_by` KHONG co trong contract goc (gia dinh lay tu JWT/role that -
    api-contracts.md §1) - them tam vao body vi auth-api CHUA duoc xay (cung
    tinh trang voi `patient_id` trong ConversationChatRequest). TODO: doc tu
    JWT/session that khi auth-api co."""

    resolved_by: str = Field(..., min_length=1, description="vd 'doctor' hoac 'caregiver' - ai xac nhan da xu ly")


class EscalationAckResponse(BaseModel):
    id: str
    status: str
    resolved_at: str
    resolved_by: str


class ConversationChatResponse(BaseModel):
    """Response 200 cua POST /api/v1/chat (api-contracts.md §4). `severity`
    dung quy uoc tieng Anh (LOW|MEDIUM|HIGH) - xem SEVERITY_VI_TO_EN trong
    backend/services/severity.py cho chuyen doi tu ConversationState noi bo.

    `safety_flag`: TEN nay do api-contracts.md §4 quy dinh (KHONG duoc doi,
    se pha contract voi FE) nhung Y NGHIA RONG HON `ConversationState[
    "safety_flag"]` noi bo - xem backend/api/chat_routes.py::
    _should_show_emergency_overlay() cho ly do va cach map dung."""

    reply: str
    classification: ClassificationOut | None = None
    severity: str | None = None
    safety_flag: bool = False
    needs_clarification: bool = False
    sources: list[SourceOut] = Field(default_factory=list)
