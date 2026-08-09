"""Phase 1 Definition of Done (specs/build-kickoff-prompt.md):
insert 1 chunk mau + 1 audit log mau, doc lai dung du lieu.

Day la integration test - can Postgres that dang chay (docker compose up -d db).
Tu dong skip neu khong ket noi duoc, khong lam fail toan bo test suite khi chua
co DB (vd may CI chua cau hinh service Postgres).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from src.db.base import SessionLocal, engine
from src.db.models import AuditLog, DrugChunk

EMBEDDING_DIM = 1536


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_insert_and_read_drug_chunk(db_session):
    """1 chunk mau, giong dung format thuc te (xem data pharmacy/Thuoc kháng virus/thuoc.json)."""
    fake_embedding = [0.001] * EMBEDDING_DIM

    chunk = DrugChunk(
        drug_id="agiclovir-5-agimexpharm",
        ten_thuoc="Agiclovir 5% Agimexpharm",
        danh_muc="Thuốc kháng virus",
        muc_nghiem_trong="Nguy hiểm",
        field_group="cach_dung",
        noi_dung="Thuốc mỡ dùng bôi ngoài.",
        noi_dung_unaccent="Thuoc mo dung boi ngoai.",
        ten_thuoc_unaccent="agiclovir 5% agimexpharm",
        embedding=fake_embedding,
        created_at=datetime.now(UTC),
    )
    db_session.add(chunk)
    db_session.commit()

    got = db_session.get(DrugChunk, chunk.id)
    assert got is not None
    assert got.drug_id == "agiclovir-5-agimexpharm"
    assert got.ten_thuoc == "Agiclovir 5% Agimexpharm"
    assert got.field_group == "cach_dung"
    assert got.muc_nghiem_trong == "Nguy hiểm"
    assert len(got.embedding) == EMBEDDING_DIM

    db_session.delete(got)
    db_session.commit()


def test_insert_and_read_audit_log(db_session):
    """1 audit log mau dung format AuditLogDTO (chatbot-rag-design.md muc 5.2)."""
    trace = [
        {"step": "safety_layer", "keyword_hit": False, "llm_flag": False, "model": None, "duration_ms": 8},
        {
            "step": "intent_classification",
            "model": "gpt-4o-mini",
            "result": "drug_info",
            "confidence": 0.93,
            "duration_ms": 340,
        },
    ]
    log = AuditLog(
        patient_id="usr_02",
        dose_event_id="dose_1001",
        utterance="thuốc này uống lúc nào",
        created_at=datetime.now(UTC),
        trace=trace,
        final_response="Uống sau ăn sáng và sau ăn tối.",
        total_duration_ms=1025.0,
    )
    db_session.add(log)
    db_session.commit()

    got = db_session.get(AuditLog, log.id)
    assert got is not None
    assert got.patient_id == "usr_02"
    assert got.trace[0]["step"] == "safety_layer"
    assert got.trace[1]["confidence"] == 0.93
    assert got.final_response == "Uống sau ăn sáng và sau ăn tối."

    db_session.delete(got)
    db_session.commit()


def test_hnsw_and_trgm_indexes_exist(db_session):
    """Xac nhan index HNSW + GIN trigram (mucd 4 chatbot-rag-design.md) da duoc tao dung boi migration."""
    rows = db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'drug_chunks'")
    ).fetchall()
    index_names = {r[0] for r in rows}
    assert "ix_drug_chunks_embedding_hnsw" in index_names
    assert "ix_drug_chunks_noi_dung_unaccent_trgm" in index_names
    assert "ix_drug_chunks_ten_thuoc_unaccent_trgm" in index_names


def test_extensions_enabled(db_session):
    rows = db_session.execute(text("SELECT extname FROM pg_extension")).fetchall()
    ext_names = {r[0] for r in rows}
    assert "vector" in ext_names
    assert "pg_trgm" in ext_names
    assert "unaccent" in ext_names
