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
from datetime import UTC, date, datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
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

    # BUILD-7C: nullable so frozen legacy rows remain compatible.  New,
    # reproducible corpora are identified by the logical chunk key rather than
    # by a random primary key.
    corpus_version: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    chunk_key: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        # HNSW index cho vector search (mo ta chi tiet trong migration - SQLAlchemy
        # khong co API tao HNSW index truc tiep, khai bao index thuong o day de
        # ORM biet cot nao co index, index HNSW that duoc tao trong migration bang raw SQL).
        Index("ix_drug_chunks_drug_id_field_group", "drug_id", "field_group"),
        Index(
            "uq_drug_chunks_corpus_chunk_key",
            "corpus_version",
            "chunk_key",
            unique=True,
            postgresql_where=text("corpus_version IS NOT NULL AND chunk_key IS NOT NULL"),
        ),
    )


class RagCorpus(Base):
    """Immutable metadata for one reproducible pgvector corpus."""

    __tablename__ = "rag_corpus"

    corpus_version: Mapped[str] = mapped_column(String, primary_key=True)
    source_manifest_hash: Mapped[str] = mapped_column(String, nullable=False)
    chunk_manifest_hash: Mapped[str] = mapped_column(String, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    index_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    expected_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class RagCorpusCheckpoint(Base):
    """Per-chunk recovery state; a completed key must never be embedded again."""

    __tablename__ = "rag_corpus_checkpoint"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    corpus_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    chunk_key: Mapped[str] = mapped_column(String, nullable=False)
    drug_chunk_id: Mapped[str | None] = mapped_column(String, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    batch_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("corpus_version", "chunk_key", name="uq_rag_corpus_checkpoint_key"),
        Index("ix_rag_corpus_checkpoint_status", "corpus_version", "status"),
    )


class RagEmbeddingReservation(Base):
    """Durable, idempotent accounting boundary around one embedding request.

    A reservation is committed before OpenAI is called.  Its response is staged
    before chunks/checkpoints are applied, so an interrupted process cannot
    silently re-embed a batch whose billable outcome is unknown.
    """

    __tablename__ = "rag_embedding_reservation"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    corpus_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    batch_key: Mapped[str] = mapped_column(String, nullable=False)
    chunk_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    planned_token_ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_request_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    provider_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Temporary, validated provider vectors. Cleared only after the same
    # transaction has inserted chunks and completed checkpoints.
    response_embeddings: Mapped[list[list[float]] | None] = mapped_column(JSON, nullable=True)
    response_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accounted_in_corpus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("corpus_version", "batch_key", name="uq_rag_embedding_reservation_batch"),
        Index("ix_rag_embedding_reservation_corpus_status", "corpus_version", "status"),
    )


class Drug(Base):
    """Danh muc thuoc - 1 dong = 1 thuoc. THEM 2026-08-12 (migration 0012).

    KHAC drug_chunks: bang do la san pham cua RAG (4 chunk/thuoc, moi chunk la
    mot doan van ban co embedding), dung de TRA LOI CAU HOI. Bang nay la DANH
    MUC: mot dong mot thuoc, chua thuoc tinh co cau truc (dang bao che, duong
    dung, ham luong), dung de TRA CUU va DIEN VAO DON THUOC.

    Vi sao phai co bang rieng thay vi them cot vao drug_chunks:
      - drug_chunks lap 4 lan moi thuoc, them dang_thuoc vao do la lap 4 lan
        cung mot gia tri.
      - drug_chunks chi chua thuoc DA EMBED (hien 226/3562). Danh muc phai co
        du 3562 thuoc thi bac si moi ke duoc don, khong phu thuoc tien embed.

    `dang_thuoc` la truong quan trong nhat o day: no la dau vao cua
    backend/services/photo_verification/dosage_form.py, quyet dinh mot lieu
    thuoc co xac minh duoc bang anh hay khong.

    `ten_thuoc_unaccent` build bang ham unaccent() NGAY TRONG SQL luc insert -
    cung quy uoc voi drug_chunks, de index va cach xu ly cau hoi luc query dung
    chung 1 logic (xem migration 0001)."""

    __tablename__ = "drug"

    # = 'id' trong 'data pharmacy/**/*.json', vd "agi-calci-agimexpharm-20x10".
    # Cung khong gian dinh danh voi drug_chunks.drug_id.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ten_thuoc: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ten_thuoc_unaccent: Mapped[str] = mapped_column(Text, nullable=False)

    dang_thuoc: Mapped[str] = mapped_column(String, nullable=False)  # "Viên nén bao phim"...
    duong_dung: Mapped[str] = mapped_column(String, nullable=False)  # "Uống"|"Tiêm"|"Bôi ngoài da"...
    ham_luong: Mapped[str | None] = mapped_column(String, nullable=True)
    tong_so_luong: Mapped[str | None] = mapped_column(String, nullable=True)  # "30 viên", "1 lọ 100ml"

    danh_muc: Mapped[str | None] = mapped_column(String, nullable=True)
    muc_nghiem_trong: Mapped[str | None] = mapped_column(String, nullable=True)  # Nhẹ|Trung bình|Nguy hiểm

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class DrugRequest(Base):
    """1 yeu cau bo sung thuoc chua co trong danh muc (THEM 2026-08-21,
    migration 0031). Duong thoat cho FB-14.

    Vi sao can bang nay: tu 2026-08-20 danh muc thuoc la allowlist DONG - bac
    si khong ke duoc thuoc khong co `drug_id` (xem services/prescription/
    service.py::_chuan_hoa_item). Khong co duong thoat thi gap thuoc ngoai
    danh muc la bac si ket han. Day la duong do: bac si gui yeu cau, admin
    duyet, duyet xong moi ke duoc.

    KHAC bang `drug`: bang do la danh muc goc nap tu artifact Canonical V2.
    Bang nay la PHAN MO RONG luc chay - them dong vao `drug` khong co tac
    dung gi vi `lay_thuoc()` mac dinh phan giai qua catalog V2 doc tu file
    JSONL trong image (v2_agent.py, @lru_cache), khong doc DB.

    `dang_thuoc` NOT NULL du bac si phai go tay: no la dau vao cua
    photo_verification/dosage_form.py, quyet dinh lieu do co xac minh duoc
    bang anh hay khong. Cho rong la tao ra mot lop thuoc khong bao gio xac
    minh duoc - dung thu FB-14 muon dep.

    `approved_drug_id` dang `req-<slug>-<hash6>`, sinh luc duyet. Tien to
    `req-` de nhin id la biet thuoc den tu duong ngoai le: tien audit, va
    tien loc ra dung tap can gop nguoc vao artifact V2 sau nay.

    NO KY THUAT CO CHU DICH: nguon su that lau dai van phai la artifact
    Canonical V2 (ADR-0012). Bang nay la cau tam.

    Thuoc duyet qua day KHONG co trong `drug_chunks` nen chatbot khong tra
    loi duoc ve no - viec sinh chunk + embedding thuoc mang RAG, tach thanh
    task rieng, khong chan luong ke don."""

    __tablename__ = "drug_request"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    requested_by_doctor_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    ten_thuoc: Mapped[str] = mapped_column(String, nullable=False)
    dang_thuoc: Mapped[str] = mapped_column(String, nullable=False)
    duong_dung: Mapped[str] = mapped_column(String, nullable=False)
    ham_luong: Mapped[str | None] = mapped_column(String, nullable=True)
    tong_so_luong: Mapped[str | None] = mapped_column(String, nullable=True)
    ly_do: Mapped[str | None] = mapped_column(Text, nullable=True)

    # PENDING | APPROVED | REJECTED
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING", index=True)
    reviewed_by_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_drug_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
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
    # THEM 2026-08-13 (migration 0020) - tab "Tinh trang suc khoe" o trang
    # Quan ly benh nhan. Du lieu co cau truc (khac `note` la text tu do).
    gender: Mapped[str | None] = mapped_column(String, nullable=True)  # "nam" | "nu" | "khac"
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # `watch` (co boolean dung chung) DA BI XOA o migration 0023 - thay bang
    # bang DoctorWatch (theo doi rieng tung bac si, xem class ben duoi).
    # THEM 2026-08-14 (migration 0022) - trang onboarding "Thong tin ca nhan"
    # ma benh nhan tu dien ngay sau lan dang nhap dau tien (frontend/src/app/
    # onboarding/profile/page.tsx). `date_of_birth` KHONG thay `year_of_birth`
    # o tren (van con nhieu noi doc year_of_birth) - luc luu dong bo
    # year_of_birth = date_of_birth.year (xem backend/api/patient_routes.py).
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    # False = chua hoan tat onboarding -> frontend bat buoc redirect. KHONG
    # suy tu cac cot khac co NULL hay khong (benh nhan co the chu y bo trong
    # 1 truong nao do sau khi da "hoan tat").
    profile_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # DB Architecture V2 additive columns (DB-4A, WIP - xem
    # docs/data/database_architecture_v2_plan.md). Nullable until backfill and
    # validation gates pass; legacy fields above remain source-compatible.
    # `date_of_birth` da co san o tren (migration 0023 patient_profile_fields),
    # khong khai bao lai o day.
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    sex: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)


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
    prescribed_by: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    prescribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)


