"""Node cua nhanh "drug_info" (build-kickoff-prompt.md Phase 5):
intent_classification, retrieval, prescription_lookup, answer_generation -
va nhanh "today_schedule" (muc 6 thiet ke, bo sung Phase 6):
today_schedule (khong LLM, query dose_event thang).

Moi node la 1 factory tra ve async function - nhan dependency (LLM classify/
generate, embed_fn, db session) qua tham so thay vi import cung, de test
duoc ma khong can goi OpenAI/Postgres that (dependency injection, giong cach
Phase 4 tach fuse_rrf() thuan khoi hybrid_search() co I/O).

Moi node ghi DUNG 1 entry vao state["trace"] theo dinh dang muc 5.2
(chatbot-rag-design.md) - step, model (neu co), input rut gon, ket qua,
confidence (neu co), duration_ms.

TU-BAO-VE THEO INTENT (Phase 6): retrieval/prescription_lookup/
answer_generation chi chay khi `state["intent"] in (None, "drug_info")` -
None duoc chap nhan de tuong thich nguoc voi test goi thang 1 node rieng le
(khong qua intent_classification truoc, xem tests/test_answer_generation_
node.py) - trong san xuat, intent_classification LUON chay truoc (node dau
tien cua danh sach) nen intent khong bao gio con None luc cac node nay chay.
Day la CUNG 1 idiom da dung cho SEVERITY/LEVEL node tu Phase 5b (tu bao ve
theo `classification`), khong phai sua orchestrator.py de dieu phoi dong -
giu nguyen ranh gioi kiem tra an toan giua TUNG node da duoc kiem chung ky
o Phase 5, khong gop nhieu buoc lai thanh 1 "node" mo (xem thao luan Phase 6
kickoff)."""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from backend.agents.state import ConversationState
from backend.agents.tools.chat_history_tool import get_chat_history_for_display
from backend.agents.tools.drug_info_tool import EmbedFn, tra_cuu_thuoc_chung
from backend.agents.tools.personal_tools import tra_cuu_don_thuoc_ca_nhan, tra_cuu_lich_uong_ca_nhan
from backend.db.models import Patient
from backend.services.retrieval import DrugInfoResult

CAVEAT_LIEU_DUNG = "Đây là liều khuyến cáo chung theo nhãn thuốc, liều thực tế của bạn có thể khác theo chỉ định của bác sĩ."
CAVEAT_THOI_DIEM_MISSING = "Thời điểm dùng cụ thể cần theo chỉ định của bác sĩ."
NO_SOURCE_MESSAGE = "Xin lỗi, tôi không có thông tin đáng tin cậy về câu hỏi này. Vui lòng hỏi bác sĩ."
NO_SCHEDULE_TODAY_MESSAGE = "Hôm nay bạn không có liều thuốc nào được lên lịch."

# Vong 3, muc 6 - cau tra loi CO DINH (khong LLM sinh, tiet kiem + tranh tu
# suy dien khong can thiet cho 1 cau chao don gian), phu ca chao hoi thuan
# lan cau ngoai pham vi thuoc.
#
# SUA vong 3, muc 9.1/9.2 (persona "Capy") - day la nhom THAN THIEN NHAT
# theo dung bang phan loai muc 9.1 (chao hoi/thong tin thuoc thuong/lich
# uong thuoc): dung ten "Capy Medi" + bieu tuong nhe nhang "<3".
#
# #21 (chatbot-rag-design.md muc 10) - GO CHOT TAM 2026-08-12: luc quyet
# dinh #21, chua co nguon du lieu ten benh nhan nao trong he thong nen giu
# ban chao khong ten. Gio bang `Patient.full_name` da co that (migration
# 0009, TASK-010-auth-api) nen ca nhan hoa duoc - nhung Patient.id CHUA co
# khoa ngoai rang buoc voi patient_id dung trong chat/prescription/dose_event
# (co y, xem docstring class Patient trong backend/db/models.py), nen 1 vai
# patient_id (du lieu test cua thanh vien khac) co the KHONG co dong Patient
# tuong ung - fallback ve ban chao khong ten trong truong hop do, khong loi.
GREETING_RESPONSE = (
    "Chào bạn, Capy Medi sẵn sàng chăm sóc bạn <3 Mình có thể giúp bạn: "
    "hỏi thông tin về 1 loại thuốc, xem lịch uống thuốc hôm nay, "
    "hoặc báo đã/chưa uống 1 liều thuốc."
)

