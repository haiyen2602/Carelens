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

HIGH_OVERLAY_MESSAGE va viec goi escalate_fn deu lay tu
src/services/escalation.py - DUNG CHUNG voi duong HIGH con lai (SEVERITY ->
LEVEL = "Nguy hiểm", src/agents/nodes/dose_confirmation_nodes.py). Khong
duoc dinh nghia rieng o day (phat hien 2026-08-08: truoc do file nay tu dinh
nghia overlay message rieng va KHONG he goi escalate_fn nao - safety_layer
redflag chi set response/severity, chua bao gio thuc su bao nguoi than/bac
si, du BR-3.5 yeu cau ca 2 duong HIGH deu phai lam viec do)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from src.agents.state import ConversationState
from src.services.escalation import (
    HIGH_OVERLAY_MESSAGE,
    TRIGGER_SAFETY_REDFLAG,
    EscalateFn,
    trigger_emergency_escalation,
)
from src.services.safety import SafetyFlag

SafetyCheckFn = Callable[[str], Awaitable[SafetyFlag]]
NodeFn = Callable[[ConversationState], Awaitable[dict]]

__all__ = ["HIGH_OVERLAY_MESSAGE", "run_conversation", "default_safety_check"]


def _apply_redflag(
    state: ConversationState, flag: SafetyFlag, interrupted_after_step: str | None, escalated: bool
) -> ConversationState:
    entry = {
        "step": "safety_layer",
        "keyword_hit": flag.source in ("keyword", "keyword+llm"),
        "llm_flag": flag.source in ("llm", "keyword+llm"),
        "matched_group": flag.matched_group,
        "interrupted_after_step": interrupted_after_step,
        "escalated_to": ["family", "doctor"] if escalated else [],
    }
    trace = [*state.get("trace", []), entry]
    return {
        **state,
        "safety_flag": True,
        "severity": "Nguy hiểm",
        "response": HIGH_OVERLAY_MESSAGE,
        "trace": trace,
    }


async def run_conversation(
    state: ConversationState,
    nodes: list[NodeFn],
    safety_check: SafetyCheckFn,
    escalate_fn: EscalateFn | None = None,
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
                escalated = await _maybe_escalate(escalate_fn, current_state, flag)
                return _apply_redflag(current_state, flag, last_completed_step, escalated)

        update = await node(current_state)  # type: ignore[arg-type]
        current_state = {**current_state, **update}
        if update.get("trace"):
            last_completed_step = update["trace"][-1].get("step")

    # Kiem tra lan cuoi sau khi het node - redflag co the toi dung luc node
    # cuoi dang chay va xong ngay sau do.
    flag = await safety_task
    if flag.is_redflag:
        escalated = await _maybe_escalate(escalate_fn, current_state, flag)
        return _apply_redflag(current_state, flag, last_completed_step, escalated)

    entry = {"step": "safety_layer", "keyword_hit": False, "llm_flag": False, "matched_group": None}
    current_state["trace"] = [*current_state.get("trace", []), entry]
    current_state["safety_flag"] = False
    return current_state  # type: ignore[return-value]


async def _maybe_escalate(escalate_fn: EscalateFn | None, current_state: ConversationState, flag: SafetyFlag) -> bool:
    if escalate_fn is None:
        return False
    reason = (
        f"Safety layer redflag - nhom={flag.matched_group!r}, tu khoa/nguon={flag.matched_keyword!r}, "
        f"phat hien qua {flag.source}"
    )
    await trigger_emergency_escalation(
        escalate_fn,
        current_state.get("patient_id", ""),
        current_state.get("dose_event_id"),
        severity="Nguy hiểm",
        urgent=True,
        trigger=TRIGGER_SAFETY_REDFLAG,
        reason=reason,
    )
    return True


async def default_safety_check(utterance: str) -> SafetyFlag:
    """Wrapper mac dinh - dung ngay, khong delay gia lap (cho production).
    Test dung safety_check rieng co delay co kiem soat (xem test_orchestrator.py)."""
    from src.services.safety import check_safety

    return check_safety(utterance)
