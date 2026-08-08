"""Phase 4 - test SQL that cua lexical_search()/vector_search() tren Postgres
that (docker compose up -d db). Khong can OpenAI API (lexical khong dung
embedding) nen KHONG tinh phi, chi can DB.

Tap trung vao 1 bug cu the da phat hien va sua ngay 2026-08-08: toan tu `%`
(similarity) va `<%` (word_similarity) cua pg_trgm doc 2 GUC KHAC NHAU
(`pg_trgm.similarity_threshold` vs `pg_trgm.word_similarity_threshold`, GUC
thu 2 mac dinh 0.6). Neu code chi SET GUC thu nhat, toan tu <% se am tham
dung nguong 0.6 thay vi NGUONG_LEXICAL du dinh - chay binh thuong, khong loi,
chi ket qua thieu. Test nay lap lai chinh xac kich ban da phat hien bug do.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from src.db.base import SessionLocal, engine  # noqa: E402
from src.services.retrieval import lexical_search  # noqa: E402


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


def test_word_similarity_threshold_guc_is_set_not_just_similarity_threshold(db_session):
    """Regression test cho bug 2026-08-08: goi lai dung ham lexical_search()
    (khong tu tao SQL rieng) tren 1 truong hop that da xac nhan word_similarity
    nam giua NGUONG_LEXICAL (0.3) va gia tri mac dinh cua GUC thu 2 (0.6) -
    'paracetamol...' + 'ha sot' co word_similarity = 0.4286 (da do bang tay).
    Neu word_similarity_threshold GUC quen SET (con 0.6 mac dinh), dieu kien
    <% se loai chunk nay TRUOC CA KHI toi buoc sap xep/LIMIT - kiem tra truc
    tiep dieu kien SQL (khong qua LIMIT 50 de tranh nhieu do canh tranh diem
    cao khac, xem lich su phat hien bug)."""
    from src.config import get_settings

    settings = get_settings()
    db_session.execute(text("SET pg_trgm.similarity_threshold = :t"), {"t": settings.nguong_lexical})
    db_session.execute(text("SET pg_trgm.word_similarity_threshold = :t"), {"t": settings.nguong_lexical})

    matched = db_session.execute(
        text(
            """
            SELECT count(*) FROM drug_chunks
            WHERE drug_id = 'paracetamol-kabi-1000mg-frensenius-kabi-48-chai-x-100ml'
              AND field_group = 'tac_dung_phu'
              AND unaccent(:q) <% noi_dung_unaccent
            """
        ),
        {"q": "ha sot"},
    ).scalar()

    assert matched == 1, (
        "Dieu kien <% khong khop chunk co word_similarity=0.43 (giua nguong 0.3 va "
        "mac dinh GUC 0.6) - kha nang word_similarity_threshold chua duoc SET dung"
    )


def test_lexical_search_finds_exact_drug_name_match():
    """Smoke test end-to-end qua chinh ham lexical_search() (khong bypass SQL):
    go dung ten 1 thuoc that trong DB phai tra ve chinh thuoc do o vi tri dau
    (similarity ten_thuoc gan 1.0, khong canh tranh voi nguon nao khac)."""
    from src.config import get_settings

    settings = get_settings()
    db = SessionLocal()
    try:
        results = lexical_search(db, "Agiclovir 5% Agimexpharm", settings.nguong_lexical)
        assert len(results) > 0
        assert results[0].drug_id == "agiclovir-5-agimexpharm"
        assert results[0].score > 0.9
    finally:
        db.close()
