"""SQLAlchemy engine/session setup - PostgreSQL + pgvector (ADR-0008).

Khong dung SQLite fallback cho phan RAG - pgvector extension chi co tren
PostgreSQL, va DATABASE_URL mac dinh trong config.py da tro thang toi
Postgres (xem docker-compose.yml). Neu can chay test khong co Postgres
that, dung pytest marker rieng (xem tests/test_db_phase1.py) thay vi doi
engine ngam.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _set_hnsw_ef_search(dbapi_connection, connection_record) -> None:
    """Vong 2, muc 6/15 (chatbot-rag-design.md) - `hnsw.ef_search` la GUC
    theo SESSION (moi connection Postgres), KHONG tu ap dung toan cuc chi vi
    dat trong config.py - phai SET tren TUNG connection. Choke-point DUY
    NHAT o day (event "connect" cua engine, chay 1 lan/connection vat ly moi
    tao ra trong pool) thay vi tu goi SET rai rac o tung noi dung
    vector_search() - dung idiom da ap dung xuyen suot du an (get_current_
    patient_id(), escalate_fn luon that): dam bao ap dung 100% bang cau truc,
    khong phu thuoc tung noi goi co nho SET hay khong (bai hoc lap lai nhieu
    lan trong du an - #17, escalate_fn - "verify dung o tang thap khong dam
    bao da wire dung o tang goi that"). Mac dinh pgvector (40) chi dat HNSW
    recall vs exact scan 84.4% (do that, eval/hnsw_recall_tuning.py) - nang
    len settings.hnsw_ef_search (chot 100) truoc khi bat ky truy van vector
    nao chay qua connection nay."""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET hnsw.ef_search = %s", (settings.hnsw_ef_search,))
    cursor.close()
    # QUAN TRONG (phat hien 2026-08-09 khi test wiring that, khong phai chi
    # tin ly thuyet): psycopg2 mac dinh autocommit=False - SET o tren tu mo
    # 1 transaction NGAM, KHONG commit gi ca thi bi ROLLBACK am tham truoc
    # khi SessionLocal() thuc su dung connection nay (xac nhan bang test that
    # - SHOW hnsw.ef_search tra ve rong neu thieu dong nay). Commit ngay tai
    # day de GUC that su ap dung cho SESSION, khong bi cuon nguoc.
    dbapi_connection.commit()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency - 1 session/request, luon dong lai sau khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