class DrugProduct(Base):
    """DB Architecture V2 operational reference to Canonical Drug V2 identity.

    DB-4A creates the empty table only. Drug V2 import/backfill happens later.
    """

    __tablename__ = "drug_product"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    legacy_drug_id: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    dosage_form: Mapped[str | None] = mapped_column(String, nullable=True)
    route: Mapped[str | None] = mapped_column(String, nullable=True)
    strength_text: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_drug_product_legacy_drug_id", "legacy_drug_id", unique=True),
        Index("ix_drug_product_display_name", "display_name"),
    )


class DrugIdMap(Base):
    """Legacy public drug_id -> Canonical Drug V2 product ID map."""

    __tablename__ = "drug_id_map"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    legacy_drug_id: Mapped[str] = mapped_column(String, nullable=False)
    drug_product_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    mapping_status: Mapped[str] = mapped_column(String, nullable=False)
    source_manifest_version: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index(
            "uq_drug_id_map_active_legacy",
            "legacy_drug_id",
            unique=True,
            postgresql_where=text("mapping_status = 'ACTIVE'"),
        ),
        Index("ix_drug_id_map_mapping_status", "mapping_status"),
    )


class DrugImage(Base):
    """Validated reference image and provenance owned by one canonical product.

    Binary content remains in the configured storage backend.  This table only
    records the deterministic storage key and enough source provenance to
    reproduce or retire an imported B-02 image safely.
    """

    __tablename__ = "drug_image"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    drug_product_id: Mapped[str] = mapped_column(ForeignKey("drug_product.id"), nullable=False, index=True)
    legacy_drug_id: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_snapshot_id: Mapped[str] = mapped_column(String, nullable=False)
    source_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    view_type: Mapped[str] = mapped_column(String, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_status: Mapped[str] = mapped_column(String, nullable=False)
    collection_version: Mapped[str] = mapped_column(String, nullable=False)
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "validation_status IN ('VALIDATED', 'INVALID', 'RETIRED')",
            name="ck_drug_image_validation_status",
        ),
        CheckConstraint("width > 0 AND height > 0 AND file_size > 0", name="ck_drug_image_dimensions"),
        UniqueConstraint(
            "drug_product_id",
            "source_snapshot_id",
            "source_url",
            "checksum_sha256",
            "view_type",
            name="uq_drug_image_source_identity",
        ),
        Index("ix_drug_image_checksum_sha256", "checksum_sha256"),
        Index("ix_drug_image_product_status", "drug_product_id", "validation_status"),
        Index(
            "uq_drug_image_validated_primary",
            "drug_product_id",
            "collection_version",
            unique=True,
            postgresql_where=text("is_primary AND validation_status = 'VALIDATED'"),
            sqlite_where=text("is_primary AND validation_status = 'VALIDATED'"),
        ),
    )


class DrugImageEmbedding(Base):
    """Versioned visual embedding for one validated reference image.

    The vector stays separate from ``DrugImage`` because encoder and
    preprocessing versions can change independently of source provenance.
    ``Vector(512)`` is deliberately fixed to the selected B-04 OpenCLIP
    baseline; a different dimensional model requires its own reviewed
    migration rather than silently mixing incompatible vectors.
    """

    __tablename__ = "drug_image_embedding"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    drug_image_id: Mapped[str] = mapped_column(ForeignKey("drug_image.id", ondelete="CASCADE"), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    embedding_version: Mapped[str] = mapped_column(String, nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(512), nullable=False)
    preprocessing_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("embedding_dimension = 512", name="ck_drug_image_embedding_dimension"),
        UniqueConstraint(
            "drug_image_id",
            "embedding_model",
            "embedding_version",
            name="uq_drug_image_embedding_model_version",
        ),
        Index("ix_drug_image_embedding_model_version", "embedding_model", "embedding_version"),
    )


class DrugRecognitionAttempt(Base):
    """Server-owned B-07 candidate lifecycle; never stores raw image/OCR/vector.

    The candidate snapshot maps an opaque action ID to the exact canonical
    product selected by B-05.  It is intentionally separate from
    ``ConversationState.active_entity``: only a successful confirmation may
    promote one of these candidates into trusted conversational context.
    """

    __tablename__ = "drug_recognition_attempt"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    recognition_version: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    candidates_json: Mapped[list] = mapped_column("candidates", JSON, nullable=False, default=list)
    requested_attribute: Mapped[str | None] = mapped_column(String, nullable=True)
    selected_drug_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_drug_recognition_attempt_scope_status", "conversation_id", "patient_id", "actor_id", "status"),
        CheckConstraint(
            "status IN ('AWAITING_CONFIRMATION', 'INSUFFICIENT_EVIDENCE', 'CONFIRMED', 'SUPERSEDED', 'EXPIRED', 'FAILED')",
            name="ck_drug_recognition_attempt_status",
        ),
    )


class DoctorReviewImageAttachment(Base):
    """B-07 private image reference for an ACTIVE doctor-takeover message.

    This intentionally is not a general chat attachment: it is scoped to a
    single handoff and may be served only to that handoff's assigned doctor.
    The database stores an opaque storage key, never a client path or bytes.
    """

    __tablename__ = "doctor_review_image_attachment"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    handoff_id: Mapped[str] = mapped_column(ForeignKey("doctor_review_request.id"), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("doctor_review_message.id"), nullable=False, unique=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("file_size > 0", name="ck_doctor_review_image_attachment_file_size"),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_doctor_review_image_attachment_mime_type",
        ),
    )


class Ingredient(Base):
    """Canonical ingredient identity imported from Drug Knowledge V2 later."""

    __tablename__ = "ingredient"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class DrugProductIngredient(Base):
    """Many-to-many link between V2 drug products and ingredients."""

    __tablename__ = "drug_product_ingredient"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    drug_product_id: Mapped[str] = mapped_column(String, nullable=False)
    ingredient_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("drug_product_id", "ingredient_id", name="uq_drug_product_ingredient_pair"),
        Index("ix_drug_product_ingredient_drug_product_id", "drug_product_id"),
        Index("ix_drug_product_ingredient_ingredient_id", "ingredient_id"),
    )


class PrescriptionItem(Base):
    """DB Architecture V2: one medication line inside a prescription."""

    __tablename__ = "prescription_item"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    prescription_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    drug_product_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    legacy_drug_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    drug_display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    dose_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    dose_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    dose_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    route: Mapped[str | None] = mapped_column(String, nullable=True)
    frequency_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # When set, ``end_date`` is an inclusive local clinical calendar date.
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    doses_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meal_instruction_code: Mapped[str | None] = mapped_column(String, nullable=True)
    meal_instruction_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    migration_source: Mapped[str | None] = mapped_column(String, nullable=True)
    migration_source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    migration_item_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_prescription_item_patient_status", "patient_id", "status"),
        Index("uq_prescription_item_migration_source", "migration_source", "migration_source_id", "migration_item_index", unique=True),
    )


class MedicationPlan(Base):
    """DB Architecture V2: actionable plan for one prescribed medication."""

    __tablename__ = "medication_plan"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    prescription_item_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    drug_product_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    legacy_drug_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (Index("ix_medication_plan_patient_status", "patient_id", "status"),)


class ScheduleRule(Base):
    """DB Architecture V2: rule used to generate per-drug dose occurrences."""

    __tablename__ = "schedule_rule"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    medication_plan_id: Mapped[str] = mapped_column(String, nullable=False)
    rule_type: Mapped[str | None] = mapped_column(String, nullable=True)
    frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    times_of_day: Mapped[list | None] = mapped_column(JSON, nullable=True)
    days_of_week: Mapped[list | None] = mapped_column(JSON, nullable=True)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_schedule_rule_medication_plan_status", "medication_plan_id", "status"),
        Index("ix_schedule_rule_status_window", "status", "start_at", "end_at"),
    )


