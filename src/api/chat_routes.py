"""POST /api/v1/chat (api-contracts.md §4, chat-api) - Phase 6. Chay
LangGraph agent (Phase 5/5b) theo 2 giai doan CUNG 1 patient utterance:

  1. intent_classification (1 node) - xac dinh utterance thuoc nhanh nao
  2. TOAN BO cac node con lai cua CA 3 nhanh (drug_info, today_schedule,
     dose_confirmation), MOI node TU BAO VE theo `state["intent"]`
     (conversation_nodes.py/dose_confirmation_nodes.py) - khong dung 1
     danh sach rieng cho tung intent, tranh phai sua orchestrator.py de ho
     tro dieu phoi dong (xem thao luan kickoff Phase 6: giu nguyen ranh gioi
     kiem tra an toan giua TUNG node da kiem chung ky o Phase 5, khong gop
     nhieu buoc thanh 1 "node" mo).

`escalate_fn` LUON la ham that (build_db_escalate_fn(db), khong injectable
rieng) - loai bo hoan toan rui ro "quen wire escalate_fn" ma
build-kickoff-prompt.md Phase 6 da ghi lai can kiem tra (khong con duong
nao goi run_conversation() ma thieu escalate_fn tu route nay)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.agents.nodes.conversation_nodes import (
    build_answer_generation_node,
    build_intent_classification_node,
    build_prescription_lookup_node,
    build_retrieval_node,
    build_today_schedule_node,
)
from src.agents.nodes.dose_confirmation_nodes import (
    build_classify_node,
    build_level_action_node,
    build_severity_node,
)
from src.agents.orchestrator import run_conversation
from src.agents.state import ConversationState
from src.api.chat_deps import ChatServices, get_chat_services
from src.db.base import get_db
from src.db.models import AuditLog
from src.models.schemas import ClassificationOut, ConversationChatRequest, ConversationChatResponse, SourceOut
from src.services.escalation import build_db_escalate_fn
from src.services.severity import SEVERITY_VI_TO_EN

chat_router = APIRouter()


@chat_router.post("/chat", response_model=ConversationChatResponse)
async def chat(
    request: ConversationChatRequest,
    db: Session = Depends(get_db),
    services: ChatServices = Depends(get_chat_services),
) -> ConversationChatResponse:
    t0 = time.monotonic()
    escalate_fn = build_db_escalate_fn(db)

    initial_state: ConversationState = {
        "patient_id": request.patient_id,
        "dose_event_id": request.dose_id,
        "utterance": request.message,
        "trace": [],
    }

    # Giai doan 1: chi intent_classification. Neu redflag toi ngay o day
    # (truoc ca khi biet intent), safety_flag=True va dung luon - khong
    # chay giai doan 2 (dung y BR-3.3: cat ngang bat ke dang o dau).
    stage1 = await run_conversation(
        initial_state,
        nodes=[build_intent_classification_node(services.classify_intent)],
        safety_check=services.safety_check,
        escalate_fn=escalate_fn,
    )

    if stage1.get("safety_flag"):
        final_state = stage1
    else:
        # TOAN BO node con lai cua CA 3 nhanh - moi node tu quyet co chay
        # hay khong dua vao state["intent"]/state["classification"]/
        # state["severity"] da co (xem docstring o dau file).
        remaining_nodes = [
            build_retrieval_node(db, services.embed_query),
            build_prescription_lookup_node(db),
            build_answer_generation_node(services.generate_answer),
            build_today_schedule_node(db),
            build_classify_node(services.classify_dose),
            build_severity_node(db, services.classify_severity),
            build_level_action_node(escalate_fn),
        ]
        final_state = await run_conversation(
            stage1,
            nodes=remaining_nodes,
            safety_check=services.safety_check,
            escalate_fn=escalate_fn,
        )

    total_duration_ms = (time.monotonic() - t0) * 1000
    _persist_audit_log(db, request, final_state, total_duration_ms)

    return _to_response(final_state)


def _persist_audit_log(
    db: Session, request: ConversationChatRequest, final_state: ConversationState, total_duration_ms: float
) -> None:
    """AuditLogDTO (chatbot-rag-design.md muc 5.2) - APPEND-ONLY, moi luot
    xu ly 1 dong, ke ca nhanh REFUSE/redflag HIGH (khong co nhanh nao bo sot
    trace - yeu cau ro trong build-kickoff-prompt.md Phase 6)."""
    audit = AuditLog(
        patient_id=request.patient_id,
        dose_event_id=request.dose_id,
        utterance=request.message,
        trace=final_state.get("trace", []),
        final_response=final_state.get("response", ""),
        total_duration_ms=total_duration_ms,
    )
    db.add(audit)
    db.commit()


def _to_response(state: ConversationState) -> ConversationChatResponse:
    classification = None
    if state.get("classification") is not None:
        classification = ClassificationOut(
            label=state["classification"],
            secondary_labels=[],  # chua lam multi-label classification (xem schemas.py)
            confidence=state.get("classification_confidence") or 0.0,
        )

    # needs_clarification: CLASSIFY confidence < 0.7 -> da hoi lai thay vi
    # doan (dose_confirmation_nodes.py) - doc lai tu trace, khong them field
    # rieng vao ConversationState (giu schema muc 9 nhu da chot).
    needs_clarification = any(
        e.get("step") == "dose_classification" and e.get("low_confidence") for e in state.get("trace", [])
    )

    severity_vi = state.get("severity")
    severity_en = SEVERITY_VI_TO_EN.get(severity_vi) if severity_vi else None

    sources = [SourceOut(drug_id=r.drug_id, field=r.field_group) for r in state.get("rag_results") or []]

    # QUAN TRONG: safety_flag noi BAN GIAO (contract) nghia la "FE bat buoc
    # hien overlay cap cuu" (api-contracts.md §4) - RONG HON
    # state["safety_flag"] noi bo (chi True khi CHINH safety_layer
    # keyword/LLM redflag kich hoat, BR-3.3). BR-3.5 noi HIGH tu CA 2 nguon
    # (safety_layer LAN SEVERITY->LEVEL) deu phai overlay ngay - neu chi map
    # thang state["safety_flag"], benh nhan bi SEVERITY danh gia la "Nguy
    # hiem" (vd bo lieu thuoc tim mach) se KHONG duoc FE hien overlay cap
    # cuu, sai BR-3.5. Dung severity_en == "HIGH" de gop ca 2 nguon.
    safety_flag = severity_en == "HIGH"

    return ConversationChatResponse(
        reply=state.get("response", ""),
        classification=classification,
        severity=severity_en,
        safety_flag=safety_flag,
        needs_clarification=needs_clarification,
        sources=sources,
    )
