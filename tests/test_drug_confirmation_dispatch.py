"""Vong 2 (chatbot-rag-design.md muc 11) - unit test _dispatch_stage() (state
machine thuan cua luong xac nhan danh tinh thuoc), bao phu du 8 stage + 3
DIEN GIAI rieng (khong duoc mo ta tuong minh trong kickoff-prompt-vong-2.md,
xem docstring dau backend/agents/nodes/drug_confirmation_nodes.py):
  1. "khong" o out_rx_confirm_pick_r1 -> quay lai menu top-3 CON LAI
  2. het ung vien de hoi (khong phai "no") -> STOP
  3. reply khong parse duoc (unscripted case, muc 8 kickoff) -> hoi lai CUNG
     menu, khong doan them

Da co du lieu that tu Phase 2-4 (drug_chunks that) - dung 2 stage can DB
(in_rx_awaiting_new_name, out_rx_awaiting_redescribe) qua DB that, cac stage
con lai KHONG can DB (candidates truyen thang, khong query lai)."""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.drug_confirmation_nodes import (  # noqa: E402
    ASK_DESCRIBE_AGAIN_MESSAGE,
    ASK_DIFFERENT_NAME_MESSAGE,
    NOT_FOUND_FINAL_MESSAGE,
    STAGE_IN_RX_AWAITING_NEW_NAME,
    STAGE_IN_RX_CONFIRM_R1,
    STAGE_IN_RX_CONFIRM_R2,
    STAGE_OUT_RX_AWAITING_REDESCRIBE,
    STAGE_OUT_RX_CHOOSE_TOP3_R1,
    STAGE_OUT_RX_CONFIRM_PICK_R1,
    STAGE_OUT_RX_CONFIRM_TOP1_R1,
    STAGE_OUT_RX_CONFIRM_TOP1_R2,
    UNPARSEABLE_CHOICE_MESSAGE_TEMPLATE,
    UNPARSEABLE_YES_NO_MESSAGE,
    _dispatch_stage,
    _fuzzy_best_match,
    _parse_choice_index,
    _parse_yes_no,
)
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Prescription  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")

CEFIXIM = {"drug_id": "cefixim-200mg-vidipha-1x10", "ten_thuoc": "Cefixim 200mg Vidipha 1x10"}
DAFLAVON = {"drug_id": "daflavon-450mg-pymepharco-4x15", "ten_thuoc": "Daflavon 450mg Pymepharco 4x15"}
FAKE_A = {"drug_id": "fake-drug-a", "ten_thuoc": "Fake Drug A"}
FAKE_B = {"drug_id": "fake-drug-b", "ten_thuoc": "Fake Drug B"}
FAKE_C = {"drug_id": "fake-drug-c", "ten_thuoc": "Fake Drug C"}


def _fake_embed(text_: str) -> list[float]:
    """Khong goi OpenAI that - lexical search (pg_trgm tren query TEXT that)
    du de tim dung Cefixim/Daflavon that trong DB, giong pattern da dung o
    tests/test_chat_routes.py."""
    import random

    return [random.Random(hash(text_) % (2**31)).gauss(0, 1) for _ in range(1536)]


# ---------------------------------------------------------------------------
# Parsing helpers (thuan, khong can DB)
# ---------------------------------------------------------------------------


def test_parse_yes_no_short_replies():
    assert _parse_yes_no("có") is True
    assert _parse_yes_no("đúng rồi") is True
    assert _parse_yes_no("vâng") is True
    assert _parse_yes_no("không") is False
    assert _parse_yes_no("không phải") is False
    assert _parse_yes_no("sai rồi") is False


def test_parse_yes_no_longer_sentences_check_start_of_reply():
    assert _parse_yes_no("không, tôi hỏi thuốc khác") is False
    assert _parse_yes_no("có, đúng thuốc đó") is True


def test_parse_yes_no_unparseable_returns_none():
    assert _parse_yes_no("tôi không chắc lắm về điều này luôn ấy") is None
    assert _parse_yes_no("thuốc này giá bao nhiêu") is None


def test_parse_choice_index_by_number():
    candidates = [FAKE_A, FAKE_B, FAKE_C]
    assert _parse_choice_index("1", candidates) == 0
    assert _parse_choice_index("2", candidates) == 1
    assert _parse_choice_index("3", candidates) == 2
    assert _parse_choice_index("4", candidates) is None


def test_parse_choice_index_by_name():
    candidates = [FAKE_A, FAKE_B, FAKE_C]
    assert _parse_choice_index("Fake Drug B", candidates) == 1


