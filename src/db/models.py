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

from src.db.base import Base

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
    status: Mapped[str] = mapped_column(String, nullable=False)  # draft|approved|active|completed|stopped
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    start_date: Mapped[str] = mapped_column(String, nullable=False)  # ISO date string, don gian hoa cho MVP
    duration_days: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


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
