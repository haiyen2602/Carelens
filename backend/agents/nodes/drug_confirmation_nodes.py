"""Vong 2 (chatbot-rag-design.md muc 11) - xac nhan danh tinh thuoc TRUOC
khi tra loi, thay the hoan toan cach doan cu (dong muc 10 #12/#15/#17).

2 node CHINH, ca 2 deu tu bao ve theo `state["intent"]` (cung idiom voi
conversation_nodes.py):

  - build_drug_identity_resolution_node: THAY CHO build_retrieval_node trong
    danh sach node chinh - chi chay khi CAU HOI MOI (chua co pending
    confirmation nao dang cho, chat_routes.py dam bao dieu nay bang cach chi
    dua node nay vao remaining_nodes khi get_pending_confirmation() tra ve
    None). Tim ung vien (uu tien don active - muc 11.1, fallback hybrid
    search - muc 11.2), GHI pending confirmation vao DB, dat response = cau
    hoi xac nhan, dat state["awaiting_drug_confirmation"] = True de
    prescription_lookup_node/answer_generation_node bo qua luot nay.

  - build_drug_confirmation_reply_node: chay khi tin nhan nay la REPLY cho 1
    cau hoi xac nhan dang cho (chat_routes.py doc pending tu DB TRUOC, truyen
    vao day qua tham so, KHONG chay intent_classification cho tin nhan nay).
    Neu resolve xong (drug_id da biet chac) - XOA pending row, SET
    state["rag_results"] qua get_chunks_by_drug_id() (mode filter, muc 4.1,
    KHONG phai hybrid search) + SET LAI state["utterance"] = original_query
    (cau hoi GOC, khong phai chu "co"/"khong" vua go) de prescription_lookup/
    answer_generation tra loi dung noi dung - roi de 2 node do chay binh
    thuong (KHONG dat awaiting_drug_confirmation). Neu con dang hoi tiep hoac
    da bo cuoc - CAP NHAT pending row, dat response + awaiting_drug_
    confirmation=True nhu tren.

State machine day du (8 stage, xem chatbot-rag-design.md muc 11.1/11.2):
  in_rx_confirm_r1 -> (yes: resolved) | (no: in_rx_awaiting_new_name)
  in_rx_awaiting_new_name -> (ten moi, fuzzy match lai trong don)
                            -> (tim duoc: in_rx_confirm_r2) | (khong: STOP)
  in_rx_confirm_r2 -> (yes: resolved) | (no: STOP, het round)

  out_rx_confirm_top1_r1 -> (yes: resolved) | (no: out_rx_choose_top3_r1)
  out_rx_choose_top3_r1 -> (chon 1/2/3: out_rx_confirm_pick_r1)
                          | ("khong tim thay": out_rx_awaiting_redescribe)
  out_rx_confirm_pick_r1 -> (yes: resolved)
                           | (no: quay lai out_rx_choose_top3_r1 voi ung vien
                             con lai - xem DIEN GIAI #1)
  out_rx_awaiting_redescribe -> (mo ta moi, hybrid search lai)
                                -> (tim duoc: out_rx_confirm_top1_r2)
                                 | (khong: STOP)
  out_rx_confirm_top1_r2 -> (yes: resolved) | (no HOAC "khong tim thay": STOP)

3 DIEN GIAI rieng, KHONG duoc mo ta tuong minh trong kickoff-prompt-vong-2.md
- can xac nhan lai, xem bao cao gui Architect:
  1. "khong" o out_rx_confirm_pick_r1 -> quay lai menu top-3 CON LAI (khong
     phai STOP ngay) - vi round-budget la "top-3 ban dau + 1 lan mo ta lai",
     chon sai 1 trong 3 chua dung het round do.
  2. in_rx_confirm_r2/out_rx_confirm_top1_r2 khong tim duoc ung vien nao de
     hoi (khong phai nguoi dung tra loi "khong", ma fuzzy-match/hybrid search
     tra ve rong) - xu ly GIONG "no" (STOP), vi da het round de thu them.
  3. reply KHONG parse duoc thanh yes/no/so thu tu (vd benh nhan go tu do
     giua luc dang cho chon 1/2/3) - day CHINH LA case "chua duoc mo ta o
     muc 5" (muc 8 kickoff) - fallback AN TOAN NHAT: hoi lai CUNG cau hoi/
     menu, khong doan them, khong tu y dong luong moi.

Vong 3, muc 8 (2026-08-12): "khong, [ten thuoc khac]" trong 1 cau (o
STAGE_IN_RX_CONFIRM_R1/STAGE_OUT_RX_CONFIRM_TOP1_R1) gio thu fuzzy-match/
hybrid-search phan con lai NGAY trong luot, xem _extract_remainder_after_no()
+ 2 nhanh yn is False. KHONG ap dung cho STAGE_OUT_RX_CONFIRM_PICK_R1 (tu
choi 1 lua chon trong top-3) - kickoff chi cho vi du ro rang cho 2 stage dau,
mo rong them stage nay de vong sau neu can, tranh tang pham vi khong duoc
yeu cau tuong minh."""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from backend.agents.nodes.conversation_nodes import EmbedFn, _append_trace
from backend.agents.state import ConversationState
from backend.agents.tools.drug_confirmation_store import clear_pending_confirmation, set_pending_confirmation
from backend.agents.tools.personal_tools import list_active_prescription_drug_items
from backend.config import get_settings
from backend.services.retrieval import fuse_rrf, fuzzy_name_search, get_chunks_by_drug_id, lexical_search, vector_search