def test_parse_choice_index_unparseable_returns_none():
    candidates = [FAKE_A, FAKE_B, FAKE_C]
    assert _parse_choice_index("tôi không biết chọn cái nào cả", candidates) is None


def test_fuzzy_best_match_abbreviation():
    candidates = [CEFIXIM, DAFLAVON]
    match = _fuzzy_best_match("cefixim", candidates)
    assert match == CEFIXIM


def test_fuzzy_best_match_no_match_returns_none():
    candidates = [CEFIXIM, DAFLAVON]
    assert _fuzzy_best_match("hoàn toàn không liên quan xyz123", candidates) is None


# ---------------------------------------------------------------------------
# TTL cho pending_drug_confirmation (review 2026-08-09)
# ---------------------------------------------------------------------------


def test_fresh_pending_confirmation_is_returned_normally():
    from backend.agents.tools.drug_confirmation_store import clear_pending_confirmation, get_pending_confirmation, set_pending_confirmation

    db = SessionLocal()
    patient_id = f"test-ttl-fresh-{uuid.uuid4().hex[:8]}"
    try:
        set_pending_confirmation(db, patient_id, [CEFIXIM], STAGE_IN_RX_CONFIRM_R1, "cefixim dùng sao")
        pending = get_pending_confirmation(db, patient_id)
        assert pending is not None
        assert pending["stage"] == STAGE_IN_RX_CONFIRM_R1
    finally:
        clear_pending_confirmation(db, patient_id)
        db.close()


def test_expired_pending_confirmation_is_treated_as_none_and_deleted():
    """Review 2026-08-09: benh nhan bo do cau hoi giua chung khong duoc de
    lai pending TREO VINH VIEN - qua TTL phai coi nhu khong co gi (tin nhan
    tiep theo la CAU HOI MOI), VA phai XOA dong het han (khong de rac)."""
    from datetime import UTC, datetime, timedelta

    from backend.agents.tools.drug_confirmation_store import clear_pending_confirmation, get_pending_confirmation
    from backend.config import get_settings
    from backend.db.models import PendingDrugConfirmation

    db = SessionLocal()
    patient_id = f"test-ttl-expired-{uuid.uuid4().hex[:8]}"
    try:
        ttl = get_settings().drug_confirmation_ttl_minutes
        expired_at = datetime.now(UTC) - timedelta(minutes=ttl + 5)
        db.add(
            PendingDrugConfirmation(
                patient_id=patient_id,
                candidates=[CEFIXIM],
                stage=STAGE_IN_RX_CONFIRM_R1,
                original_query="cefixim dùng sao",
                retry_count=0,
                created_at=expired_at,
            )
        )
        db.commit()

        pending = get_pending_confirmation(db, patient_id)
        assert pending is None, "qua TTL phai coi nhu khong co pending"

        # phai da bi XOA that khoi DB, khong chi "an" o tang tra ve
        row = (
            db.query(PendingDrugConfirmation)
            .filter(PendingDrugConfirmation.patient_id == patient_id)
            .one_or_none()
        )
        assert row is None, "dong het han phai bi xoa khoi DB, khong duoc de lai"
    finally:
        clear_pending_confirmation(db, patient_id)
        db.close()


def test_core_name_keeps_short_alphanumeric_identifier_not_just_stops_at_first_digit():
    """Review 2026-08-09 (lan 2): du lieu that co thuoc TEN BAT DAU bang 1
    token dang so+chu ngan ("3b Agi-neurin Agimexpharm 10x10") - dieu kien cu
    "dung o tu dau tien bat dau bang chu so" lam core RONG HOAN TOAN cho
    thuoc nay (fallback ve ca chuoi, vo hieu hoa core-name). Phai phan biet
    dosage THAT (ket thuc bang don vi/dang NxN) voi token dinh danh ngan."""
    from backend.agents.nodes.drug_confirmation_nodes import _drug_core_name

    assert _drug_core_name("3b Agi-neurin Agimexpharm 10x10") == "3b agi-neurin agimexpharm"
    assert _drug_core_name("AMMG 3b Trường THỌ 5x10") == "ammg 3b truong tho"
    # khong duoc regress: dosage that (bao gom dang %) van phai dung dung
    assert _drug_core_name("Fluopas 0.025% Quảng BÌNH 10g") == "fluopas"
    assert _drug_core_name("Cefixim 200mg Vidipha 1x10") == "cefixim"


