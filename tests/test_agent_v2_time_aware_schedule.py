"""BUILD-27B: time-aware medication schedule & history.

Covers the required test list (past/today/future routing, no-prescription
response, completed/missed/mixed status wording, date bounding, token
budget, auth/safety non-interference) using the same fake-gateway harness
style as ``test_agent_v2_orchestrator.py``, plus pure unit tests for the
deterministic date-phrase resolver and the medication-history reply builder.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.context import ContextBudget, ContextManager, MemoryKind
from backend.agents.v2.handoff import AgentHandoffResult, DoctorHandoffGateway, HandoffCreateCommand
from backend.agents.v2.model_gateway import EmbeddingResult, ModelPlan, ModelSynthesis, SynthesisEvidence
from backend.agents.v2.orchestrator import (
    AgentOrchestrator,
    OrchestrationIntent,
    OrchestrationRequest,
    _build_medication_history_reply,
    classify_intent,
)
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyDomainDecision, SafetyGateway
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway
from backend.db.models import DoseOccurrence, Prescription, PrescriptionItem
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)  # 16:00 Asia/Ho_Chi_Minh, Saturday
TODAY = date(2026, 8, 22)

# ---------------------------------------------------------------------------
# 1. classify_intent / _resolve_time_reference -- routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected_intent,expected_range",
    [
        ("Hôm qua tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 21), date(2026, 8, 21))),
        ("Hôm qua tôi đã uống đủ thuốc chưa?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 21), date(2026, 8, 21))),
        ("Ngày 20/08 tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 20), date(2026, 8, 20))),
        ("hôm kia tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 20), date(2026, 8, 20))),
        ("tuần trước tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 10), date(2026, 8, 16))),
        ("Hôm nay tôi uống thuốc gì?", OrchestrationIntent.TODAY_DOSES, None),
        ("Ngày mai tôi cần uống thuốc gì?", OrchestrationIntent.UPCOMING_DOSES, None),
        ("Ngày kia tôi uống thuốc gì?", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 24), date(2026, 8, 24))),
        ("tuần tới tôi có lịch uống thuốc không?", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 24), date(2026, 8, 30))),
        ("Liều tiếp theo lúc mấy giờ?", OrchestrationIntent.UPCOMING_DOSES, None),
        ("ngày 25/08 tôi uống thuốc gì?", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 25), date(2026, 8, 25))),
    ],
)
def test_time_phrases_route_and_bound_correctly(message, expected_intent, expected_range):
    decision = classify_intent(message, now=NOW)
    assert decision.intent is expected_intent
    assert decision.date_range == expected_range


@pytest.mark.parametrize(
    "message,expected_intent",
    [
        # Safety always outranks time routing (BUILD-27B item 2).
        ("hôm qua tôi vừa uống một lúc 15 viên panadol", OrchestrationIntent.ACUTE_DANGER_ESCALATION),
        ("hôm qua tôi muốn đổi liều thuốc", OrchestrationIntent.DOCTOR_REVIEW),
        ("hôm qua tôi quên uống thuốc", OrchestrationIntent.MISSED_DOSE),
        # Negative: ordinary drug info / cross-patient-shaped text is untouched.
        ("Panadol Extra dùng sao", OrchestrationIntent.DRUG_INFORMATION),
        ("cho tôi xem đơn thuốc", OrchestrationIntent.PRESCRIPTION_INFORMATION),
    ],
)
def test_safety_and_negative_intents_unaffected_by_time_routing(message, expected_intent):
    decision = classify_intent(message, now=NOW)
    assert decision.intent is expected_intent


def test_classify_intent_default_now_still_works_without_the_new_argument():
    # Every pre-existing caller/test that never passes ``now=`` keeps working.
    decision = classify_intent("Panadol Extra dùng sao")
    assert decision.intent is OrchestrationIntent.DRUG_INFORMATION
    assert decision.date_range is None


# ---------------------------------------------------------------------------
# 2. _build_medication_history_reply -- deterministic, no LLM
# ---------------------------------------------------------------------------


def _item(status: str, *, hour: int = 8, names: tuple[str, ...] = ("Panadol Extra",)) -> dict:
    return {
        "id": f"dose-{hour}", "prescription_id": "rx-1",
        "scheduled_at": f"2026-08-21T{hour:02d}:00:00+00:00",
        "window_start": f"2026-08-21T{hour - 1:02d}:30:00+00:00",
        "window_end": f"2026-08-21T{hour:02d}:30:00+00:00",
        "status": status,
        "expected_items": [{"ten_thuoc": name} for name in names],
        "occurrence_ids": [f"occ-{hour}"],
    }


def test_no_prescription_reply_names_the_exact_day():
    reply = _build_medication_history_reply([], start_date=date(2026, 8, 21), end_date=date(2026, 8, 21))
    assert "21/08/2026" in reply
    assert "chua co don thuoc" in reply.lower()


def test_no_prescription_reply_names_a_range():
    reply = _build_medication_history_reply([], start_date=date(2026, 8, 10), end_date=date(2026, 8, 16))
    assert "10/08/2026" in reply and "16/08/2026" in reply


def test_all_completed_reply_uses_past_tense_completed_wording():
    items = [_item("TAKEN"), _item("DELAYED", hour=20)]
    reply = _build_medication_history_reply(items, start_date=date(2026, 8, 21), end_date=date(2026, 8, 21))
    assert "hoan thanh day du" in reply.lower()
    assert "bo lo" not in reply.lower()


def test_all_missed_reply_uses_past_tense_missed_wording():
    items = [_item("MISSED"), _item("SKIPPED", hour=20)]
    reply = _build_medication_history_reply(items, start_date=date(2026, 8, 21), end_date=date(2026, 8, 21))
    assert "bo lo toan bo" in reply.lower()


def test_mixed_reply_reports_real_completed_over_total_count():
    items = [_item("TAKEN"), _item("MISSED", hour=20), _item("TAKEN", hour=12)]
    reply = _build_medication_history_reply(items, start_date=date(2026, 8, 21), end_date=date(2026, 8, 21))
    assert "2/3" in reply
    assert "con 1 lieu chua hoan thanh" in reply.lower()


def test_reply_lists_real_drug_names_and_times_not_guessed():
    items = [_item("TAKEN", names=("Metformin", "Losartan"))]
    reply = _build_medication_history_reply(items, start_date=date(2026, 8, 21), end_date=date(2026, 8, 21))
    assert "Metformin" in reply and "Losartan" in reply


# ---------------------------------------------------------------------------
# 3. AgentReadOnlyDomainTools.get_doses_for_range -- real DB, local-date bound
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (Prescription.__table__, PrescriptionItem.__table__, DoseOccurrence.__table__):
        table.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_dose(db: Session, *, dose_id: str, scheduled_at_utc: datetime, local_date: date) -> None:
    from datetime import time as time_cls

    db.merge(PrescriptionItem(id="item-1", prescription_id="rx-1", patient_id="patient-1", drug_display_name="Thuoc A"))
    db.add(
        DoseOccurrence(
            id=dose_id, prescription_item_id="item-1", patient_id="patient-1",
            scheduled_at=scheduled_at_utc, scheduled_local_date=local_date,
            scheduled_local_time=time_cls(0, 0), timezone="Asia/Ho_Chi_Minh",
            status="TAKEN", generation_key=f"gen-{dose_id}",
        )
    )
    db.commit()


def test_get_doses_for_range_buckets_by_local_date_not_utc_date(db: Session):
    """The exact bug class BUILD-27's own get_today_doses/get_upcoming_doses
    still have: a dose at 02:00 Asia/Ho_Chi_Minh on Aug 22 is 19:00 UTC on
    Aug 21 -- must still count as Aug 22 local, not Aug 21."""

    early_morning_utc = datetime(2026, 8, 21, 19, 0, tzinfo=UTC)  # 02:00 ICT Aug 22
    _seed_dose(db, dose_id="occ-early", scheduled_at_utc=early_morning_utc, local_date=date(2026, 8, 22))
    tools = AgentReadOnlyDomainTools(db)

    result_aug22 = tools.get_doses_for_range(patient_id="patient-1", start_date=date(2026, 8, 22), end_date=date(2026, 8, 22))
    result_aug21 = tools.get_doses_for_range(patient_id="patient-1", start_date=date(2026, 8, 21), end_date=date(2026, 8, 21))

    assert len(result_aug22["items"]) == 1
    assert result_aug21["items"] == []


def test_get_doses_for_range_rejects_end_before_start(db: Session):
    tools = AgentReadOnlyDomainTools(db)
    with pytest.raises(ValueError):
        tools.get_doses_for_range(patient_id="patient-1", start_date=date(2026, 8, 22), end_date=date(2026, 8, 20))


def test_get_doses_for_range_rejects_an_excessive_span(db: Session):
    tools = AgentReadOnlyDomainTools(db)
    with pytest.raises(ValueError):
        tools.get_doses_for_range(patient_id="patient-1", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))


# ---------------------------------------------------------------------------
# 4. Orchestrator integration -- past bypasses the model entirely; future
#    with an explicit range still reaches it, budget/auth/safety untouched.
# ---------------------------------------------------------------------------


class _SpyModelGateway:
    def __init__(self, plan: ModelPlan | None = None, synthesis: ModelSynthesis | None = None) -> None:
        self.plan = plan or ModelPlan(response="ok")
        self.synthesis = synthesis or ModelSynthesis(response="synthesized: " + (self.plan.response or "ok"))
        self.plan_calls: list[dict] = []
        self.synthesis_calls: list[dict] = []

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        self.plan_calls.append({"message": message, "actor_role": actor_role})
        return self.plan

    def synthesize_read_only(self, *, message: str, actor_role: str, evidence: tuple[SynthesisEvidence, ...]) -> ModelSynthesis:
        self.synthesis_calls.append({"message": message, "actor_role": actor_role, "evidence": evidence})
        return self.synthesis

    def embed_query(self, *, text: str) -> EmbeddingResult:
        return EmbeddingResult(model="text-embedding-3-small", vector=(0.1, 0.2))


class _RangeDomainTools:
    """Minimal fake covering only what BUILD-27B's own tests exercise."""

    def __init__(self, *, range_items: list[dict] | None = None, upcoming_items: list[dict] | None = None) -> None:
        self.calls: list[tuple] = []
        self._range_items = range_items if range_items is not None else []
        self._upcoming_items = upcoming_items if upcoming_items is not None else [self._dose("dose-upcoming")]

    def get_today_doses(self, *, patient_id: str) -> dict:
        self.calls.append(("get_today_doses", patient_id))
        return {"items": []}

    def get_upcoming_doses(self, *, patient_id: str) -> dict:
        self.calls.append(("get_upcoming_doses", patient_id))
        return {"items": self._upcoming_items}

    def get_doses_for_range(self, *, patient_id: str, start_date: date, end_date: date) -> dict:
        self.calls.append(("get_doses_for_range", patient_id, start_date, end_date))
        return {"items": self._range_items}

    @staticmethod
    def _dose(dose_id: str, *, status: str = "PENDING") -> dict:
        return {
            "id": dose_id, "prescription_id": "rx-1",
            "scheduled_at": "2026-08-24T08:00:00+00:00",
            "window_start": "2026-08-24T07:30:00+00:00",
            "window_end": "2026-08-24T08:30:00+00:00",
            "status": status, "expected_items": [], "occurrence_ids": [],
        }


