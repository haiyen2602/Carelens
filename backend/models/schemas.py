from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, EmailStr, Field

from backend.services.email_identity import normalize_email

# SUA 2026-08-17 (yeu cau PM: "Google va dang nhap thu cong cung 1 email thi
# phai la CUNG 1 tai khoan"): chuan hoa email NGAY O BIEN thay vi o tung route.
# Truoc day "MCK@gmail.com" (dang ky thu cong) va "mck@gmail.com" (Google luon
# tra ve dang chuan) la 2 tai khoan khac nhau, vi `account.email` co UNIQUE
# nhung Postgres so sanh chuoi phan biet chu hoa/thuong.
#
# Dat o day (pydantic BeforeValidator) de dung duoc cho CA duong doc va duong
# ghi trong cung 1 dinh nghia: request nao khai bao `NormalizedEmail` thi email
# vao route DA la dang chuan, khong route nao phai tu nho goi .lower().
# `BeforeValidator` chay TRUOC EmailStr nen " MCK@Gmail.com " vua duoc lam sach
# vua van bi kiem tra dinh dang email.
NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email)]

# THEM 2026-08-21 (FB-08, FB-09): chan gia tri phi thuc te o chi so co the.
#
# Truoc day chi co `min`/`max` tren the <input> HTML, ma HTML bo qua duoc bang
# DevTools hoac curl - reviewer nhap chieu cao 18 cm van luu duoc.
#
# Day la chan CUNG: chi tu choi nhung gi KHONG THE la con nguoi. Muc dich la
# bat LOI NHAP LIEU (nham don vi "1.7" thay vi "170", thieu chu so "170"->"17",
# nham pound sang kg), khong phai ap dat chinh sach y khoa.
#
# Vi sao khong chon khoang hep hon nhu 140-200 (nguoi lon): product-vision.md
# khong gioi han app cho nguoi lon, chan cung o 140 nghia la khong ai dang ky
# duoc cho mot dua tre - hong am tham va kho chan doan hon nhieu so voi viec
# bo lot mot gia tri la. Khoang hep do thuoc tang canh bao mem o frontend.
#
#   40 cm  : thap hon moi tre so sinh du thang (45-55 cm) nen khong chan oan
#            nguoi that, dong thoi bat tron 18 / 17 / 1.7
#   250 cm : nguoi cao nhat tung ghi nhan la 272 cm, dung mot nguoi trong lich su
#   2 kg   : bao duoc tre so sinh du thang; tre sinh non duoi 1 kg nam long ap
#            trong benh vien, khong phai doi tuong cua app nhac uong thuoc
#   400 kg : cao hon moi benh nhan thuc te
CHIEU_CAO_CM_MIN, CHIEU_CAO_CM_MAX = 40.0, 250.0
CAN_NANG_KG_MIN, CAN_NANG_KG_MAX = 2.0, 400.0
TUOI_TOI_DA = 120

ChieuCaoCm = Annotated[float, Field(ge=CHIEU_CAO_CM_MIN, le=CHIEU_CAO_CM_MAX)]
CanNangKg = Annotated[float, Field(ge=CAN_NANG_KG_MIN, le=CAN_NANG_KG_MAX)]


def _kiem_ngay_sinh(gia_tri: date | None) -> date | None:
    """Ngay sinh phai o qua khu va trong vong TUOI_TOI_DA nam.

    Dung chung cho moi duong ghi ngay sinh - dat o schema chu khong o route de
    khong route nao phai tu nho goi lai.
    """
    if gia_tri is None:
        return gia_tri
    hom_nay = date.today()
    if gia_tri > hom_nay:
        raise ValueError("Ngày sinh không thể ở tương lai.")
    if gia_tri.year < hom_nay.year - TUOI_TOI_DA:
        raise ValueError(f"Ngày sinh không hợp lệ - vượt quá {TUOI_TOI_DA} tuổi.")
    return gia_tri


NgaySinh = Annotated[date, AfterValidator(_kiem_ngay_sinh)]


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login (api-contracts.md §1)."""

    email: NormalizedEmail
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """POST /api/v1/auth/register (api-contracts.md §1).

    SUA 2026-08-17 (yeu cau PM): tu dang ky CHI cho role `patient` (benh
    nhan/nguoi than dung chung). `doctor`/`caregiver`/`admin` chi tao duoc qua
    account-api (§1b) boi admin - truoc day `doctor` mo cho tu dang ky nen ai
    cung tao duoc tai khoan bac si va thay du lieu benh nhan.
    """

    full_name: str = Field(..., min_length=1, max_length=100)
    email: NormalizedEmail
    password: str = Field(..., min_length=8, max_length=128)
    role: Literal["patient"] = "patient"
    provider_account_id: str | None = None


class VerifyEmailRequest(BaseModel):
    """POST /api/v1/auth/verify-email."""

    token: str = Field(..., min_length=1)


class VerifyEmailSyncRequest(BaseModel):
    """POST /api/v1/auth/verify-email-sync (Supabase Auth Email Verification Sync)."""

    email: NormalizedEmail
    provider_account_id: str | None = None
    # Cho phep upsert: neu Account chua ton tai (backend register loi/race
    # condition) thi backend tu tao Account moi voi is_email_verified=True.
    # Lay tu Supabase user metadata (full_name).
    full_name: str | None = None


class ResendVerificationRequest(BaseModel):
    """POST /api/v1/auth/resend-verification."""

    email: NormalizedEmail


class ForgotPasswordRequest(BaseModel):
    """POST /api/v1/auth/forgot-password."""

    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    """POST /api/v1/auth/reset-password."""

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class ResetPasswordSyncRequest(BaseModel):
    """POST /api/v1/auth/reset-password-sync (Supabase Auth Reset Sync)."""

    email: NormalizedEmail
    new_password: str = Field(..., min_length=8, max_length=128)
    provider_account_id: str | None = None


class ChangePasswordRequest(BaseModel):
    """POST /api/v1/auth/change-password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class SetPasswordRequest(BaseModel):
    """POST /api/v1/auth/set-password (them 2026-08-17, api-contracts.md §1c).

    KHONG co `current_password` - day la diem khac biet duy nhat so voi
    ChangePasswordRequest, va la ly do endpoint nay phai ton tai rieng: tai
    khoan tao qua Google chua he co mat khau nguoi dung nao de nhap vao do.
    Bu lai, endpoint CHI nhan tai khoan `auth_provider="google"` - tai khoan
    da co mat khau van buoc phai di duong /auth/change-password (co xac minh
    mat khau cu), neu khong thi 1 access_token bi lo se doi duoc mat khau ma
    khong can biet mat khau cu."""

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