class ScheduleRuleTime(Base):
    """One normalized local wall-clock time within a DB-4D schedule rule.

    ``schedule_rule_id`` intentionally has no FK until operational validation
    is complete. The unique pair prevents duplicate per-rule daily times.
    """

    __tablename__ = "schedule_rule_time"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    schedule_rule_id: Mapped[str] = mapped_column(String, nullable=False)
    local_time: Mapped[time] = mapped_column(Time, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("schedule_rule_id", "local_time", name="uq_schedule_rule_time_local_time"),)


class ScheduleRuleCycle(Base):
    """Optional repeating on/off cycle attached one-to-one to a schedule rule.

    Checks and the parent FK are intentionally delayed until DB-4D operational
    validation; no scheduler consumes this table in the current task.
    """

    __tablename__ = "schedule_rule_cycle"

    schedule_rule_id: Mapped[str] = mapped_column(String, primary_key=True)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    on_days: Mapped[int] = mapped_column(Integer, nullable=False)
    off_days: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class DoseOccurrence(Base):
    """DB Architecture V2: one medicine / one scheduled dose."""

    __tablename__ = "dose_occurrence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    medication_plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    prescription_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    drug_product_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    legacy_drug_id: Mapped[str | None] = mapped_column(String, nullable=True)
    schedule_rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scheduled_local_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generation_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    legacy_dose_event_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_dose_occurrence_medication_plan_scheduled", "medication_plan_id", "scheduled_at"),
        Index("ix_dose_occurrence_patient_scheduled", "patient_id", "scheduled_at"),
        Index("ix_dose_occurrence_status_scheduled", "status", "scheduled_at"),
        Index("ix_dose_occurrence_patient_status_scheduled", "patient_id", "status", "scheduled_at"),
        Index("ix_dose_occurrence_legacy_drug_scheduled", "legacy_drug_id", "scheduled_at"),
        Index(
            "ix_dose_occurrence_patient_local_schedule",
            "patient_id",
            "scheduled_local_date",
            "scheduled_local_time",
        ),
    )


class DoseEventLog(Base):
    """DB Architecture V2 immutable dose event log.

    Physical name is intentionally `dose_event_log` to avoid redefining legacy
    `dose_event` before cutover/stabilization.
    """

    __tablename__ = "dose_event_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dose_occurrence_id: Mapped[str] = mapped_column(String, nullable=False)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    medication_plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    drug_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_dose_event_log_idempotency_key", "idempotency_key", unique=True),
        Index("ix_dose_event_log_occurrence_created", "dose_occurrence_id", "created_at"),
        Index("ix_dose_event_log_patient_event_at", "patient_id", "event_at"),
        Index("ix_dose_event_log_event_type_event_at", "event_type", "event_at"),
        Index("ix_dose_event_log_plan_event_at", "medication_plan_id", "event_at"),
    )


class NotificationJob(Base):
    """DB Architecture V2 notification queue/state, not dose status source."""

    __tablename__ = "notification_job"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    dose_occurrence_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    notification_type: Mapped[str] = mapped_column(String, nullable=False)
    recipient_type: Mapped[str] = mapped_column(String, nullable=False)
    recipient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_notification_job_status_scheduled", "status", "scheduled_at"),
        Index("ix_notification_job_patient_scheduled", "patient_id", "scheduled_at"),
        Index("ix_notification_job_recipient_status", "recipient_type", "recipient_id", "status"),
        Index("ix_notification_job_provider_message", "provider", "provider_message_id"),
    )


class MedicationSafetyPolicy(Base):
    """DB Architecture V2 auditable medication safety policy."""

    __tablename__ = "medication_safety_policy"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scope_type: Mapped[str] = mapped_column(String, nullable=False)
    scope_id: Mapped[str] = mapped_column(String, nullable=False)
    risk_type: Mapped[str] = mapped_column(String, nullable=False)
    risk_level: Mapped[str] = mapped_column(String, nullable=False)
    action_policy: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[str] = mapped_column(String, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "risk_type", "policy_version", name="uq_medication_safety_policy_version"),
        Index("ix_medication_safety_policy_scope_risk", "scope_type", "scope_id", "risk_type"),
        Index("ix_medication_safety_policy_risk_review", "risk_type", "review_status"),
        Index("ix_medication_safety_policy_valid_window", "valid_from", "valid_to"),
        Index(
            "ix_medication_safety_policy_reviewed_scope",
            "scope_type",
            "scope_id",
            "risk_type",
            postgresql_where=text("review_status = 'REVIEWED'"),
        ),
        Index(
            "ix_medication_safety_policy_legacy_scope",
            "scope_type",
            "scope_id",
            "risk_type",
            postgresql_where=text("source_type = 'LEGACY_CATEGORY_RULE'"),
        ),
    )


class MissedDoseAssessment(Base):
    """DB Architecture V2 durable missed/delayed dose safety assessment."""

    __tablename__ = "missed_dose_assessment"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    dose_occurrence_id: Mapped[str] = mapped_column(String, nullable=False)
    medication_plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    drug_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_type: Mapped[str] = mapped_column(String, nullable=False)
    risk_level: Mapped[str] = mapped_column(String, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String, nullable=False)
    policy_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Immutable policy-provenance snapshots added by DB-4H.  The referenced
    # policy can later be superseded, but the historical assessment must still
    # show whether its decision came from reviewed, legacy, or default logic.
    policy_source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    policy_review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    assessment_version: Mapped[str] = mapped_column(String, nullable=False)
    evaluator: Mapped[str] = mapped_column(String, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_missed_dose_assessment_idempotency_key", "idempotency_key", unique=True),
        Index("ix_missed_dose_assessment_occurrence_evaluated", "dose_occurrence_id", "evaluated_at"),
        Index("ix_missed_dose_assessment_patient_evaluated", "patient_id", "evaluated_at"),
        Index("ix_missed_dose_assessment_policy_id", "policy_id"),
        Index("ix_missed_dose_assessment_risk_level_time", "risk_type", "risk_level", "evaluated_at"),
    )


class SafetyEvent(Base):
    """DB Architecture V2 append-only safety event/audit record."""

    __tablename__ = "safety_event"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dose_occurrence_id: Mapped[str | None] = mapped_column(String, nullable=True)
    drug_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    missed_dose_assessment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_safety_event_idempotency_key", "idempotency_key", unique=True),
        Index("ix_safety_event_patient_created", "patient_id", "created_at"),
        Index("ix_safety_event_type_created", "event_type", "created_at"),
        Index("ix_safety_event_severity_created", "severity", "created_at"),
        Index("ix_safety_event_dose_occurrence_id", "dose_occurrence_id"),
        Index("ix_safety_event_assessment_id", "missed_dose_assessment_id"),
    )


class DoctorReviewRequest(Base):
    """Auditable Doctor Handoff request created only after a safety gate.

    These columns deliberately have no hard FK while the operational identity
    tables retain legacy string identifiers.  Relationship validation belongs
    to the domain service and is repeated for every transition.
    """

    __tablename__ = "doctor_review_request"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_doctor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_actor_id: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    risk_disposition: Mapped[str] = mapped_column(String, nullable=False)
    patient_question: Mapped[str] = mapped_column(Text, nullable=False)
    agent_summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_provenance: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    verified_context_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_by_doctor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    doctor_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # BUILD-44: takeover lifecycle (ASSIGNED -> ACTIVE -> RESOLVED), additive
    # -- the ANSWERED/answered_at/answered_by_doctor_id/doctor_answer columns
    # above are a separate, pre-existing "quick answer, no takeover" path
    # (BUILD-10) left completely unchanged; see the BUILD-44 report for why
    # the two lifecycles are kept distinct rather than merged.
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_doctor_id: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("uq_doctor_review_request_idempotency", "idempotency_key", unique=True),
        Index("ix_doctor_review_request_patient_status", "patient_id", "status"),
        Index("ix_doctor_review_request_doctor_status", "assigned_doctor_id", "status"),
        Index("ix_doctor_review_request_created", "created_at"),
    )


class DoctorReviewMessage(Base):
    """BUILD-44: the real-time patient/doctor/system message thread for one
    handoff episode -- scoped by ``handoff_id``, not a general always-on
    chat history. See the BUILD-44 report's own audit for why neither the
    legacy ``ChatMessage`` table (patient_id-only, never written by Agent
    V2) nor the pre-existing, entirely-unused ``Conversation``/``Message``
    pair below was reused for this narrower, handoff-scoped purpose."""

    __tablename__ = "doctor_review_message"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    handoff_id: Mapped[str] = mapped_column(String, nullable=False)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    # "PATIENT" | "DOCTOR" | "SYSTEM" -- never "ASSISTANT": Agent V2 does not
    # speak during an ACTIVE takeover (see backend/services/agent_doctor_
    # takeover.py), so there is structurally nothing for that role to mean
    # in this table.
    sender_role: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_doctor_review_message_handoff_created", "handoff_id", "created_at"),
        Index("ix_doctor_review_message_patient_id", "patient_id"),
    )