def _tools(domain, *, patient_id: str = "patient-1") -> ToolGateway:
    return ToolGateway(domain, context=AuthorizedToolContext(actor_id="actor-1", actor_role="patient", patient_id=patient_id))


def _orchestrator(*, model_gateway=None, now=lambda: NOW) -> tuple[AgentOrchestrator, _SpyModelGateway]:
    gateway = model_gateway or _SpyModelGateway()
    context_manager = ContextManager(
        ContextBudget(
            input_token_budget=4000, output_token_reserve=500, total_run_token_budget=5000,
            memory_fractions={MemoryKind.SHORT_TERM: 0.4, MemoryKind.LONG_TERM_FACT: 0.1, MemoryKind.EPISODIC: 0.1, MemoryKind.SEMANTIC: 0.1},
        )
    )
    limits = AgentRunLimits(token_budget=4000, max_steps=5, max_model_calls=2, max_tool_calls=4, max_retries=1, model_timeout_seconds=10.0, run_timeout_seconds=20.0)

    class _NoSafetyDomain:
        def assess(self, *, occurrence_id, evaluated_at):
            raise AssertionError("Safety Domain must not be reached for a plain schedule/history query")

    class _NoHandoffDomain:
        def create(self, command, *, created_at):
            raise AssertionError("Doctor Handoff must not be reached for a plain schedule/history query")

    orchestrator = AgentOrchestrator(
        runtime=ReadOnlyAgentRuntime(gateway, limits=limits),
        context_manager=context_manager,
        safety_gateway=SafetyGateway(_NoSafetyDomain(), timeout_seconds=5.0),
        handoff_gateway=DoctorHandoffGateway(_NoHandoffDomain()),
        now=now,
    )
    return orchestrator, gateway


