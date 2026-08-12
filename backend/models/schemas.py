from pydantic import BaseModel, Field


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
    khong nam trong pham vi Phase 0-7 cua build-kickoff-prompt.md). TODO:
    xoa field nay khoi body, doc tu JWT khi auth-api co that."""

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
    src/services/severity.py cho chuyen doi tu ConversationState noi bo.

    `safety_flag`: TEN nay do api-contracts.md §4 quy dinh (KHONG duoc doi,
    se pha contract voi FE) nhung Y NGHIA RONG HON `ConversationState[
    "safety_flag"]` noi bo - xem src/api/chat_routes.py::
    _should_show_emergency_overlay() cho ly do va cach map dung."""

    reply: str
    classification: ClassificationOut | None = None
    severity: str | None = None
    safety_flag: bool = False
    needs_clarification: bool = False
    sources: list[SourceOut] = Field(default_factory=list)
