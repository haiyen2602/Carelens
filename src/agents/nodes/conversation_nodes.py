"""4 node chinh cua luong hoi thoai (build-kickoff-prompt.md Phase 5):
intent_classification, retrieval, prescription_lookup, answer_generation.

Moi node la 1 factory tra ve async function - nhan dependency (LLM classify/
generate, embed_fn, db session) qua tham so thay vi import cung, de test
duoc ma khong can goi OpenAI/Postgres that (dependency injection, giong cach
Phase 4 tach fuse_rrf() thuan khoi hybrid_search() co I/O).

Moi node ghi DUNG 1 entry vao state["trace"] theo dinh dang muc 5.2
(chatbot-rag-design.md) - step, model (neu co), input rut gon, ket qua,
confidence (neu co), duration_ms.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from sqlalchemy.orm import Session

from src.agents.state import ConversationState
from src.agents.tools.drug_info_tool import EmbedFn, tra_cuu_thuoc_chung
from src.agents.tools.personal_tools import tra_cuu_don_thuoc_ca_nhan

CAVEAT_LIEU_DUNG = "Đây là liều khuyến cáo chung theo nhãn thuốc, liều thực tế của bạn có thể khác theo chỉ định của bác sĩ."
CAVEAT_THOI_DIEM_MISSING = "Thời điểm dùng cụ thể cần theo chỉ định của bác sĩ."
NO_SOURCE_MESSAGE = "Xin lỗi, tôi không có thông tin đáng tin cậy về câu hỏi này. Vui lòng hỏi bác sĩ."


def _append_trace(state: ConversationState, entry: dict) -> list[dict]:
    return [*state.get("trace", []), entry]


class IntentClassifyFn(Protocol):
    def __call__(self, utterance: str) -> tuple[str, float]: ...


class AnswerGenerateFn(Protocol):
    def __call__(self, utterance: str, rag_results: list) -> str: ...


def build_intent_classification_node(classify_fn: IntentClassifyFn, model_name: str = "gpt-4o-mini"):
    async def node(state: ConversationState) -> dict:
        t0 = time.monotonic()
        intent, confidence = classify_fn(state["utterance"])
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


def build_retrieval_node(db: Session, embed_query: EmbedFn):
    async def node(state: ConversationState) -> dict:
        t0 = time.monotonic()
        outcome = tra_cuu_thuoc_chung(db, state["utterance"], embed_query)
        duration_ms = (time.monotonic() - t0) * 1000
        entry = {
            "step": "retrieval",
            "mode": "hybrid_search",
            "query": state["utterance"],
            "no_source_found": outcome.no_source_found,
            "result_count": len(outcome.results),
            "duration_ms": duration_ms,
        }
        return {"rag_results": outcome.results, "trace": _append_trace(state, entry)}

    return node


def build_prescription_lookup_node(db: Session):
    async def node(state: ConversationState) -> dict:
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


def build_answer_generation_node(generate_fn: AnswerGenerateFn, model_name: str = "gpt-4o-mini"):
    """2 caveat TACH RIENG thanh 2 boolean khac nhau trong trace - KHONG gop
    chung 1 field (chot lai truoc khi code, xem lich su thao luan Phase 4/5).
    Ca 2 deu duoc CODE chen tuong minh (khong dua vao system prompt cua LLM
    tu nho chen) - dam bao 100% nhat quan, dung tinh than "moi hanh dong AI
    deu truy vet duoc"."""

    async def node(state: ConversationState) -> dict:
        t0 = time.monotonic()
        rag_results = state.get("rag_results") or []
        base_answer = generate_fn(state["utterance"], rag_results)

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


def build_refuse_node():
    """NOSRC -> REFUSE (BR-7.3, muc 4.4): khong dua chunk diem thap/rong vao
    prompt, tra loi tu choi co dinh."""

    async def node(state: ConversationState) -> dict:
        entry = {"step": "refuse", "reason": "no_source_found", "duration_ms": 0.0}
        return {"response": NO_SOURCE_MESSAGE, "trace": _append_trace(state, entry)}

    return node


NodeFn = Callable[[ConversationState], "dict"]