# Vong 4, muc 2.2 - LLM gate hep pham vi, chay TRUOC _fuzzy_best_match()/
# _search_distinct_drug_candidates() o 2 nhanh reply-parsing (STAGE_IN_RX_
# AWAITING_NEW_NAME/STAGE_OUT_RX_AWAITING_REDESCRIBE). Mac dinh permissive
# (luon True) - GIU NGUYEN hanh vi cu cho moi test/call site khong truyen
# tham so nay tuong minh (tranh phai sua hang chuc test khong lien quan gate
# nay); production (chat_deps.py::get_chat_services) LUON wire ham that
# (classify_drug_reply_plausibility), khong dua vao default nay.
DrugReplyPlausibilityFn = Callable[[str], bool]
FuzzyCandidateSelectFn = Callable[[str, list[dict]], str | None]


def _default_drug_reply_plausibility(_reply: str) -> bool:
    return True


def _default_fuzzy_candidate_select(_utterance: str, candidates: list[dict]) -> str | None:
    """Compatibility default for tests/call sites not wired to the LLM service.

    Production always injects `select_fuzzy_drug_candidate`. Khong co LLM thi
    phai fail-closed, khong tu lay top-1 cua case mo ho/diem thap; xac nhan
    benh nhan khong thay the duoc viec tranh tao candidate vo nghia.
    """
    return None

# ---------------------------------------------------------------------------
# Stage constants (luu trong PendingDrugConfirmation.stage)
# ---------------------------------------------------------------------------

STAGE_IN_RX_CONFIRM_R1 = "in_rx_confirm_r1"
STAGE_IN_RX_AWAITING_NEW_NAME = "in_rx_awaiting_new_name"
STAGE_IN_RX_CONFIRM_R2 = "in_rx_confirm_r2"
STAGE_OUT_RX_CONFIRM_TOP1_R1 = "out_rx_confirm_top1_r1"
STAGE_OUT_RX_CHOOSE_TOP3_R1 = "out_rx_choose_top3_r1"
STAGE_OUT_RX_CONFIRM_PICK_R1 = "out_rx_confirm_pick_r1"
STAGE_OUT_RX_AWAITING_REDESCRIBE = "out_rx_awaiting_redescribe"
STAGE_OUT_RX_CONFIRM_TOP1_R2 = "out_rx_confirm_top1_r2"

# ---------------------------------------------------------------------------
# Response text - 2 NHOM KHAC NHAU, SUA 2026-08-09 (review): ban truoc gan 1
# comment CẦN CHỐT chung cho CA 5 hang so, nhung 3 hang so dau la NGUYEN VAN
# tu kickoff-prompt-vong-2.md (da qua PM khi chot thiet ke, KHONG can duyet
# lai) - gan nham thanh "chua duyet" la SAI, tu lam giam do tin cay cua chinh
# marker CẦN CHỐT (neu dung tran lan cho ca noi dung da duyet, marker mat y
# nghia phan biet). Tach ro 2 nhom.
# ---------------------------------------------------------------------------

# Vong 4, soul.md: day la toan bo response constants nhom A cua luong xac
# nhan thuoc. Da duoc phep restyle, khong thay doi state machine hay overlay.
NOT_FOUND_FINAL_MESSAGE = "Dạ, mình chưa tìm được thông tin về thuốc này ạ. Bạn hỏi thêm bác sĩ hoặc dược sĩ để chắc chắn hơn nhé."
ASK_DIFFERENT_NAME_MESSAGE = "Dạ, bạn cho mình biết tên một thuốc khác trong đơn được không ạ?"
ASK_DESCRIBE_AGAIN_MESSAGE = "Dạ, bạn mô tả lại tên thuốc rõ hơn giúp mình được không ạ?"
UNPARSEABLE_YES_NO_MESSAGE = 'Dạ, mình chưa hiểu rõ ý bạn ạ. Bạn có thể trả lời "có" hoặc "không" giúp mình được không?'
UNPARSEABLE_CHOICE_MESSAGE_TEMPLATE = (
    "Dạ, mình chưa hiểu lựa chọn của bạn ạ. Bạn chọn một trong các thuốc dưới đây, hoặc trả lời "
    '"không tìm thấy" nhé:\n{options}'
)
TOO_MANY_UNPARSEABLE_REPLIES_MESSAGE = (
    "Dạ, mình vẫn chưa hiểu rõ câu trả lời của bạn ạ. Bạn có thể hỏi lại khi tiện, hoặc liên hệ bác sĩ để được hỗ trợ thêm nhé."
)
# So lan LIEN TIEP toi da cho phep hoi lai CUNG 1 stage vi reply khong parse
# duoc (yes/no/so thu tu) - KHAC round-budget (dem theo so ung vien da thu,
# xem PendingDrugConfirmation.retry_count docstring). Vuot nguong nay ->
# dung han bang TOO_MANY_UNPARSEABLE_REPLIES_MESSAGE, tranh vong lap vo han.
MAX_UNPARSEABLE_RETRIES = 3


def _confirm_question(ten_thuoc: str) -> str:
    return f"Dạ, mình xin phép hỏi bạn muốn biết thông tin về thuốc {ten_thuoc} đúng không ạ?"


