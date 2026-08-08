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
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from src.agents.state import ConversationState
from src.services.safety import SafetyFlag

SafetyCheckFn = Callable[[str], Awaitable[SafetyFlag]]
NodeFn = Callable[[ConversationState], Awaitable[dict]]

HIGH_OVERLAY_MESSAGE = (
    "⚠️ Đây có thể là tình huống khẩn cấp. Vui lòng liên hệ cấp cứu 115 ngay. "
    "Người thân và bác sĩ của bạn đã được thông báo."
)


def _apply_redflag(state: ConversationState, flag: SafetyFlag, interrupted_after_step: str | None) -> ConversationState:
    entry = {
        "step": "safety_layer",
        "keyword_hit": flag.source in ("keyword", "keyword+llm"),
        "llm_flag": flag.source in ("llm", "keyword+llm"),
        "matched_group": flag.matched_group,
        "interrupted_after_step": interrupted_after_step,
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
) -> ConversationState:
    """Chay `nodes` tuan tu, song song voi `safety_check(state["utterance"])`
    chay nhu 1 asyncio.Task doc lap ngay tu dau. Kiem tra task nay giua moi
    cap node lien tiep - redflag o bat ky diem kiem tra nao deu dung luong
    chinh ngay, ghi ro trace dung sau buoc nao (khong phai trace rong hay
    gia vo chay het binh thuong)."""
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
                return _apply_redflag(current_state, flag, last_completed_step)

        update = await node(current_state)  # type: ignore[arg-type]
        current_state = {**current_state, **update}
        if update.get("trace"):
            last_completed_step = update["trace"][-1].get("step")

    # Kiem tra lan cuoi sau khi het node - redflag co the toi dung luc node
    # cuoi dang chay va xong ngay sau do.
    flag = await safety_task
    if flag.is_redflag:
        return _apply_redflag(current_state, flag, last_completed_step)

    entry = {"step": "safety_layer", "keyword_hit": False, "llm_flag": False, "matched_group": None}
    current_state["trace"] = [*current_state.get("trace", []), entry]
    current_state["safety_flag"] = False
    return current_state  # type: ignore[return-value]


async def default_safety_check(utterance: str) -> SafetyFlag:
    """Wrapper mac dinh - dung ngay, khong delay gia lap (cho production).
    Test dung safety_check rieng co delay co kiem soat (xem test_orchestrator.py)."""
    from src.services.safety import check_safety

    return check_safety(utterance)