GREETING_QUICK_REPLIES = [
    "Hỏi về 1 loại thuốc",
    "Xem lịch uống thuốc hôm nay",
    "Báo đã/chưa uống thuốc",
]


def _greeting_response_for(full_name: str | None) -> str:
    if not full_name:
        return GREETING_RESPONSE
    return (
        f"Chào {full_name}, Capy Medi sẵn sàng chăm sóc bạn <3 Mình có thể giúp bạn: "
        "hỏi thông tin về 1 loại thuốc, xem lịch uống thuốc hôm nay, "
        "hoặc báo đã/chưa uống 1 liều thuốc."
    )

_DRUG_INFO_INTENTS = (None, "drug_info")  # None: goi node truc tiep, ngoai orchestrator (test)


def _append_trace(state: ConversationState, entry: dict) -> list[dict]:
    return [*state.get("trace", []), entry]


def _normalize_for_match(text: str) -> str:
    """Bo dau + lowercase, dung so sanh ten_thuoc voi cau hoi bang Python
    thuan (khong can goi DB unaccent() SQL) - xem _filter_cross_drug_mismatch."""
    nfkd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return stripped.lower()


def _filter_cross_drug_mismatch(
    rag_results: list[DrugInfoResult], utterance: str
) -> list[DrugInfoResult]:
    """[Vá tạm 2026-08-09, mục 10 #17 - KHÔNG thay thế #12/#15, chỉ chặn đúng
    kiểu case đã phát hiện] Phát hiện qua Phase 7: recall miss (#14) có thể
    khiến rag_results chứa chunk của 1 THUỐC KHÁC hoàn toàn cùng field_group
    (không chỉ field_group khác cùng thuốc) - vd hỏi "AME Prazol... tác dụng
    phụ" nhưng model trả lời bằng nội dung "Prazo PRO" (chế phẩm khác), xác
    nhận qua drug_id lệch thật, không phải hallucination (LLM-judge không bắt
    được lớp lỗi này vì nội dung CÓ THẬT trong context, chỉ sai thuốc).

    Vá bằng string-match rẻ, không cần hạ tầng resolve drug_id đầy đủ (#12/
    #15, để dành backlog): nếu câu hỏi CHỨA NGUYÊN VĂN (không dấu, không phân
    biệt hoa/thường) ten_thuoc của >=1 chunk trong rag_results, coi các
    drug_id đó là "đã xác nhận đúng thuốc đang hỏi" và loại bỏ MỌI chunk của
    drug_id KHÁC trước khi đưa vào generate_fn - không để model thấy nội dung
    thuốc không liên quan. Nếu KHÔNG chunk nào khớp tên trong câu hỏi (câu
    hỏi chung, không nêu tên 1 thuốc cụ thể, hoặc tên gõ sai/khác đủ nhiều để
    không match substring) - GIỮ NGUYÊN rag_results, không lọc, vì không đủ
    tin cậy để biết "đúng thuốc" là drug_id nào.

    Giới hạn đã biết: chỉ bắt được case câu hỏi lặp lại chính xác ten_thuoc
    (đúng dạng câu hỏi GT set) - không bắt được tên viết tắt/gõ sai/diễn đạt
    khác. Không thay thế được #12 (routing dùng đơn thuốc active) hay #15
    (thuốc không tồn tại trong corpus)."""
    if not rag_results:
        return rag_results
    norm_utterance = _normalize_for_match(utterance)
    matched_drug_ids = {
        r.drug_id for r in rag_results if _normalize_for_match(r.ten_thuoc) in norm_utterance
    }
    if not matched_drug_ids:
        return rag_results
    return [r for r in rag_results if r.drug_id in matched_drug_ids]


class IntentClassifyFn(Protocol):
    def __call__(self, utterance: str) -> tuple[str, float]: ...


class AnswerGenerateFn(Protocol):
    def __call__(self, utterance: str, rag_results: list) -> str: ...


class SearchFn(Protocol):
    def __call__(self, db: Session, query: str, embed_query: EmbedFn): ...


