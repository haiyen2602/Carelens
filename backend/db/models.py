"""ORM models:
  - drug_chunks: RAG data thuoc, 4 chunk/thuoc (Phase 1/3, chatbot-rag-design.md muc 3.1)
  - audit_log: AuditLogDTO, append-only (Phase 1, BR-7.5, chatbot-rag-design.md muc 5.2)
  - prescription, dose_event: them o Phase 5 - chi du de 2 tool
    tra_cuu_lich_uong_ca_nhan/tra_cuu_don_thuoc_ca_nhan (chatbot-rag-design.md
    muc 6) co du lieu that de query, KHONG phai trien khai day du FEAT-001-004
    (nam ngoai pham vi tai lieu nay - xem chatbot-rag-design.md muc 1). Schema
    khop PrescriptionDTO/DoseEventDTO (api-contracts.md §2, §3); `items`/
    `expected_items` luu JSON thay vi bang con rieng - don gian hoa hop ly cho
    MVP, KHONG phai quyet dinh kien truc cuoi cung cho FEAT-001-004 that.
  - escalation: them o Phase 6 - noi that de escalate_fn (src/services/
    escalation.py) ghi vao, khop EscalationDTO (api-contracts.md §6/§8). Day
    la NGUON DUY NHAT cho ca 2 duong kich hoat HIGH (safety_layer redflag VA
    SEVERITY -> LEVEL = "Nguy hiểm") - khong xay bang rieng cho tung duong.

KHONG duoc UPDATE/DELETE audit_log o tang ung dung - xem ghi chu trong
migrations/versions/, chi duoc INSERT.
"""

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

EMBEDDING_DIM = 1536  # text-embedding-3-small (config.py: embedding_model)


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DrugChunk(Base):
    """1 dong = 1 chunk cua 1 thuoc (4 chunk/thuoc, field_group khac nhau).
    Xem specs/chatbot-rag-design.md muc 3.1 cho chunking strategy va prefix."""

    __tablename__ = "drug_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    drug_id: Mapped[str] = mapped_column(String, nullable=False, index=True)  # = thuoc.id trong data pharmacy
    # Ten thuoc goc (chua unaccent) - can rieng vi DrugInfoDTO (api-contracts.md §8)
    # bat buoc co ten_thuoc; ten_thuoc_unaccent (ben duoi) chi dung de so khop
    # lexical, khong dung de hien thi cho benh nhan.
    ten_thuoc: Mapped[str] = mapped_column(String, nullable=False)
    danh_muc: Mapped[str] = mapped_column(String, nullable=False)
    muc_nghiem_trong: Mapped[str] = mapped_column(String, nullable=False)  # Nhe|Trung binh|Nguy hiem

    field_group: Mapped[str] = mapped_column(String, nullable=False)  # cong_dung|tac_dung_phu|cach_dung|bao_quan
    noi_dung: Mapped[str] = mapped_column(Text, nullable=False)

    # Cot bo dau, build bang ham unaccent() ngay trong SQL luc insert (Phase 3),
    # KHONG build o application layer - de dam bao index va cach xu ly cau hoi
    # luc query dung chung 1 logic (xem build-kickoff-prompt.md Phase 3).
    noi_dung_unaccent: Mapped[str] = mapped_column(Text, nullable=False)
    ten_thuoc_unaccent: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        # HNSW index cho vector search (mo ta chi tiet trong migration - SQLAlchemy
        # khong co API tao HNSW index truc tiep, khai bao index thuong o day de
        # ORM biet cot nao co index, index HNSW that duoc tao trong migration bang raw SQL).
        Index("ix_drug_chunks_drug_id_field_group", "drug_id", "field_group"),
    )


