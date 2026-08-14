"""Dieu phoi 1 luot xu ly utterance: chay `safety_check` NHU 1 TASK DOC LAP,
song song voi day cac node cua "luong chinh" (ADR-0009: "Safety layer khong
phai 1 node trong graph chinh"). Giua MOI 2 node lien tiep, kiem tra
safety_task da xong chua - neu xong VA la redflag, dung ngay luong chinh,
khong chay tiep cac node con lai.

Do chi tiet ky thuat: don vi "cat ngang" o day la RANH GIOI GIUA 2 NODE (sau
khi 1 node chay xong, truoc khi node ke tiep bat dau) - khong phai preempt
giua chung 1 lan goi API dang chay (vd huy nua chung 1 lan goi LLM). Day la
do hat hop ly cho kien truc node-based (LangGraph) - "cat ngang" thuc su o
muc do nay da du chung minh redflag khong bi bo lo du toi luc nao trong
luong chinh (ADR-0009 rang buoc #3), khong phai chi kiem tra truoc khi bat
dau (tuc "gan nhu luon lo di 1 nua neu redflag toi giua chung").

Cac hang so overlay message (OVERDOSE_OVERLAY_MESSAGE, SYMPTOM_OVERLAY_
MESSAGE...) va viec goi escalate_fn deu lay tu src/services/escalation.py -
DUNG CHUNG voi duong HIGH con lai (SEVERITY -> LEVEL = "Nguy hiểm",
src/agents/nodes/dose_confirmation_nodes.py). Khong duoc dinh nghia rieng o
day (phat hien 2026-08-08: truoc do file nay tu dinh nghia overlay message
rieng va KHONG he goi escalate_fn nao - safety_layer redflag chi set
response/severity, chua bao gio thuc su bao nguoi than/bac si, du BR-3.5
yeu cau ca 2 duong HIGH deu phai lam viec do).

Vong 2 (2026-08-09, chatbot-rag-design.md muc 7.1): 2 nhom redflag
(SafetyFlag.matched_group) gio co overlay RIENG - "overdose_risk" ->
OVERDOSE_OVERLAY_MESSAGE, "clinical" -> SYMPTOM_OVERLAY_MESSAGE. SUA 2026-08-09 (review): matched_
group=None (LLM layer flag redflag ma KHONG khop keyword group nao - tuc
chinh he thong cung chua biet day la loai nguy hiem gi, co the khong phai
lieu dung/trieu chung ma la thu khac hoan toan) dung GENERIC_OVERLAY_
MESSAGE rieng - KHONG ep vao overdose/symptom, vi gan nham nhan cu the se
dua thong tin SAI nhung nghe cu the cho nguoi nhan canh bao (cung ban chat
rui ro voi #17: thong tin sai nhung tu tin)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from backend.agents.state import ConversationState
from backend.services.escalation import (
    CATEGORY_EXPLANATIONS,
    GENERIC_OVERLAY_MESSAGE,
    OVERDOSE_OVERLAY_MESSAGE,
    SELF_HARM_OVERLAY_MESSAGE,
    SYMPTOM_OVERLAY_MESSAGE,
    TRIGGER_SAFETY_REDFLAG,
    EscalateFn,
    EscalationOutcome,
    trigger_emergency_escalation,
)
from backend.services.safety import SafetyFlag

SafetyCheckFn = Callable[[str], Awaitable[SafetyFlag]]
NodeFn = Callable[[ConversationState], Awaitable[dict]]
RedflagAuditFn = Callable[[ConversationState, SafetyFlag], Awaitable[dict]]

__all__ = [
    "OVERDOSE_OVERLAY_MESSAGE",
    "SYMPTOM_OVERLAY_MESSAGE",
    "GENERIC_OVERLAY_MESSAGE",
    "run_conversation",
    "default_safety_check",
]


def _apply_redflag(
    state: ConversationState, flag: SafetyFlag, interrupted_after_step: str | None, escalation: EscalationOutcome | None
) -> ConversationState:
    entry = {
        "step": "safety_layer",
        "keyword_hit": flag.source in ("keyword", "keyword+llm"),
        "llm_flag": flag.source in ("llm", "keyword+llm"),
        "matched_group": flag.matched_group,
        "level": flag.level,  # MOI vong 3
        "llm_category": flag.llm_category,  # MOI vong 3
        "llm_reasoning": flag.llm_reasoning,  # MOI vong 3
        "interrupted_after_step": interrupted_after_step,
        # escalated_to CHI liet ke target THUC SU thanh cong (khong phai "da
        # goi") - escalation_failed ghi ro target nao that bai + vi sao, de
        # co the goi lai thu cong neu can (phat hien 2026-08-08: 1 kenh loi
        # khong duoc lam mat dau vet cua kenh do trong audit log).
        "escalated_to": escalation.succeeded if escalation else [],
        "escalation_failed": escalation.failed if escalation else {},
    }
    trace = [*state.get("trace", []), entry]
    # Chon overlay theo category - uu tien llm_category (taxonomy 5 nhom,
    # muc 3.1) truoc, fallback matched_group (lop keyword, chi co 2 nhom) neu
    # LLM khong cung cap category (vd LLM loi/timeout, chi con keyword flag).
    # self_harm -> SELF_HARM (muc 10 #18); wrong_drug -> GENERIC (muc 10 #19,
    # PM quyet dinh khong can overlay rieng); con lai/khong ro -> GENERIC
    # (khong doan bua, xem docstring dau file - cung nguyen tac da dung cho
    # matched_group=None truoc day).
    if flag.llm_category == "dosage_risk" or flag.matched_group == "overdose_risk":
        overlay_message = OVERDOSE_OVERLAY_MESSAGE
    elif flag.llm_category in ("clinical_symptom", "severe_reaction") or flag.matched_group == "clinical":
        overlay_message = SYMPTOM_OVERLAY_MESSAGE
    elif flag.llm_category == "self_harm":
        overlay_message = SELF_HARM_OVERLAY_MESSAGE
    else:
        overlay_message = GENERIC_OVERLAY_MESSAGE

    # Vong 3, muc 9.3 (muc 10 #23) - ghep them 1 cau giai thich ngan theo
    # DUNG category (taxonomy muc 3.1) SAU overlay_message da chon, neu co
    # category ro rang (llm_category). Khong co category (vd chi keyword
    # trigger, matched_group="overdose_risk"/"clinical" khong map 1-1 sang
    # 5 category taxonomy) -> khong ghep gi them, giu nguyen overlay_message
    # nhu truoc, tranh doan sai category tu nguon keyword.
    explanation = CATEGORY_EXPLANATIONS.get(flag.llm_category) if flag.llm_category else None
    if explanation:
        overlay_message = f"{overlay_message} {explanation}"

    return {
        **state,
        "safety_flag": True,
        "severity": "Nguy hiểm",
        "response": overlay_message,
        "trace": trace,
    }


async def _run_redflag_audit(
    redflag_audit_fn: RedflagAuditFn | None, current_state: ConversationState, flag: SafetyFlag
) -> ConversationState:
    """Audit khong duoc phep chan overlay an toan neu no bi loi."""
    if redflag_audit_fn is None:
        return current_state
    try:
        update = await redflag_audit_fn(current_state, flag)
    except Exception as exc:  # noqa: BLE001 - safety response phai fail-safe
        entry = {
            "step": "side_effect_audit",
            "trigger": "safety_redflag",
            "result": "unavailable",
            "error": type(exc).__name__,
            "duration_ms": 0.0,
        }
        return {**current_state, "trace": [*current_state.get("trace", []), entry]}
    return {**current_state, **update}


async def run_conversation(
    state: ConversationState,
    nodes: list[NodeFn],
    safety_check: SafetyCheckFn,
    escalate_fn: EscalateFn | None = None,
    redflag_audit_fn: RedflagAuditFn | None = None,
) -> ConversationState:
    """Chay `nodes` tuan tu, song song voi `safety_check(state["utterance"])`
    chay nhu 1 asyncio.Task doc lap ngay tu dau. Kiem tra task nay giua moi
    cap node lien tiep - redflag o bat ky diem kiem tra nao deu dung luong
    chinh ngay, ghi ro trace dung sau buoc nao (khong phai trace rong hay
    gia vo chay het binh thuong).

    `escalate_fn` (optional - None = khong escalate, dung cho test/truong
    hop chua wiring that o Phase 6) duoc goi qua CUNG 1 ham dung chung
    src/services/escalation.py voi duong HIGH con lai (SEVERITY -> LEVEL,
    xem dose_confirmation_nodes.py) - ca 2 duong PHAI hoi tu ve 1 cho."""
    safety_task = asyncio.create_task(safety_check(state["utterance"]))
    current_state = dict(state)
    last_completed_step: str | None = None

    for node in nodes:
        # Nhuong quyen dieu khien cho event loop truoc khi kiem tra - neu
        # safety_task khong co await ben trong (vd redflag phat hien tuc
        # thi), no can it nhat 1 lan event loop chay de duoc thuc thi va
        # danh dau done(); khong co dong nay, task moi tao co the chua bao
        # gio duoc chay truoc khi vong lap qua het cac node.
        await asyncio.sleep(0)
        if safety_task.done():
            flag = safety_task.result()
            if flag.is_redflag:
                current_state = await _run_redflag_audit(redflag_audit_fn, current_state, flag)
                escalation = await _maybe_escalate(escalate_fn, current_state, flag)
                return _apply_redflag(current_state, flag, last_completed_step, escalation)

        update = await node(current_state)  # type: ignore[arg-type]
        current_state = {**current_state, **update}
        if update.get("trace"):
            last_completed_step = update["trace"][-1].get("step")

    # Kiem tra lan cuoi sau khi het node - redflag co the toi dung luc node
    # cuoi dang chay va xong ngay sau do.
    flag = await safety_task
    if flag.is_redflag:
        current_state = await _run_redflag_audit(redflag_audit_fn, current_state, flag)
        escalated = await _maybe_escalate(escalate_fn, current_state, flag)
        return _apply_redflag(current_state, flag, last_completed_step, escalated)

    # SUA vong 3, muc 3 - TRUOC day entry nay LUON hardcode "khong flag gi"
    # (dung khi safety_layer chi la keyword thuan) - gio LLM co the tra ve
    # "Nhẹ"/"Trung bình" (khong cat luong chinh, xem SafetyFlag.is_redflag)
    # nhung VAN can ghi day du vao trace de audit thay lop nay da chay va
    # ket qua that, khong chi "false" mo ho (kickoff-prompt-vong-3.md muc 3:
    # "bước safety_layer vẫn ghi vào trace dù không redflag, để audit thấy
    # lớp này đã chạy" - ap dung ca cho Nhẹ/Trung bình, khong chi truong hop
    # sach hoan toan).
    entry = {
        "step": "safety_layer",
        "keyword_hit": flag.source in ("keyword", "keyword+llm"),
        "llm_flag": flag.source in ("llm", "keyword+llm"),
        "matched_group": flag.matched_group,
        "level": flag.level,
        "llm_category": flag.llm_category,
        "llm_reasoning": flag.llm_reasoning,
    }
    current_state["trace"] = [*current_state.get("trace", []), entry]
    current_state["safety_flag"] = False
    current_state = await _maybe_medium_acknowledge(escalate_fn, current_state, flag)
    return current_state  # type: ignore[return-value]


# Vong 3 (phan hoi review 2026-08-12) - PM quyet dinh 4 cau hoi chinh sach
# (a/b/c/d, chatbot-rag-design.md muc 10 #26):
#   (a) chi 2/5 category: self_harm + clinical_symptom (khong phai moi
#       category Trung binh - wrong_drug/dosage_risk o muc Trung binh de
#       chi la nham lan nho, escalate ngay se qua nhay, dung y kickoff lo
#       ngai "bao dong gia").
#   (b) CHI kenh "family" nhan tin nhan chu dong - bac si KHONG duoc chu
#       dong bao, chi xem duoc qua bang Escalation/trace khi tra cuu (da co
#       san, khong can them gi).
#   (c) benh nhan CO nhan 1 cau ghi nhan nhe - khong im lang hoan toan.
#   (d) chap nhan floor theo category (_CATEGORY_LEVEL_FLOOR, safety.py)
#       lam tang so case bi escalate - uu tien khong bo sot hon la giam bao
#       dong gia cho 2 category da co bang chung dao dong that.
#
# SUA 2026-08-12 (phan hoi review lan 2) - BUG THAT phat hien: ban dau (a)
# va (c) bi GOP CHUNG 1 dieu kien (ca 2 chi chay khi category thuoc
# _MEDIUM_ESCALATE_CATEGORIES), khien 3/5 category Trung binh con lai
# (wrong_drug/dosage_risk/severe_reaction - ke ca wrong_drug vua duoc
# _CATEGORY_LEVEL_FLOOR nang len toi thieu Trung binh) IM LANG HOAN TOAN -
# quay lai dung bug rong-response da tung sua o vong 2, chi hep pham vi
# lai con 3/5 category thay vi ca 5. (c) la cau tra loi chung cho MOI
# "Trung bình" (dung y "bat ke (a)/(b)/(d) quyet the nao" da de xuat truoc
# do), (a) CHI gioi han pham vi ESCALATE - 2 dieu kien nay PHAI doc lap,
# khong dung chung 1 gate.
_MEDIUM_ESCALATE_CATEGORIES = frozenset({"self_harm", "clinical_symptom"})
_MEDIUM_ACKNOWLEDGMENT = "(Capy đã ghi nhận điều bạn vừa chia sẻ.)"


async def _maybe_medium_acknowledge(
    escalate_fn: EscalateFn | None, current_state: ConversationState, flag: SafetyFlag
) -> ConversationState:
    """KHONG cat luong chinh (khac _apply_redflag/is_redflag). 2 tac dung
    phu DOC LAP, xem ghi chu SUA o tren:
      - Ghep 1 cau ghi nhan nhe vao response - AP DUNG CHO MOI "Trung bình"
        (moi category, ca 5/5), khong chi 2 category duoc escalate.
      - Escalate kenh "family" - CHI 2 category trong _MEDIUM_ESCALATE_
        CATEGORIES (chinh sach (a), gioi han rieng, hep hon dieu kien tren)."""
    if flag.level != "Trung bình":
        return current_state

    if escalate_fn is not None and flag.llm_category in _MEDIUM_ESCALATE_CATEGORIES:
        reason = (
            f"Safety layer 'Trung bình' - category={flag.llm_category!r}, "
            f"llm_reasoning={flag.llm_reasoning!r}"
        )
        try:
            # Goi THANG escalate_fn cho DUNG 1 kenh "family" - KHONG qua
            # trigger_emergency_escalation() (ham do luon goi CA HAI kenh
            # cung luc qua asyncio.gather, khong chon rieng duoc 1 kenh).
            await escalate_fn(
                "family",
                current_state.get("patient_id", ""),
                current_state.get("dose_event_id"),
                "Trung bình",
                False,
                TRIGGER_SAFETY_REDFLAG,
                reason,
            )
        except Exception:  # noqa: BLE001 - best-effort, khong lam sap luong chinh (cung tinh than BR-6.3)
            pass

    existing_response = current_state.get("response") or ""
    current_state["response"] = (
        f"{existing_response} {_MEDIUM_ACKNOWLEDGMENT}".strip() if existing_response else _MEDIUM_ACKNOWLEDGMENT
    )
    return current_state


async def _maybe_escalate(
    escalate_fn: EscalateFn | None, current_state: ConversationState, flag: SafetyFlag
) -> EscalationOutcome | None:
    if escalate_fn is None:
        return None
    reason = (
        f"Safety layer redflag - level={flag.level!r}, nhom_keyword={flag.matched_group!r}, "
        f"tu khoa={flag.matched_keyword!r}, llm_category={flag.llm_category!r}, "
        f"llm_reasoning={flag.llm_reasoning!r}, phat hien qua {flag.source}"
    )
    return await trigger_emergency_escalation(
        escalate_fn,
        current_state.get("patient_id", ""),
        current_state.get("dose_event_id"),
        severity="Nguy hiểm",
        urgent=True,
        trigger=TRIGGER_SAFETY_REDFLAG,
        reason=reason,
    )


async def default_safety_check(utterance: str) -> SafetyFlag:
    """Wrapper mac dinh - dung ngay, khong delay gia lap (cho production).
    Test dung safety_check rieng co delay co kiem soat (xem test_orchestrator.py).

    SUA vong 3, muc 3 (2026-08-12): truoc day goi check_safety(utterance)
    KHONG kem llm_classifier - dieu tra kien truc (vong-3-investigation.md
    muc 2) xac nhan day CHINH LA ly do production khong co lop LLM nao ca.
    Gio wire classify_safety_llm (backend/services/classification.py) - LLM
    la lop CHINH tu day, chay trong executor (chay dong bo/blocking, dua ra
    thread pool de KHONG block event loop - check_safety() ban than no la
    ham dong bo, phu hop voi cach asyncio.to_thread duoc thiet ke)."""
    import asyncio

    from backend.services.classification import classify_safety_llm
    from backend.services.safety import check_safety

    return await asyncio.to_thread(check_safety, utterance, classify_safety_llm)