def _top3_menu(candidates: list[dict]) -> str:
    lines = [f"{i + 1}. {c['ten_thuoc']}" for i, c in enumerate(candidates)]
    lines.append('Hoặc trả lời "không tìm thấy" nếu không phải thuốc nào ở trên nhé.')
    return "Dạ, mình chưa chắc đây có đúng thuốc bạn hỏi không ạ. Bạn muốn hỏi một trong các thuốc sau phải không?\n" + "\n".join(
        lines
    )


# ---------------------------------------------------------------------------
# Parsing (deterministic, khong goi LLM - cau tra loi xac nhan thuong ngan,
# giu chi phi thap dung tinh than cost-consciousness xuyen suot du an)
# ---------------------------------------------------------------------------


def _strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _normalize(text: str) -> str:
    return _strip_diacritics(text or "").lower().strip()


_YES_EXACT = {"co", "dung", "dung roi", "phai", "phai roi", "vang", "ok", "chinh xac", "dung vay"}
_NO_EXACT = {"khong", "khong phai", "sai", "sai roi", "nham", "khong dung"}
_NOT_FOUND_PHRASE = "khong tim thay"

# "u"/"um" (u/ừm) CO Y loai khoi day - qua ngan/de trung voi tu de dan ("um",
# "ừm de toi nghi da" = con dang ngap ngung, KHONG phai dong y) - phat hien
# qua test_in_rx_confirm_r1_unparseable_reasks_same_stage khi build, "ừm"
# unaccent thanh "um" tung bi hieu nham la "co" (regex prefix "^um\b").


def _parse_yes_no(reply: str) -> bool | None:
    norm = _normalize(reply)
    if norm in _NO_EXACT:
        return False
    if norm in _YES_EXACT:
        return True
    if re.match(r"^(khong|k)\b", norm):
        return False
    if re.match(r"^(co|dung|vang)\b", norm):
        return True
    return None


def _is_not_found_reply(reply: str) -> bool:
    return _NOT_FOUND_PHRASE in _normalize(reply)


# Vong 3, muc 8 - cung tien to "khong"/"k" da dung de PHAT HIEN decline o
# _parse_yes_no (regex "^(khong|k)\b"), dung LAI o day de TACH phan con lai
# cua cau (vd "khong, cefixim" -> "cefixim") - benh nhan hay tra loi "khong,
# [ten thuoc khac]" trong 1 cau thay vi 2 luot rieng (tu choi -> hoi lai ten
# -> xac nhan). Hoat dong tren _normalize(reply) (bo dau + thuong) - an toan
# vi _fuzzy_best_match() normalize lai chinh no, khong mat gi khi normalize 2 lan.
_NO_PREFIX_RE = re.compile(r"^(khong|k)\b[\s,\.\-]*")


def _extract_remainder_after_no(reply: str) -> str:
    """Rong neu "khong" la CA CAU (khong kem ten) - giu dung hanh vi cu
    (hoi lai ten khac / hien top-3) cho case nay, KHONG doan bua khi khong
    co gi de doan."""
    norm = _normalize(reply)
    return _NO_PREFIX_RE.sub("", norm, count=1).strip()


def _parse_choice_index(reply: str, candidates: list[dict]) -> int | None:
    norm = _normalize(reply)
    if norm in ("1", "2", "3"):
        idx = int(norm) - 1
        if idx < len(candidates):
            return idx
    for i, c in enumerate(candidates):
        name_norm = _normalize(c["ten_thuoc"])
        if name_norm and (name_norm in norm or norm in name_norm):
            return i
    return None


_DOSAGE_UNITS = (
    "mg", "mcg", "miu", "iu", "ml", "kg", "vien", "goi", "ong", "chai", "lieu", "vi", "v", "g",
)  # fmt: skip
_PACKAGING_RE = re.compile(r"^\d+x\d+$")  # "3x10", "2x14"
_PURE_NUMBER_RE = re.compile(r"^[\d.]+%?(/[\d.]+%?)?$")  # "100", "0.025", "0.025%", "30/70"


def _looks_like_dosage_or_packaging(word: str) -> bool:
    """True neu `word` la 1 token DOSAGE/DONG GOI that (vd "250mg", "3x10",
    "0.025", "100v"), KHAC voi 1 token dinh danh NGAN dang so+chu (vd "3b",
    "5fu") - phat hien qua review 2026-08-09 voi du lieu that: "3b Agi-neurin
    Agimexpharm 10x10" co TU DAU TIEN la "3b" (bat dau bang so) - ban truoc
    (dung "w[0].isdigit()") dung NGAY o day, core rong hoan toan, fallback ve
    CA CHUOI (khong phai collision nhung vo hieu hoa core-name cho ca thuoc
    nay). Phan biet: dosage token LUON ket thuc bang 1 don vi biet truoc
    (mg/ml/v/...) hoac la so thuan/dang NxN - "3b"/"5fu" khong khop dieu kien
    nao trong so do, nen duoc GIU LAI trong core."""
    if _PACKAGING_RE.match(word) or _PURE_NUMBER_RE.match(word):
        return True
    for unit in _DOSAGE_UNITS:
        if word == unit:
            return True
        if word.endswith(unit):
            prefix = word[: -len(unit)]
            if prefix and re.match(r"^[\d.]+$", prefix):
                return True
    return False