# ---------------------------------------------------------------------------
# 11.1 in-prescription flow
# ---------------------------------------------------------------------------


def test_in_rx_confirm_r1_yes_resolves():
    result = _dispatch_stage(None, _fake_embed, "p1", STAGE_IN_RX_CONFIRM_R1, [CEFIXIM], "cefixim dùng sao", "có")
    assert result.resolved_drug_id == CEFIXIM["drug_id"]


def test_in_rx_confirm_r1_no_asks_different_name():
    result = _dispatch_stage(None, _fake_embed, "p1", STAGE_IN_RX_CONFIRM_R1, [CEFIXIM], "cefixim dùng sao", "không")
    assert result.resolved_drug_id is None
    assert result.stop is False
    assert result.response == ASK_DIFFERENT_NAME_MESSAGE
    assert result.new_pending[1] == STAGE_IN_RX_AWAITING_NEW_NAME


def test_in_rx_confirm_r1_unparseable_reasks_same_stage():
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_IN_RX_CONFIRM_R1, [CEFIXIM], "cefixim dùng sao", "ừm để tôi nghĩ đã"
    )
    assert result.resolved_drug_id is None
    assert result.stop is False
    assert result.response == UNPARSEABLE_YES_NO_MESSAGE
    assert result.new_pending[1] == STAGE_IN_RX_CONFIRM_R1


def test_in_rx_awaiting_new_name_finds_match_asks_confirm_r2(db_session_with_prescription):
    db, patient_id = db_session_with_prescription
    result = _dispatch_stage(db, _fake_embed, patient_id, STAGE_IN_RX_AWAITING_NEW_NAME, [], "orig q", "daflavon")
    assert result.resolved_drug_id is None
    assert result.new_pending[1] == STAGE_IN_RX_CONFIRM_R2
    assert result.new_pending[0][0]["drug_id"] == DAFLAVON["drug_id"]


def test_in_rx_awaiting_new_name_no_match_stops(db_session_with_prescription):
    """DIEN GIAI #2: khong tim duoc gi voi ten moi - het round, STOP."""
    db, patient_id = db_session_with_prescription
    result = _dispatch_stage(
        db, _fake_embed, patient_id, STAGE_IN_RX_AWAITING_NEW_NAME, [], "orig q", "xyz không tồn tại 12345"
    )
    assert result.resolved_drug_id is None
    assert result.stop is True
    assert result.response == NOT_FOUND_FINAL_MESSAGE


def test_in_rx_confirm_r2_yes_resolves():
    result = _dispatch_stage(None, _fake_embed, "p1", STAGE_IN_RX_CONFIRM_R2, [DAFLAVON], "orig q", "có")
    assert result.resolved_drug_id == DAFLAVON["drug_id"]


def test_in_rx_confirm_r2_no_stops_no_third_round():
    """Het round - KHONG con vong 3, du benh nhan tu choi tiep."""
    result = _dispatch_stage(None, _fake_embed, "p1", STAGE_IN_RX_CONFIRM_R2, [DAFLAVON], "orig q", "không")
    assert result.resolved_drug_id is None
    assert result.stop is True
    assert result.response == NOT_FOUND_FINAL_MESSAGE


# ---------------------------------------------------------------------------
# 11.2 out-of-prescription flow
# ---------------------------------------------------------------------------


def test_out_rx_confirm_top1_r1_yes_resolves():
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_TOP1_R1, [FAKE_A, FAKE_B, FAKE_C], "orig q", "đúng rồi"
    )
    assert result.resolved_drug_id == FAKE_A["drug_id"]


def test_out_rx_confirm_top1_r1_no_shows_top3():
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_TOP1_R1, [FAKE_A, FAKE_B, FAKE_C], "orig q", "không"
    )
    assert result.resolved_drug_id is None
    assert result.new_pending[1] == STAGE_OUT_RX_CHOOSE_TOP3_R1
    assert result.new_pending[0] == [FAKE_B, FAKE_C]
    assert "1. Fake Drug B" in result.response
    assert "2. Fake Drug C" in result.response


def test_out_rx_choose_top3_picks_valid_index_asks_confirm():
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CHOOSE_TOP3_R1, [FAKE_B, FAKE_C], "orig q", "1"
    )
    assert result.resolved_drug_id is None
    assert result.new_pending[1] == STAGE_OUT_RX_CONFIRM_PICK_R1
    assert result.new_pending[0][0] == FAKE_B, "picked candidate phai o dau danh sach"
    assert result.response == "Bạn muốn thông tin về thuốc Fake Drug B đúng không?"