class Conversation(Base):
    """DB Architecture V2 conversation session."""

    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_conversation_patient_started", "patient_id", "started_at"),
        Index("ix_conversation_status_last_message", "status", "last_message_at"),
    )


class Message(Base):
    """DB Architecture V2 message keyed by conversation."""

    __tablename__ = "message"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (Index("ix_message_conversation_created", "conversation_id", "created_at"),)


class AgentRun(Base):
    """DB Architecture V2 agent run audit without chain-of-thought.

    BUILD-32: the columns below `metadata_json` were added to make Agent V2's
    real per-run token usage/cost/duration/timeout/error/empty-reply/
    evaluation-version durable -- previously this data was computed correctly
    (`backend.agents.v2.model_gateway`, `backend.agents.v2.observability`) but
    only ever reached an in-memory ring buffer
    (`backend.services.telemetry`, capped at 200 traces, reset on every
    restart/deploy) or an unqueryable structured log line. Stamped best-effort,
    post-response, by `backend.api.agent_v2_routes._persist_durable_trace` --
    see that function's own docstring for why (some terminal paths never reach
    the synchronous checkpoint-recording code path this table's earlier
    columns are written from). `cost_status`/`NOT_AVAILABLE` (not a fabricated
    `0`) is the honest state when the model isn't in the configured pricing
    catalog; `evaluation_version` mirrors the one row this run also gets in
    `AgentRunEvaluation`.
    """

    __tablename__ = "agent_run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    intent: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # BUILD-32 durable observability columns (additive, all nullable/defaulted
    # so existing rows/readers are unaffected).
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Ownership reference distinct from `patient_id` -- the authenticated
    # caller, who may be a caregiver acting for `patient_id` rather than the
    # patient themselves. Stamped by
    # `backend.api.agent_v2_routes._persist_durable_trace` (not at checkpoint
    # creation time, which has no actor_id today) -- see
    # `backend.services.agent_feedback.verify_trace_ownership`, the durable
    # equivalent of the old ring-buffer actor-hash check.
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    pricing_version: Mapped[str | None] = mapped_column(String, nullable=True)
    input_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    # AVAILABLE | NOT_AVAILABLE -- NEVER a fabricated 0 for unknown pricing.
    cost_status: Mapped[str] = mapped_column(String, nullable=False, default="NOT_AVAILABLE")
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Canonical taxonomy -- see backend.agents.v2.runtime's ERROR_CODE_*
    # constants. NULL for a non-error terminal status.
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    empty_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluation_version: Mapped[str | None] = mapped_column(String, nullable=True)
    # BUILD-36: stamped from settings.rag_prompt_version/rag_retriever_version
    # at the same _persist_durable_trace write point as `model` above --
    # deployment-wide constants at any given moment (this app has no
    # per-request prompt/retrieval override), so within one deployment every
    # row gets the same value; the point is enabling a real before/after
    # comparison ACROSS deployments (Admin Monitoring V2's Versions tab),
    # not a per-run varying signal. NULL for any row written before this
    # column existed -- never backfilled/guessed.
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)
    retrieval_version: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("ix_agent_run_conversation_started", "conversation_id", "started_at"),
        Index("ix_agent_run_patient_started", "patient_id", "started_at"),
        Index("ix_agent_run_trace_id", "trace_id"),
        Index("ix_agent_run_status_created", "status", "created_at"),
        Index("ix_agent_run_error_code_created", "error_code", "created_at"),
        Index("ix_agent_run_prompt_version", "prompt_version"),
        Index("ix_agent_run_retrieval_version", "retrieval_version"),
    )


class AgentRunSpan(Base):
    """BUILD-32: one durable, sanitized real-time span per instrumented step
    of one Agent V2 run (router/model/tool/retrieval/safety/handoff/
    checkpoint/guardrail/runtime/time_query/grounding/evaluation -- see
    `backend.agents.v2.observability.TraceComponent`).

    Deliberately NOT a reuse of `AgentToolEvent` (BUILD-32 audit: that table
    is tool-call-specific by schema -- `tool_name` is `NOT NULL` -- and has
    zero writers; forcing a tool name onto e.g. a safety-evaluation span would
    be a semantic mismatch). `started_at`/`completed_at`/`duration_ms` are the
    exact real wall-clock values `AgentTelemetry.span()`/`record_model()`
    measured live during the actual orchestrator/runtime call -- this row is
    written a few milliseconds later (best-effort, post-response, from
    `backend.agents.v2.observability.BufferingSink`), not reconstructed after
    the fact. `metadata_json` holds only the same sanitized attribute
    allowlist already enforced by `observability._sanitize_attributes` --
    never prompts, model reasoning, or raw tool payloads.
    """

    __tablename__ = "agent_run_span"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    span_name: Mapped[str] = mapped_column(String, nullable=False)
    span_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OK")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_agent_run_span_run_started", "agent_run_id", "started_at"),
        Index("ix_agent_run_span_trace_id", "trace_id"),
        Index("ix_agent_run_span_type_started", "span_type", "started_at"),
    )


class AgentRunEvaluation(Base):
    """BUILD-32: durable Evaluation V2 result for one Agent V2 run --
    previously only ever written into `trace.metadata["evaluation_v2"]` on
    the in-memory ring buffer (`backend.services.telemetry`). `metrics_json`
    holds the same sanitized `EvaluationResult.as_dict()` shape
    (`backend.agents.v2.evaluation_v2`) already computed today: per-dimension
    status (AVAILABLE/NOT_APPLICABLE/NOT_AVAILABLE) and score, never hidden
    reasoning.
    """

    __tablename__ = "agent_run_evaluation"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    evaluation_version: Mapped[str] = mapped_column(String, nullable=False)
    execution_path: Mapped[str | None] = mapped_column(String, nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_agent_run_evaluation_agent_run_id", "agent_run_id", unique=True),
        Index("ix_agent_run_evaluation_trace_id", "trace_id"),
    )


class AgentRunJudge(Base):
    """BUILD-33: durable production LLM Judge result for one Agent V2 run.

    Only a sampled/ticketed/anomalous subset of runs ever get a row here (see
    ``backend.agents.v2.judge_eligibility`` -- most COMPLETED runs get none at
    all, by design, never a fabricated "not judged" row). Written in two
    steps, both best-effort and never allowed to affect the real chat
    response:

    1. **Enqueue** (synchronous, cheap, no LLM call) -- right after
       ``AgentRunEvaluation`` is persisted in
       ``backend.api.agent_v2_routes._persist_durable_trace`` (or from
       ``backend.services.agent_feedback.create_ticket`` for a reported
       turn), a row is inserted with ``judge_status="JUDGE_PENDING"`` and a
       sanitized input snapshot (below). This is the ONLY place the actual
       query/response TEXT for a Judge-eligible run is captured: BUILD-32's
       durable ``AgentRun``/``AgentRunSpan`` deliberately never carry it
       (privacy-minimization, see that build's report §6), and the in-memory
       ring buffer that does hold it is not guaranteed to still have it by
       the time a background worker tick runs later.
    2. **Score** (asynchronous, out-of-band, real LLM call) --
       ``backend.services.agent_judge_worker.process_pending_judge_batch``,
       run periodically off ``backend.services.escalation_scheduler``'s
       existing shared APScheduler (never inline in the request/response
       path), updates the same row to ``JUDGE_COMPLETED``/``JUDGE_FAILED``.

    ``sanitized_query``/``sanitized_response``/``sanitized_context_json`` hold
    ONLY what ``judge_input.build_judge_input`` assembled after its own
    PII/PHI rejection guard: user query, final response, execution_path, tool
    NAMES (never raw tool output/payload), citation labels, and (for a
    golden-set case, BUILD-35) the expected ground truth. Never a system
    prompt, chain-of-thought, JWT/credential, or unrelated patient history.

    Safety/Handoff authority is structurally unaffected: nothing in
    ``backend/agents/v2/orchestrator.py``, ``safety.py``, or ``runtime.py``
    ever reads this table -- a Judge result is display/review-only, exactly
    per BUILD-33 §5's "Judge KHONG duoc tu thay doi Safety/Handoff runtime
    decision."
    """

    __tablename__ = "agent_run_judge"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)

    judge_status: Mapped[str] = mapped_column(String, nullable=False, default="JUDGE_PENDING")
    eligibility_reason: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    execution_path: Mapped[str | None] = mapped_column(String, nullable=True)

    judge_provider: Mapped[str] = mapped_column(String, nullable=False)
    judge_model: Mapped[str] = mapped_column(String, nullable=False)
    judge_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rubric_name: Mapped[str] = mapped_column(String, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String, nullable=False)
    judge_prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    evaluation_version: Mapped[str | None] = mapped_column(String, nullable=True)

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimension_scores_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    flags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_status: Mapped[str] = mapped_column(String, nullable=False, default="NOT_AVAILABLE")

    sanitized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Duplicate protection (BUILD-33 §8): the same run must never be
        # scored twice under the same model+rubric+prompt configuration. A
        # DIFFERENT judge_model/rubric_version/prompt_version for the same
        # run is a deliberate re-evaluation (e.g. after a rubric bump), not a
        # duplicate, so it is intentionally NOT blocked by this index.
        Index(
            "uq_agent_run_judge_run_model_rubric_prompt",
            "agent_run_id",
            "judge_model",
            "rubric_version",
            "judge_prompt_version",
            unique=True,
        ),
        Index("ix_agent_run_judge_trace_id", "trace_id"),
        Index("ix_agent_run_judge_status_priority_created", "judge_status", "priority", "created_at"),
    )