def _drug_core_name(ten_thuoc: str) -> str:
    """Lay phan TEN CHINH cua thuoc (cac TU DAU TIEN, dung lai truoc token
    DOSAGE/DONG GOI that - xem _looks_like_dosage_or_packaging - vd "cefixim"
    tu "Cefixim 200mg Vidipha 1x10") - benh nhan thuong chi nhac/go phan nay
    trong cau hoi TU NHIEN (vd "cefixim la thuoc gi"), khong go lai ca chuoi
    day du kem ham luong/dong goi. So khop nguyen ca cau hoi voi ca ten day
    du (nhu ban dau) bi PHA LOANG boi do dai chenh lech - "cefixim la thuoc
    gi" (20 ky tu) vs "cefixim 200mg vidipha 1x10" (26 ky tu) chi ra
    ratio~0.44 (duoi threshold) du 2 cau RO RANG cung noi ve 1 thuoc - phat
    hien qua test that khi build, sua bang cach uu tien so khop CORE NAME
    truoc, fallback ratio toan chuoi sau.

    QUAN TRONG (sua lan 2, review 2026-08-09) - dung nhan dien DOSAGE THAT
    (ket thuc bang don vi, hoac dang NxN/so thuan) de dung, KHONG chi "bat
    dau bang chu so": ban dau dung dieu kien "tu bat dau bang chu so thi
    dung" khien "b1" (Vitamin B1) van dung y VI b1 bat dau bang chu cai - ban
    THU 2 nay moi phat hien them: neu chinh THUOC co ten bat dau bang 1 token
    dang "3b" (vd "3b Agi-neurin..." - co that trong data), dieu kien cu se
    dung o tu DAU TIEN, core rong hoan toan, fallback ve CA CHUOI (khong
    collision nhung vo hieu hoa hoan toan core-name cho thuoc do). Dinh nghia
    lai theo "co phai dosage/dong goi that khong" thay vi "co bat dau bang so
    khong" - "3b"/"5fu" (ngan, khong ket thuc bang don vi) duoc GIU trong
    core."""
    norm = _normalize(ten_thuoc)
    words = norm.split()
    core_words: list[str] = []
    for w in words:
        if not w or _looks_like_dosage_or_packaging(w):
            break
        core_words.append(w)
    core = " ".join(core_words)
    return core or norm


def _fuzzy_best_match(query: str, candidates: list[dict], threshold: float = 0.5) -> dict | None:
    """`candidates`: list cua {drug_id, ten_thuoc}. String similarity DON
    GIAN (difflib.SequenceMatcher + boost cho prefix/substring/core-name de
    bat viet tat VA cau hoi tu nhien) - dung y kickoff: tap don thuoc active
    nho, khong can hybrid search phuc tap."""
    norm_q = _normalize(query)
    if not norm_q:
        return None
    best: dict | None = None
    best_score = 0.0
    for c in candidates:
        norm_name = _normalize(c["ten_thuoc"])
        if not norm_name:
            continue
        score = SequenceMatcher(None, norm_q, norm_name).ratio()
        if norm_name.startswith(norm_q) or norm_q in norm_name or norm_name in norm_q:
            score = max(score, 0.7)
        # Core name (vd "cefixim") xuat hien nhu 1 TU RIENG trong cau hoi -
        # tin hieu manh du cau hoi dai hon nhieu ten day du cua thuoc.
        core = _drug_core_name(c["ten_thuoc"])
        if core and re.search(rf"\b{re.escape(core)}\b", norm_q):
            score = max(score, 0.75)
        if score > best_score:
            best_score = score
            best = c
    if best is not None and best_score >= threshold:
        return best
    return None


def _dedupe_distinct_drugs(results: list, n: int) -> list[dict]:
    """[Tach rieng 2026-08-09, phan hoi review muc 6 - truoc day logic nay
    NAM INLINE trong _search_distinct_drug_candidates(), khong the unit-test
    doc lap voi DB gia - chi co 1 test o tests/test_retrieval.py xac nhan
    invariant OR (chunk chi qua 1 trong 2 nguong van phai lot vao ket qua)
    cho fuse_rrf() THUAN, KHONG co test nao xac nhan invariant do CON SONG
    SOT sau buoc dedup-theo-drug_id nay (code MOI viet cho muc 5/11, chua
    tung duoc kiem chung truc tiep) - rui ro that: dedup co the vo tinh lam
    mat 1 candidate chi qua duoc 1 nguong neu logic viet sai, du fuse_rrf()
    ban than no dung.

    Nhan thang `results` (list DrugInfoResult DA qua fuse_rrf, giu nguyen
    thu tu RRF) - dedup theo drug_id, giu ban ghi DAU TIEN gap cho moi
    drug_id (thu tu RRF quyet dinh ban ghi nao la "dau tien"), cat con
    toi da `n`."""
    seen: set[str] = set()
    distinct: list[dict] = []
    for r in results:
        if r.drug_id not in seen:
            seen.add(r.drug_id)
            distinct.append({"drug_id": r.drug_id, "ten_thuoc": r.ten_thuoc})
        if len(distinct) >= n:
            break
    return distinct


def _search_distinct_drug_candidates(db: Session, query: str, embedding: list[float], n: int = 4) -> list[dict]:
    """Hybrid search (muc 4.2-4.3) nhung lay POOL LON hon (top_k=50 truoc khi
    cat) roi dedup theo drug_id - "ung vien" o muc 11.2 la THUOC, khong phai
    CHUNK. Can pool lon vi #14 da xac nhan: nhieu chunk cua CUNG 1 thuoc hay
    dung gan nhau trong top-k mac dinh (5), neu chi lay top-5 chunk roi dedup
    co the con LAI IT HON n thuoc phan biet."""
    settings = get_settings()
    vec = vector_search(db, embedding, settings.nguong_vector)
    lex = lexical_search(db, query, settings.nguong_lexical)
    outcome = fuse_rrf(vec, lex, k=settings.rrf_k, top_k=50)
    return _dedupe_distinct_drugs(outcome.results, n)