class OAuthLoginRequest(BaseModel):
    """POST /api/v1/auth/oauth/google - "Login with Google" (api-contracts.md §1).

    KHONG co `password`, KHONG co `role`: nguoi goi la Route Handler cua chinh
    frontend (server-to-server, chan bang header X-Internal-Secret), gui sang
    danh tinh Google DA duoc Better Auth xac thuc xong. Tai khoan tao qua duong
    nay luon la `patient` - giong rang buoc cua RegisterRequest (chi admin tao
    duoc doctor/caregiver/admin, xem §1b), khong the nang quyen bang cach tu go
    role vao body.

    `provider_account_id` la `sub` cua Google (dinh danh on dinh, KHONG doi khi
    nguoi dung doi email hien thi) - luu de doi chieu/ho tro dieu tra sau nay.
    Viec GHEP voi tai khoan cu van dua tren `email`: bang `account` chi co UNIQUE
    tren email, va Google da xac thuc chinh email do (email_verified).
    """

    email: NormalizedEmail
    full_name: str = Field(..., min_length=1, max_length=100)
    provider_account_id: str = Field(..., min_length=1)
    # Google tra `email_verified=false` cho mot so tai khoan Workspace cau hinh
    # dac biet. Fail-closed: backend TU CHOI (400) neu chua xac thuc, vi neu
    # khong, ai co email chua xac thuc trung voi 1 tai khoan mat khau san co se
    # chiem duoc tai khoan do.
    email_verified: bool = True


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
    # THEM (migration 0022) - chi co y nghia khi role="patient" (frontend
    # dung de quyet dinh co bat buoc redirect sang /onboarding/profile hay
    # khong). None cho role khac patient - CHUA co onboarding tuong tu cho
    # doctor/caregiver/admin.
    profile_completed: bool | None = None
    # THEM (migration 0025, Login with Google) - frontend dung de biet tai
    # khoan nay co mat khau hay khong: "google" => chua co, phai hien "Đặt mật
    # khẩu" (POST /auth/set-password) thay vi "Đổi mật khẩu" (doi mat khau cu
    # ma nguoi dung khong the co). Xem components/account-settings.tsx.
    auth_provider: str = "password"
    # THEM (migration 0052) - cung logic voi profile_completed o tren: chi co
    # y nghia khi role=patient (None cho role khac). Frontend doc gia tri nay
    # ngay tu /auth/me de trang "Hom nay" biet co bat buoc chup anh hay khong
    # ma khong can goi them API rieng.
    photo_capture_enabled: bool | None = None



AccountRole = Literal["doctor", "patient", "caregiver", "admin", "super_admin"]
AccountStatus = Literal["active", "locked"]


class AccountCreateRequest(BaseModel):
    """POST /api/v1/accounts (account-api, admin - xem specs/api-contracts.md
    muc them sau TASK-010). `patient_id`/`doctor_id`: lien ket TOI THIEU
    (text tu do, admin go tay khop du lieu demo co san vd 'demo-patient-01')
    - CHUA co UI chon tu danh sach, ngoai pham vi (xem tasks/TASK-010-auth-api.md)."""

    email: NormalizedEmail
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1)
    role: AccountRole
    patient_id: str | None = None
    doctor_id: str | None = None


class AccountStatusUpdateRequest(BaseModel):
    status: AccountStatus


class AccountUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: NormalizedEmail | None = None



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


class DrugCatalogResponse(BaseModel):
    """GET /api/v1/drugs/catalog - trang tra cuu cua bac si (duyet + loc + phan trang).

    `total` la tong so thuoc KHOP BO LOC (khong phai so item trang nay) - can
    de tinh so trang.
    """

    total: int
    items: list[DrugSummary]


class DrugFiltersResponse(BaseModel):
    """Cac gia tri co that trong danh muc, de do vao dropdown loc."""

    dang_thuoc: list[str]
    duong_dung: list[str]


class DrugDetail(DrugSummary):
    """GET /api/v1/drugs/{drug_id} - trang tra cuu thuoc cua bac si (chi doc).

    Khac DrugSummary o cho co them phan van ban mo ta lay tu `drug_chunks`.
    Chi tai khi bac si bam mo mot thuoc cu the, khong phai moi lan go phim -
    nen ly do "khong tra tac_dung_phu" cua DrugSummary khong ap dung o day.

    4 truong van ban co the None: moi 226/3562 thuoc da duoc embed. None =
    "chua co du lieu", KHONG phai loi.
    """

    danh_muc: str | None = None
    cong_dung: str | None = None
    tac_dung_phu: str | None = None
    cach_dung: str | None = None
    bao_quan: str | None = None


