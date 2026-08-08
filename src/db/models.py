"""ORM models:
  - drug_chunks: RAG data thuoc, 4 chunk/thuoc (Phase 1/3, chatbot-rag-design.md muc 3.1)
  - audit_log: AuditLogDTO, append-only (Phase 1, BR-7.5, chatbot-rag-design.md muc 5.2)

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
