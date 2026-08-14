"""Vong 2, muc 6/15 (chatbot-rag-design.md) - xac nhan `hnsw.ef_search` THAT SU
duoc ap dung qua choke-point o backend/db/base.py (event "connect" tren engine),
KHONG chi dung khi go tay trong psql/script rieng. Dung bai hoc lap lai nhieu
lan trong du an nay (escalate_fn, #17 cross-drug filter): verify o tang thap
(1 lan SET trong 1 script) KHONG dam bao da wire dung o tang goi THAT (session
lay tu SessionLocal() production dung) - phai test qua DUNG choke-point.

Integration test - can Postgres that dang chay (docker compose up -d db)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def test_ef_search_applied_automatically_via_connect_event_no_manual_set():
    """Lay session THANG tu SessionLocal() (dung cach production/get_db()
    dung) - KHONG tu goi SET nao trong test nay. Neu gia tri KHONG dung
    settings.hnsw_ef_search, nghia la choke-point o db/base.py khong chay
    hoac khong ap dung dung - loi wire, khong phai loi gia tri."""
    settings = get_settings()
    db = SessionLocal()
    try:
        row = db.execute(text("SHOW hnsw.ef_search")).fetchone()
        assert int(row[0]) == settings.hnsw_ef_search, (
            f"hnsw.ef_search that su la {row[0]!r}, ky vong {settings.hnsw_ef_search} "
            "- event 'connect' o backend/db/base.py khong ap dung dung, hoac khong chay"
        )
    finally:
        db.close()


def test_ef_search_still_in_effect_after_using_session_for_a_query():
    """GUC theo SESSION (connection vat ly) - phai con hieu luc SAU KHI da
    dung session do de chay 1 truy van khac (khong bi reset ngoai y muon
    giua chung boi code khac trong cung request)."""
    settings = get_settings()
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))  # 1 truy van "binh thuong" truoc
        row = db.execute(text("SHOW hnsw.ef_search")).fetchone()
        assert int(row[0]) == settings.hnsw_ef_search
    finally:
        db.close()


def test_bluepine_regression_now_found_via_real_search_distinct_drug_candidates():
    """Regression THAT cho dung case da lo ra bug (mucr 6/15): truoc khi sua
    (ef_search mac dinh 40), _search_distinct_drug_candidates() cho cau hoi
    nay tra ve 3 thuoc KHONG lien quan, thieu han Bluepine (da xac nhan bang
    exact scan: Bluepine la chunk gan nhat THAT, cosine=0.72). Sau khi wire
    ef_search=100 qua dung choke-point (khong phai chi verify rieng le), goi
    LAI DUNG ham production nay (khong reimplement) phai tim thay Bluepine
    trong danh sach candidate.

    Goi OpenAI THAT (1 embedding call, chi phi nho) - test nay LA bang chung
    end-to-end manh nhat: dung ham that, dung session lay theo dung cach
    production dung, dung cau hoi that da gay loi."""
    from backend.agents.nodes.drug_confirmation_nodes import _search_distinct_drug_candidates
    from backend.services.embeddings import embed_query

    db = SessionLocal()
    try:
        utterance = "Bluepine 5mg BLUE 6x10 có thể gây ra tác dụng phụ nào?"
        embedding = embed_query(utterance)
        candidates = _search_distinct_drug_candidates(db, utterance, embedding, n=4)
        drug_ids = [c["drug_id"] for c in candidates]
        assert "bluepine-5mg-blue-6x10" in drug_ids, (
            f"Bluepine van bi thieu khoi candidate list ({drug_ids}) - ef_search co the chua duoc ap "
            "dung dung qua _search_distinct_drug_candidates(), hoac gia tri chua du cao"
        )
    finally:
        db.close()