class PatientSummary(BaseModel):
    """GET /api/v1/patients — chua trong api-contracts.md, xem drug_routes.py."""

    id: str
    full_name: str
    year_of_birth: int | None = None
    note: str | None = None
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None


class PrescriptionItemIn(BaseModel):
    """Mot dong thuoc trong don. `drug_id` BAT BUOC (doi 2026-08-20, FB-14):
    danh muc `drug` la allowlist dong, khong con cho ke thuoc tu go tay.

    `ten_thuoc`/`dang_thuoc`/`duong_dung`/`ham_luong` van nhan de khong lam vo
    client cu, nhung BI BO QUA hoan toan: backend/services/prescription/
    service.py::_chuan_hoa_item doc lai ca 4 truong tu danh muc theo `drug_id`.
    Dung dua vao chung de hien thi - gia tri that nam trong response.

    `start_date`/`duration_days` la khoang ngay RIENG cua tung thuoc (vd 2
    thuoc trong cung 1 phac do nhung uong so ngay khac nhau) - None nghia la
    dung chung khoang ngay cua ca phac do (Prescription.start_date/
    duration_days), xem backend/services/scheduling/generator.py."""

    drug_id: str = Field(..., min_length=1)
    ten_thuoc: str | None = None
    dang_thuoc: str | None = None
    duong_dung: str | None = None
    ham_luong: str | None = None
    lieu_dung: str = Field(..., min_length=1)
    thoi_diem_dung: str | None = None
    so_vien_moi_lan: int | None = Field(default=None, gt=0)
    gio_nhac: list[str] = Field(default_factory=list, min_length=1)
    # DB-4E additive schedule fields. Older clients can omit all of them;
    # backend then derives doses/day from ``gio_nhac`` and writes no cycle.
    doses_per_day: int | None = Field(default=None, gt=0)
    has_cycle: bool = False
    cycle_on_days: int | None = Field(default=None, gt=0)
    cycle_off_days: int | None = Field(default=None, ge=0)
    start_date: str | None = None
    duration_days: int | None = Field(default=None, gt=0)


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


class PrescriptionUpdateRequest(BaseModel):
    """PUT /api/v1/prescriptions/{id} - sua thuoc/lich cua mot phac do dang
    `draft` hoac `active` (BR-1.3, business-rules.md). Ghi de toan bo `items`
    (khong merge tung dong) - don gian hon va dung voi cach form kê don gui
    len (luon gui lai ca danh sach thuoc)."""

    doctor_id: str = Field(..., min_length=1)
    items: list[PrescriptionItemIn] = Field(..., min_length=1)
    note: str | None = None


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
    # >0 CHI tren response cua PATCH /doses/{id} khi lan goi NAY vua cong
    # diem thuong (backend/api/dose_routes.py::_dose_summary) - THEM
    # 2026-08-26 de FE bao ngay "+N diem" (yeu cau UX, xem reward_ledger.py
    # ::award_dose_on_time). GET /doses (danh sach) luon tra 0.
    points_awarded: int = 0


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
    status: str  # dang_xu_ly|khop|lech|khong_xac_minh_duoc|loi_he_thong|do_tin_cay_thap
    matched: bool | None = None  # None khi con dang_xu_ly/loi_he_thong/do_tin_cay_thap
    expected_by_form: dict[str, int]
    detected_by_form: dict[str, int]
    confidence: str | None = None
    next_action: str | None = None  # None khi con dang_xu_ly/loi_he_thong/do_tin_cay_thap
    message: str
    created_at: str
    # >0 khi anh nay VUA duoc xac nhan khop va cong diem thuong (THEM
    # 2026-08-26, migration 0051 - xem backend/services/photo_verification/
    # verifier.py). None khi khong ap dung (chua xong/khong khop/tre...).
    points_awarded: int | None = None
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


class AgentV2ReadOnlyRequest(BaseModel):
    """Temporary BUILD-1 endpoint contract; no write action is representable."""

    patient_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=5000)


class AgentV2ReadOnlyResponse(BaseModel):
    status: str
    reply: str
    tools: list[str] = Field(default_factory=list)


class AgentV2OrchestrateRequest(BaseModel):
    """BUILD-16 end-to-end orchestration contract; still flag-gated OFF.

    ``conversation_id``/``session_id`` scope short-term memory recall to one
    conversation session; when omitted they default to one-shot values so a
    caller that does not track conversations yet still gets a valid, isolated
    run. ``dose_id`` is optional context only: Safety binds the occurrence
    from a verified server-side lookup, never from this field directly (see
    ``backend.agents.v2.orchestrator._resolve_occurrence``)."""

    patient_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_id: str | None = None
    session_id: str | None = None
    dose_id: str | None = None
    # BUILD-22 (optional): opts a caller into HTTP-level replay -- retrying
    # with the same key/actor/patient returns the identical prior response
    # instead of running the orchestrator (and creating a Doctor Handoff)
    # again. See backend.services.agent_idempotency. Omitted -> unchanged
    # BUILD-16 behavior (a fresh agent_run_id every call, no replay).
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    selected_action: "SuggestedActionIn | None" = None


