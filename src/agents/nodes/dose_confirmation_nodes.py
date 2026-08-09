"""3 node cua nhanh "Xac nhan lieu" (chatbot-rag-design.md muc 8, nhanh
CLASSIFY -> SEVERITY -> LEVEL) - Phase 5b, bo sung sau khi phat hien Phase 5
kickoff prompt liet thieu nhanh nay (chi liet 4 node cua nhanh drug_info).

Day la 1 danh sach node RIENG (dose_confirmation), doc lap voi 4 node cua
nhanh drug_info trong conversation_nodes.py - ca 2 nhanh deu chay qua CUNG 1
`run_conversation()` (src/agents/orchestrator.py, khong doi), chi khac
`nodes=[...]` truyen vao. Viec CHON nhanh nao (dua theo ket qua intent) la
trach nhiem cua Phase 6 (FastAPI routing/graph.py), chua lam o day.

CLASSIFY: phan loai 4 nhan (FEAT-005). confidence < 0.7 -> KHONG doan, hoi
lai (chatbot-rag-design.md muc 8: "confidence < 0.7 -> hoi lai").
SEVERITY: FEAT-007, chi chay khi CLASSIFY cho ra MISSED/DELAYED/SIDE_EFFECT.
LEVEL: 3 nhanh hanh dong (business-rules.md §3) - Nhe/Trung binh/Nguy hiem.
"""

from __future__ import annotations

import time
from typing import Protocol

from sqlalchemy.orm import Session

from src.agents.nodes.conversation_nodes import _append_trace
from src.agents.state import ConversationState
from src.agents.tools.personal_tools import tra_cuu_dose_event_ca_nhan
from src.services.escalation import (
    MISSED_DOSE_OVERLAY_MESSAGE,
    SIDE_EFFECT_OVERLAY_MESSAGE,
    TRIGGER_MISSED_DOSE,
    TRIGGER_SIDE_EFFECT,
    EscalateFn,
    trigger_emergency_escalation,
)
from src.services.retrieval import get_chunks_by_drug_id
from src.services.severity import combine_severity

CLASSIFY_CONFIDENCE_THRESHOLD = 0.7
ASK_AGAIN_MESSAGE = (
    "Mình chưa chắc bạn muốn xác nhận điều gì — bạn có thể nói rõ hơn không "
    "(đã uống rồi, quên uống, uống trễ, hay đang có tác dụng phụ)?"
)

# BR-3.6 + muc 8: nguon RAG chinh cho SEVERITY la CA 2 chunk cong_dung (chua
# field "tac_dung" - cong dung chung cua thuoc) LAN tac_dung_phu (rui ro khi
# dung) gop lai, dua vao classify_fn 1 lan (quyet dinh 2026-08-08, xem
# thao luan truoc khi code Phase 5b - van ban muc 8 chi ghi "tac_dung" nhung
# mapping thuc te (muc 3.1) la field_group "cong_dung", con "tac_dung_phu"
# (rui ro) moi la nguon hop ly hon rieng le - gop ca 2 de khong phai chon 1).
SEVERITY_SOURCE_FIELD_GROUPS = ("cong_dung", "tac_dung_phu")

LOW_ACTION = "log_and_monitor_48h"
MEDIUM_ACTION = "escalate_family_and_doctor"
HIGH_ACTION = "escalate_emergency"

# TODO [CẦN CHỐT — noi dung chua duyet chinh thuc]: phat hien 2026-08-08 qua
# 1 lan chay that qua /api/v1/chat - CA 3 nhanh duoi day (TAKEN, Nhẹ, Trung
# bình) truoc do KHONG set `response` gi ca, khien benh nhan nhan ve chuoi
# rong sau khi bao "toi chua uong lieu" - im lang tuyet doi, khong phan biet
# duoc voi app loi/crash (te hon ca placeholder xau). KHAC voi
# MISSED_DOSE_OVERLAY_MESSAGE/SIDE_EFFECT_OVERLAY_MESSAGE (src/services/
# escalation.py) - do la noi dung MAN HINH KHUNG HOANG, can PM+mentor duyet
# ky vi rui ro tam ly cao; 3 cau duoi day chi la XAC NHAN DA GHI NHAN, rui ro
# chon sai cau chu THAP hon nhieu - van danh dau CAN CHOT (chua phai final
# chinh thuc) nhung KHONG chan viec co 1 phan hoi thay vi im lang.
TAKEN_RESPONSE = "Đã ghi nhận bạn đã uống thuốc lần này. Cảm ơn bạn đã xác nhận!"
LOW_ACTION_RESPONSE = (
    "Đã ghi nhận thông tin của bạn. Đây là mức độ nhẹ, hệ thống sẽ tiếp tục theo dõi trong 48 giờ tới."
)
MEDIUM_ACTION_RESPONSE = "Đã ghi nhận thông tin của bạn. Người thân và bác sĩ đã được thông báo để theo dõi thêm."