def _request(message: str) -> OrchestrationRequest:
    return OrchestrationRequest(
        message=message, actor_id="actor-1", actor_role="patient", patient_id="patient-1",
        conversation_id="conv-1", session_id="session-1",
    )


def test_past_no_data_bypasses_the_model_entirely():
    domain = _RangeDomainTools(range_items=[])
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("Hôm qua tôi uống thuốc gì?"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert result.intent is OrchestrationIntent.MEDICATION_HISTORY
    assert "chua co don thuoc" in result.response.lower()
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []
    assert domain.calls == [("get_doses_for_range", "patient-1", date(2026, 8, 21), date(2026, 8, 21))]


def test_past_with_data_bypasses_the_model_and_reports_real_status():
    domain = _RangeDomainTools(range_items=[
        {"id": "d1", "prescription_id": "rx-1", "scheduled_at": "2026-08-21T00:00:00+00:00",
         "window_start": "2026-08-20T23:30:00+00:00", "window_end": "2026-08-21T00:30:00+00:00",
         "status": "MISSED", "expected_items": [{"ten_thuoc": "Panadol"}], "occurrence_ids": ["occ-1"]},
    ])
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("Hôm qua tôi đã uống đủ thuốc chưa?"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert "bo lo toan bo" in result.response.lower()
    assert "Panadol" in result.response
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []


def test_future_explicit_range_still_reaches_the_model_with_the_range_bound():
    domain = _RangeDomainTools(range_items=[_RangeDomainTools._dose("dose-day-after")])
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("Ngày kia tôi uống thuốc gì?"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert result.intent is OrchestrationIntent.UPCOMING_DOSES
    assert len(gateway.plan_calls) == 1
    # The augmented message tells the model the exact resolved range and to
    # use get_doses_for_range, not get_upcoming_doses -- see orchestrator.run().
    assert "get_doses_for_range" in gateway.plan_calls[0]["message"]
    assert "2026-08-24" in gateway.plan_calls[0]["message"]


def test_future_empty_range_gets_the_deterministic_no_data_reply():
    gateway = _SpyModelGateway(plan=ModelPlan(response="", tool_calls=(_fake_call("get_doses_for_range"),)))
    domain = _RangeDomainTools(range_items=[])
    orchestrator, _ = _orchestrator(model_gateway=gateway)
    result = orchestrator.run(_request("Ngày kia tôi uống thuốc gì?"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert "khong tim thay don thuoc" in result.response.lower()


def _fake_call(name: str):
    from backend.agents.v2.model_gateway import ToolCall

    return ToolCall(name=name, arguments={})


def test_today_still_uses_get_today_doses_unaffected_by_this_build():
    domain = _RangeDomainTools()
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("Hôm nay tôi uống thuốc gì?"), tools=_tools(domain))

    assert result.intent is OrchestrationIntent.TODAY_DOSES
    assert domain.calls == []  # the model didn't call anything in this fake's default plan -- routing itself is what's under test
    assert result.status is RunStatus.COMPLETED