class AgentSafetyEvent(Base):
    """BUILD-34: canonical, durable Safety/Handoff monitoring event for one
    Agent V2 run. Written best-effort, post-response (same shape as every
    other durability step in ``backend.api.agent_v2_routes``:
    ``_persist_durable_trace``/``enqueue_run_judge``), purely from an
    already-completed ``OrchestrationResult``'s ``safety_decision``/
    ``handoff_result`` -- this table NEVER changes what Safety/Handoff
    decided (BUILD-34 §12: monitoring only, not a redesign of the Safety
    engine), only records it durably for Admin.

    One row per run whose ``SafetyDecision.outcome`` was
    ``SAFETY_BLOCKED`` or ``HANDOFF_REQUIRED`` -- a plain ``SAFE`` outcome
    (the overwhelming majority of traffic) gets no row at all, by design
    (BUILD-34's own "not 100% of traffic" spirit, mirrored from BUILD-33's
    Judge eligibility).

    ``handoff_status``/``resolved_at`` here are a SNAPSHOT taken at the
    moment this row was written -- ``DoctorReviewRequest.status`` can change
    later (a doctor answers/cancels) and this table is deliberately never
    synced back to reflect that (syncing would mean writing to this table
    from the doctor-side resolution route, a real behavior-adjacent change
    outside BUILD-34's monitoring-only scope). Admin reads for CURRENT
    status/unresolved-count/time-to-review always LEFT JOIN
    ``DoctorReviewRequest`` live via ``handoff_id`` -- see
    ``backend.services.agent_safety_monitoring`` -- never trust this row's
    own snapshot columns for "is this resolved right now."
    """

    __tablename__ = "agent_safety_event"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)

    outcome: Mapped[str] = mapped_column(String, nullable=False)  # SAFETY_BLOCKED | HANDOFF_REQUIRED
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)  # LOW | MEDIUM | HIGH | CRITICAL
    severity_source: Mapped[str] = mapped_column(String, nullable=False)  # risk_level_field | reason_code_mapped
    safety_path: Mapped[str | None] = mapped_column(String, nullable=True)  # Evaluation V2 execution_path (SAFETY|HANDOFF)
    provenance: Mapped[str | None] = mapped_column(String, nullable=True)  # SafetyDecision.provenance

    handoff_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handoff_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handoff_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Snapshot only -- see class docstring. Never re-read as "current" status.
    handoff_status: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. HANDOFF_FAILURE

    evaluation_version: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Deliberately always NULL on this row -- resolution is read live from
    # DoctorReviewRequest.answered_at/cancelled_at, never synced here. Kept
    # as a real column (not omitted) because BUILD-34's own canonical
    # contract names it explicitly; see class docstring for why it stays
    # unpopulated rather than a second, staleness-prone copy of state.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_agent_safety_event_agent_run_id", "agent_run_id"),
        Index("ix_agent_safety_event_trace_id", "trace_id"),
        Index("ix_agent_safety_event_patient_id", "patient_id"),
        Index("ix_agent_safety_event_handoff_id", "handoff_id"),
        Index("ix_agent_safety_event_severity_created", "severity", "created_at"),
        Index("ix_agent_safety_event_reason_code_created", "reason_code", "created_at"),
        Index("ix_agent_safety_event_created_at", "created_at"),
    )


class AgentRunCheckpoint(Base):
    """Durable, sanitized execution checkpoint for the disabled Agent V2 path.

    This table intentionally stores references and state-machine values only.
    It never stores prompts, model reasoning, tool arguments/results, tokens,
    secrets, or a copy of patient conversation content.
    """

    __tablename__ = "agent_run_checkpoint"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workflow_state: Mapped[str] = mapped_column(String, nullable=False)
    completed_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resolved_entities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    verified_context_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    safety_disposition: Mapped[str | None] = mapped_column(String, nullable=True)
    pending_action: Mapped[str] = mapped_column(String, nullable=False)
    terminal_status: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_agent_run_checkpoint_run", "agent_run_id", unique=True),
        Index("ix_agent_run_checkpoint_pending_updated", "pending_action", "updated_at"),
        Index("ix_agent_run_checkpoint_terminal_updated", "terminal_status", "updated_at"),
    )


class AgentIdempotencyKey(Base):
    """BUILD-22: HTTP-level replay record for /agent/v2/orchestrate.

    Distinct from ``AgentRunCheckpoint`` (crash-recovery resume of an
    in-flight run): this row lets a caller's retried HTTP request for an
    ALREADY-FINISHED run get back the exact same response without invoking
    the orchestrator again. The unique constraint on
    ``(actor_id, patient_id, idempotency_key)`` is the sole concurrency gate
    -- a genuinely concurrent duplicate blocks on the DB-level unique-index
    insert until the first request commits, then observes its final
    ``COMPLETED`` row. Bound to both actor and patient so an identical key
    string from a different account or for a different patient can never
    collide with or replay someone else's run.
    """

    __tablename__ = "agent_idempotency_key"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_agent_idempotency_key_actor_patient_key",
            "actor_id",
            "patient_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_agent_idempotency_key_expires_at", "expires_at"),
    )


class AgentToolEvent(Base):
    """DB Architecture V2 sanitized tool-call audit event."""

    __tablename__ = "agent_tool_event"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    input_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_agent_tool_event_run_created", "agent_run_id", "created_at"),
        Index("ix_agent_tool_event_tool_created", "tool_name", "created_at"),
    )


class AgentFeedbackTicket(Base):
    """BUILD-29: a patient's direct report of a problematic Agent V2 reply,
    with everything an Admin needs to trace it back to the exact
    conversation/trace that produced it.

    ``actor_id``/``patient_id`` are ALWAYS bound server-side from the
    authenticated JWT (see ``backend.services.agent_feedback.create_ticket``)
    -- never trusted from the request body, so a caller cannot file a report
    "as" another patient. ``conversation_id``/``trace_id``/``agent_run_id``
    and the message text itself DO come from the client (the values it
    already received back from a real ``/agent/v2/orchestrate`` call), since
    Agent V2 has no durable server-side message log to read them back from
    (short-term memory is process-local/ephemeral by design -- see
    ``backend.agents.v2.short_term_memory``); ``trace_id`` ownership is still
    verified against the telemetry buffer when the trace is still present
    (``backend.services.agent_feedback.verify_trace_ownership``), so a
    fabricated trace_id belonging to a different account is rejected rather
    than silently accepted.

    ``priority``/``p0_review_required`` are always server-assigned
    (``classify_priority``) -- a reporting patient never sets their own
    priority.
    """

    __tablename__ = "agent_feedback_ticket"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_message: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    chatbot_version: Mapped[str] = mapped_column(String, nullable=False, default="agent-v2")
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")
    priority: Mapped[str] = mapped_column(String, nullable=False)
    p0_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # BUILD-29 §9 idempotency anchor: one (actor, assistant turn, reason)
        # combination can only ever produce one ticket -- a double-click or
        # retried submit hits this unique index and the existing row is
        # returned instead of a duplicate being inserted (see
        # ``agent_feedback.create_ticket``'s ``IntegrityError`` handling,
        # mirroring ``backend.services.agent_idempotency``'s savepoint
        # pattern). A patient reporting the SAME turn for a DIFFERENT reason
        # is a deliberately distinct ticket, not a duplicate.
        Index(
            "uq_agent_feedback_ticket_actor_run_reason",
            "actor_id",
            "agent_run_id",
            "reason",
            unique=True,
        ),
        Index("ix_agent_feedback_ticket_status_created", "status", "created_at"),
        Index("ix_agent_feedback_ticket_priority_created", "priority", "created_at"),
        Index("ix_agent_feedback_ticket_conversation", "conversation_id"),
        Index("ix_agent_feedback_ticket_chatbot_version", "chatbot_version"),
        # BUILD-36 audit: judge_result_out()/agent_safety_monitoring's
        # ticket<->safety-event correlation both filter directly by these
        # two columns (neither previously indexed) -- added once BUILD-36
        # made this a genuinely hot path (ticket detail drill-down), not
        # speculatively for every column that is ever filtered on.
        Index("ix_agent_feedback_ticket_trace_id", "trace_id"),
        Index("ix_agent_feedback_ticket_agent_run_id", "agent_run_id"),
    )