class SuggestedActionIn(BaseModel):
    """Client echo of a server-issued action; authorization stays server-side."""

    action_id: str = Field(..., min_length=1, max_length=100)
    type: Literal["topic_followup", "drug_followup", "schedule_followup"]
    value: str = Field(..., min_length=1, max_length=80)
    entity_id: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=160)


class SuggestedActionOut(SuggestedActionIn):
    label: str = Field(..., min_length=1, max_length=100)


class AgentV2CitationOut(BaseModel):
    title: str
    source: str
    url: str | None = None


class AgentV2OrchestrateResponse(BaseModel):
    status: str
    reply: str
    intent: str
    tools: list[str] = Field(default_factory=list)
    citations: list[AgentV2CitationOut] = Field(default_factory=list)
    safety_disposition: str | None = None
    handoff_id: str | None = None
    # BUILD-42: user-safe handoff metadata (spec SS14) -- SAFETY/UNCERTAINTY/
    # USER_REQUEST, derived server-side (see answerability.handoff_type_for),
    # never a raw internal reason_code, risk score, or Judge output.
    handoff_required: bool = False
    handoff_type: str | None = None
    trace_id: str
    agent_run_id: str
    suggested_actions: list[SuggestedActionOut] = Field(default_factory=list)


class DrugImageCandidateOut(BaseModel):
    """Patient-safe B-07 visual candidate; no score/OCR/provenance leaks."""

    action_id: str = Field(min_length=1, max_length=200)
    product_display_name: str = Field(min_length=1, max_length=300)
    strength_text: str | None = Field(default=None, max_length=160)
    rank: int = Field(ge=1, le=3)


class DrugImageRecognitionOut(BaseModel):
    status: Literal[
        "CANDIDATES",
        "INSUFFICIENT_EVIDENCE",
        "SAFETY_DEFERRED",
        "DOCTOR_ACTIVE",
        "RECOGNITION_UNAVAILABLE",
    ]
    reply: str
    recognition_attempt_id: str | None = None
    outcome: str | None = None
    recognition_version: str | None = None
    candidates: list[DrugImageCandidateOut] = Field(default_factory=list)
    requested_attribute: str | None = None


class DrugImageConfirmRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1, max_length=200)
    recognition_attempt_id: str = Field(min_length=1, max_length=200)
    action_id: str = Field(min_length=1, max_length=200)


class DrugImageConfirmOut(BaseModel):
    status: Literal["CONFIRMED"]
    reply: str
    recognition_attempt_id: str
    canonical_drug_product_id: str
    requested_attribute: str | None = None
    tools: list[str] = Field(default_factory=list)


# BUILD-29: user feedback ticket + session/trace issue tracking. See
# backend/services/agent_feedback.py for the authorization/idempotency/
# auto-classification logic these schemas are the wire contract for.
AgentFeedbackReason = Literal[
    "WRONG_ANSWER",  # Trả lời sai
    "NOT_UNDERSTOOD",  # Không hiểu câu hỏi
    "WRONG_MEDICATION_INFO",  # Sai thông tin thuốc/lịch thuốc
    "UNSAFE_OR_INAPPROPRIATE",  # Câu trả lời không phù hợp/an toàn
    "TECHNICAL_ERROR",  # Phản hồi bị lỗi
    "OTHER",  # Khác
]
AgentFeedbackStatus = Literal["OPEN", "INVESTIGATING", "FIXED", "CLOSED", "WONT_FIX"]
AgentFeedbackPriority = Literal["P0", "P1", "P2", "P3"]


class AgentFeedbackCreateRequest(BaseModel):
    """POST /agent/v2/feedback -- deliberately carries NO patient_id/actor_id
    field at all (see ``create_ticket``: both are always bound server-side
    from the authenticated JWT, never trusted from the client). Every other
    field here is exactly what the client already received back from the
    real ``/agent/v2/orchestrate`` call being reported (or, for the message
    text, what it already rendered) -- the user never types a trace/session
    id by hand.
    """

    conversation_id: str = Field(..., min_length=1)
    trace_id: str | None = Field(default=None, min_length=1)
    agent_run_id: str = Field(..., min_length=1)
    user_message: str = Field(..., min_length=1, max_length=5000)
    assistant_message: str = Field(..., min_length=1, max_length=10000)
    reason: AgentFeedbackReason
    user_note: str | None = Field(default=None, max_length=1000)


class AgentFeedbackTicketOut(BaseModel):
    """Admin-facing ticket representation -- returned by the list/detail/
    update endpoints, all gated behind ``require_role("admin")``."""

    id: str
    actor_id: str
    patient_id: str
    conversation_id: str
    trace_id: str | None
    agent_run_id: str
    user_message: str
    assistant_message: str
    reason: AgentFeedbackReason
    user_note: str | None
    chatbot_version: str
    status: AgentFeedbackStatus
    priority: AgentFeedbackPriority
    p0_review_required: bool
    admin_note: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class AgentFeedbackTicketListOut(BaseModel):
    items: list[AgentFeedbackTicketOut]
    total: int
    limit: int
    offset: int