def _format_context_prefix(history: list[dict]) -> str:
    """Vong 3, muc 7.2 - dinh dang cua so ngu canh 15 phut gan day thanh 1
    doan prefix, ghep TRUOC utterance that. CO Y KHONG doi signature cua
    classify_intent/generate_answer (Protocol IntentClassifyFn/AnswerGenerateFn
    van chi nhan 1 chuoi utterance) - tranh thay doi lam vo hang chuc fake da
    co trong tests/ (build_intent_classification_node/build_answer_generation_
    node CHI them 1 tham so `db` MOI, optional, khong doi cach goi classify_
    fn/generate_fn ben trong)."""
    if not history:
        return ""
    lines = [f"{'Bệnh nhân' if h['role'] == 'patient' else 'Trợ lý'}: {h['content']}" for h in history]
    return "Ngữ cảnh hội thoại gần đây (15 phút gần nhất):\n" + "\n".join(lines) + "\n\nCâu hỏi hiện tại: "


def build_intent_classification_node(
    classify_fn: IntentClassifyFn, db: Session | None = None, model_name: str = "gpt-4o-mini"
):
    """`db` THEM 2026-08-12 (vong 3, muc 7.2) - optional, mac dinh None =
    hanh vi CU nguyen ven (khong lay ngu canh, dung cho test goi truc tiep
    khong qua DB that). Khi co `db` (production, xem chat_routes.py), lay
    cua so 15 phut gan day GHEP VAO utterance TRUOC KHI goi classify_fn -
    KHONG doi state["utterance"] goc (chi dung ban ghep cho lan goi LLM nay,
    cac buoc sau van doc utterance goc nguyen ven, xem docstring
    _format_context_prefix)."""

    async def node(state: ConversationState) -> dict:
        t0 = time.monotonic()
        augmented_utterance = state["utterance"]
        if db is not None:
            from backend.agents.tools.chat_history_tool import get_recent_context

            history = get_recent_context(db, state["patient_id"])
            augmented_utterance = _format_context_prefix(history) + state["utterance"]
        intent, confidence = classify_fn(augmented_utterance)
        duration_ms = (time.monotonic() - t0) * 1000
        entry = {
            "step": "intent_classification",
            "model": model_name,
            "result": intent,
            "confidence": confidence,
            "duration_ms": duration_ms,
        }
        return {"intent": intent, "trace": _append_trace(state, entry)}

    return node