class AgentActivitySnapshot(Base):
    """BUILD-30: one durable, sanitized activity timeline per real Agent V2
    run -- the source of truth for GET /agent/v2/traces/{trace_id}/activity.

    Deliberately NOT sourced from (or dependent on) the telemetry ring
    buffer (``backend.services.telemetry``, capped at 200 traces process-
    wide, reset on every deploy -- see BUILD-29's own documented limitation
    for the admin ticket explorer). This table is written once, best-effort,
    right after ``AgentOrchestrator.run()`` returns (see
    ``backend.api.agent_v2_routes._persist_activity_snapshot``), from the
    real ``OrchestrationResult`` alone -- so it survives redeploys and does
    not compete for space with unrelated traffic. A run from before this
    table existed simply has no row (honest "unavailable", not a fabricated
    empty timeline).

    ``activities_json`` holds ONLY the sanitized DTO shape
    (type/label/status/duration_ms/source_count) built by
    ``backend.services.agent_activity.build_activity_timeline`` -- never
    prompts, model reasoning, raw tool arguments/results, or any other
    internal detail. ``patient_id`` is stored directly (not a one-way hash)
    since this table is only ever read back through the patient-safe
    activity endpoint, which checks it by plain equality against the
    requesting patient's own JWT-bound patient_id.
    """

    __tablename__ = "agent_activity_snapshot"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_run_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    intent: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_agent_activity_snapshot_agent_run_id", "agent_run_id", unique=True),
        Index("ix_agent_activity_snapshot_trace_id", "trace_id"),
        Index("ix_agent_activity_snapshot_patient_created", "patient_id", "created_at"),
    )


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
    # PENDING|TAKEN|MISSED|DELAYED|CANCELLED|AWAITING_CAREGIVER - them
    # AWAITING_CAREGIVER 2026-08-12 (khop api-contracts.md §3, cot nay truoc do
    # thieu gia tri nay dung khong dong bo voi contract) khi ADR-0011 het 2 lan
    # chup lai anh van khong khop - xem backend/services/photo_verification/verifier.py.
    status: Mapped[str] = mapped_column(String, nullable=False)
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


class HourlyConversationSummary(Base):
    """Vong 4, muc 5 - tom tat doc lap cua 1 gio hoi thoai da ket thuc.

Khac voi cua so 15 phut, ban ghi nay khong bao gio duoc tu dong dua vao
intent/answer prompt. Chi `chat_history_query` va dashboard tuong lai moi
doc. `hidden` giu nguyen nghia "an lich su" cua ChatMessage cho ca summary.
"""

    __tablename__ = "hourly_conversation_summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_count: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    hidden: Mapped[bool] = mapped_column(nullable=False, default=False)

    __table_args__ = (Index("uq_hourly_conversation_summaries_patient_hour", "patient_id", "hour_bucket", unique=True),)


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
    # So diem thuong VUA cong khi anh nay duoc xac nhan KHOP (THEM
    # 2026-08-26, migration 0051) - xem backend/services/reward_ledger.py
    # ::award_dose_on_time. NULL o moi dong khac (lech/khong_xac_minh_duoc/
    # loi_he_thong/do_tin_cay_thap/AWAITING_CAREGIVER), khong phai 0: NULL
    # nghia la "khong ap dung", 0 se lam FE tuong nham la co xet nhung
    # khong duoc gi. Cho GET /photo-verifications/{id} (patient/page.tsx
    # poll ket qua) bao ngay "+N diem" ma benh nhan khong phai mo rieng
    # trang Diem thuong.
    points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Account(Base):
    """TASK-010 (api-contracts.md muc 1, auth-api) - 1 bang chung cho CAC
    role (doctor|patient|caregiver|admin|super_admin), phan biet qua cot `role`.
    - `super_admin`: quyen cao nhat, quan ly moi tai khoan ke ca admin.
    - `admin`: quan tri vien van hanh, chi quan ly doctor|patient|caregiver.

    `patient_id`/`doctor_id` la lien ket TOI THIEU de get_current_patient_id()
    (backend/api/security.py) doc duoc patient_id cua chinh nguoi dang dang
    nhap khi role=patient - CHUA phai mo hinh lien ket day du bac si<->benh
    nhan<->nguoi than (user-roles.md, thuoc FEAT-001/quan ly tai khoan cua
    admin, ngoai pham vi TASK-010). KHONG lien quan gi den bang `Patient`
    (patient_id o day la string tu do, khop DoseEvent/Prescription.patient_id
    - Patient la 1 khai niem khac, xem class Patient o tren)."""

    __tablename__ = "account"

    # UNIQUE tren BIEU THUC `lower(btrim(email))` (migration 0026): "1 email =
    # 1 tai khoan" khong phan biet chu hoa/thuong. UNIQUE tren cot `email` o
    # duoi KHONG du - Postgres so sanh chuoi co phan biet chu hoa/thuong, nen
    # "MCK@gmail.com" va "mck@gmail.com" la 2 dong hop le, tao ra 2 tai khoan
    # cho cung 1 nguoi (bug that 2026-08-17: dang ky tay bang chu hoa roi bam
    # "Login with Google" - Google tra ve email chuan hoa).
    #
    # Khai bao o day de model KHOP voi DB that, va de bieu thuc chi ton tai o
    # 3 cho PHAI trung nhau tung chu: index nay, migration 0026, va
    # backend/services/email_identity.py::account_email_key() (bieu thuc dung
    # khi tra cuu - lech mot ky tu la Postgres bo qua index, moi lan dang nhap
    # thanh 1 lan quet ca bang).
    __table_args__ = (
        Index("ux_account_email_normalized", text("lower(btrim(email))"), unique=True),
    )

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
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verification_token: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # THEM sau (migration 0018) - moc thoi gian doi mat khau gan nhat, dung de
    # THU HOI moi token da phat truoc do (JWT khong the "xoa" tu xa, nen phai
    # co 1 moc trong DB de so voi claim `iat` - xem backend/services/auth.py::
    # token_revoked_by_password_change). NULL = chua tung doi mat khau ->
    # khong thu hoi gi (tai khoan tao truoc migration 0018).
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # THEM sau (migration 0025, "Login with Google") - "password" | "google".
    # Tai khoan sinh ra tu Google KHONG co mat khau nguoi dung nao ca:
    # `password_hash` cua no la bcrypt cua 1 chuoi ngau nhien khong ai biet
    # (xem auth_routes.py::_oauth_upsert_account) - co y, de POST /auth/login
    # bang mat khau khong bao gio dang nhap duoc vao tai khoan Google, thay vi
    # de password_hash rong/NULL (verify_password se nem loi thay vi tra False).
    # Cot nay la cach DUY NHAT phan biet "chua tung dat mat khau" - thieu no
    # thi luong doi mat khau se doi "mat khau hien tai" cua thu khong ton tai.
    auth_provider: Mapped[str] = mapped_column(String, nullable=False, default="password")
    # THEM sau (migration 0031, ADR-0013 Supabase Auth migration) - Supabase User UUID (neu co)
    supabase_uid: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)


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