class AuditLog(Base):
    """1 dong = 1 AuditLogDTO (1 luot xu ly 1 utterance cua benh nhan).
    APPEND-ONLY (BR-7.5) - khong duoc UPDATE/DELETE tu code ung dung."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dose_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    utterance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Mang cac buoc (safety_layer, intent_classification, retrieval, prescription_lookup,
    # answer_generation...) dung dinh dang mo ta o chatbot-rag-design.md muc 5.2.
    trace: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    final_response: Mapped[str] = mapped_column(Text, nullable=False)
    total_duration_ms: Mapped[float] = mapped_column(Float, nullable=False)


class Patient(Base):
    """Ho so benh nhan. THEM 2026-08-12 (migration 0009).

    KHONG PHAI bang tai khoan dang nhap. Khong co mat khau, email, role hay
    JWT - nhung thu do thuoc domain `auth` (auth-api, api-contracts.md §1),
    chua chot va khong phai pham vi cua bang nay.

    Tach nhu vay vi ho so benh nhan va tai khoan dang nhap la hai thu khac
    nhau: nguoi than co tai khoan ma khong phai benh nhan; benh nhan cao tuoi
    co the khong bao gio tu dang nhap. Khi auth-api xong, chi can them mot cot
    `user_id` nullable de noi, khong phai sua lai bang nay.

    CHUA dat khoa ngoai tu prescription.patient_id/dose_event.patient_id sang
    day (co y): may cac thanh vien khac dang co san du lieu voi patient_id tuy
    y, them FK bay gio se lam `alembic upgrade` cua ho loi. Kiem tra o tang
    services truoc (patient_id khong ton tai -> 404 theo api-contracts.md §10),
    them FK sau khi ca nhom da don du lieu."""

    __tablename__ = "patient"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    year_of_birth: Mapped[int | None] = mapped_column(nullable=True)
    # Bac si phu trach - BR-1.2 (chi bac si phu trach moi duoc duyet phac do).
    doctor_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # vd "Tang huyet ap, sau dot quy"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Prescription(Base):
    """Khop PrescriptionDTO (api-contracts.md §2). `items` la JSON array, moi
    phan tu: {ten_thuoc, ham_luong, dang_thuoc, lieu_dung, duong_dung,
    thoi_diem_dung, so_vien_moi_lan, gio_nhac, drug_id} - drug_id de join
    nguoc ve drug_chunks, thoi_diem_dung la nguon that duy nhat cho tool
    tra_cuu_don_thuoc_ca_nhan (chatbot-rag-design.md muc 3.1)."""

    __tablename__ = "prescription"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # draft|approved|active|completed|stopped|rejected
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    start_date: Mapped[str] = mapped_column(String, nullable=False)  # ISO date string, don gian hoa cho MVP
    duration_days: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # THEM 2026-08-12 (migration 0010) - 3 cot con thieu so voi PrescriptionDTO
    # (api-contracts.md §2). `note` la o "Luu y" tren form bac si;
    # approved_by/approved_at la yeu cau cua BR-1.5 (moi chuyen trang thai phai
    # ghi lai actor + thoi diem). Deu nullable de du lieu cu khong hong.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DoseEvent(Base):
    """Khop DoseEventDTO (api-contracts.md §3). `expected_items`: list cac
    {drug_id, ten_thuoc, so_vien} - dung cho tool tra_cuu_lich_uong_ca_nhan
    (vd "hom nay toi uong thuoc gi")."""

    __tablename__ = "dose_event"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    prescription_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # PENDING|TAKEN|MISSED|DELAYED|CANCELLED
    expected_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Escalation(Base):
    """Khop EscalationDTO (api-contracts.md §6, §8). 1 dong = 1 canh bao
    HIGH/MEDIUM da kich hoat, du tu safety_layer redflag (trigger=
    'safety_redflag') hay tu SEVERITY->LEVEL (trigger='missed_dose'|
    'side_effect' tuy classification). `severity` luu theo quy uoc
    api-contracts.md (LOW|MEDIUM|HIGH, tieng Anh) - KHAC voi
    ConversationState.severity noi bo (Nhẹ|Trung bình|Nguy hiểm, tieng Viet) -
    xem SEVERITY_VI_TO_EN trong src/services/severity.py, chuyen doi ngay
    truoc khi ghi vao bang nay, khong luu lan 2 quy uoc trong cung 1 cot."""

    __tablename__ = "escalation"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dose_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False)  # LOW|MEDIUM|HIGH
    trigger: Mapped[str] = mapped_column(String, nullable=False)  # missed_dose|side_effect|safety_redflag|photo_mismatch
    raw_utterance: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")  # OPEN|ACKED|RESOLVED
    # Vd ["caregiver", "doctor"] - target "family" noi bo cua escalate_fn map
    # sang "caregiver" o day de khop dung tu vung EscalationDTO.
    notified: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # THEM vong 2, muc 13 (chatbot-rag-design.md) - co che nhac lai theo moc
    # thoi gian co dinh (t=15p/25p/35p, xem src/services/escalation_reminder.py).
    # `status` DA CO SAN o tren dung lam tin hieu "dung nhac lai chua" (OPEN
    # = van con nhac, RESOLVED = da xu ly, dung nhac) - KHONG them cot
    # resolved: bool rieng de tranh 2 nguon trang thai co the lech nhau.
    reminder_count: Mapped[int] = mapped_column(nullable=False, default=1)  # 1 = da gui t=0, chua tinh nhac lai
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)  # vd "doctor"/"caregiver"


class ChatMessage(Base):
    """Vong 3, muc 7.1 (chatbot-rag-design.md) - lich su chat DAY DU cho
    HIEN THI lai cho benh nhan, luu MOI tin nhan (ca patient lan assistant),
    KHONG gioi han thoi gian. KHAC HAN cua so ngu canh ngan han 15 phut (muc
    7.2, backend/agents/tools/chat_history_tool.py::get_recent_context()) -
    bang nay CHI dung de hien thi, KHONG tu dong dua vao LLM.

    "Xoa doan chat" = an khoi man hinh benh nhan (hidden=True, QUYET DINH
    #20, chatbot-rag-design.md muc 10) - KHONG xoa that khoi DB. audit_log
    la kho du lieu HOAN TOAN TACH BIET (BR-7.5, da co tu Phase 1) - an 1 tin
    nhan o day KHONG anh huong gi toi audit_log, bac si/doi ky thuat van tra
    cuu duoc day du qua audit_log nhu thuong."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "patient" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
    # #20 - soft-delete, mac dinh False (hien thi binh thuong).
    hidden: Mapped[bool] = mapped_column(nullable=False, default=False)


class PhotoVerification(Base):
    """1 dong = 1 LAN gui anh xac nhan lieu thuoc. THEM 2026-08-12 (migration 0011).

    Nhieu dong cho cung mot dose_event: ADR-0011 cho toi da 2 lan chup lai
    (tong 3 lan gui), `attempt` cho biet day la lan thu may.

    KHONG luu anh trong DB, chi luu duong dan: anh thuoc la du lieu y te (PHI)
    theo BR-4.3, phai de ngoai repo va co kiem soat truy cap rieng.

    `ket_qua` luu 3 gia tri (khop|lech|khong_xac_minh_duoc) chu KHONG phai mot
    cot boolean `matched`: lieu toan thuoc tiem la truong hop thu ba - benh
    nhan khong lam gi sai, he thong chi khong co cach kiem chung - gop no vao
    "khong khop" se khien dashboard bac si dem nham thanh lieu co van de.
    Truong `matched` cua api-contracts.md §5 suy ra tu day (= khop), khong luu
    lan 2 de tranh 2 nguon trang thai lech nhau.

    `thong_bao` luu DUNG cau da noi voi benh nhan - can cho audit: sau nay
    truy lai mot ca bat thuong thi phai biet luc do he thong da bao gi, khong
    the dung lai tu ket qua vi cau chu co the da doi."""

    __tablename__ = "photo_verification"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dose_event_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(nullable=False, default=1)  # 1..3 (ADR-0011)

    # {"vien_nen": 2, "vien_nang": 1} - da gop theo dang bao che, xem
    # backend/services/photo_verification/matcher.py
    expected_by_form: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    detected_by_form: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    ket_qua: Mapped[str] = mapped_column(String, nullable=False)  # khop|lech|khong_xac_minh_duoc
    confidence: Mapped[str | None] = mapped_column(String, nullable=True)  # cao|trung_binh|thap
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)  # ghi_chu model tra ve
    thong_bao: Mapped[str] = mapped_column(Text, nullable=False)  # cau da noi voi benh nhan

    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Account(Base):
    """TASK-010 (api-contracts.md muc 1, auth-api) - 1 bang chung cho CA 4
    role (doctor|patient|caregiver|admin), phan biet qua cot `role` - dung
    quyet dinh da chot voi PM 2026-08-12 (KHONG tach bang/endpoint rieng
    theo role, tranh lech contract Draft san trong specs/api-contracts.md).

    `patient_id`/`doctor_id` la lien ket TOI THIEU de get_current_patient_id()
    (backend/api/security.py) doc duoc patient_id cua chinh nguoi dang dang
    nhap khi role=patient - CHUA phai mo hinh lien ket day du bac si<->benh
    nhan<->nguoi than (user-roles.md, thuoc FEAT-001/quan ly tai khoan cua
    admin, ngoai pham vi TASK-010). KHONG lien quan gi den bang `Patient`
    (patient_id o day la string tu do, khop DoseEvent/Prescription.patient_id
    - Patient la 1 khai niem khac, xem class Patient o tren)."""

    __tablename__ = "account"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # doctor|patient|caregiver|admin
    # Neu role=patient: chinh patient_id cua nguoi nay (dung boi
    # get_current_patient_id de khong tin patient_id nguoi dung tu go trong
    # body). Neu role=doctor: KHONG dung cot nay (bac si co the phu trach
    # nhieu benh nhan - can bang lien ket rieng, chua co trong TASK-010).
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    doctor_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # THEM sau TASK-010 (migration 0013) - account-api (admin quan ly tai
    # khoan). "active"|"locked". KHONG co "pending" - khong co luong tu
    # dang ky, moi tai khoan do admin tao truc tiep la active ngay. PHAI
    # duoc kiem tra trong POST /auth/login (backend/api/auth_routes.py) -
    # neu khong, tinh nang khoa tai khoan chi la UI gia, khong chan dang
    # nhap that.
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")