def _log_rejection(patient_id: str, original_query: str, rejected_drug_id: str) -> None:
    """Muc 11.4 - log RIENG (khong lan vao audit_log, muc dich khac: du lieu
    cai thien matching, khong phai audit an toan). PM da xac nhan muon dung
    log nay ve sau. MVP: ghi qua logging chuan (khong xay bang DB rieng -
    chua co yeu cau doc lai log nay tu code, chi can khong mat di ma khong
    can ha tang moi ngay bay gio)."""
    logging.getLogger("drug_confirmation_rejection").info(
        "patient_id=%s original_query=%r rejected_drug_id=%s", patient_id, original_query, rejected_drug_id
    )


# ---------------------------------------------------------------------------
# Node 1: cau hoi MOI (chua co pending confirmation nao)
# ---------------------------------------------------------------------------


def build_drug_identity_resolution_node(
    db: Session,
    embed_query: EmbedFn,
    select_fuzzy_candidate_fn: FuzzyCandidateSelectFn = _default_fuzzy_candidate_select,
):
    """THAY THE build_retrieval_node trong danh sach node chinh cho drug_info
    (muc 11 - chi dung o day khi KHONG co pending confirmation, do
    chat_routes.py dam bao qua viec chon danh sach node nao de chay)."""

    async def node(state: ConversationState) -> dict:
        if state.get("intent") not in ("drug_info",):
            entry = {
                "step": "drug_identity_resolution",
                "skipped": True,
                "reason": f"intent={state.get('intent')!r}",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        patient_id = state["patient_id"]
        utterance = state["utterance"]

        # 11.1: uu tien thuoc trong don active
        rx_items = list_active_prescription_drug_items(db, patient_id)
        rx_match = _fuzzy_best_match(utterance, rx_items)
        if rx_match is not None:
            set_pending_confirmation(
                db, patient_id, candidates=[rx_match], stage=STAGE_IN_RX_CONFIRM_R1, original_query=utterance
            )
            duration_ms = (time.monotonic() - t0) * 1000
            entry = {
                "step": "drug_identity_resolution",
                "branch": "in_prescription",
                "stage": STAGE_IN_RX_CONFIRM_R1,
                "candidate_drug_id": rx_match["drug_id"],
                "duration_ms": duration_ms,
            }
            return {
                "response": _confirm_question(rx_match["ten_thuoc"]),
                "awaiting_drug_confirmation": True,
                "quick_replies": ["Có", "Không"],
                "trace": _append_trace(state, entry),
            }

        # Vong 4, muc 3.1-3.3: ngoai don dung fuzzy name search top-5 lam
        # duong chinh, khong goi embedding. Hybrid chi con la fallback sau
        # khi benh nhan tu choi va mo ta lai o STAGE_OUT_RX_AWAITING_REDESCRIBE.
        fuzzy_top5 = fuzzy_name_search(db, utterance, top_k=5)
        if not fuzzy_top5:
            duration_ms = (time.monotonic() - t0) * 1000
            entry = {
                "step": "drug_identity_resolution",
                "branch": "out_of_prescription",
                "stage": None,
                "result": "no_candidates_at_all",
                "duration_ms": duration_ms,
            }
            return {
                "response": NOT_FOUND_FINAL_MESSAGE,
                "awaiting_drug_confirmation": True,
                "trace": _append_trace(state, entry),
            }

        fuzzy_candidates = [
            {"drug_id": candidate.drug_id, "ten_thuoc": candidate.ten_thuoc, "score": candidate.score}
            for candidate in fuzzy_top5
        ]
        top1_score = fuzzy_candidates[0]["score"]
        top2_score = fuzzy_candidates[1]["score"] if len(fuzzy_candidates) > 1 else 0.0
        score_gap = top1_score - top2_score
        settings = get_settings()
        is_fast_path = (
            top1_score >= settings.fuzzy_name_high_threshold
            and score_gap >= settings.fuzzy_name_gap_threshold
        )

        if is_fast_path:
            selected_candidates = fuzzy_candidates
            candidate_selection = "fuzzy_fast_path"
        else:
            selected_drug_id = select_fuzzy_candidate_fn(utterance, fuzzy_candidates)
            selected = next((candidate for candidate in fuzzy_candidates if candidate["drug_id"] == selected_drug_id), None)
            # Phan hoi review PR#37 (bot phoenix-mentor): fuzzy_name_search()
            # dung DISTINCT ON (drug_id) nen fuzzy_candidates khong co drug_id
            # trung (retrieval.py) - nhung so sanh o day van dung drug_id
            # TUONG MINH (khong dua vao "!=" so sanh ca dict) de invariant nay
            # khong phu thuoc ngam vao 1 file khac, tranh vo neu logic dedupe
            # ben do thay doi sau nay.
            if selected is None:
                duration_ms = (time.monotonic() - t0) * 1000
                entry = {
                    "step": "drug_identity_resolution",
                    "branch": "out_of_prescription",
                    "stage": None,
                    "result": "llm_no_safe_candidate",
                    "top1_score": top1_score,
                    "top2_score": top2_score,
                    "score_gap": score_gap,
                    "duration_ms": duration_ms,
                }
                return {
                    "response": NOT_FOUND_FINAL_MESSAGE,
                    "awaiting_drug_confirmation": True,
                    "trace": _append_trace(state, entry),
                }
            selected_candidates = [
                selected,
                *(candidate for candidate in fuzzy_candidates if candidate["drug_id"] != selected_drug_id),
            ]
            candidate_selection = "llm_candidate_review"

        # PendingDrugConfirmation chi la state machine UI; giu dung shape cu
        # {drug_id, ten_thuoc}, khong luu diem fuzzy khong can thiet vao DB.
        candidates = [{"drug_id": candidate["drug_id"], "ten_thuoc": candidate["ten_thuoc"]} for candidate in selected_candidates]
        duration_ms = (time.monotonic() - t0) * 1000
        top1 = candidates[0]
        set_pending_confirmation(
            db, patient_id, candidates=candidates, stage=STAGE_OUT_RX_CONFIRM_TOP1_R1, original_query=utterance
        )
        entry = {
            "step": "drug_identity_resolution",
            "branch": "out_of_prescription",
            "stage": STAGE_OUT_RX_CONFIRM_TOP1_R1,
            "candidate_drug_id": top1["drug_id"],
            "candidate_selection": candidate_selection,
            "top1_score": top1_score,
            "top2_score": top2_score,
            "score_gap": score_gap,
            "duration_ms": duration_ms,
        }
        return {
            "response": _confirm_question(top1["ten_thuoc"]),
            "awaiting_drug_confirmation": True,
            "quick_replies": ["Có", "Không"],
            "trace": _append_trace(state, entry),
        }

    return node


# ---------------------------------------------------------------------------
# Node 2: REPLY cho 1 cau hoi xac nhan dang cho
# ---------------------------------------------------------------------------


@dataclass
class _StepResult:
    resolved_drug_id: str | None
    response: str | None
    # (candidates, stage, original_query) neu con tiep tuc hoi; None neu
    # resolved HOAC stop (khong con pending row nao nua).
    new_pending: tuple[list[dict], str, str] | None
    stop: bool  # True neu day la cau tra loi CUOI CUNG (khong tim thay), phai clear pending


# Vong 3, muc 6.1 (#22 - PM cho build truoc, chua xac nhan shape voi team
# app) - suy quick_replies TAP TRUNG tai 1 cho, dua tren `stage` da co san,
# thay vi sua ca 24 diem tao _StepResult rai rac ben tren (rui ro lech thu
# tu tham so positional). Chi anh huong UI goi y nut bam - benh nhan van go
# tay tu do binh thuong, khong doi logic parse reply nao ca.
_CONFIRM_STAGES = {
    STAGE_IN_RX_CONFIRM_R1,
    STAGE_IN_RX_CONFIRM_R2,
    STAGE_OUT_RX_CONFIRM_TOP1_R1,
    STAGE_OUT_RX_CONFIRM_TOP1_R2,
    STAGE_OUT_RX_CONFIRM_PICK_R1,
}
NOT_FOUND_QUICK_REPLY = "Không tìm thấy thuốc tôi cần"


def _infer_quick_replies(stage: str, candidates: list[dict]) -> list[str] | None:
    if stage in _CONFIRM_STAGES:
        return ["Có", "Không"]
    if stage == STAGE_OUT_RX_CHOOSE_TOP3_R1:
        return [c["ten_thuoc"] for c in candidates] + [NOT_FOUND_QUICK_REPLY]
    # STAGE_IN_RX_AWAITING_NEW_NAME / STAGE_OUT_RX_AWAITING_REDESCRIBE - can
    # ten thuoc tu do, khong co goi y nut bam co dinh nao hop ly.
    return None


def build_drug_confirmation_reply_node(
    db: Session,
    embed_query: EmbedFn,
    pending: dict,
    is_drug_reply_fn: DrugReplyPlausibilityFn = _default_drug_reply_plausibility,
):
    """`pending`: dict tra ve tu get_pending_confirmation() (chat_routes.py
    doc TRUOC khi goi node nay, truyen vao qua closure - khong doc lai tu DB
    trong node de tranh race giua doc va handle trong CUNG 1 request).

    `is_drug_reply_fn`: vong 4 muc 2.2 - LLM gate hep pham vi, mac dinh
    permissive (xem docstring DrugReplyPlausibilityFn dau file)."""

    async def node(state: ConversationState) -> dict:
        t0 = time.monotonic()
        patient_id = state["patient_id"]
        reply = state["utterance"]
        stage = pending["stage"]
        candidates = pending["candidates"]
        original_query = pending["original_query"]

        result = _dispatch_stage(db, embed_query, patient_id, stage, candidates, original_query, reply, is_drug_reply_fn)
        duration_ms = (time.monotonic() - t0) * 1000

        if result.resolved_drug_id is not None:
            clear_pending_confirmation(db, patient_id)
            rag_results = get_chunks_by_drug_id(db, result.resolved_drug_id)
            entry = {
                "step": "drug_confirmation_reply",
                "stage": stage,
                "outcome": "resolved",
                "resolved_drug_id": result.resolved_drug_id,
                "duration_ms": duration_ms,
            }
            return {
                "rag_results": rag_results,
                "utterance": original_query,  # tra loi dung cau hoi GOC, khong phai "co"/"khong"
                "trace": _append_trace(state, entry),
            }

        if result.stop:
            clear_pending_confirmation(db, patient_id)
            entry = {"step": "drug_confirmation_reply", "stage": stage, "outcome": "gave_up", "duration_ms": duration_ms}
            return {"response": result.response, "awaiting_drug_confirmation": True, "trace": _append_trace(state, entry)}

        assert result.new_pending is not None
        new_candidates, new_stage, new_original_query = result.new_pending

        # STAGE KHONG DOI = reply khong parse duoc (yes/no/so thu tu), phai
        # hoi lai DUNG cau/menu cu (xem _dispatch_stage cac nhanh unparseable)
        # - KHAC round-budget (dem theo so ung vien da thu). Dem RIENG so lan
        # LIEN TIEP nay, vuot MAX_UNPARSEABLE_RETRIES thi dung han, tranh vong
        # lap vo han khi benh nhan go linh tinh (phat hien qua review 2026-08-09).
        if new_stage == stage:
            retry_count = pending.get("retry_count", 0) + 1
            if retry_count >= MAX_UNPARSEABLE_RETRIES:
                clear_pending_confirmation(db, patient_id)
                entry = {
                    "step": "drug_confirmation_reply",
                    "stage": stage,
                    "outcome": "gave_up_too_many_unparseable_replies",
                    "retry_count": retry_count,
                    "duration_ms": duration_ms,
                }
                return {
                    "response": TOO_MANY_UNPARSEABLE_REPLIES_MESSAGE,
                    "awaiting_drug_confirmation": True,
                    "trace": _append_trace(state, entry),
                }
        else:
            retry_count = 0  # co tien trien that (stage doi) - reset

        set_pending_confirmation(db, patient_id, new_candidates, new_stage, new_original_query, retry_count)
        entry = {
            "step": "drug_confirmation_reply",
            "stage": stage,
            "outcome": "continue",
            "new_stage": new_stage,
            "retry_count": retry_count,
            "duration_ms": duration_ms,
        }
        return {
            "response": result.response,
            "awaiting_drug_confirmation": True,
            "quick_replies": _infer_quick_replies(new_stage, new_candidates),
            "trace": _append_trace(state, entry),
        }

    return node


def _dispatch_stage(
    db: Session,
    embed_query: EmbedFn,
    patient_id: str,
    stage: str,
    candidates: list[dict],
    original_query: str,
    reply: str,
    is_drug_reply_fn: DrugReplyPlausibilityFn = _default_drug_reply_plausibility,
) -> _StepResult:
    if stage == STAGE_IN_RX_CONFIRM_R1:
        yn = _parse_yes_no(reply)
        if yn is True:
            return _StepResult(candidates[0]["drug_id"], None, None, False)
        if yn is False:
            # Vong 3, muc 8 - "khong, [ten thuoc khac]" trong 1 cau: thu fuzzy-
            # match phan con lai NGAY trong luot nay (dung §5.1, cung ham/pool
            # da dung o build_drug_identity_resolution_node) - tiet kiem 1
            # luot so voi hoi lai ten roi moi xac nhan. Rong hoac khong khop
            # gi -> giu NGUYEN hanh vi cu (regression bat buoc theo kickoff).
            remainder = _extract_remainder_after_no(reply)
            if remainder:
                rx_items = list_active_prescription_drug_items(db, patient_id)
                match = _fuzzy_best_match(remainder, rx_items)
                if match is not None:
                    return _StepResult(
                        None,
                        _confirm_question(match["ten_thuoc"]),
                        ([match], STAGE_IN_RX_CONFIRM_R2, original_query),
                        False,
                    )
            return _StepResult(
                None, ASK_DIFFERENT_NAME_MESSAGE, ([], STAGE_IN_RX_AWAITING_NEW_NAME, original_query), False
            )
        return _StepResult(
            None, UNPARSEABLE_YES_NO_MESSAGE, (candidates, STAGE_IN_RX_CONFIRM_R1, original_query), False
        )

    if stage == STAGE_IN_RX_AWAITING_NEW_NAME:
        # Vong 4, muc 2.2/2.3 - LLM gate TRUOC khi fuzzy match: khong co
        # nguong similarity nao tach sach duoc reply khong lien quan (xem
        # docstring classify_drug_reply_plausibility, classification.py).
        # Gate tra "khong" -> xu ly GIONG HET "khong tim duoc gi" (DIEN GIAI
        # #2), khong goi _fuzzy_best_match() nua.
        if not is_drug_reply_fn(reply):
            return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)
        # reply o day la TEN THUOC MOI (khong phai yes/no) - fuzzy match lai
        # trong don active cua benh nhan (muc 11.1).
        rx_items = list_active_prescription_drug_items(db, patient_id)
        match = _fuzzy_best_match(reply, rx_items)
        if match is None:
            # DIEN GIAI #2: khong tim duoc gi voi ten moi - het round, STOP.
            return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)
        return _StepResult(
            None, _confirm_question(match["ten_thuoc"]), ([match], STAGE_IN_RX_CONFIRM_R2, reply), False
        )

    if stage == STAGE_IN_RX_CONFIRM_R2:
        yn = _parse_yes_no(reply)
        if yn is True:
            return _StepResult(candidates[0]["drug_id"], None, None, False)
        # "no" HOAC khong parse duoc deu la STOP o vong 2 (da het round).
        return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)

    if stage == STAGE_OUT_RX_CONFIRM_TOP1_R1:
        yn = _parse_yes_no(reply)
        if yn is True:
            return _StepResult(candidates[0]["drug_id"], None, None, False)
        if yn is False:
            # Vong 3, muc 8 - cung y tuong nhu nhanh in-prescription o tren,
            # ap dung §5.2 (hybrid search) thay vi §5.1 (fuzzy match don
            # active). Neu tim duoc ung vien ro rang -> hoi xac nhan ngay,
            # dua vao STAGE ..._R2 (giong duong "mo ta lai" - da dung 1 lan
            # thu, khong mo lai top-3 tu dau). Khong tim duoc -> giu NGUYEN
            # hanh vi cu (top-3 menu tu candidates con lai).
            remainder = _extract_remainder_after_no(reply)
            if remainder:
                embedding = embed_query(remainder)
                new_candidates = _search_distinct_drug_candidates(db, remainder, embedding, n=1)
                if new_candidates:
                    top1 = new_candidates[0]
                    return _StepResult(
                        None,
                        _confirm_question(top1["ten_thuoc"]),
                        ([top1], STAGE_OUT_RX_CONFIRM_TOP1_R2, original_query),
                        False,
                    )
            rest = candidates[1:4]
            if not rest:
                return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)
            return _StepResult(None, _top3_menu(rest), (rest, STAGE_OUT_RX_CHOOSE_TOP3_R1, original_query), False)
        return _StepResult(
            None, UNPARSEABLE_YES_NO_MESSAGE, (candidates, STAGE_OUT_RX_CONFIRM_TOP1_R1, original_query), False
        )

    if stage == STAGE_OUT_RX_CHOOSE_TOP3_R1:
        if _is_not_found_reply(reply):
            return _StepResult(
                None, ASK_DESCRIBE_AGAIN_MESSAGE, ([], STAGE_OUT_RX_AWAITING_REDESCRIBE, original_query), False
            )
        idx = _parse_choice_index(reply, candidates)
        if idx is None:
            # DIEN GIAI #3 (unscripted case, muc 8 kickoff) - fallback AN
            # TOAN NHAT: hoi lai CUNG menu, khong doan them.
            options = "\n".join(f"{i + 1}. {c['ten_thuoc']}" for i, c in enumerate(candidates))
            return _StepResult(
                None,
                UNPARSEABLE_CHOICE_MESSAGE_TEMPLATE.format(options=options),
                (candidates, STAGE_OUT_RX_CHOOSE_TOP3_R1, original_query),
                False,
            )
        picked = candidates[idx]
        remaining = [c for i, c in enumerate(candidates) if i != idx]
        return _StepResult(
            None,
            _confirm_question(picked["ten_thuoc"]),
            ([picked, *remaining], STAGE_OUT_RX_CONFIRM_PICK_R1, original_query),
            False,
        )

    if stage == STAGE_OUT_RX_CONFIRM_PICK_R1:
        picked = candidates[0]
        rest = candidates[1:]
        yn = _parse_yes_no(reply)
        if yn is True:
            return _StepResult(picked["drug_id"], None, None, False)
        if yn is False:
            _log_rejection(patient_id, original_query, picked["drug_id"])
            # DIEN GIAI #1: quay lai menu top-3 CON LAI, KHONG stop ngay -
            # round-budget ("top-3 ban dau + 1 lan mo ta lai") chua het.
            if not rest:
                return _StepResult(
                    None, ASK_DESCRIBE_AGAIN_MESSAGE, ([], STAGE_OUT_RX_AWAITING_REDESCRIBE, original_query), False
                )
            return _StepResult(None, _top3_menu(rest), (rest, STAGE_OUT_RX_CHOOSE_TOP3_R1, original_query), False)
        return _StepResult(
            None, UNPARSEABLE_YES_NO_MESSAGE, (candidates, STAGE_OUT_RX_CONFIRM_PICK_R1, original_query), False
        )

    if stage == STAGE_OUT_RX_AWAITING_REDESCRIBE:
        # Vong 4, muc 2.2/2.3 - cung ly do voi nhanh STAGE_IN_RX_AWAITING_
        # NEW_NAME o tren. Gate chay TRUOC ca embed_query() - tiet kiem luon
        # 1 lan goi embedding khi reply ro rang khong lien quan.
        if not is_drug_reply_fn(reply):
            return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)
        embedding = embed_query(reply)
        new_candidates = _search_distinct_drug_candidates(db, reply, embedding, n=1)
        if not new_candidates:
            # DIEN GIAI #2: khong tim duoc gi voi mo ta moi - het round, STOP.
            return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)
        top1 = new_candidates[0]
        return _StepResult(
            None, _confirm_question(top1["ten_thuoc"]), ([top1], STAGE_OUT_RX_CONFIRM_TOP1_R2, reply), False
        )

    if stage == STAGE_OUT_RX_CONFIRM_TOP1_R2:
        if _is_not_found_reply(reply):
            return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)
        yn = _parse_yes_no(reply)
        if yn is True:
            return _StepResult(candidates[0]["drug_id"], None, None, False)
        # "no" HOAC khong parse duoc: het round, STOP (khong con vong nao
        # nua o day - dung y "toi da dung 2 vong" cua kickoff).
        return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)

    # Khong ro stage (khong nen xay ra - du lieu DB bi hong/stage cu tu
    # version code truoc) - fail an toan: STOP thay vi crash.
    return _StepResult(None, NOT_FOUND_FINAL_MESSAGE, None, True)