class AgentFeedbackTraceSummaryOut(BaseModel):
    """Sanitized trace detail for one ticket -- deliberately the same shape
    already exposed by GET /admin/rag/traces/{trace_id} (no new Trace
    Explorer built here, per instruction), never the model's own hidden
    chain-of-thought (Agent V2 never persists that to telemetry at all --
    only the final response text and structured tool/safety/handoff
    observations, see backend/api/agent_v2_routes.py::_record_agent_v2_telemetry).
    ``None`` when the trace has aged out of the in-memory buffer (BUILD-25's
    documented limitation: at most the last 200 traces process-wide,
    reset on every deploy) -- the ticket itself still carries the reported
    text either way.
    """

    trace_id: str
    found: bool
    intent: str | None = None
    tools: list[str] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    safety_outcome: str | None = None
    handoff_created: bool = False
    model: str | None = None
    latency_ms: float | None = None
    scores: dict[str, float | int | str | bool] = Field(default_factory=dict)
    final_response: str | None = None
    status: str | None = None


class AgentFeedbackSessionMessageOut(BaseModel):
    """One turn in the ticket's conversation, for the Admin session view
    (BUILD-29 §6) -- sourced from the same telemetry trace buffer as
    /admin/rag/traces, filtered by session_id == the ticket's
    conversation_id, never a new persistence layer."""

    trace_id: str
    timestamp: datetime
    query_preview: str
    final_answer_preview: str
    status: str
    is_reported_turn: bool


class AgentFeedbackSessionOut(BaseModel):
    conversation_id: str
    items: list[AgentFeedbackSessionMessageOut]
    total: int
    limit: int
    offset: int


class AgentFeedbackJudgeOut(BaseModel):
    """BUILD-33 §11/§12: ticket detail's view of the durable Judge V2 result
    for this same run's ``agent_run_id``, when one exists (``None`` on the
    parent field when it does not -- see
    ``backend.services.agent_feedback.judge_result_out``, never a fabricated
    pending/empty result). Deliberately excludes the raw sanitized query/
    response snapshot -- the ticket's own ``user_message``/
    ``assistant_message`` already carry that text; this schema is
    provenance + score only, per BUILD-33 §8."""

    judge_status: str
    judge_provider: str
    judge_model: str
    rubric_name: str
    rubric_version: str
    judge_prompt_version: str
    eligibility_reason: str
    overall_score: float | None = None
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    confidence: float | None = None
    failure_reason: str | None = None
    evaluated_at: datetime | None = None


class AgentFeedbackEvaluationOut(BaseModel):
    """BUILD-36: ticket detail's view of this run's durable Evaluation V2
    result (backend.db.models.AgentRunEvaluation) -- already the sanitized
    status/source/reason-per-metric shape ``evaluation_v2.dispatch_
    evaluation`` produces (never a numeric heuristic score, which is
    ring-buffer-only, see BUILD-36 report's own audit). ``None`` on the
    parent field when no row exists (a pre-BUILD-32 run, or a durable-read
    hiccup) -- never a fabricated disposition."""

    evaluation_version: str
    execution_path: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentFeedbackSafetyOut(BaseModel):
    """BUILD-36: ticket detail's view of this run's real Safety/Handoff
    event (backend.db.models.AgentSafetyEvent), live-joined against
    DoctorReviewRequest exactly like every other BUILD-34 read -- never the
    row's own stale snapshot. ``None`` on the parent field when this run
    never triggered Safety (the overwhelming majority of tickets)."""

    outcome: str
    reason_code: str
    severity: str
    handoff_required: bool
    handoff_created: bool
    handoff_id: str | None = None
    handoff_status_live: str | None = None
    handoff_resolved: bool = False
    assigned_doctor_id: str | None = None
    time_to_review_seconds: float | None = None


class AgentFeedbackTicketDetailOut(BaseModel):
    ticket: AgentFeedbackTicketOut
    trace: AgentFeedbackTraceSummaryOut
    judge: AgentFeedbackJudgeOut | None = None
    evaluation: AgentFeedbackEvaluationOut | None = None
    safety: AgentFeedbackSafetyOut | None = None


class AgentFeedbackTicketUpdateRequest(BaseModel):
    """PATCH /admin/tickets/{id} -- every field optional so an Admin can
    update just one at a time. ``priority``/``status`` here are the ONLY
    place either can change after ticket creation (the creating patient
    never supplies either -- see AgentFeedbackCreateRequest)."""

    status: AgentFeedbackStatus | None = None
    priority: AgentFeedbackPriority | None = None
    admin_note: str | None = Field(default=None, max_length=2000)


# BUILD-30: user-visible, patient-safe activity timeline. Deliberately a
# SEPARATE, much narrower contract than AgentFeedbackTraceSummaryOut
# (BUILD-29's admin-only trace summary) -- see
# backend.services.agent_activity.build_activity_timeline's own docstring
# for exactly which fields are allowed and why (never prompts, model
# reasoning, raw tool arguments/results, DB rows, JWT/patient_id, secrets,
# or internal policy text).
class AgentActivityItemOut(BaseModel):
    type: str
    label: str
    status: str
    duration_ms: float | None = None
    source_count: int | None = None


class AgentActivityOut(BaseModel):
    trace_id: str
    available: bool
    activities: list[AgentActivityItemOut] = Field(default_factory=list)


class ClassificationOut(BaseModel):
    label: str  # TAKEN | MISSED | DELAYED | SIDE_EFFECT
    secondary_labels: list[str] = Field(
        default_factory=list, description="Luon rong o ban nay - chua lam multi-label classification"
    )
    confidence: float


class SourceOut(BaseModel):
    drug_id: str
    field: str  # field_group (cong_dung|tac_dung_phu|cach_dung|bao_quan)