class CaregiverLink(Base):
    """Bang lien ket bac si<->benh nhan<->nguoi than THAT (specs/user-roles.md:
    1 benh nhan co 0..n nguoi than, 1 nguoi than co the gan voi nhieu benh
    nhan, CHI admin duoc quan ly lien ket nay). THEM 2026-08-13 (migration 0016).

    Truoc bang nay, `Account.patient_id` (backend/db/models.py::Account) chi
    cho 1 tai khoan role=caregiver gan voi DUY NHAT 1 patient_id - khong dung
    duoc cho truong hop 1 nguoi than theo doi nhieu benh nhan (vd 1 nguoi con
    cham 2 bo me). Bang nay KHONG thay the Account.patient_id (van giu de
    tuong thich nguoc voi TASK-010), la lop lien ket RONG HON, dung rieng cho
    2 man hinh moi: "nguoi lien he gia dinh" cua bac si (xem 1 benh nhan) va
    "nguoi than dang theo doi" cua caregiver (xem nhieu benh nhan).

    `caregiver_account_id`/`patient_id` la string tu do, KHONG dat FK that -
    cung ly do da giai thich tren class Patient o tren: cac thanh vien khac
    co the dang co san du lieu patient_id/account_id chua duoc don, them FK
    ngay bay gio se lam `alembic upgrade` cua ho loi giua chung. Kiem tra ton
    tai o tang service/route neu can (404 ro rang), khong dua vao rang buoc DB."""

    __tablename__ = "caregiver_link"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    caregiver_account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    relationship: Mapped[str] = mapped_column(String, nullable=False)  # vd "Con gái"/"Vợ"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # THEM 2026-08-13 (migration 0020) - "pending"|"accepted". Admin tao thang
    # ("accepted") - da xac nhan thay. Benh nhan tu moi nhau qua POST
    # /caregiver-links/invites bat dau "pending", chi hien trong danh sach
    # dang theo doi (GET ?caregiver_account_id=) sau khi nguoi duoc theo doi
    # tu chap nhan (POST /caregiver-links/{id}/accept).
    status: Mapped[str] = mapped_column(String, nullable=False, default="accepted")


class Nudge(Base):
    """1 lời nhắc nhẹ nguoi than gui cho benh nhan dang theo doi (THEM
    2026-08-20, migration 0030) - qua sheet "Nhac nhe" o /patient/family
    (frontend/src/app/patient/family/page.tsx). Benh nhan poll GET
    /nudges/unseen (backend/api/nudge_routes.py) de hien banner trong app -
    repo chua co ha tang realtime (WebSocket/SSE) nen dung short polling,
    xem ADR chon huong trong plan tinh nang nay.

    `seen_at` duoc set NGAY trong chinh request GET /nudges/unseen tra ve
    dong do (kieu "pop khoi hang doi") - khong co endpoint ack rieng, cung
    trang thai don gian hoa nhu Escalation.ack (POST /escalations/{id}/ack):
    hanh dong vo hai, khong can xu ly race condition rieng.

    `caregiver_account_id`/`patient_id` la string tu do, KHONG dat FK that -
    cung ly do da giai thich o CaregiverLink/Patient o tren."""

    __tablename__ = "nudge"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    caregiver_account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PushSubscription(Base):
    """1 thiet bi da dong y nhan Web Push cua 1 benh nhan (THEM 2026-08-20,
    migration 0031). Nho co bang nay, backend gui duoc thong bao toi may benh
    nhan NGAY CA KHI ho da dong han tab/trinh duyet - dieu ma co che poll o
    client (frontend/src/components/capy/capy-shell.tsx) khong lam duoc.

    `endpoint` la URL rieng do dich vu day cua chinh trinh duyet cap (FCM cho
    Chrome, Mozilla autopush cho Firefox, Apple Push cho Safari) - dat UNIQUE
    vi no chinh la danh tinh cua 1 thiet bi: subscribe lai tu cung may phai
    UPSERT dong cu, khong de sinh ra 2 dong roi ban trung 2 lan.

    `p256dh`/`auth` la 2 khoa trinh duyet cap de MA HOA payload - khong co
    chung thi dich vu day chi chuyen duoc goi tin rong.

    `patient_id` la string tu do, KHONG dat FK that - cung ly do da giai
    thich o CaregiverLink/Nudge o tren."""

    __tablename__ = "push_subscription"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String, nullable=False)
    auth: Mapped[str] = mapped_column(String, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PushReminderSent(Base):
    """Da day push cho (benh nhan, khung gio, moc) nao roi - ban ghi PHIA
    SERVER tuong duong localStorage cua client (frontend/src/lib/
    dose-reminder-log.ts), nhung dung chung cho MOI thiet bi cua benh nhan
    nen khong bi day trung khi ho dang nhap tren 2 may.

    Khoa duy nhat la (patient_id, slot_at, moc) - `slot_at` la KHUNG GIO chu
    khong phai dose_event_id: nhieu thuoc cung hen 1 gio la nhieu dong
    DoseEvent rieng nhung chi dang 1 lan nhac (xem dose_push_reminder.py)."""

    __tablename__ = "push_reminder_sent"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False)
    slot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    moc: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 | 15 | 30 (phut ke tu gio hen)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("patient_id", "slot_at", "moc", name="uq_push_reminder_sent_slot"),
    )


class DoctorWatch(Base):
    """1 bac si dang "theo doi" 1 benh nhan (THEM 2026-08-14, migration 0023,
    thay `Patient.watch` cu - xem ghi chu tren class Patient). Khac
    `Patient.doctor_id` (bac si PHU TRACH, chi 1) - 1 benh nhan co the duoc
    NHIEU bac si theo doi doc lap (vd hoi chan), moi nguoi tu bam nut "Theo
    doi" rieng, khong anh huong nhau.

    Dung lam DICH loc "Hop canh bao"/chuong thong bao trong app (GET
    /escalations, backend/api/reporting_routes.py::list_escalations) - bac
    si CHI thay canh bao cua benh nhan minh dang theo doi, khong phai toan
    bo benh nhan (quyet dinh PM 2026-08-14).

    `doctor_id`/`patient_id` la string tu do, KHONG dat FK that - cung ly do
    da giai thich o CaregiverLink/Patient o tren."""

    __tablename__ = "doctor_watch"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    doctor_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("uq_doctor_watch_doctor_patient", "doctor_id", "patient_id", unique=True),
    )


class SystemAuditLog(Base):
    """Luu vet nhat ky he thong (System Audit Log).
    APPEND-ONLY: Khong duoc UPDATE hoac DELETE tu code ung dung (rang buoc an toan).
    Ho tro ghi nhat ky hanh dong cua Admin, Bac si, Benh nhan va He thong.
    """

    __tablename__ = "system_audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String, nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )


class AgentGoldenRun(Base):
    """BUILD-36: durable persistence for one BUILD-35 golden-evaluation run.

    BUILD-35's own runner (``scripts/agent_v2/run_golden_evaluation.py``)
    deliberately only ever wrote JSON/Markdown files to a gitignored local
    directory -- fine for a human running it on their own machine, but a
    live Admin dashboard cannot query a file that only exists on whichever
    laptop/CI runner happened to execute the last golden run. This table is
    populated by that SAME runner's own optional ``--persist`` flag (never
    by any other writer) -- additive only, the JSON/Markdown file output is
    completely unchanged. ``id`` reuses the runner's own ``run_id`` (already
    a unique, sortable UTC timestamp string, e.g. "20260825T070211Z") rather
    than a fresh UUID, so a human comparing a dashboard row to a JSON
    filename on disk sees the exact same identifier.

    The `*_json` columns are the runner's own already-computed dicts,
    stored verbatim (same values the JSON file on disk has) -- this table
    is a durable mirror of that JSON, not a re-derivation of it. The
    handful of denormalized top-level columns (``pass_rate``,
    ``regression_gate_passed``, etc.) exist ONLY so "latest run"/"gate
    currently failing" queries do not need to parse JSON in SQL -- they are
    computed once at persist time from the same source, never independently.
    """

    __tablename__ = "agent_golden_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    golden_set_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    git_commit: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # NULL (not 0.0) when total_cases == 0 -- same "never fabricate a rate
    # from a zero denominator" rule as every rate this project computes.
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    regression_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    aggregate_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    regression_gate_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    comparisons_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # index=True already generates ix_agent_golden_run_created_at -- an
    # earlier version of this class ALSO declared the same index explicitly
    # in __table_args__ under the identical name, which is a hard duplicate
    # (not just redundant) and fails table creation outright. Caught by
    # this build's own new unit tests failing to even set up their SQLite
    # fixture, not by inspection.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)


class AgentGoldenRunCase(Base):
    """BUILD-36: one row per golden case's result within one persisted
    ``AgentGoldenRun`` -- lets the dashboard list/filter failed cases by
    category without parsing the parent row's JSON. Deliberately no hard FK
    to ``AgentGoldenRun.id`` (plain indexed string column) -- same
    no-hard-FK-between-operational-tables convention this project already
    uses for ``AgentSafetyEvent``/``DoctorReviewRequest`` and every other
    BUILD-32-35 durable table.
    """

    __tablename__ = "agent_golden_run_case"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # No index=True here -- __table_args__ below already declares
    # ix_agent_golden_run_case_run_id explicitly; index=True would generate
    # the identical name a second time (the same real duplicate-index bug
    # AgentGoldenRun's own created_at column had, caught by this build's
    # own unit tests failing to even set up their SQLite fixture).
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checks_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_agent_golden_run_case_run_id", "run_id"),
        Index("ix_agent_golden_run_case_category_passed", "category", "passed"),
    )