def test_out_rx_choose_top3_not_found_asks_redescribe():
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CHOOSE_TOP3_R1, [FAKE_B, FAKE_C], "orig q", "không tìm thấy"
    )
    assert result.resolved_drug_id is None
    assert result.stop is False
    assert result.response == ASK_DESCRIBE_AGAIN_MESSAGE
    assert result.new_pending[1] == STAGE_OUT_RX_AWAITING_REDESCRIBE


def test_out_rx_choose_top3_unparseable_reply_reasks_same_menu():
    """DIEN GIAI #3 - unscripted case (muc 8 kickoff): benh nhan go tu do
    thay vi chon so/nut - fallback AN TOAN NHAT: hoi lai CUNG menu."""
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CHOOSE_TOP3_R1, [FAKE_B, FAKE_C], "orig q", "tôi không rõ lắm"
    )
    assert result.resolved_drug_id is None
    assert result.stop is False
    assert result.new_pending == ([FAKE_B, FAKE_C], STAGE_OUT_RX_CHOOSE_TOP3_R1, "orig q"), (
        "phai giu NGUYEN candidates va stage - hoi lai, khong tu y doan"
    )
    assert "Fake Drug B" in result.response and "Fake Drug C" in result.response


def test_out_rx_confirm_pick_r1_yes_resolves():
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_PICK_R1, [FAKE_B, FAKE_C], "orig q", "có"
    )
    assert result.resolved_drug_id == FAKE_B["drug_id"]


def test_out_rx_confirm_pick_r1_no_loops_back_to_top3_menu_with_remaining():
    """DIEN GIAI #1: "khong" o day KHONG duoc STOP ngay - quay lai menu
    top-3 voi ung vien CON LAI (round-budget chua het)."""
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_PICK_R1, [FAKE_B, FAKE_C], "orig q", "không"
    )
    assert result.resolved_drug_id is None
    assert result.stop is False
    assert result.new_pending == ([FAKE_C], STAGE_OUT_RX_CHOOSE_TOP3_R1, "orig q")
    assert "Fake Drug C" in result.response


def test_out_rx_confirm_pick_r1_no_with_no_remaining_asks_redescribe():
    """Neu picked la ung vien CUOI CUNG con lai, tu choi -> chuyen sang mo ta
    lai (khong con gi trong menu de quay lai)."""
    result = _dispatch_stage(None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_PICK_R1, [FAKE_B], "orig q", "không")
    assert result.resolved_drug_id is None
    assert result.response == ASK_DESCRIBE_AGAIN_MESSAGE
    assert result.new_pending[1] == STAGE_OUT_RX_AWAITING_REDESCRIBE


def test_out_rx_awaiting_redescribe_finds_match(db_session_no_prescription):
    db = db_session_no_prescription
    result = _dispatch_stage(
        db, _fake_embed, "p1", STAGE_OUT_RX_AWAITING_REDESCRIBE, [], "orig q", "Cefixim 200mg Vidipha 1x10"
    )
    assert result.resolved_drug_id is None
    assert result.new_pending[1] == STAGE_OUT_RX_CONFIRM_TOP1_R2
    assert result.new_pending[0][0]["drug_id"] == CEFIXIM["drug_id"]


def test_out_rx_awaiting_redescribe_no_match_stops(db_session_no_prescription):
    """DIEN GIAI #2: khong tim duoc gi voi mo ta moi - het round, STOP."""
    db = db_session_no_prescription
    result = _dispatch_stage(
        db, _fake_embed, "p1", STAGE_OUT_RX_AWAITING_REDESCRIBE, [], "orig q", "zzzxxxqqqwww1234 vô nghĩa"
    )
    assert result.resolved_drug_id is None
    assert result.stop is True
    assert result.response == NOT_FOUND_FINAL_MESSAGE


def test_out_rx_confirm_top1_r2_yes_resolves():
    result = _dispatch_stage(None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_TOP1_R2, [FAKE_A], "orig q", "đúng")
    assert result.resolved_drug_id == FAKE_A["drug_id"]


def test_out_rx_confirm_top1_r2_no_stops_no_third_round():
    result = _dispatch_stage(None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_TOP1_R2, [FAKE_A], "orig q", "không")
    assert result.resolved_drug_id is None
    assert result.stop is True
    assert result.response == NOT_FOUND_FINAL_MESSAGE


