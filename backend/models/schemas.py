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


class DrugSummary(BaseModel):
    """Mot thuoc trong ket qua tra cuu danh muc (GET /api/v1/drugs).

    Du de dien mot dong thuoc vao don, khong hon. KHONG co tac_dung/
    tac_dung_phu - nhung thu do thuoc luong RAG (drug_chunks), tra kem o day
    se khien o tim kiem tai ve hang chuc KB van ban cho MOI lan go phim.

    `dang_thuoc` la truong quan trong nhat: no quyet dinh mot lieu co xac minh
    duoc bang anh hay khong (backend/services/photo_verification/dosage_form.py).
    """

    drug_id: str
    ten_thuoc: str
    dang_thuoc: str
    duong_dung: str
    ham_luong: str | None = None
    tong_so_luong: str | None = None
    muc_nghiem_trong: str | None = None


class DrugSearchResponse(BaseModel):
    query: str
    count: int
    items: list[DrugSummary]


class PatientSummary(BaseModel):
    """GET /api/v1/patients — chua trong api-contracts.md, xem drug_routes.py."""

    id: str
    full_name: str
    year_of_birth: int | None = None
    note: str | None = None


class PrescriptionItemIn(BaseModel):
    """Mot dong thuoc trong don. `drug_id` rong van hop le (bac si tu go ten
    khong co trong danh muc) - se duoc chuan hoa lai o backend/services/
    prescription/service.py::_chuan_hoa_item, KHONG tin dang_thuoc/duong_dung
    trinh duyet gui len."""

    drug_id: str | None = None
    ten_thuoc: str = Field(..., min_length=1)
    dang_thuoc: str | None = None
    duong_dung: str | None = None
    ham_luong: str | None = None
    lieu_dung: str = Field(..., min_length=1)
    thoi_diem_dung: str | None = None
    so_vien_moi_lan: int | None = Field(default=None, gt=0)
    gio_nhac: list[str] = Field(default_factory=list, min_length=1)


class PrescriptionCreateRequest(BaseModel):
    """POST /api/v1/prescriptions (api-contracts.md §2).

    `doctor_id` KHONG co trong contract goc (gia dinh lay tu JWT - api-
    contracts.md §1), them tam vao body cung ly do voi `patient_id` trong
    ConversationChatRequest: auth-api CHUA duoc xay trong repo nay.
    TODO: xoa field nay khoi body, doc tu JWT khi auth-api co that."""

    patient_id: str = Field(..., min_length=1)
    doctor_id: str = Field(..., min_length=1)
    items: list[PrescriptionItemIn] = Field(..., min_length=1)
    note: str | None = None
    start_date: str | None = None
    duration_days: int | None = Field(default=None, gt=0)


class PrescriptionDecisionRequest(BaseModel):
    """Body chung cho approve/reject/stop - chi can biet ai quyet dinh."""

    doctor_id: str = Field(..., min_length=1)


class PrescriptionOut(BaseModel):
    """PrescriptionDTO (api-contracts.md §2, §8)."""

    id: str
    patient_id: str
    doctor_id: str
    status: str
    items: list[dict]
    note: str | None = None
    start_date: str
    duration_days: int
    approved_by: str | None = None
    approved_at: str | None = None


class PrescriptionApproveResponse(BaseModel):
    id: str
    status: str
    approved_by: str
    approved_at: str
    dose_events_created: int


class PrescriptionListResponse(BaseModel):
    items: list[PrescriptionOut]


class DoseSummary(BaseModel):
    """GET /api/v1/doses?patient_id= — chua trong api-contracts.md dung dinh
    dang day du (thieu reminder_level/evidence, khong co cot tuong ung trong
    DoseEvent hien tai) - chi du de trang benh nhan biet lieu nao dang PENDING
    va can gi de chup anh. Can Architect duyet truoc khi coi la contract on
    dinh (ADR-0003)."""

    id: str
    prescription_id: str
    scheduled_at: str
    window_start: str
    window_end: str
    status: str
    expected_items: list[dict]


class PhotoSubmitResponse(BaseModel):
    """POST /api/v1/doses/{id}/photo — 202, chua co ket qua.

    KHAC api-contracts.md §5 (dang response 200 dong bo voi matched/
    detected_count ngay lap tuc): mot lan goi mo hinh do duoc 26-265 giay,
    qua lau de giu trong 1 request HTTP. Frontend phai hoi lai qua GET
    /api/v1/photo-verifications/{verification_id}. CHUA duoc cap nhat vao
    api-contracts.md - can Architect duyet truoc khi coi la on dinh (ADR-0003)."""

    verification_id: str
    status: str  # luon la "dang_xu_ly" ngay sau khi gui
    attempt: int
    max_attempts: int
    message: str


class PhotoVerificationOut(BaseModel):
    """GET /api/v1/photo-verifications/{id} — trang thai hien tai cua 1 lan gui anh."""

    id: str
    dose_event_id: str
    attempt: int
    max_attempts: int
    status: str  # dang_xu_ly|khop|lech|khong_xac_minh_duoc|loi_he_thong
    matched: bool | None = None  # None khi con dang_xu_ly hoac loi_he_thong
    expected_by_form: dict[str, int]
    detected_by_form: dict[str, int]
    confidence: str | None = None
    next_action: str | None = None  # None khi con dang_xu_ly hoac loi_he_thong
    message: str


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


class CurrentEscalationResponse(BaseModel):
    """GET /api/v1/escalations/current (vong 2 muc 4 y 4 - CAN CHOT, PM chot
    2026-08-12: dung field da co san tren Escalation, khong them cot moi).
    FE goi de quyet dinh co hien banner "de xuat goi cap cuu" lien tuc tu
    t=15p (escalation_reminder.py) toi khi resolved hay khong - shape TAM
    THOI, chua trao doi voi team app (cung tinh trang #22)."""

    status: str  # OPEN|ACKED|RESOLVED
    severity: str  # LOW|MEDIUM|HIGH
    reminder_count: int
    created_at: str


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
    # Vong 3 muc 6.1 (#22 - PM cho build truoc, CHUA xac nhan shape voi team
    # app, xem tasks/TASK-010-build-chatbot.md "Con mo"). None/rong = FE
    # khong hien nut goi y, chi co o textbox tu do nhu binh thuong.
    quick_replies: list[str] | None = None


# ---------------------------------------------------------------------------
# Vong 3, muc 7.1 (chatbot-rag-design.md muc 10 #26) - endpoint xem/xoa lich
# su chat. SHAPE TAM THOI - CHUA trao doi voi team app (cung tinh trang nhu
# #22 quick_replies) - dung POST (khong phai GET/DELETE chuan REST) de tai
# su dung dung 1 cho noi get_current_patient_id() (chi nhan duoc than co
# .patient_id tu body, xem backend/api/security.py) thay vi tu doc query
# param o day, giu dung nguyen tac "1 CHO NOI DUY NHAT" cho patient_id.
# -----------------------------------------------------------------------------


class ChatHistoryRequest(BaseModel):
    patient_id: str = Field(..., min_length=1)


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageOut] = Field(default_factory=list)


class ChatHistoryHideResponse(BaseModel):
    hidden_count: int
