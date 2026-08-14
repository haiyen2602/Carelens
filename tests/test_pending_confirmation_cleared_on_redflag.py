"""Vong 3, muc 4 (chatbot-rag-design.md muc 10 #26/backend.api.chat_routes) -
fix bug that: neu safety_layer trigger redflag trong luc dang co 1 pending_
drug_confirmation dang treo, PHAI xoa ngay pending do - khong de 2 trang thai
(dang cho xac nhan thuoc + dang co redflag) ton tai cung luc, tranh tin nhan
TIEP THEO bi ep nham qua bo phan tich co/khong cu.

Race THAT qua /api/v1/chat, khong mock timing - dung pattern e2e da co o
test_drug_confirmation_e2e.py (DB that, LLM fake qua dependency override)."""

import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.tools.drug_confirmation_store import (  # noqa: E402
    get_pending_confirmation,
    set_pending_confirmation,
)
from backend.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.safety import SafetyFlag  # noqa: E402

_UNRELATED_EMBEDDING = [random.Random(42).gauss(0, 1) for _ in range(1536)]


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


async def _clean_safety_check(utterance: str) -> SafetyFlag:
    return SafetyFlag(is_redflag=False, matched_group=None, matched_keyword=None, source="keyword")


async def _instant_redflag_safety_check(utterance: str) -> SafetyFlag:
    return SafetyFlag(
        is_redflag=True, matched_group="clinical", matched_keyword="đau ngực", source="keyword", level="Nguy hiểm"
    )


def _override_services(**fakes) -> None:
    defaults = {
        "classify_intent": lambda u: ("drug_info", 0.95),
        "classify_dose": lambda u: ("TAKEN", 0.95),
        "generate_answer": lambda u, r: f"Câu trả lời giả lập cho: {u}",
        "classify_severity": lambda combined_text: None,
        "embed_query": lambda t: _UNRELATED_EMBEDDING,
        "safety_check": _clean_safety_check,
    }
    defaults.update(fakes)
    app.dependency_overrides[get_chat_services] = lambda: ChatServices(**defaults)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_redflag_while_replying_to_pending_confirmation_clears_it(client):
    """Kich ban chinh cua muc 4: dang co 1 pending (cho xac nhan thuoc), tin
    nhan TIEP THEO vua la reply cho pending do VUA la 1 cau redflag ro rang -
    (a) redflag duoc xu ly dung, (b) pending bi xoa, (c) tin nhan ke tiep sau
    do duoc hieu la cau hoi MOI, khong bi ep qua bo phan tich co/khong cu."""
    patient_id = f"test-redflag-pending-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    set_pending_confirmation(
        db,
        patient_id,
        candidates=[{"drug_id": "cefixim-200mg-vidipha-1x10", "ten_thuoc": "Cefixim 200mg Vidipha 1x10"}],
        stage="in_rx_confirm_r1",
        original_query="cefixim dùng sao",
    )
    db.close()

    _override_services(safety_check=_instant_redflag_safety_check)

    turn1 = await client.post(
        "/api/v1/chat", json={"patient_id": patient_id, "message": "em thấy khó thở với tức ngực quá"}
    )
    assert turn1.status_code == 200
    body1 = turn1.json()
    assert body1["safety_flag"] is True, "phai duoc xu ly dung nhu 1 redflag"

    db2 = SessionLocal()
    pending_after = get_pending_confirmation(db2, patient_id)
    db2.close()
    assert pending_after is None, "pending_drug_confirmation PHAI bi xoa ngay sau khi redflag trigger"

    # Turn 2: tin nhan HOAN TOAN khong lien quan - neu con pending cu, se bi
    # hieu nham la reply "co"/"khong" cho cau hoi xac nhan cefixim da cu.
    _override_services(safety_check=_clean_safety_check)
    turn2 = await client.post(
        "/api/v1/chat", json={"patient_id": patient_id, "message": "daflavon dùng sao"}
    )
    assert turn2.status_code == 200
    body2 = turn2.json()
    # Phai duoc xu ly nhu CAU HOI MOI (chay qua drug_identity_resolution
    # that, KHONG phai qua dispatch cua pending da bi xoa) - response se la
    # cau hoi xac nhan danh tinh thuoc MOI (muc 11), KHONG phai bat kha
    # UNPARSEABLE_YES_NO_MESSAGE cua stage cu.
    assert "Mình chưa hiểu ý bạn" not in body2["reply"]
