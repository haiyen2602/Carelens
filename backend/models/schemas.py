from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login (api-contracts.md §1)."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """POST /api/v1/auth/register (api-contracts.md §1).

    Tu dang ky chi cho 2 role: `patient` (benh nhan/nguoi than dung chung) va
    `doctor`. `caregiver`/`admin` chi tao duoc qua account-api (§1b) boi admin.
    """

    full_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: Literal["doctor", "patient"] = "patient"


class VerifyEmailRequest(BaseModel):
    """POST /api/v1/auth/verify-email."""

    token: str = Field(..., min_length=1)


class ResendVerificationRequest(BaseModel):
    """POST /api/v1/auth/resend-verification."""

    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    """POST /api/v1/auth/forgot-password."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """POST /api/v1/auth/reset-password."""

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    """POST /api/v1/auth/change-password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    """`user` object trong response cua /auth/login (api-contracts.md §1)."""

    id: str
    full_name: str
    role: str
    is_email_verified: bool = True


class LoginResponse(BaseModel):
    """Response 200 cua POST /api/v1/auth/login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class ChangePasswordResponse(LoginResponse):
    """Response 200 cua POST /api/v1/auth/change-password.

    KE THUA LoginResponse (tra ca access_token + refresh_token MOI) vi doi mat
    khau THU HOI moi token cu (account.password_changed_at, migration 0018) -
    ke ca token cua chinh thiet bi vua goi. Neu chi tra `detail`, nguoi vua doi
    mat khau se bi dang xuat khoi chinh thiet bi cua minh ngay sau khi doi.
    Giu `detail` de phia client cu (chi doc `detail`) khong vo."""

    detail: str


class MeResponse(BaseModel):
    """GET /api/v1/auth/me."""

    id: str
    full_name: str
    email: str
    role: str
    is_email_verified: bool = True
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
    """GET /api/v1/photo-verifications/{id} — trang thai hien tai cua 1 lan gui anh.

    Cung dung cho GET /api/v1/doses/{id}/photo-verifications (liet ke lich su
    cac lan gui cua 1 lieu) - `created_at`/`has_image` them vao cho man hinh
    lich su benh nhan (patient/history), khong pha vo response cu vi la truong
    them, khong doi truong san co."""

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
    created_at: str
    has_image: bool


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


# ---------------------------------------------------------------------------
# THEM 2026-08-13 - reporting domain (adherence, danh sach escalation/
# audit-log cho dashboard bac si). Xem backend/api/reporting_routes.py va
# backend/services/reporting/adherence.py. CHUA co trong api-contracts.md -
# cung tinh trang voi PatientSummary/DoseSummary o tren (endpoint moi, chua
# duoc Architect duyet - ADR-0003).
# ---------------------------------------------------------------------------


class ReportingPatientOut(BaseModel):
    """GET /api/v1/reporting/patients - 1 dong trong danh sach benh nhan cua
    dashboard bao cao. `adherence_pct` co the None (chua co lieu nao den han
    - xem backend/services/reporting/adherence.py), KHONG suy ra la 0%."""

    id: str
    full_name: str
    year_of_birth: int | None = None
    note: str | None = None
    watch: bool
    adherence_pct: float | None = None


class PatientWatchUpdateRequest(BaseModel):
    watch: bool


class PatientWatchOut(BaseModel):
    id: str
    watch: bool


class EscalationOut(BaseModel):
    """GET /api/v1/escalations - 1 dong Escalation nguyen ven (khong tong hop
    gi them), xem backend/db/models.py::Escalation cho y nghia tung cot."""

    id: str
    patient_id: str
    dose_event_id: str | None = None
    severity: str
    trigger: str
    raw_utterance: str | None = None
    reason: str
    created_at: str
    status: str
    notified: list[str] = Field(default_factory=list)
    reminder_count: int
    last_reminder_at: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None


class AuditLogOut(BaseModel):
    """GET /api/v1/audit-log - 1 dong AuditLog nguyen ven. `trace` giu nguyen
    dinh dang JSON da luu (chatbot-rag-design.md muc 5.2), khong bien doi lai."""

    id: str
    patient_id: str
    dose_event_id: str | None = None
    utterance: str
    created_at: str
    trace: list
    final_response: str
    total_duration_ms: float


# ---------------------------------------------------------------------------
# THEM 2026-08-13 - caregiver/family domain (specs/user-roles.md: lien ket
# bac si<->benh nhan<->nguoi than, chi admin quan ly). Xem
# backend/api/caregiver_routes.py va backend/db/models.py::CaregiverLink.
# ---------------------------------------------------------------------------


class CaregiverLinkCreateRequest(BaseModel):
    caregiver_account_id: str = Field(..., min_length=1)
    patient_id: str = Field(..., min_length=1)
    relationship: str = Field(..., min_length=1)


class CaregiverLinkOut(BaseModel):
    """Response cua POST /api/v1/caregiver-links (tao moi)."""

    id: str
    caregiver_account_id: str
    patient_id: str
    relationship: str
    created_at: str
    status: str = "accepted"


class CaregiverLinkForPatientOut(BaseModel):
    """1 phan tu trong GET /api/v1/caregiver-links?patient_id=... - man hinh
    "nguoi lien he gia dinh" cua bac si khi xem 1 benh nhan. `caregiver_name`
    lay tu Account.full_name qua join, KHONG luu lai trung lap tren
    caregiver_link (tranh 2 nguon du lieu ten co the lech nhau khi nguoi
    dung doi ten tai khoan)."""

    id: str
    caregiver_account_id: str
    caregiver_name: str
    relationship: str
    created_at: str
    status: str = "accepted"


class CaregiverInviteCreateRequest(BaseModel):
    """POST /api/v1/caregiver-links/invites - benh nhan dang dang nhap tu
    moi 1 benh nhan khac de theo doi. `patient_id` la nguoi SE DUOC theo doi
    (khong phai nguoi gui loi moi - do la current_user)."""

    patient_id: str = Field(..., min_length=1)
    relationship: str = Field(..., min_length=1)


class PendingInviteOut(BaseModel):
    """1 phan tu trong GET /api/v1/caregiver-links/pending - loi moi CHUA
    duoc nguoi duoc theo doi chap nhan. `inviter_name` lay tu
    Account.full_name qua join, cung ly do voi caregiver_name o tren."""

    id: str
    caregiver_account_id: str
    inviter_name: str
    relationship: str
    created_at: str


class OpenEscalationBrief(BaseModel):
    """1 escalation OPEN rut gon, dung trong CaregiverMonitoredPatientOut ben
    duoi - man hinh caregiver chi can biet co canh bao gi dang mo, khong can
    day du nhu EscalationOut (xem GET /api/v1/escalations cho ban day du)."""

    id: str
    level: str
    title: str
    created_at: str


class DayAdherenceStatus(BaseModel):
    """1 ngay trong `week_history` cua CaregiverMonitoredPatientOut - suy ra
    tu cac DoseEvent trong ngay do (khong phai 1 cot rieng trong DB). Ngay
    khong co lieu nao duoc lich thi KHONG xuat hien trong mang (bo qua, xem
    backend/api/caregiver_routes.py)."""

    date: str  # "YYYY-MM-DD"
    status: str  # taken|late|missed


class CaregiverMonitoredPatientOut(BaseModel):
    """1 phan tu trong GET /api/v1/caregiver-links?caregiver_account_id=... -
    man hinh "nguoi than dang theo doi" cua chinh 1 tai khoan caregiver."""

    link_id: str
    patient_id: str
    full_name: str
    year_of_birth: int | None = None
    note: str | None = None
    relationship: str
    adherence_pct: float | None = None
    dose_taken_today: int
    dose_total_today: int
    open_escalations: list[OpenEscalationBrief] = Field(default_factory=list)
    week_history: list[DayAdherenceStatus] = Field(default_factory=list)


class DoseStatusUpdateRequest(BaseModel):
    """PATCH /api/v1/doses/{dose_id} (backend/api/dose_routes.py) - benh
    nhan/nguoi than/bac si tu cap nhat trang thai 1 lieu (vd tu bao "da
    uong" khong qua chatbot)."""

    status: str = Field(
        ..., description="PENDING|TAKEN|MISSED|DELAYED|CANCELLED|AWAITING_CAREGIVER"
    )