class PatientRewardAccount(Base):
    """So diem thuong cua 1 benh nhan (THEM 2026-08-25, migration 0049).

    Hai loai diem TACH RIENG, khong suy ra duoc tu nhau:
      - `lifetime_points` (LP): CHI TANG, khong bao gio giam - dung de xet
        Rank tron doi (Dong/Bac/Vang/Kim Cuong). Doi qua KHONG dung toi cot
        nay, nen benh nhan da len Rank thi giu Rank vinh vien (yeu cau
        nghiep vu ro rang trong reward/reward.md).
      - `spendable_points` (SP): tang cung luc voi LP khi duoc thuong, nhung
        GIAM khi doi qua. Day la so du that su tieu duoc.

    Moi lan cong/tru deu ghi kem 1 dong PatientRewardEvent - bang nay chi la
    ban TONG HOP de doc nhanh (khong phai phai cong don ca ledger moi biet so
    du). Hai bang phai luon duoc ghi trong CUNG 1 transaction.

    `patient_id` la khoa chinh (moi benh nhan dung 1 dong duy nhat) va la
    string tu do, KHONG dat FK that - cung ly do da giai thich o
    CaregiverLink/Patient o tren."""

    __tablename__ = "patient_reward_account"

    patient_id: Mapped[str] = mapped_column(String, primary_key=True)
    lifetime_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spendable_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PatientRewardEvent(Base):
    """Ledger append-only: MOI lan cong/tru diem la 1 dong (THEM 2026-08-25,
    migration 0049). Vua la lich su hien cho benh nhan xem, vua la co che
    CHONG CONG TRUNG.

    `occurred_on` la NGAY (local, khong phai timestamp) ma su kien duoc tinh
    cong - cung voi UniqueConstraint ben duoi, no bien "cong diem 1 lan/ngay"
    thanh rang buoc o tang DB thay vi chi la if/else o tang service: goi
    award_* nhieu lan trong cung 1 ngay chi co dong dau tien duoc ghi, cac
    lan sau bi DB tu choi (IntegrityError -> service nuot va bo qua).

    Rieng event_type="REDEEM" (doi qua) KHONG chiu rang buoc 1-lan/ngay do:
    benh nhan co the doi nhieu mon khac nhau trong cung 1 ngay. De van chan
    duoc "doi trung 1 mon", REDEEM dung `item_id` (cot rieng ben duoi) -
    xem reward_ledger.redeem_item(). Vi vay `occurred_on` cua REDEEM van
    duoc ghi (de hien lich su theo ngay) nhung khong tham gia khoa duy nhat
    -> UniqueConstraint chi ap dung cho cac loai theo-ngay, va de lam duoc
    the ma van dung 1 constraint, REDEEM ghi `occurred_on` = NULL.

    `points_delta` am khi tru (doi qua), duong khi cong. `item_id` chi co
    gia tri voi REDEEM, NULL voi moi loai khac.

    `patient_id` la string tu do, KHONG dat FK that - cung ly do da giai
    thich o CaregiverLink/Patient o tren."""

    __tablename__ = "patient_reward_event"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # DOSE_ON_TIME | DAILY_SURVEY | WEEKLY_STREAK | MONTHLY_STREAK | REDEEM
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    points_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL voi REDEEM (xem docstring) - co gia tri voi cac loai cong theo ngay.
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Chi co gia tri voi REDEEM: slug mon qua trong reward_catalog.py.
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nhan hien thi tren lich su, chot lai TAI THOI DIEM ghi (vd ten mon qua)
    # - gia/ten trong catalog co the doi ve sau, lich su cu phai giu nguyen.
    label: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        # Postgres coi moi NULL la khac nhau -> cac dong REDEEM (occurred_on
        # NULL) khong bao gio dung nhau o index nay, dung nhu y muon.
        #
        # LOAI TRU DOSE_ON_TIME (migration 0050): tu 2026-08-26 diem uong
        # thuoc cong theo TUNG LIEU nen 1 ngay co nhieu dong. Cac loai con
        # lai VAN phai 1-lan-moi-ngay va van duoc DB chan o day. Rieng
        # DOSE_ON_TIME chong cong trung o tang service bang phep tru
        # "dang le duoc" - "da cong hom nay" (reward_ledger).
        Index(
            "uq_patient_reward_event_daily_non_dose",
            "patient_id",
            "event_type",
            "occurred_on",
            unique=True,
            # Khai cho CA HAI dialect: prod chay Postgres, nhung test
            # (tests/test_reward_ledger.py) dung SQLite in-memory. Neu chi
            # co postgresql_where, SQLAlchemy bo qua no tren SQLite va tao
            # index unique TOAN PHAN -> chan mat dong DOSE_ON_TIME thu hai
            # trong ngay, test do nhung prod xanh (hoac nguoc lai).
            postgresql_where=text("event_type <> 'DOSE_ON_TIME'"),
            sqlite_where=text("event_type <> 'DOSE_ON_TIME'"),
        ),
        Index("ix_patient_reward_event_patient_created", "patient_id", "created_at"),
        Index("ix_patient_reward_event_patient_item", "patient_id", "item_id"),
    )



class TelegramLink(Base):
    """1 tai khoan Telegram da noi voi 1 benh nhan (THEM 2026-08-27, migration
    0056) - kenh nhac gio uong thuoc THU HAI ben canh Web Push.

    TAI SAO PHAI CO BANG NAY, khong dung thang so dien thoai benh nhan da co o
    Patient.phone: Bot API cua Telegram khong gui duoc tin theo so dien thoai
    hay email, chi theo `chat_id`, va chat_id CHI sinh ra sau khi chinh nguoi
    dung bam /start voi bot (co che chong spam cua Telegram, khong phai thieu
    sot API). Vi vay quan he benh nhan <-> chat_id phai luu lai o day sau khi
    ghep thanh cong 1 lan, dung mai ve sau.

    `account_id` la string tu do, KHONG dat FK that - cung ly do da giai thich
    o class Patient/PushSubscription."""

    __tablename__ = "telegram_link"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # KHOA THEO TAI KHOAN, khong theo ho so benh nhan (doi o migration 0059):
    # nguoi than cung phai nhan duoc canh bao ma ho khong co patient_id - ho
    # la Account role=caregiver noi qua caregiver_link. "1 tai khoan = 1
    # Telegram" cung xu ly luon nguoi vua la benh nhan vua la nguoi than cua
    # vo/chong: 1 dong duy nhat, nhan ca hai loai tin.
    account_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # BigInteger: xem ghi chu trong migration 0056 (id Telegram vuot 2^31).
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    # False = benh nhan tam tat nhac Telegram nhung VAN giu lien ket, bat lai
    # chi la 1 cu gat (migration 0057). Khac han viec xoa dong nay - xoa xong
    # muon nhan lai phai lam lai ca luong ghep tu dau.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class TelegramLinkToken(Base):
    """Ma dung 1 lan de ghep "nguoi vua bam /start tren Telegram" voi "benh
    nhan dang dang nhap tren web" (THEM 2026-08-27, migration 0056).

    Luong: web sinh token -> mo link t.me/<bot>?start=<token> -> Telegram gui
    "/start <token>" toi bot -> backend doi token lay chat_id -> ghi
    TelegramLink. Khong co token thi backend nhan duoc chat_id nhung KHONG
    biet no la cua benh nhan nao.

    `used_at` giu lai dong da dung thay vi xoa - de phan biet "token sai/bia"
    voi "token dung nhung da xai roi", tra loi duoc dung thong bao cho nguoi
    dung khi ho bam lai link cu."""

    __tablename__ = "telegram_link_token"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PatientNotificationPref(Base):
    """Tuy chon thong bao cua 1 benh nhan (THEM 2026-08-27, migration 0058).

    HAI TANG, co y tach roi:
      - `dose_reminder_enabled` = tang 1, CO muon duoc nhac uong thuoc khong
      - `web_push_enabled`      = tang 2, nhac qua duong nao

    Tat tang 1 thi khong kenh nao gui, du tung kenh van dang bat - dung thu
    tu ma nguoi dung mong doi khi nhin man hinh Cai dat.

    Kenh Telegram KHONG o day ma o TelegramLink.enabled: kenh do chi ton tai
    khi co lien ket, luu chung voi lien ket thi xoa lien ket la sach ca tuy
    chon, khong de lai dong mo coi.

    KHONG tao san dong cho moi benh nhan: khong co dong = mac dinh bat het
    (xem lay_tuy_chon trong backend/services/notification_pref.py). Chi ghi
    khi benh nhan that su doi gi do."""

    __tablename__ = "patient_notification_pref"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    dose_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    web_push_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