def build_greeting_node(db: Session):
    """Vong 3, muc 6 - tu bao ve theo intent=="greeting" giong moi node khac
    (khong dung danh sach rieng cho tung intent, xem docstring dau file).
    Khong goi LLM - response gan nhu co dinh, chi 1 truy van DB don gian
    (Patient theo patient_id) de ca nhan hoa ten (#21) neu co."""

    async def node(state: ConversationState) -> dict:
        if state.get("intent") != "greeting":
            entry = {
                "step": "greeting",
                "skipped": True,
                "reason": f"intent={state.get('intent')!r}",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        patient = db.get(Patient, state["patient_id"])
        full_name = patient.full_name if patient else None
        duration_ms = (time.monotonic() - t0) * 1000
        entry = {"step": "greeting", "personalized": full_name is not None, "duration_ms": duration_ms}
        return {
            "response": _greeting_response_for(full_name),
            "quick_replies": GREETING_QUICK_REPLIES,
            "trace": _append_trace(state, entry),
        }

    return node


def build_chat_history_query_node(db: Session):
    """Vong 3, muc 7.3(a) - tu bao ve theo intent=="chat_history_query".
    KHONG dua ca utterance vao search_chat_history() lam tu khoa (cau hoi
    tu nhien nhu "truoc day toi tung hoi thuoc gi" gan nhu chac chan KHONG
    xuat hien nguyen van trong tin nhan cu, ILIKE se luon rong) - dung
    "5 tin nhan GAN NHAT cua chinh benh nhan" lam recap mac dinh, huu ich
    hon tra ve rong cho pham vi cau hoi chung chung kickoff mo ta. KHONG
    dung LLM (deterministic, giong tinh than today_schedule_node).

    QUAN TRONG ve THU TU: chat_routes.py CHI luu tin nhan cua luot hien tai
    (ca patient utterance lan response) vao chat_messages SAU KHI toan bo
    run_conversation() (bao gom node nay) da chay xong - tai thoi diem node
    nay doc history, cau hoi HIEN TAI CHUA duoc luu, nen history chi chua
    tin nhan THAT SU o qua khu, khong can tu loai bo phan tu cuoi."""

    async def node(state: ConversationState) -> dict:
        if state.get("intent") != "chat_history_query":
            entry = {
                "step": "chat_history_query",
                "skipped": True,
                "reason": f"intent={state.get('intent')!r}",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        history = get_chat_history_for_display(db, state["patient_id"])
        patient_messages = [h for h in history if h["role"] == "patient"][-5:]
        duration_ms = (time.monotonic() - t0) * 1000

        if not patient_messages:
            response = "Mình chưa thấy lịch sử trò chuyện nào trước đó của bạn."
        else:
            lines = [f"- {m['content']}" for m in patient_messages]
            response = "Gần đây bạn từng hỏi:\n" + "\n".join(lines)

        entry = {"step": "chat_history_query", "message_count": len(patient_messages), "duration_ms": duration_ms}
        return {"response": response, "trace": _append_trace(state, entry)}

    return node


def build_retrieval_node(db: Session, embed_query: EmbedFn, search_fn: SearchFn = tra_cuu_thuoc_chung):
    """`search_fn` injectable (mac dinh `tra_cuu_thuoc_chung` that, goi DB) -
    de test duoc filter #17 ben duoi ma khong can Postgres that, cung idiom
    voi `generate_fn`/`classify_fn` o cac node khac.

    Loc cross-drug mismatch (muc 10 #17, phat hien 2026-08-09) NGAY O DAY,
    KHONG phai chi o answer_generation_node: `prescription_lookup_node` chay
    SAU retrieval nhung TRUOC answer_generation (muc 8), va dung thang
    `rag_results[0].drug_id` de tra don thuoc ca nhan - neu chi loc o
    answer_generation_node (nhu ban va tam dau tien), prescription_lookup_node
    van doc duoc rag_results CHUA loc, van co the tra nham don thuoc (gio
    uong that cua benh nhan) cua 1 thuoc khac hoan toan. Loc o day dam bao
    CA HAI node phia sau deu nhan duoc state["rag_results"] da loc san - van
    GIU loc lai o answer_generation_node (idempotent, khong doi ket qua neu
    da loc roi) theo dung tinh than "moi node tu bao ve", khong phu thuoc
    ngam vao thu tu chay dung cua node khac."""

    async def node(state: ConversationState) -> dict:
        if state.get("intent") not in _DRUG_INFO_INTENTS:
            entry = {"step": "retrieval", "skipped": True, "reason": f"intent={state.get('intent')!r}", "duration_ms": 0.0}
            return {"trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        outcome = search_fn(db, state["utterance"], embed_query)
        raw_count = len(outcome.results)
        filtered_results = _filter_cross_drug_mismatch(outcome.results, state["utterance"])
        duration_ms = (time.monotonic() - t0) * 1000
        entry = {
            "step": "retrieval",
            "mode": "hybrid_search",
            "query": state["utterance"],
            "no_source_found": outcome.no_source_found,
            "result_count": len(filtered_results),
            "cross_drug_filtered_count": raw_count - len(filtered_results),
            "duration_ms": duration_ms,
        }
        return {"rag_results": filtered_results, "trace": _append_trace(state, entry)}

    return node


def build_prescription_lookup_node(db: Session):
    async def node(state: ConversationState) -> dict:
        if state.get("intent") not in _DRUG_INFO_INTENTS or state.get("awaiting_drug_confirmation"):
            entry = {
                "step": "prescription_lookup",
                "skipped": True,
                "reason": (
                    f"intent={state.get('intent')!r}"
                    if not state.get("awaiting_drug_confirmation")
                    else "awaiting_drug_confirmation"
                ),
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        rag_results = state.get("rag_results") or []
        if not rag_results:
            entry = {"step": "prescription_lookup", "found": False, "reason": "no_rag_results", "duration_ms": 0.0}
            return {"prescription_instruction": None, "trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        drug_id = rag_results[0].drug_id
        item = tra_cuu_don_thuoc_ca_nhan(db, state["patient_id"], drug_id)
        duration_ms = (time.monotonic() - t0) * 1000
        entry = {
            "step": "prescription_lookup",
            "drug_id": drug_id,
            "found": item is not None,
            "thoi_diem_dung": item.get("thoi_diem_dung") if item else None,
            "duration_ms": duration_ms,
        }
        return {
            "prescription_instruction": item.get("thoi_diem_dung") if item else None,
            "trace": _append_trace(state, entry),
        }

    return node


def build_answer_generation_node(generate_fn: AnswerGenerateFn, db: Session | None = None, model_name: str = "gpt-4o-mini"):
    """2 caveat TACH RIENG thanh 2 boolean khac nhau trong trace - KHONG gop
    chung 1 field (chot lai truoc khi code, xem lich su thao luan Phase 4/5).
    Ca 2 deu duoc CODE chen tuong minh (khong dua vao system prompt cua LLM
    tu nho chen) - dam bao 100% nhat quan, dung tinh than "moi hanh dong AI
    deu truy vet duoc".

    REFUSE (BR-7.3, muc 4.4) GOP VAO DAY thay vi 1 node rieng (phat hien
    2026-08-08, review Phase 6 kickoff): `rag_results` rong (retrieval_node
    da bao `no_source_found`, hoac RRF khong con gi) -> tu choi ngay, KHONG
    goi generate_fn - truoc do build_refuse_node() ton tai nhung KHONG BAO
    GIO duoc noi vao danh sach node nao ca (dead code tu Phase 5), nghia la
    luong that se van goi LLM sinh cau tra loi voi 0 nguon RAG (rui ro bia
    thong tin ma khong ai bat duoc, vi khong co test nao goi qua danh sach
    node day du de lo ra)."""

    async def node(state: ConversationState) -> dict:
        if state.get("intent") not in _DRUG_INFO_INTENTS or state.get("awaiting_drug_confirmation"):
            entry = {
                "step": "answer_generation",
                "skipped": True,
                "reason": (
                    f"intent={state.get('intent')!r}"
                    if not state.get("awaiting_drug_confirmation")
                    else "awaiting_drug_confirmation"
                ),
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        rag_results = state.get("rag_results") or []
        rag_results = _filter_cross_drug_mismatch(rag_results, state["utterance"])
        if not rag_results:
            entry = {"step": "refuse", "reason": "no_source_found", "duration_ms": 0.0}
            return {"response": NO_SOURCE_MESSAGE, "trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        augmented_utterance = state["utterance"]
        if db is not None:
            from backend.agents.tools.chat_history_tool import get_recent_context

            history = get_recent_context(db, state["patient_id"])
            augmented_utterance = _format_context_prefix(history) + state["utterance"]
        base_answer = generate_fn(augmented_utterance, rag_results)

        parts = [base_answer]
        caveat_lieu_dung_inserted = False
        caveat_thoi_diem_missing_inserted = False

        used_cach_dung = any(r.field_group == "cach_dung" for r in rag_results)
        if used_cach_dung:
            parts.append(CAVEAT_LIEU_DUNG)
            caveat_lieu_dung_inserted = True

        prescription_instruction = state.get("prescription_instruction")
        if prescription_instruction:
            parts.append(f"Theo đơn thuốc của bạn: {prescription_instruction}.")
        elif rag_results:
            # co ket qua RAG (thuoc chung) nhung KHONG co chi dinh ca nhan cho
            # thuoc nay - phai noi ro, khong duoc im lang bo qua (muc 3.1).
            parts.append(CAVEAT_THOI_DIEM_MISSING)
            caveat_thoi_diem_missing_inserted = True

        response = " ".join(parts)
        duration_ms = (time.monotonic() - t0) * 1000
        entry = {
            "step": "answer_generation",
            "model": model_name,
            "sources_used": [f"{r.drug_id}:{r.field_group}" for r in rag_results],
            "caveat_lieu_dung_inserted": caveat_lieu_dung_inserted,
            "caveat_thoi_diem_missing_inserted": caveat_thoi_diem_missing_inserted,
            "duration_ms": duration_ms,
        }
        return {"response": response, "trace": _append_trace(state, entry)}

    return node


# Vong 3, muc 5.1 - fixed-offset +07:00 (VN khong DST), cung pattern da
# dung o scripts/log_*.py va scripts/seed_*.py (sua cung dot voi bug
# timezone o do).
VN_TZ = timezone(timedelta(hours=7))

# Muc 5.2 - khung gio buoi DA CHOT (kickoff-prompt-vong-3.md). Gio 0h-5h
# (truoc "Sang") KHONG duoc dinh nghia tuong minh trong kickoff - gan vao
# "toi" (gan nhat ve mat sinh hoat, tranh 1 khung gio nao đó bi rot khoi moi
# phan loai) - quyet dinh tu suy luan, ghi ro o day de khong ai tuong nham
# la yeu cau tuong minh.
_BUOI_RANGES: dict[str, tuple[int, int]] = {
    "sang": (5, 11),
    "trua": (11, 13),
    "chieu": (13, 18),
    "toi": (18, 24),
}
_BUOI_LABELS = {"sang": "sáng", "trua": "trưa", "chieu": "chiều", "toi": "tối"}
_BUOI_ORDER = ["sang", "trua", "chieu", "toi"]


def _buoi_of_hour(hour: int) -> str:
    for buoi, (start, end) in _BUOI_RANGES.items():
        if start <= hour < end:
            return buoi
    return "toi"  # 0h-5h - xem ghi chu tren


def _detect_requested_buoi(utterance: str) -> str | None:
    """Muc 5.3 - so khop tu khoa THUAN (khong LLM, dung quyet dinh goc "domain
    nay khong can LLM").

    BUG THAT phat hien khi test truc tiep (khong phai suy doan) - CO Y
    KHONG dung _normalize_for_match() (bo dau) o day: "tôi" (dai tu nhan
    xung, cuc pho bien - hau nhu moi cau benh nhan go deu co) va "tối"
    (buoi toi) deu bo dau thanh "toi" giong het nhau, gay false-positive
    tren GAN NHU MOI cau (vd "hôm nay tôi uống thuốc gì" bi hieu NHAM la
    hoi rieng buoi toi, an mat lich ca ngay con lai - loi an toan/do tin
    cay that, khong phai chi tieu bien). Chi so khop tren chuoi CO GIU DAU
    (chi ha thuong) - benh nhan go KHONG dau se khong duoc phat hien buoi
    (fallback AN TOAN: tra CA NGAY) thay vi doan sai va lam mat du lieu."""
    lowered = utterance.lower()
    for buoi, label in _BUOI_LABELS.items():
        if label in lowered:
            return buoi
    return None


_DOSAGE_UNITS = ("mg", "mcg", "miu", "iu", "ml", "kg", "vien", "goi", "ong", "chai", "lieu", "vi", "g")
_PACKAGING_RE = re.compile(r"^\d+x\d+$")


def _looks_like_dosage_token(word: str) -> bool:
    lw = _normalize_for_match(word)
    if _PACKAGING_RE.match(lw):
        return True
    for unit in _DOSAGE_UNITS:
        if lw == unit or (lw.endswith(unit) and re.match(r"^[\d.]+$", lw[: -len(unit)])):
            return True
    return False


def _short_drug_name(ten_thuoc: str) -> str:
    """Muc 5.4 - rut gon CHI o tang HIEN THI (khong doi drug_id/tang luu
    tru/match - tranh lap lai rui ro core-name da gap o muc 5 vong 2). Giu
    ten + ham luong DAU TIEN gap duoc, bo hang san xuat + quy cach dong goi
    phia sau (vd "Solufemo 100mg Hataphar 20 ỐNG" -> "Solufemo 100mg").
    Khong tim thay token ham luong nao -> giu nguyen ca chuoi (an toan hon
    doan sai)."""
    if not ten_thuoc:
        return ten_thuoc
    kept: list[str] = []
    for w in ten_thuoc.split():
        kept.append(w)
        if _looks_like_dosage_token(w):
            return " ".join(kept)
    return ten_thuoc


def _group_events_by_hour(parsed: list[tuple[datetime, dict]]) -> dict[int, list[dict]]:
    by_hour: dict[int, list[dict]] = {}
    for dt, e in parsed:
        by_hour.setdefault(dt.hour, []).append(e)
    return by_hour


def _format_full_day_answer(now: datetime, by_hour: dict[int, list[dict]]) -> str:
    """Muc 5.4 - format khi hoi CA NGAY ("hôm nay uống thuốc gì")."""
    sections = [f"Hôm nay, ngày {now.day} tháng {now.month} năm {now.year}"]
    for hour in sorted(by_hour):
        evs = by_hour[hour]
        buoi = _buoi_of_hour(hour)
        names: list[str] = []
        all_taken = True
        for e in evs:
            names.extend(_short_drug_name(i.get("ten_thuoc", "?")) for i in (e.get("expected_items") or []))
            if e["status"] != "TAKEN":
                all_taken = False
        status_text = "đã uống" if all_taken else "chưa uống"
        sections.append(f"Buổi {_BUOI_LABELS[buoi]}, {hour} giờ bạn cần uống:\n- {', '.join(names)} ({status_text})")
    return "\n\n".join(sections)


def _format_buoi_answer(db: Session, patient_id: str, buoi: str, by_hour: dict[int, list[dict]]) -> str:
    """Muc 5.4 - format khi hoi THEO BUOI cu the ("buổi sáng tôi cần uống
    thuốc gì"), co ghep thoi_diem_dung tu don thuoc THAT (khong phai RAG -
    dung y muc 3.1). Cung thoi_diem_dung + khong thieu ai -> gop 1 cau.
    Khac nhau HOAC co thuoc thieu thoi_diem_dung -> liet rieng tung dong,
    thuoc thieu thoi_diem_dung thi BO HAN phan do (khong hien cho trong)."""
    lines: list[str] = []
    for hour in sorted(by_hour):
        evs = by_hour[hour]
        drug_entries: list[tuple[str, str | None]] = []
        for e in evs:
            for item in e.get("expected_items") or []:
                short_name = _short_drug_name(item.get("ten_thuoc", "?"))
                thoi_diem = None
                drug_id = item.get("drug_id")
                if drug_id:
                    presc_info = tra_cuu_don_thuoc_ca_nhan(db, patient_id, drug_id)
                    if presc_info:
                        thoi_diem = presc_info.get("thoi_diem_dung")
                drug_entries.append((short_name, thoi_diem))

        distinct_thoi_diem = {td for (_n, td) in drug_entries if td}
        missing_thoi_diem = any(td is None for (_n, td) in drug_entries)

        if len(distinct_thoi_diem) <= 1 and not missing_thoi_diem:
            names = ", ".join(n for n, _td in drug_entries)
            td = next(iter(distinct_thoi_diem)) if distinct_thoi_diem else None
            if td:
                lines.append(f"Buổi {_BUOI_LABELS[buoi]} bạn cần uống {names} vào lúc {hour} giờ, {td}.")
            else:
                lines.append(f"Buổi {_BUOI_LABELS[buoi]} bạn cần uống {names} vào lúc {hour} giờ.")
        else:
            lines.append(f"Buổi {_BUOI_LABELS[buoi]}, {hour} giờ bạn cần uống:")
            for n, td in drug_entries:
                lines.append(f"- {n}, {td}." if td else f"- {n}.")
    return "\n".join(lines)


def build_today_schedule_node(db: Session):
    """Nhanh "Hôm nay tôi uống thuốc gì" (muc 6 thiet ke goc, viet lai hoan
    toan o vong 3 muc 5) - query truc tiep `dose_event` theo patient_id,
    KHONG LLM (dung quyet dinh goc "1 tool call SQL, khong can LLM suy
    luan" - loc buoi cung bang so khop tu khoa thuan, khong phai suy luan
    ngu nghia). Tu bao ve theo intent giong cac node khac.

    Vong 3 sua 3 van de cu: (1) CHI loc dung HOM NAY (truoc day tra ve TOAN
    BO lich su, khong loc ngay); (2) them loc theo buoi khi cau hoi nhac ten
    buoi (muc 5.3); (3) format lai theo dung 2 vi du PM dua, kem thoi_diem_
    dung THAT tu don thuoc khi hoi theo buoi (muc 5.4)."""

    async def node(state: ConversationState) -> dict:
        if state.get("intent") != "today_schedule":
            entry = {
                "step": "today_schedule",
                "skipped": True,
                "reason": f"intent={state.get('intent')!r}",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        now = datetime.now(VN_TZ)
        events = tra_cuu_lich_uong_ca_nhan(db, state["patient_id"], on_date=now)

        requested_buoi = _detect_requested_buoi(state["utterance"])
        parsed: list[tuple[datetime, dict]] = []
        for e in events:
            dt = datetime.fromisoformat(e["scheduled_at"]).astimezone(VN_TZ)
            if requested_buoi and _buoi_of_hour(dt.hour) != requested_buoi:
                continue
            parsed.append((dt, e))

        by_hour = _group_events_by_hour(parsed)
        duration_ms = (time.monotonic() - t0) * 1000

        if not by_hour:
            response = NO_SCHEDULE_TODAY_MESSAGE
        elif requested_buoi:
            response = _format_buoi_answer(db, state["patient_id"], requested_buoi, by_hour)
        else:
            response = _format_full_day_answer(now, by_hour)

        entry = {
            "step": "today_schedule",
            "dose_event_count": len(parsed),
            "requested_buoi": requested_buoi,
            "duration_ms": duration_ms,
        }
        return {"response": response, "trace": _append_trace(state, entry)}

    return node


NodeFn = Callable[[ConversationState], "dict"]
