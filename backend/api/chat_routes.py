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
nao goi run_conversation() ma thieu escalate_fn tu route nay).

TASK-010: Depends(get_current_user) - auth-api that (api-contracts.md §1),
thay rao tam require_internal_secret (chatbot-rag-design.md muc 10 #10) da
xoa khoi route nay. get_current_patient_id() gio nhan them CurrentUser de
doc patient_id tu JWT khi nguoi goi la role=patient (xem backend/api/security.py).

Vong 2 (chatbot-rag-design.md muc 12): input guardrail chay TRUOC ca
run_conversation() (chan injection som, khong de utterance doc hai toi duoc
intent_classification) - neu blocked, KHONG chay graph, tra loi tu choi
lich su, van ghi du audit. Output guardrail chay SAU khi co final_state,
TRUOC khi tra ve nguoi dung - co the redact/thay response, ghi vao audit
log DUNG response DA REDACT (khong luu ban goc co secret vao DB).

Vong 2 (chatbot-rag-design.md muc 11): NEU benh nhan dang co 1 pending_
drug_confirmation (bang DB rieng, song sot qua nhieu request/worker) - tin
nhan nay la REPLY xac nhan, KHONG phai cau hoi moi. Bo qua han giai doan 1
(intent_classification) trong truong hop nay - dat intent='drug_info'
THANG (da biet chac tu luot truoc), chay qua build_drug_confirmation_
reply_node roi TIEP TUC qua prescription_lookup/answer_generation NEU da
resolve xong drug_id trong luot nay. build_retrieval_node CU khong con
duoc dua vao danh sach node nua - thay bang build_drug_identity_
resolution_node (chi dung khi CAU HOI MOI, khong co pending nao)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.agents.nodes.conversation_nodes import (
    build_answer_generation_node,
    build_chat_history_query_node,
    build_greeting_node,
    build_intent_classification_node,
    build_prescription_lookup_node,
    build_today_schedule_node,
)
from backend.agents.nodes.dose_confirmation_nodes import (
    build_classify_node,
    build_level_action_node,
    build_severity_node,
)
from backend.agents.nodes.drug_confirmation_nodes import (
    build_drug_confirmation_reply_node,
    build_drug_identity_resolution_node,
)
from backend.agents.orchestrator import run_conversation
from backend.agents.state import ConversationState
from backend.agents.tools.chat_history_tool import (
    get_chat_history_for_display,
    hide_all_chat_messages,
    save_chat_message,
)
from backend.agents.tools.drug_confirmation_store import clear_pending_confirmation, get_pending_confirmation
from backend.api.chat_deps import ChatServices, get_chat_services
from backend.api.rate_limit import rate_limit_check
from backend.api.security import CurrentUser, get_current_patient_id, get_current_user
from backend.db.base import get_db
from backend.db.models import AuditLog
from backend.models.schemas import (
    ChatHistoryHideResponse,
    ChatHistoryRequest,
    ChatHistoryResponse,
    ChatMessageOut,
    ClassificationOut,
    ConversationChatRequest,
    ConversationChatResponse,
    SourceOut,
)
from backend.services.escalation import build_db_escalate_fn
from backend.services.guardrails import (
    INPUT_GUARDRAIL_REFUSAL_MESSAGE,
    check_input_guardrail,
    check_output_guardrail,
)
from backend.services.severity import SEVERITY_VI_TO_EN

chat_router = APIRouter()


@chat_router.post(
    "/chat",
    response_model=ConversationChatResponse,
    dependencies=[Depends(rate_limit_check)],
)
async def chat(
    request: ConversationChatRequest,
    db: Session = Depends(get_db),
    services: ChatServices = Depends(get_chat_services),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationChatResponse:
    t0 = time.monotonic()
    patient_id = get_current_patient_id(request, current_user)
    escalate_fn = build_db_escalate_fn(db)

    initial_state: ConversationState = {
        "patient_id": patient_id,
        "dose_event_id": request.dose_id,
        "utterance": request.message,
        "trace": [],
    }

    t_guard0 = time.monotonic()
    guardrail_result = check_input_guardrail(request.message)
    input_guardrail_duration_ms = (time.monotonic() - t_guard0) * 1000
    if guardrail_result.blocked:
        # KHONG chay run_conversation() - utterance nghi injection khong duoc
        # dua toi bat ky LLM call nao (ke ca intent_classification), chan
        # SOM nhat co the (muc 12.1).
        entry = {
            "step": "input_guardrail",
            "blocked": True,
            "category": guardrail_result.category,
            "matched_pattern": guardrail_result.matched_pattern,
            "duration_ms": input_guardrail_duration_ms,
        }
        final_state = {
            **initial_state,
            "response": INPUT_GUARDRAIL_REFUSAL_MESSAGE,
            "safety_flag": False,
            "trace": [entry],
        }
    else:
        pending = get_pending_confirmation(db, patient_id)
        if pending is not None:
            # Tin nhan nay la REPLY cho 1 cau hoi xac nhan dang cho (muc 11) -
            # KHONG chay intent_classification, da biet chac intent tu luot
            # truoc. Van chay qua run_conversation() (khong tu xay final_state
            # thang) de safety_layer VAN duoc rai song song tren tin nhan nay
            # (BR-3.3 - benh nhan co the noi trieu chung khan cap ngay trong
            # 1 cau tra loi xac nhan, khong duoc bo qua kiem tra nay).
            initial_state["intent"] = "drug_info"
            reply_nodes = [
                build_drug_confirmation_reply_node(db, services.embed_query, pending),
                build_prescription_lookup_node(db),
                build_answer_generation_node(services.generate_answer, db=db),
            ]
            final_state = await run_conversation(
                initial_state,
                nodes=reply_nodes,
                safety_check=services.safety_check,
                escalate_fn=escalate_fn,
            )
        else:
            # Giai doan 1: chi intent_classification. Neu redflag toi ngay o
            # day (truoc ca khi biet intent), safety_flag=True va dung luon -
            # khong chay giai doan 2 (dung y BR-3.3: cat ngang bat ke dang o dau).
            stage1 = await run_conversation(
                initial_state,
                nodes=[build_intent_classification_node(services.classify_intent, db=db)],
                safety_check=services.safety_check,
                escalate_fn=escalate_fn,
            )

            if stage1.get("safety_flag"):
                final_state = stage1
            else:
                # TOAN BO node con lai cua CA 3 nhanh - moi node tu quyet co
                # chay hay khong dua vao state["intent"]/state["classification"]/
                # state["severity"] da co (xem docstring o dau file).
                # build_drug_identity_resolution_node THAY build_retrieval_
                # node cu (muc 11) - hybrid search gio chi dung de tim ung
                # vien dua ra hoi xac nhan, khong con tra loi truc tiep.
                remaining_nodes = [
                    build_drug_identity_resolution_node(db, services.embed_query),
                    build_prescription_lookup_node(db),
                    build_answer_generation_node(services.generate_answer, db=db),
                    build_today_schedule_node(db),
                    build_classify_node(services.classify_dose),
                    build_severity_node(db, services.classify_severity),
                    build_level_action_node(escalate_fn),
                    build_greeting_node(db),
                    build_chat_history_query_node(db),
                ]
                final_state = await run_conversation(
                    stage1,
                    nodes=remaining_nodes,
                    safety_check=services.safety_check,
                    escalate_fn=escalate_fn,
                )

    # Vong 3, muc 4 - fix bug thuc: neu safety_layer trigger redflag (bat ke
    # dang o nhanh nao - dang tra loi 1 cau hoi xac nhan cu, HOAC vua tao 1
    # pending MOI ngay trong luot nay qua build_drug_identity_resolution_
    # node), PHAI xoa ngay pending_drug_confirmation dang treo cho patient
    # nay - khong de 2 trang thai (dang cho xac nhan thuoc + dang co redflag)
    # ton tai cung luc, tranh tin nhan TIEP THEO (co the hoan toan khong lien
    # quan, ke ca vai ngay sau) bi ep nham qua bo phan tich co/khong cu.
    # clear_pending_confirmation() idempotent (DELETE WHERE, khong loi neu
    # khong co dong nao) - goi vo dieu kien khi safety_flag=True an toan hon
    # kiem tra "co pending truoc do khong" (bao phu ca truong hop pending
    # MOI tao ngay trong luot nay, xem kickoff-prompt-vong-3.md muc 4).
    if final_state.get("safety_flag"):
        clear_pending_confirmation(db, patient_id)

    # Output guardrail (muc 12.2) - chay SAU khi co final_state, TRUOC khi
    # ghi audit/tra ve nguoi dung. redact/thay response NEU can - audit log
    # phai luu DUNG response da redact, khong luu ban goc co secret vao DB.
    #
    # SUA 2026-08-09 (phan hoi review) - LUON ghi 1 entry trace cho buoc nay,
    # KHONG chi khi redacted=True nhu ban truoc. Dung nguyen tac audit da ap
    # dung nhat quan xuyen suot du an (caveat_lieu_dung_inserted/caveat_thoi_
    # diem_missing_inserted o conversation_nodes.py, escalated_to/escalation_
    # failed o escalation.py - deu ghi ro gia tri KE CA False/rong, khong bao
    # gio de "vang mat" mang nghia ngam dinh): "vang mat" trong trace co 2
    # cach hieu khac han nhau ma nhin GIONG HET nhau - "da kiem tra, khong
    # trigger" hay "chua tung chay toi buoc kiem tra" (loi, nhanh code khac
    # quen goi, exception) - dung LOAI mo ho da tung gay hau qua that (REFUSE
    # dead code, escalate_fn optional). Ghi moi lan CON cho phep tinh dung ty
    # le kich hoat truc tiep tu audit_log (mau so = so lan step nay xuat hien,
    # khong phai suy doan bang tong so request).
    t_output_guard0 = time.monotonic()
    output_guard = check_output_guardrail(final_state.get("response", ""), patient_id)
    output_guardrail_duration_ms = (time.monotonic() - t_output_guard0) * 1000
    final_state = {
        **final_state,
        "response": output_guard.response,
        "trace": [
            *final_state.get("trace", []),
            {
                "step": "output_guardrail",
                "redacted": output_guard.redacted,
                # `reasons` chi chua TEN LOAI phat hien duoc, KHONG bao gio
                # chua gia tri THAT bi lo (xem docstring check_output_guardrail)
                # - trace nay se luu vao AuditLog (Postgres), khong duoc
                # bien chinh audit log thanh 1 noi luu ro ri thu 2. Rong ([])
                # khi khong trigger, khong phai thieu key.
                "reasons": output_guard.redaction_reasons,
                "duration_ms": output_guardrail_duration_ms,
            },
        ],
    }

    total_duration_ms = (time.monotonic() - t0) * 1000
    _persist_audit_log(db, patient_id, request, final_state, total_duration_ms)

    # Vong 3, muc 7.1 - luu CA HAI tin nhan (patient + assistant) vao
    # chat_messages CHO LUOT NAY, SAU KHI toan bo run_conversation() (bao
    # gom cua so ngu canh 15 phut, muc 7.2) da chay xong - co y KHONG luu
    # truoc do, de get_recent_context()/build_chat_history_query_node() goi
    # TRONG luot nay khong vo tinh doc lai chinh cau hoi/tra loi cua chinh
    # luot nay nhu the la "lich su qua khu" (xem docstring build_chat_
    # history_query_node). Luu response DA REDACT (output guardrail, giong
    # nguyen tac audit_log - khong luu ban goc co secret vao bat ky kho hien
    # thi nao).
    save_chat_message(db, patient_id, "patient", request.message)
    save_chat_message(db, patient_id, "assistant", final_state.get("response", ""))

    return _to_response(final_state)


@chat_router.post("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    request: ChatHistoryRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatHistoryResponse:
    """Vong 3, muc 7.1 - lich su chat DAY DU cho benh nhan xem lai (khong
    phai ngu canh dua vao LLM, xem docstring chat_history_tool.py). Mac
    dinh khong tra tin nhan da bi an (#20).

    TASK-010 (auth-api that): doi tu rao tam require_internal_secret sang
    JWT that (Depends(get_current_user)) - truoc do endpoint nay chi kiem
    tra 1 shared secret, KHONG xac thuc danh tinh, nen bat ky ai biet secret
    co the doc lich su chat cua BAT KY patient_id nao tu go trong body. Dung
    dung 1 cho noi get_current_patient_id() nhu chinh docstring cua ham do
    yeu cau, khong tao duong doc patient_id rieng cho history."""
    patient_id = get_current_patient_id(request, current_user)
    messages = get_chat_history_for_display(db, patient_id)
    return ChatHistoryResponse(messages=[ChatMessageOut(**m) for m in messages])


@chat_router.post("/chat/history/hide", response_model=ChatHistoryHideResponse)
async def hide_chat_history(
    request: ChatHistoryRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatHistoryHideResponse:
    """Vong 3, muc 7.1/#20 - "xoá đoạn chat" = an khoi man hinh (soft-delete),
    audit_log KHONG doi. Idempotent (goi lai khi da an het van tra ve 0,
    khong loi). TASK-010: cung doi sang JWT that, xem ghi chu get_chat_history."""
    patient_id = get_current_patient_id(request, current_user)
    hidden_count = hide_all_chat_messages(db, patient_id)
    return ChatHistoryHideResponse(hidden_count=hidden_count)


def _persist_audit_log(
    db: Session,
    patient_id: str,
    request: ConversationChatRequest,
    final_state: ConversationState,
    total_duration_ms: float,
) -> None:
    """AuditLogDTO (chatbot-rag-design.md muc 5.2) - APPEND-ONLY, moi luot
    xu ly 1 dong, ke ca nhanh REFUSE/redflag HIGH (khong co nhanh nao bo sot
    trace - yeu cau ro trong build-kickoff-prompt.md Phase 6).

    `patient_id` TASK-010: nhan lai gia tri DA duoc chat() tinh 1 lan qua
    get_current_patient_id(request, current_user) (dong ~94) - KHONG goi lai
    get_current_patient_id() o day, vi ham nay khong co current_user (can
    JWT da xac thuc) va KHONG duoc doc thang request.patient_id (dung y thiet
    ke ghi trong get_current_patient_id() - 1 cho noi duy nhat)."""
    audit = AuditLog(
        patient_id=patient_id,
        dose_event_id=request.dose_id,
        utterance=request.message,
        trace=final_state.get("trace", []),
        final_response=final_state.get("response", ""),
        total_duration_ms=total_duration_ms,
    )
    db.add(audit)
    db.commit()


def _should_show_emergency_overlay(severity_en: str | None) -> bool:
    """Tra ve gia tri se dien vao `ConversationChatResponse.safety_flag`.

    QUAN TRONG - day KHONG PHAI `state["safety_flag"]` doc lai truc tiep, va
    2 cai TEN GIONG NHAU nhung Y NGHIA KHAC NHAU (phat hien 2026-08-08, code
    review Phase 6):
      - `state["safety_flag"]` (ConversationState noi bo, muc 9 thiet ke) -
        nghia HEP: chi True khi CHINH safety_layer (keyword/LLM redflag,
        BR-3.3, ADR-0009) kich hoat. False ke ca khi SEVERITY node rieng
        (FEAT-007) tu ket luan "Nguy hiểm".
      - `ConversationChatResponse.safety_flag` (JSON tra cho FE, TEN nay do
        api-contracts.md §4 quy dinh - KHONG duoc doi ten field ngoai nay du
        muon, se pha contract voi FE) - nghia RONG: "FE bat buoc hien
        overlay cap cuu" (BR-3.5) - phai True cho CA HAI nguon kich hoat
        HIGH (safety_layer redflag LAN SEVERITY->LEVEL = Nguy hiểm), khong
        chi 1 trong 2.

    Ham rieng, ten ro rang nay ton tai DE KHONG AI (ke ca agent khac) vo
    tinh doc `state.get("safety_flag")` roi gan thang vao response - day
    chinh xac la dang bug ten trung nhau tung gay ra lo ho escalation o
    Phase 5b (safety_layer redflag khong he goi escalate_fn)."""
    return severity_en == "HIGH"


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

    return ConversationChatResponse(
        reply=state.get("response", ""),
        classification=classification,
        severity=severity_en,
        safety_flag=_should_show_emergency_overlay(severity_en),
        needs_clarification=needs_clarification,
        sources=sources,
        quick_replies=state.get("quick_replies"),
    )
