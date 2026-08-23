"""BUILD-30: user-safe Agent V2 activity timeline.

``build_activity_timeline()`` is a pure function of the real
``OrchestrationResult`` a completed ``AgentOrchestrator.run()`` call already
produced -- deliberately NOT derived from (or dependent on) the telemetry
ring buffer (``backend.services.telemetry``), unlike BUILD-29's admin ticket
explorer. Every item in the returned list corresponds to something that
genuinely happened in this exact run; a step this module has no real signal
for is simply omitted, never fabricated or defaulted in. In particular: no
"đang suy nghĩ"/"đã gọi Main Model" step is ever added here at all, so a
zero-Main-Model-call run (BUILD-28's deterministic schedule composer) can
never show one by construction, not by a runtime check.

The returned dicts are the ONLY thing ever persisted (see
``backend.db.models.AgentActivitySnapshot``) or served back to the patient
(see ``backend.api.agent_v2_routes``'s new activity endpoint) -- no prompts,
no model reasoning, no raw tool arguments/results, no DB rows, no JWT/
patient_id/secrets. Every field is one of: type, label, status,
duration_ms (always ``None`` in this build -- see module docstring in the
PR description for why), source_count.
"""

from __future__ import annotations

from typing import TypedDict

from backend.agents.v2.conversation_state import SuggestedAction
from backend.agents.v2.orchestrator import _SCHEDULE_INTENTS, OrchestrationIntent, OrchestrationResult
from backend.agents.v2.runtime import RunStatus


class ActivityItem(TypedDict, total=False):
    type: str
    label: str
    status: str
    duration_ms: float | None
    source_count: int


# BUILD-30 §5's own mapping table, plus two tools it left unmapped
# (get_active_prescriptions/get_dose_status) filled in with the same honest,
# narrow-label convention as the rest of this table -- never a generic
# "Đã gọi công cụ X" that would leak the raw tool name.
_TOOL_ACTIVITY: dict[str, tuple[str, str]] = {
    "search_drug": ("drug_info", "Đã tra thông tin thuốc"),
    "get_drug_info": ("drug_info", "Đã tra thông tin thuốc"),
    "get_today_doses": ("schedule", "Đã kiểm tra lịch dùng thuốc"),
    "get_upcoming_doses": ("schedule", "Đã kiểm tra lịch dùng thuốc"),
    "get_doses_for_range": ("schedule", "Đã kiểm tra lịch dùng thuốc"),
    "get_active_prescriptions": ("prescription", "Đã kiểm tra đơn thuốc"),
    "get_dose_status": ("dose_status", "Đã kiểm tra trạng thái liều thuốc"),
}

# The exact 4 intents _INTENT_CONFIG binds a real safety_trigger or
# bypass_to_handoff to (backend/agents/v2/orchestrator.py) -- read directly
# from that static table's own values, not re-derived/guessed here. A
# RouterDecision isn't available this far down the stack (only the finished
# OrchestrationResult is), so this module keys off the one thing that
# structurally never changes without also changing _INTENT_CONFIG itself.
_SAFETY_DETECTION_INTENTS = frozenset(
    {
        OrchestrationIntent.MISSED_DOSE,
        OrchestrationIntent.DELAYED_DOSE,
        OrchestrationIntent.ACUTE_DANGER_ESCALATION,
        OrchestrationIntent.DOCTOR_REVIEW,
    }
)


