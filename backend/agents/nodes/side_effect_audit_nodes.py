"""Vong 4, muc 4 - audit match trieu chung voi `tac_dung_phu`.

Node nay chi ghi trace cho bac si, khong dat `response` va khong ket luan
nguyen nhan cho benh nhan. Ngoai SIDE_EFFECT, callback redflag dung chung
duoc orchestrator goi truoc overlay de khong mat audit khi luong bi cat ngang.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.agents.nodes.conversation_nodes import _append_trace
from backend.agents.state import ConversationState
from backend.agents.tools.drug_info_tool import EmbedFn
from backend.agents.tools.personal_tools import list_active_prescription_drug_items
from backend.config import get_settings
from backend.services.drug_knowledge.v2_agent import SideEffectMatchResult, search_active_adverse_effects
from backend.services.safety import SafetyFlag

SideEffectMatchFn = Callable[[str, str], bool]
ActivePrescriptionItemsFn = Callable[[Session, str], list[dict]]
SideEffectSearchFn = Callable[[Session, str, list[str], EmbedFn], list[SideEffectMatchResult]]


def _default_side_effect_match(_utterance: str, _side_effect_content: str) -> bool:
    """Fail-closed default cho call site/test chua wire LLM production."""
    return False


def _is_symptom_redflag(flag: SafetyFlag) -> bool:
    return flag.matched_group == "clinical" or flag.llm_category in {"clinical_symptom", "severe_reaction"}


def _match_message(result: SideEffectMatchResult) -> str:
    return f"Có thể liên quan tới tác dụng phụ của {result.ten_thuoc} (độ khớp {result.score:.0%})"


def _audit_side_effect_matches(
    state: ConversationState,
    db: Session,
    embed_query: EmbedFn,
    match_fn: SideEffectMatchFn,
    trigger: str,
    list_active_items_fn: ActivePrescriptionItemsFn,
    search_fn: SideEffectSearchFn,
) -> dict:
    t0 = time.monotonic()
    active_items = list_active_items_fn(db, state["patient_id"])
    active_drug_ids = [item["drug_id"] for item in active_items]
    raw_candidates = search_fn(db, state["utterance"], active_drug_ids, embed_query) if active_drug_ids else []
    candidate_threshold = get_settings().side_effect_candidate_threshold
    candidates = [candidate for candidate in raw_candidates if candidate.score >= candidate_threshold]

    matches: list[dict] = []
    matcher_failures: list[str] = []
    for candidate in candidates:
        try:
            is_match = match_fn(state["utterance"], candidate.noi_dung)
        except Exception:  # noqa: BLE001 - audit loi khong duoc chan safety/response
            matcher_failures.append(candidate.drug_id)
            continue
        if is_match:
            matches.append(
                {
                    "drug_id": candidate.drug_id,
                    "ten_thuoc": candidate.ten_thuoc,
                    "score": candidate.score,
                    "message": _match_message(candidate),
                }
            )

    duration_ms = (time.monotonic() - t0) * 1000
    entry = {
        "step": "side_effect_audit",
        "trigger": trigger,
        "source_field_groups": ["tac_dung_phu"],
        "active_drug_ids": active_drug_ids,
        "candidate_threshold": candidate_threshold,
        "raw_candidate_count": len(raw_candidates),
        "candidate_count": len(candidates),
        "knowledge_backend": get_settings().drug_knowledge_backend,
        "matches": matches,
        "result": "matched" if matches else ("unavailable" if matcher_failures else "không tìm thấy liên hệ rõ ràng"),
        "matcher_failures": matcher_failures,
        "duration_ms": duration_ms,
    }
    return {"trace": _append_trace(state, entry)}


def build_side_effect_audit_node(
    db: Session,
    embed_query: EmbedFn,
    match_fn: SideEffectMatchFn = _default_side_effect_match,
    list_active_items_fn: ActivePrescriptionItemsFn = list_active_prescription_drug_items,
    search_fn: SideEffectSearchFn = search_active_adverse_effects,
):
    """Chay sau CLASSIFY chi khi nhan `SIDE_EFFECT`; khong sua response."""

    async def node(state: ConversationState) -> dict:
        if state.get("classification") != "SIDE_EFFECT":
            entry = {
                "step": "side_effect_audit",
                "skipped": True,
                "reason": f"classification={state.get('classification')!r}",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}
        return _audit_side_effect_matches(
            state, db, embed_query, match_fn, "dose_classification", list_active_items_fn, search_fn
        )

    return node


def build_redflag_side_effect_audit(
    db: Session,
    embed_query: EmbedFn,
    match_fn: SideEffectMatchFn = _default_side_effect_match,
    list_active_items_fn: ActivePrescriptionItemsFn = list_active_prescription_drug_items,
    search_fn: SideEffectSearchFn = search_active_adverse_effects,
):
    """Callback cho orchestrator, chi audit redflag co trieu chung."""

    async def audit(state: ConversationState, flag: SafetyFlag) -> dict:
        if not _is_symptom_redflag(flag):
            entry = {
                "step": "side_effect_audit",
                "skipped": True,
                "reason": "redflag_không_phải_triệu_chứng",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}
        return _audit_side_effect_matches(
            state, db, embed_query, match_fn, "safety_redflag", list_active_items_fn, search_fn
        )

    return audit