class PendingDrugConfirmation(Base):
    """Vong 2 (chatbot-rag-design.md muc 11.3) - luu trang thai "dang cho
    benh nhan xac nhan danh tinh thuoc" GIUA 2 lan goi HTTP. BAT BUOC phai
    la bang DB (khong phai in-memory) vi POST /api/v1/chat la stateless
    per-request - neu chi luu trong ConversationState/memory, gia tri mat
    ngay sau khi request ket thuc, VA se hong voi nhieu worker process (muc
    10 #10: sap co nhieu nguoi dung that, nhieu kha nang chay nhieu worker -
    dung nguyen tac da ap dung cho scheduler o muc 13, SQLAlchemyJobStore
    khong phai in-memory).

    `patient_id` la PRIMARY KEY (khong phai id rieng) - 1 benh nhan CHI co
    toi da 1 pending confirmation tai 1 thoi diem (dung y thiet ke: khi tin
    nhan moi toi, kiem tra dung 1 dong nay theo patient_id, khong can query
    nhieu dong roi loc "cai nao moi nhat")."""

    __tablename__ = "pending_drug_confirmation"

    patient_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Danh sach ung vien dang cho xac nhan - {drug_id, ten_thuoc} moi phan tu.
    # 1 phan tu khi dang hoi xac nhan don/top-1 (muc 11.1, 11.2 buoc dau); toi
    # da 3 phan tu khi o buoc "chon 1 trong top-3" (muc 11.2 buoc 1).
    candidates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # "in_prescription_round1" | "in_prescription_round2" |
    # "out_of_prescription_round1" | "out_of_prescription_round2" (muc 11.3)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # THEM 2026-08-09 (review) - dem so lan LIEN TIEP reply KHONG parse duoc
    # (yes/no/so thu tu) o CUNG 1 stage - KHAC round-budget (dem theo so ung
    # vien da thu). Reset ve 0 moi khi CO tien trien (stage doi) - chi tang
    # khi phai hoi lai DUNG stage cu vi khong hieu reply. Vuot nguong ->
    # dung han, tranh vong lap vo han khi benh nhan go linh tinh.
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