class DoseClassifyFn(Protocol):
    def __call__(self, utterance: str) -> tuple[str, float]: ...


class SeverityClassifyFn(Protocol):
    def __call__(self, combined_text: str) -> str | None: ...


def build_classify_node(classify_fn: DoseClassifyFn, model_name: str = "gpt-4o-mini"):
    """FEAT-005. Ghi ca `raw_result` (nhan LLM thuc te tra ve) LAN `result`
    (None neu confidence thap - khong dung nhan nay) vao trace - audit duoc
    ca truong hop he thong chon KHONG hanh dong theo phan loai cua LLM.

    Tu bao ve theo `state["intent"]` (Phase 6, None duoc chap nhan de tuong
    thich test goi thang node - xem conversation_nodes.py cho cung idiom) -
    tranh ton 1 lan goi LLM cho utterance khong phai dose_confirmation."""

    async def node(state: ConversationState) -> dict:
        if state.get("intent") not in (None, "dose_confirmation"):
            entry = {
                "step": "dose_classification",
                "skipped": True,
                "reason": f"intent={state.get('intent')!r}",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        label, confidence = classify_fn(state["utterance"])
        duration_ms = (time.monotonic() - t0) * 1000

        low_confidence = confidence < CLASSIFY_CONFIDENCE_THRESHOLD
        entry = {
            "step": "dose_classification",
            "model": model_name,
            "raw_result": label,
            "result": None if low_confidence else label,
            "confidence": confidence,
            "low_confidence": low_confidence,
            "duration_ms": duration_ms,
        }
        result: dict = {
            "classification": None if low_confidence else label,
            "classification_confidence": confidence,
            "trace": _append_trace(state, entry),
        }
        if low_confidence:
            result["response"] = ASK_AGAIN_MESSAGE
        return result

    return node


def build_severity_node(db: Session, classify_severity_fn: SeverityClassifyFn):
    """FEAT-007. Bo qua (khong chay danh gia) neu CLASSIFY khong cho ra 1
    trong 3 nhan can danh gia muc do - bao gom ca truong hop TAKEN (khong can
    danh gia) LAN truong hop confidence thap (CLASSIFY da hoi lai, chua biet
    nhan that). `drug_id` lay tu `dose_event.expected_items[0]` CUA DUNG
    patient_id (qua tra_cuu_dose_event_ca_nhan) - KHONG dung `rag_results`
    cua nhanh drug_info (2 nhanh doc lap, co the rong o day)."""

    async def node(state: ConversationState) -> dict:
        classification = state.get("classification")
        if classification not in ("MISSED", "DELAYED", "SIDE_EFFECT"):
            entry = {
                "step": "severity_assessment",
                "skipped": True,
                "reason": f"classification={classification!r} khong can danh gia muc do",
                "duration_ms": 0.0,
            }
            return {"trace": _append_trace(state, entry)}

        t0 = time.monotonic()
        dose_event_id = state.get("dose_event_id")
        dose_event = (
            tra_cuu_dose_event_ca_nhan(db, state["patient_id"], dose_event_id) if dose_event_id else None
        )
        expected_items = (dose_event or {}).get("expected_items") or []
        drug_id = expected_items[0]["drug_id"] if expected_items else None

        chunks = get_chunks_by_drug_id(db, drug_id) if drug_id else []
        relevant = [c for c in chunks if c.field_group in SEVERITY_SOURCE_FIELD_GROUPS]
        combined_text = "\n\n".join(c.noi_dung for c in relevant)

        # BR-3.2: khong xac dinh duoc thuoc/khong co chunk nao lien quan ->
        # an toan truoc, fallback toi thieu la "Trung bình" (khong suy dien
        # "Nhẹ" tu viec thieu du lieu).
        fallback_severity = relevant[0].muc_nghiem_trong if relevant else "Trung bình"
        rag_severity = classify_severity_fn(combined_text) if combined_text else None
        final_severity = combine_severity(rag_severity, fallback_severity)
        duration_ms = (time.monotonic() - t0) * 1000

        entry = {
            "step": "severity_assessment",
            "drug_id": drug_id,
            "source_field_groups": list(SEVERITY_SOURCE_FIELD_GROUPS),
            "rag_severity": rag_severity,
            "fallback_severity": fallback_severity,
            "result": final_severity,
            "duration_ms": duration_ms,
        }
        return {"severity": final_severity, "trace": _append_trace(state, entry)}

    return node


def build_level_action_node(escalate_fn: EscalateFn):
    """LEVEL -> 3 nhanh hanh dong (business-rules.md §3). Trung binh/Nguy
    hiem goi `trigger_emergency_escalation()` (src/services/escalation.py -
    DUNG CHUNG voi duong HIGH tu safety_layer redflag, xem orchestrator.py)
    de goi `escalate_fn` cho family VA doctor SONG SONG (khong xep hang -
    BR-3.5 "gui thang ca nguoi than va bac si"), do `duration_ms` thuc te de
    kiem tra kha nang dat SLA (<2' cho Nguy hiem) - o day chi la mo phong
    (escalate_fn injectable), khong phai do tren ha tang push that."""

    async def node(state: ConversationState) -> dict:
        classification = state.get("classification")
        severity = state.get("severity")

        if classification == "TAKEN":
            entry = {"step": "level_action", "action": "log_only", "duration_ms": 0.0}
            return {"response": TAKEN_RESPONSE, "trace": _append_trace(state, entry)}

        if severity is None:
            # Hoac dang cho lam ro (CLASSIFY confidence thap - da hoi lai o
            # buoc truoc, response da duoc set boi CLASSIFY roi), hoac nhanh
            # nay khong ap dung (intent khac, response da duoc set boi node
            # cua nhanh do roi) - khong hanh dong, KHONG set response o day
            # (se ghi de mat response da co tu buoc truoc).
            entry = {"step": "level_action", "action": "none", "reason": "no_severity", "duration_ms": 0.0}
            return {"trace": _append_trace(state, entry)}

        if severity == "Nhẹ":
            entry = {"step": "level_action", "action": LOW_ACTION, "duration_ms": 0.0}
            return {"response": LOW_ACTION_RESPONSE, "trace": _append_trace(state, entry)}

        urgent = severity == "Nguy hiểm"
        action = HIGH_ACTION if urgent else MEDIUM_ACTION
        trigger = TRIGGER_SIDE_EFFECT if classification == "SIDE_EFFECT" else TRIGGER_MISSED_DOSE
        reason = f"SEVERITY={severity} tu classification={classification!r} (BR-3.1-3.6)"

        t0 = time.monotonic()
        outcome = await trigger_emergency_escalation(
            escalate_fn,
            state["patient_id"],
            state.get("dose_event_id"),
            severity,
            urgent,
            trigger,
            reason,
        )
        duration_ms = (time.monotonic() - t0) * 1000

        entry = {
            "step": "level_action",
            "action": action,
            # CHI liet ke target THUC SU thanh cong, khong phai "da goi" -
            # escalation_failed ghi ro target nao that bai + vi sao (phat
            # hien 2026-08-08: escalate cap cuu can biet chinh xac kenh nao
            # loi, khong duoc gop chung thanh 1 trang thai "da escalate").
            "escalated_to": outcome.succeeded,
            "escalation_failed": outcome.failed,
            "parallel": True,
            "duration_ms": duration_ms,
        }
        result: dict = {"trace": _append_trace(state, entry)}
        # trigger da tinh o tren: TRIGGER_SIDE_EFFECT hoac TRIGGER_MISSED_DOSE
        # (chatbot-rag-design.md muc 7.1) - map thang sang overlay tuong ung.
        urgent_message = (
            SIDE_EFFECT_OVERLAY_MESSAGE if trigger == TRIGGER_SIDE_EFFECT else MISSED_DOSE_OVERLAY_MESSAGE
        )
        result["response"] = urgent_message if urgent else MEDIUM_ACTION_RESPONSE
        return result

    return node
