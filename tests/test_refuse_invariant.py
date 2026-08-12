"""Phase 6 code review (2026-08-08) - xac nhan tuong minh dieu kien REFUSE
(gop vao answer_generation_node) dung DUNG tin hieu: rag_results rong
CHI XAY RA khi hybrid_search that su no_source_found=True (BR-7.3, muc 4.4),
KHONG BAO GIO vi 1 loi ky thuat khac (DB loi, embed_query loi...) bi am
tham nuot thanh "khong co nguon" - dung y thiet ke Phase 4 tach rieng
`no_source_found` khoi list rong thay vi collapse lam 1.

Chung minh bang 2 test doc lap:
  1. no_source_found that (query vo nghia that, DB that) -> rag_results
     rong -> REFUSE. (duong TICH CUC: dung tin hieu)
  2. embed_query loi (loi ky thuat) -> exception LAN THANG qua retrieval_node,
     KHONG bi nuot thanh rag_results rong/REFUSE. (duong TIEU CUC: khong
     nham lan loi ky thuat voi "khong co nguon")
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.conversation_nodes import build_answer_generation_node, build_retrieval_node  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


@pytest.mark.asyncio
async def test_genuine_no_source_found_yields_empty_rag_results_and_refuse():
    """Duong TICH CUC: no_source_found that (khong fake) -> rag_results
    rong -> answer_generation_node REFUSE."""
    db = SessionLocal()
    try:
        # Vector khong lien quan (Gauss ngau nhien, KHONG phai vector 0
        # degenerate - xem ghi chu trong test_chat_routes.py) + query lexical
        # vo nghia that (khong chua tu tieng Viet that nao).
        import random

        unrelated_vector = [random.Random(7).gauss(0, 1) for _ in range(1536)]

        retrieval_node = build_retrieval_node(db, embed_query=lambda t: unrelated_vector)
        state = {
            "patient_id": "p1",
            "intent": "drug_info",
            "utterance": "qzxjklmwvbpfgh1111zzzzxxxxyyyywwww8888",
            "trace": [],
        }
        retrieval_update = await retrieval_node(state)

        retrieval_trace = retrieval_update["trace"][-1]
        assert retrieval_trace["no_source_found"] is True, "test nay phai that su khong tim thay nguon nao"
        assert retrieval_update["rag_results"] == [], (
            "INVARIANT: no_source_found=True phai luon di kem rag_results rong (khong collapse sai)"
        )

        merged_state = {**state, **retrieval_update}
        answer_node = build_answer_generation_node(generate_fn=lambda u, r: "khong duoc goi toi day")
        answer_update = await answer_node(merged_state)

        assert answer_update["trace"][-1]["step"] == "refuse"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_technical_error_in_retrieval_propagates_does_not_silently_refuse():
    """Duong TIEU CUC: loi ky thuat (embed_query raise) KHONG duoc am tham
    bien thanh rag_results rong/REFUSE - phai lan ra ngoai that su, de loi
    duoc thay (vd tra ve 500), khong bi bao che thanh 'khong co thong tin'
    (2 tinh huong khac nhau ve ban chat, khong duoc lam nguoi dung/bac si
    nham lan)."""

    def broken_embed(text: str) -> list[float]:
        raise RuntimeError("OpenAI API timeout (mo phong loi ky thuat that)")

    db = SessionLocal()
    try:
        retrieval_node = build_retrieval_node(db, embed_query=broken_embed)
        state = {"patient_id": "p1", "intent": "drug_info", "utterance": "paracetamol", "trace": []}

        with pytest.raises(RuntimeError, match="OpenAI API timeout"):
            await retrieval_node(state)
    finally:
        db.close()