def test_full_chain_rejected_candidates_never_reappear_in_later_menus():
    """Review 2026-08-09: chuoi DAY DU - tu choi top-1 (A), duoc menu [B,C,D],
    chon B, tu choi B, PHAI duoc menu chi con [C,D] - KHONG duoc A hay B xuat
    hien lai o bat ky buoc nao sau do."""
    D = {"drug_id": "fake-drug-d", "ten_thuoc": "Fake Drug D"}
    candidates_r0 = [FAKE_A, FAKE_B, FAKE_C, D]

    # Buoc 1: tu choi top-1 (FAKE_A)
    r1 = _dispatch_stage(None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_TOP1_R1, candidates_r0, "orig q", "không")
    assert r1.new_pending[1] == STAGE_OUT_RX_CHOOSE_TOP3_R1
    menu1_candidates = r1.new_pending[0]
    assert FAKE_A not in menu1_candidates, "A (top-1 vua tu choi) khong duoc xuat hien trong menu top-3"
    assert menu1_candidates == [FAKE_B, FAKE_C, D]

    # Buoc 2: chon "1" (=FAKE_B) tu menu
    r2 = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CHOOSE_TOP3_R1, menu1_candidates, "orig q", "1"
    )
    assert r2.new_pending[1] == STAGE_OUT_RX_CONFIRM_PICK_R1
    assert r2.new_pending[0][0] == FAKE_B

    # Buoc 3: tu choi FAKE_B - PHAI quay lai menu CHI con [C, D], KHONG co A/B
    r3 = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_PICK_R1, r2.new_pending[0], "orig q", "không"
    )
    assert r3.new_pending[1] == STAGE_OUT_RX_CHOOSE_TOP3_R1
    final_menu = r3.new_pending[0]
    assert FAKE_A not in final_menu, "A khong duoc xuat hien lai o buoc sau"
    assert FAKE_B not in final_menu, "B (vua tu choi lan 2) khong duoc xuat hien lai"
    assert final_menu == [FAKE_C, D]
    assert "Fake Drug A" not in r3.response
    assert "Fake Drug B" not in r3.response


def test_repeated_unparseable_replies_hit_retry_cap_and_stop():
    """Review 2026-08-09: round-budget (so ung vien da thu) KHONG bi tieu ton
    boi reply khong parse duoc - can 1 cap RIENG, xac nhan qua nhieu lan goi
    _dispatch_stage lien tiep VOI CUNG stage/candidates (mo phong dung cach
    build_drug_confirmation_reply_node dung ket qua nay de dem retry_count)."""
    unparseable_replies = ["ừm để tôi nghĩ đã xem sao nhỉ", "cái gì cơ", "tôi không chắc lắm đâu"]
    stage = STAGE_OUT_RX_CONFIRM_TOP1_R1
    candidates = [FAKE_A, FAKE_B, FAKE_C]
    for reply in unparseable_replies:
        result = _dispatch_stage(None, _fake_embed, "p1", stage, candidates, "orig q", reply)
        assert result.resolved_drug_id is None
        assert result.stop is False, f"reply={reply!r} khong duoc tu STOP o tang dispatch - cap nam o tang node"
        assert result.new_pending[1] == stage, "van la cung stage (chua parse duoc)"


def test_out_rx_confirm_top1_r2_not_found_reply_also_stops():
    """Kickoff: "hoac lai chon khong tim thay lan 2" -> CUNG stop nhu "no"."""
    result = _dispatch_stage(
        None, _fake_embed, "p1", STAGE_OUT_RX_CONFIRM_TOP1_R2, [FAKE_A], "orig q", "không tìm thấy"
    )
    assert result.resolved_drug_id is None
    assert result.stop is True
    assert result.response == NOT_FOUND_FINAL_MESSAGE


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session_no_prescription():
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def db_session_with_prescription():
    db = SessionLocal()
    patient_id = f"test-dispatch-{uuid.uuid4().hex[:8]}"
    presc = Prescription(
        patient_id=patient_id,
        doctor_id="doc-1",
        status="approved",
        items=[
            {"ten_thuoc": CEFIXIM["ten_thuoc"], "drug_id": CEFIXIM["drug_id"]},
            {"ten_thuoc": DAFLAVON["ten_thuoc"], "drug_id": DAFLAVON["drug_id"]},
        ],
        start_date=datetime.now(UTC).date().isoformat(),
        duration_days=7,
    )
    db.add(presc)
    db.commit()
    yield db, patient_id
    db.query(Prescription).filter(Prescription.patient_id == patient_id).delete(synchronize_session=False)
    db.commit()
    db.close()