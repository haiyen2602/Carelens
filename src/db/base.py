"""SQLAlchemy engine/session setup - PostgreSQL + pgvector (ADR-0008).

Khong dung SQLite fallback cho phan RAG - pgvector extension chi co tren
PostgreSQL, va DATABASE_URL mac dinh trong config.py da tro thang toi
Postgres (xem docker-compose.yml). Neu can chay test khong co Postgres
that, dung pytest marker rieng (xem tests/test_db_phase1.py) thay vi doi
engine ngam.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency - 1 session/request, luon dong lai sau khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