class EscalationAckResponse(BaseModel):
    """POST /api/v1/escalations/{id}/ack (api-contracts.md §6, vong 2 muc
    13). `resolved_by` truoc day nhan tu request body (TODO tam thoi luc
    chua co JWT that) - tu 2026-08-20 doc thang tu JWT (current_user) trong
    backend/api/escalation_routes.py, khong con nhan tu client nua."""

    id: str
    status: str
    resolved_at: str
    resolved_by: str


# `DISMISSED` = bac si da xem va danh gia KHONG can xu ly - khac "RESOLVED"
# (da xu ly that). Them 2026-08-23 cho nut "Tu choi" o Hop canh bao
# (frontend/src/app/doctor/alerts/page.tsx), truoc do trang thai nay chi song
# trong state React nen mat khi tai lai trang. Escalation.status la cot String
# thuong (khong phai Enum/CHECK ben DB) nen KHONG can migration - nhung
# escalation_reminder.py chi quet status="OPEN", nghia la chuyen sang ACKED
# hay DISMISSED deu DUNG nhac lai, giong RESOLVED.
ESCALATION_STATUSES = ("OPEN", "ACKED", "RESOLVED", "DISMISSED")


class EscalationStatusUpdateRequest(BaseModel):
    """PATCH /api/v1/escalations/{id}/status - dat trang thai TUY Y (khac
    /ack chi mot chieu -> RESOLVED). Cho phep quay ve "OPEN" de nguoi dung
    hoan tac ngay sau khi bam nham (nut "Hoàn tác" trong toast o FE)."""

    status: Literal["OPEN", "ACKED", "RESOLVED", "DISMISSED"]


class EscalationStatusResponse(BaseModel):
    """`resolved_at`/`resolved_by` la None khi trang thai quay ve OPEN/ACKED
    (hai truong nay chi co nghia khi canh bao da duoc chot lai) - KHAC
    EscalationAckResponse o tren luon co gia tri vi chi di mot chieu."""

    id: str
    status: str
    resolved_at: str | None = None
    resolved_by: str | None = None


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
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    # Benh nhan tu nhap o onboarding (migration 0022), co the con None. Them
    # 2026-08-23 de bac si goi thang tu Hop canh bao thay vi phai doi trang -
    # endpoint nay da la require_role("doctor","admin") san.
    phone: str | None = None
    watch: bool
    adherence_pct: float | None = None


class DoseDayOut(BaseModel):
    """1 ngay trong bieu do "Tinh trang lieu trong 7 ngay" (trang Tong quan
    thong tin cua bac si). `date` la ngay theo GIO VIET NAM, khong phai UTC -
    xem ghi chu ve mui gio trong reporting_routes.py::get_dose_summary.

    `total` = taken + delayed + missed, tuc chi cac lieu DA CO KET QUA. Lieu
    con PENDING/AWAITING_CAREGIVER khong nam trong day - cung nguyen tac voi
    compute_adherence_pct() (khong dua lieu chua den han vao mau)."""

    date: str
    taken: int
    delayed: int
    missed: int
    total: int


class MissedWindowOut(BaseModel):
    """1 cot trong bieu do "Khung gio hay bo lo" - dem so lieu MISSED theo
    khung gio trong ngay (gio Viet Nam)."""

    key: str  # morning|noon|afternoon|evening
    label: str
    missed: int


class AdherenceBucketOut(BaseModel):
    """1 nhom trong bieu do "Phan bo muc tuan thu". `key="no_data"` la nhom
    benh nhan CHUA co lieu nao den han trong ky - truoc day nhom nay chi nam
    o mot dong chu nho duoi tieu de, trong khi thuc te no thuong la nhom DONG
    NHAT (vd 53/67), tuc bieu do dang giau di phan lon benh nhan."""

    key: str  # good|fair|poor|bad|no_data
    label: str
    count: int


class PatientAdherenceOut(BaseModel):
    """Tuan thu cua 1 benh nhan TRONG KY dang xem (khong phai tu truoc toi
    nay). `adherence_pct=None` = chua co lieu nao den han trong ky.

    `due` di kem de giao dien biet mau to hay nho: "bo lo 100%" cua 1 lieu va
    cua 200 lieu la hai cau chuyen khac han nhau."""

    patient_id: str
    full_name: str
    note: str | None = None
    adherence_pct: float | None = None
    due: int
    taken: int


class PeriodTotalsOut(BaseModel):
    """Tong hop CA KY - dung cho ky hien tai lan ky lien truoc (so sanh xu
    huong). Ky truoc dai dung bang ky hien tai va ke sat phia truoc, de mui
    ten tang/giam so cung do dai thoi gian."""

    average_adherence_pct: float | None = None
    due: int
    taken: int
    delayed: int
    missed: int


class DoseSummaryOut(BaseModel):
    """GET /api/v1/reporting/dose-summary - MOT nguon duy nhat cho ca trang
    "Tong quan thong tin", gop lai vi tat ca deu quet CUNG mot tap DoseEvent.

    Vi sao gop het vao day thay vi de frontend tu tinh tu `patients`: truoc
    2026-08-23 the "Tuan thu trung binh" lay tu compute_adherence_pct() -
    tinh tren TOAN BO lieu tu truoc toi nay - con cac bieu do ben canh chi
    7 ngay. Hai con so canh nhau nhung khac cua so thoi gian, khong dong nao
    noi cho nguoi doc biet, nen trang vua bao "1.46%" vua cho thay "6/7 ngay
    khong co lieu nao". Gio moi so lieu tren trang deu thuoc DUNG mot ky.

    `patient_count` = so benh nhan trong pham vi, de giao dien phan biet
    "khong co lieu nao" voi "chua theo doi benh nhan nao" - hai tinh huong
    deu cho bieu do rong nhung loi khuyen cho bac si khac han."""

    days: int
    from_date: str  # YYYY-MM-DD, gio Viet Nam
    to_date: str
    patient_count: int
    with_data_count: int
    without_data_count: int
    high_risk_count: int
    current: PeriodTotalsOut
    previous: PeriodTotalsOut
    buckets: list[AdherenceBucketOut]
    patients: list[PatientAdherenceOut]
    daily: list[DoseDayOut]
    missed_by_window: list[MissedWindowOut]