def build_activity_timeline(
    result: OrchestrationResult,
    *,
    suggested_actions: tuple[SuggestedAction, ...] = (),
    selected_action: SuggestedAction | None = None,
) -> list[ActivityItem]:
    """Build the sanitized, real-events-only timeline for one finished run.

    Order mirrors the actual pipeline order in ``AgentOrchestrator.run()``:
    router -> time query -> safety detection -> tools -> retrieval/vinmec ->
    safety check -> handoff -> terminal outcome. ``duration_ms`` is always
    omitted (``None``) in this build -- see the module docstring in the PR
    description for why (it is explicitly optional per the DTO contract;
    Agent V2 has no reliable per-step timing outside the telemetry ring
    buffer this module deliberately does not depend on).
    """

    activities: list[ActivityItem] = []

    def add(type_: str, label: str, *, status: str = "completed", source_count: int | None = None) -> None:
        item: ActivityItem = {"type": type_, "label": label, "status": status, "duration_ms": None}
        if source_count is not None:
            item["source_count"] = source_count
        activities.append(item)

    # 1. The deterministic router always classifies every message -- real
    # for every single request, regardless of what it resolved to.
    add("intent", "Đã xác định yêu cầu")

    # BUILD-29D.2: the selection was validated against the latest action
    # state before orchestration, so this is a real user-safe event. It
    # contains only the label the user saw, never IDs, tool arguments, or
    # hidden reasoning.
    if selected_action is not None:
        add("suggested_action.selected", f'Bạn chọn "{selected_action.label}"')

    # 2. BUILD-28 Time Query Engine -- real only for the 3 schedule intents
    # (MEDICATION_HISTORY/TODAY_DOSES/UPCOMING_DOSES), which structurally
    # cannot resolve without it (RouterDecision.time_range is always
    # populated for exactly these three).
    if result.intent in _SCHEDULE_INTENTS:
        add("time_query", "Đã xác định thời gian")

    # 3. A safety-relevant signal was found in the message itself (before
    # Safety Domain is actually consulted below) -- real for exactly the
    # intents _INTENT_CONFIG binds a safety_trigger/handoff bypass to.
    if result.intent in _SAFETY_DETECTION_INTENTS:
        add("safety_detected", "Phát hiện nội dung cần kiểm tra an toàn")

    # 4. Real tool calls only, deduped by the LABEL they map to (not the raw
    # tool name) -- e.g. search_drug and get_drug_info in the same turn must
    # not show "Đã tra thông tin thuốc" twice. Order preserved from the
    # first tool call that earned each label.
    seen_labels: set[str] = set()
    for tool_result in result.tool_results:
        mapped = _TOOL_ACTIVITY.get(tool_result.name)
        if mapped is None or mapped[1] in seen_labels:
            continue
        seen_labels.add(mapped[1])
        add(*mapped)

    # 5. Retrieval (internal RAG) -- real only for GENERAL_MEDICAL_INFORMATION
    # (the one intent _INTENT_CONFIG sets use_retrieval=True for).
    # source_count is the real count of non-Vinmec citations this run
    # actually returned (0 is a real, honest count -- "looked but found
    # nothing", not "didn't look").
    if result.intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION:
        count = sum(1 for c in result.citations if c.source != "vinmec-web")
        add("retrieval", "Đã tìm nguồn thông tin liên quan", source_count=count)

    # 6. Vinmec Web -- real only for VINMEC_WEB_INFORMATION (the one intent
    # _INTENT_CONFIG sets use_vinmec_web=True for).
    if result.intent is OrchestrationIntent.VINMEC_WEB_INFORMATION:
        count = sum(1 for c in result.citations if c.source == "vinmec-web")
        add("vinmec_web", "Đã tra cứu nguồn Vinmec", source_count=count)

    # 7. Safety Domain actually produced a real decision for this run.
    # Never exposes outcome/reason_code text -- the step existing at all
    # already tells the user "an toàn đã được kiểm tra"; the terminal-status
    # branch below is what distinguishes SAFE-and-continued from blocked.
    if result.safety_decision is not None:
        add("safety", "Đã kiểm tra an toàn")

    # 8. A real Doctor Handoff record was created.
    if result.handoff_result is not None:
        add("handoff", "Đã chuyển yêu cầu để bác sĩ xem xét")

    # 9. Exactly one honest terminal step, keyed off the real RunStatus --
    # never a generic "hoàn thành" when the run did not actually complete
    # normally, and never a second/duplicate handoff step when step 8
    # above already reported the real terminal event for that path.
    if result.status is RunStatus.COMPLETED:
        add("generation", "Đã hoàn thành câu trả lời")
    elif result.status is RunStatus.HANDOFF_CREATED:
        pass  # step 8 above is the real terminal event for this path
    elif result.status is RunStatus.SAFETY_BLOCKED:
        add("safety", "Chưa thể trả lời do đánh giá an toàn chưa được xác nhận", status="blocked")
    elif result.status is RunStatus.HANDOFF_REQUIRED:
        add("handoff", "Yêu cầu đang chờ được chuyển đến bác sĩ", status="pending")
    else:  # FAILED, TIMEOUT, BUDGET_EXCEEDED, CANCELLED
        add("error", "Không thể hoàn thành yêu cầu này", status="failed")

    if suggested_actions:
        add("suggested_actions.created", "Đã tạo gợi ý cho câu hỏi tiếp theo")

    return activities


__all__ = ["ActivityItem", "build_activity_timeline"]
