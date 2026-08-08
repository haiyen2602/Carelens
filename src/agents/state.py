"""State schema.

`AgentState`: template goc cua boilerplate AI20K (src/agents/graph.py,
src/api/routes.py van dung - thuoc pham vi Phase 6 "FastAPI endpoint", CHUA
dung toi trong Phase 5) - giu nguyen, khong xoa, de khong lam vo cac test/
import hien co ngoai pham vi Phase 5.

`ConversationState`: state that cua VMEC-04 chatbot, dung theo dung schema da
chot o specs/chatbot-rag-design.md muc 9, khong tu y doi field. `trace` tich
luy tung buoc (safety_layer, intent_classification, retrieval,
prescription_lookup, answer_generation...) theo dinh dang muc 5.2, dung de
ghi vao AuditLogDTO khi ket thuc (Phase 6). 2 truong caveat
(caveat_lieu_dung_inserted, caveat_thoi_diem_missing_inserted) la 2 boolean
TACH RIENG trong entry trace cua buoc answer_generation - khong gop chung 1
field (chot lai o Phase 4 review, nhac lai truoc khi code Phase 5)."""

from __future__ import annotations

from typing import Literal, TypedDict

from src.services.retrieval import DrugInfoResult


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent (template boilerplate AI20K).

    Mỗi node đọc và ghi vào state này.
    total=False cho phép tất cả fields là optional.
    """

    query: str
    context: str
    analysis: str
    response: str
    error: str
    metadata: dict


class ConversationState(TypedDict, total=False):
    patient_id: str
    dose_event_id: str | None
    utterance: str

    intent: Literal["drug_info", "today_schedule", "dose_confirmation"] | None
    classification: Literal["TAKEN", "MISSED", "DELAYED", "SIDE_EFFECT"] | None
    classification_confidence: float | None

    rag_results: list[DrugInfoResult]
    prescription_instruction: str | None  # thoi_diem_dung tu PrescriptionDTO.items[] neu co (muc 3.1)

    severity: Literal["Nhẹ", "Trung bình", "Nguy hiểm"] | None
    safety_flag: bool  # ket qua song song, khong phu thuoc cac field tren

    trace: list[dict]
    response: str