class PatientWatchUpdateRequest(BaseModel):
    watch: bool


class PatientWatchOut(BaseModel):
    id: str
    watch: bool


class PatientHealthUpdateRequest(BaseModel):
    """PATCH /api/v1/patients/{id} - sua tab "Tinh trang suc khoe". Tat ca
    field deu optional (partial update) - None nghia la "khong doi", KHONG
    phai "xoa ve rong" (chua co nhu cau xoa ve None qua API nay)."""

    note: str | None = None
    gender: str | None = None
    height_cm: ChieuCaoCm | None = None
    weight_kg: CanNangKg | None = None


class PatientProfileUpdateRequest(BaseModel):
    """PATCH /api/v1/patients/me - benh nhan tu dien thong tin ca nhan o
    trang onboarding (migration 0022). Tat ca field optional (partial
    update, cung quy uoc voi PatientHealthUpdateRequest o tren) - nhung
    frontend yeu cau nhap du date_of_birth/phone/address/gender/height_cm/weight_kg truoc khi
    goi, de lan goi dau tien la lan danh dau profile_completed=True."""

    date_of_birth: NgaySinh | None = None
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    gender: str | None = None
    height_cm: ChieuCaoCm | None = None
    weight_kg: CanNangKg | None = None
    # THEM (migration 0052) - man hinh Cai dat cho benh nhan tu bat/tat yeu
    # cau chup anh khi xac nhan uong thuoc, xem Patient.photo_capture_enabled.
    photo_capture_enabled: bool | None = None


class PatientProfileOut(BaseModel):
    """GET/PATCH /api/v1/patients/me."""

    id: str
    full_name: str
    date_of_birth: date | None = None
    year_of_birth: int | None = None
    phone: str | None = None
    address: str | None = None
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    profile_completed: bool = False
    photo_capture_enabled: bool = True


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
    # Lay tu Account.email qua CUNG cai join da co san (khong them truy van).
    # Day la cach lien lac DUY NHAT toi nguoi than ma he thong dang luu -
    # caregiver_link va account deu KHONG co cot so dien thoai. Them
    # 2026-08-23 cho khoi "Liên hệ người thân" trong Hop canh bao cua bac si.
    caregiver_email: str | None = None
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


class SentInviteOut(BaseModel):
    """1 phan tu trong GET /api/v1/caregiver-links/sent - loi moi CHINH nguoi
    dang dang nhap da gui (voi tu cach caregiver_account_id qua POST
    .../invites), con "pending". Chieu NGUOC voi PendingInviteOut o tren (do
    la loi moi NGUOI KHAC gui toi minh). `patient_name` lay tu
    Patient.full_name qua join, cung ly do voi caregiver_name/inviter_name."""

    id: str
    patient_id: str
    patient_name: str
    relationship: str
    created_at: str


class NudgeCreateRequest(BaseModel):
    """POST /api/v1/nudges - nguoi than dang dang nhap gui 1 loi nhac nhe cho
    `patient_id` ho dang theo doi (accepted). `caregiver_account_id` KHONG
    nam trong body - lay tu current_user, cung pattern voi
    CaregiverInviteCreateRequest."""

    patient_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class NudgeOut(BaseModel):
    """Response cua POST /api/v1/nudges va GET /api/v1/nudges/unseen.
    `caregiver_name` lay tu Account.full_name qua join, cung ly do voi
    caregiver_name tren CaregiverLinkForPatientOut."""

    id: str
    caregiver_account_id: str
    caregiver_name: str
    patient_id: str
    message: str
    created_at: str


class HealthLogCreateRequest(BaseModel):
    """POST /api/v1/health-log - benh nhan tu ghi nhat ky suc khoe
    (frontend/src/app/patient/health/page.tsx). `level` khop AlertLevel phia
    frontend (low|mid|high) - "low" chi luu nhat ky rieng cho benh nhan xem
    lai (KHONG tao Escalation), "mid"/"high" moi tao Escalation that de
    nguoi than/bac si thay, xem backend/api/health_log_routes.py."""

    text: str = Field(default="", description="Mo ta trieu chung - co the rong")
    level: Literal["low", "mid", "high"]


class HealthLogCreateResponse(BaseModel):
    escalation_id: str | None = Field(
        default=None, description="None neu level=low (khong tao Escalation)"
    )


class PushSubscribeKeys(BaseModel):
    """2 khoa trinh duyet cap de MA HOA payload push - khong co chung thi
    dich vu day chi chuyen duoc goi tin rong."""

    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


class PushSubscribeRequest(BaseModel):
    """POST /api/v1/push/subscribe - shape khop nguyen ven doi tuong
    PushSubscription.toJSON() cua trinh duyet, de frontend gui thang khong
    phai nan lai. `patient_id` KHONG nam trong body - lay tu JWT."""

    endpoint: str = Field(..., min_length=1)
    keys: PushSubscribeKeys


class PushVapidKeyResponse(BaseModel):
    public_key: str = Field(default="", description="Rong = chua cau hinh VAPID, push tat")


class TelegramLinkStartResponse(BaseModel):
    """POST /api/v1/telegram/link-token - link benh nhan bam de ghep tai khoan.

    Tra ve ca `deep_link` da lap san thay vi de frontend tu noi chuoi: username
    bot nam o config backend, frontend khong nen giu ban sao thu hai (cung ly
    do voi VAPID public key o tren)."""

    deep_link: str = Field(..., description="https://t.me/<bot>?start=<token>")
    expires_in_seconds: int


class TelegramStatusResponse(BaseModel):
    """GET /api/v1/telegram/status - frontend hien nut 'Kết nối' hay 'Đã kết nối'."""

    configured: bool = Field(..., description="False = server chua cau hinh bot, an tinh nang di")
    linked: bool
    username: str | None = None
    # TACH BIET voi `linked`: da noi tai khoan (linked) nhung tam tat nhac
    # (enabled=False) la trang thai hop le - frontend hien cong tac o vi tri
    # tat, KHONG hien nut "Kết nối" lai.
    enabled: bool = False


class TelegramPreferenceRequest(BaseModel):
    """PATCH /api/v1/telegram/link - bat/tat nhac Telegram, GIU lien ket."""

    enabled: bool


class NotificationPrefResponse(BaseModel):
    """GET /api/v1/notifications/preferences - man hinh Cai dat 2 tang.

    Gom CA tuy chon Telegram vao day du no luu o bang khac
    (telegram_link.enabled): man hinh Cai dat ve 1 khoi thong bao duy nhat,
    bat frontend goi 2 endpoint roi tu ghep lai chi de lo chi tiet luu tru
    o dau la viec khong can thiet."""

    # HAI CO KHONG LOAI TRU NHAU - 1 nguoi vua co lich uong thuoc cua chinh
    # minh vua theo doi bo/me la chuyen binh thuong. Frontend dung 2 co nay
    # de quyet dinh hien phan nao, KHONG dua vao Account.role (chi giu duoc
    # 1 gia tri nen se cat mat 1 nua vai tro).
    is_patient: bool = True
    is_caregiver: bool = False
    dose_reminder_enabled: bool
    web_push_enabled: bool
    telegram_configured: bool = Field(..., description="False = server chua cau hinh bot, an muc Telegram")
    telegram_linked: bool
    telegram_enabled: bool
    telegram_username: str | None = None


class NotificationPrefRequest(BaseModel):
    """PATCH /api/v1/notifications/preferences.

    MOI truong deu None-able va chi ap dung truong duoc gui: man hinh Cai dat
    gat 1 cong tac tai 1 thoi diem, gui ca cum se ghi de nham gia tri cong
    tac kia neu benh nhan dang mo 2 tab."""

    dose_reminder_enabled: bool | None = None
    web_push_enabled: bool | None = None


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


class SystemAuditLogOut(BaseModel):
    id: str
    actor_id: str | None = None
    actor_name: str
    actor_role: str
    action: str
    target: str | None = None
    created_at: datetime


class SystemAuditLogListResponse(BaseModel):
    items: list[SystemAuditLogOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# BUILD-44: Doctor Chat Queue & Takeover. Wire contract for
# backend/api/doctor_review_routes.py -- reads backend/services/
# doctor_handoff.py's DoctorReviewRequest/DoctorReviewMessage rows only;
# never exposes verified_context_refs/agent_summary raw internals (SS4:
# "no hidden reasoning, no raw Judge output, no chain-of-thought").
# ---------------------------------------------------------------------------


class DoctorReviewQueueItemOut(BaseModel):
    handoff_id: str
    patient_id: str
    patient_name: str
    conversation_id: str | None = None
    handoff_type: str
    reason_code: str
    risk_disposition: str
    status: str
    patient_question: str
    created_at: datetime
    assigned_doctor_id: str | None = None
    assigned_at: datetime | None = None
    activated_at: datetime | None = None
    resolved_at: datetime | None = None


class DoctorReviewQueueResponse(BaseModel):
    items: list[DoctorReviewQueueItemOut]
    total: int


class DoctorReviewMessageOut(BaseModel):
    id: str
    sender_role: str
    actor_id: str | None = None
    content: str
    created_at: datetime
    image_attachment_id: str | None = None


class DoctorReviewDetailOut(BaseModel):
    handoff_id: str
    patient_id: str
    patient_name: str
    conversation_id: str | None = None
    handoff_type: str
    reason_code: str
    risk_disposition: str
    status: str
    patient_question: str
    created_at: datetime
    assigned_doctor_id: str | None = None
    assigned_at: datetime | None = None
    activated_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by_doctor_id: str | None = None
    messages: list[DoctorReviewMessageOut] = Field(default_factory=list)


class DoctorReviewSendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class PatientHandoffStatusOut(BaseModel):
    """GET /api/v1/agent/v2/handoff/status (backend/api/agent_v2_routes.py)
    -- the patient's own view of their current handoff, if any. Never
    exposes ``assigned_doctor_id``/other patients' data; only what this
    patient is authorized to see about their own episode."""

    has_active_handoff: bool
    handoff_id: str | None = None
    handoff_type: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    activated_at: datetime | None = None
    messages: list[DoctorReviewMessageOut] = Field(default_factory=list)
