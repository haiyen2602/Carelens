"""BUILD-27B/28: time-aware medication schedule & history.

Covers the required test list (past/today/future routing, no-prescription
response, completed/missed/mixed status wording, date bounding, token
budget, auth/safety non-interference) using the same fake-gateway harness
style as ``test_agent_v2_orchestrator.py``, plus pure unit tests for the
deterministic schedule-reply composer.

BUILD-28 supersedes two BUILD-27B assumptions this file used to encode:
  - a bare "hôm nay"/"ngày mai"/"sắp tới" no longer leaves
    ``RouterDecision.time_range`` unset -- every schedule-shaped phrase
    resolves to a real ``TimeRange`` (see ``time_query_engine.
    resolve_time_query``).
  - TODAY_DOSES and UPCOMING_DOSES joined MEDICATION_HISTORY in bypassing
    the Main Model entirely (BUILD-28 §6/§8: schedule-only queries make
    zero Main Model calls, so BUDGET_EXCEEDED is impossible for them by
    construction) -- there is no longer a "future range still reaches the
    model" case to test; all three are answered by one deterministic
    composer, ``_build_schedule_reply``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.answerability import AnswerabilityOutcome, AnswerabilityReasonCode
from backend.agents.v2.context import ContextBudget, ContextManager, MemoryKind
from backend.agents.v2.handoff import DoctorHandoffGateway
from backend.agents.v2.model_gateway import EmbeddingResult, ModelPlan, ModelSynthesis, SynthesisEvidence
from backend.agents.v2.orchestrator import (
    AgentOrchestrator,
    OrchestrationIntent,
    OrchestrationRequest,
    _build_schedule_reply,
    classify_intent,
)
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyGateway
from backend.agents.v2.time_query_engine import TimeGranularity, TimeRange, TimeRelation, resolve_time_query
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway
from backend.db.models import DoseOccurrence, Prescription, PrescriptionItem
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)  # 16:00 Asia/Ho_Chi_Minh, Saturday
TODAY = date(2026, 8, 22)


def _time_range(start: date, end: date, *, relation: TimeRelation, granularity: TimeGranularity = TimeGranularity.EXPLICIT, label: str = "test") -> TimeRange:
    """Build a ``TimeRange`` directly for composer unit tests -- mirrors
    ``time_query_engine._make_range`` without depending on that private
    helper."""

    from datetime import time
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    return TimeRange(
        start_datetime=datetime.combine(start, time.min, tzinfo=tz),
        end_datetime=datetime.combine(end, time.max, tzinfo=tz),
        timezone="Asia/Ho_Chi_Minh",
        granularity=granularity,
        relation=relation,
        is_past=relation is TimeRelation.PAST,
        is_future=relation is TimeRelation.FUTURE,
        label=label,
    )


# ---------------------------------------------------------------------------
# 1. classify_intent / resolve_time_query -- routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected_intent,expected_range",
    [
        ("Hôm qua tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 21), date(2026, 8, 21))),
        ("Hôm qua tôi đã uống đủ thuốc chưa?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 21), date(2026, 8, 21))),
        ("Ngày 20/08 tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 20), date(2026, 8, 20))),
        ("hôm kia tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 20), date(2026, 8, 20))),
        ("tuần trước tôi uống thuốc gì?", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 10), date(2026, 8, 16))),
        ("Hôm nay tôi uống thuốc gì?", OrchestrationIntent.TODAY_DOSES, (date(2026, 8, 22), date(2026, 8, 22))),
        ("Ngày mai tôi cần uống thuốc gì?", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 23), date(2026, 8, 23))),
        ("Ngày kia tôi uống thuốc gì?", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 24), date(2026, 8, 24))),
        ("tuần tới tôi có lịch uống thuốc không?", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 24), date(2026, 8, 30))),
        ("ngày 25/08 tôi uống thuốc gì?", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 25), date(2026, 8, 25))),
    ],
)
def test_time_phrases_route_and_bound_correctly(message, expected_intent, expected_range):
    decision = classify_intent(message, now=NOW)
    assert decision.intent is expected_intent
    assert (decision.time_range.start_date, decision.time_range.end_date) == expected_range


def test_liều_tiếp_theo_resolves_to_the_vague_upcoming_window():
    decision = classify_intent("Liều tiếp theo lúc mấy giờ?", now=NOW)
    assert decision.intent is OrchestrationIntent.UPCOMING_DOSES
    assert decision.time_range is not None
    assert decision.time_range.relation is TimeRelation.FUTURE


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
    assert decision.time_range is None


# ---------------------------------------------------------------------------
# 2. _build_schedule_reply -- deterministic, no LLM
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


# All PAST-range composer tests use a "now" well after every item's own
# scheduled_at, so every item counts as due -- the same behavior BUILD-27B
# originally specified for a purely past range.
_AFTER_ALL_ITEMS = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)


def test_no_prescription_reply_names_the_exact_day():
    tr = _time_range(date(2026, 8, 21), date(2026, 8, 21), relation=TimeRelation.PAST)
    reply = _build_schedule_reply([], time_range=tr, now=_AFTER_ALL_ITEMS)
    assert "21/08/2026" in reply
    assert "chưa có đơn thuốc" in reply.lower()


def test_no_prescription_reply_names_a_range():
    tr = _time_range(date(2026, 8, 10), date(2026, 8, 16), relation=TimeRelation.PAST)
    reply = _build_schedule_reply([], time_range=tr, now=_AFTER_ALL_ITEMS)
    assert "10/08/2026" in reply and "16/08/2026" in reply


def test_all_completed_reply_uses_past_tense_completed_wording():
    tr = _time_range(date(2026, 8, 21), date(2026, 8, 21), relation=TimeRelation.PAST)
    items = [_item("TAKEN"), _item("DELAYED", hour=20)]
    reply = _build_schedule_reply(items, time_range=tr, now=_AFTER_ALL_ITEMS)
    assert "hoàn thành đầy đủ" in reply.lower()
    assert "bỏ lỡ" not in reply.lower()


def test_all_missed_reply_uses_past_tense_missed_wording():
    tr = _time_range(date(2026, 8, 21), date(2026, 8, 21), relation=TimeRelation.PAST)
    items = [_item("MISSED"), _item("SKIPPED", hour=20)]
    reply = _build_schedule_reply(items, time_range=tr, now=_AFTER_ALL_ITEMS)
    assert "bỏ lỡ toàn bộ" in reply.lower()


def test_mixed_reply_reports_real_completed_over_total_count():
    tr = _time_range(date(2026, 8, 21), date(2026, 8, 21), relation=TimeRelation.PAST)
    items = [_item("TAKEN"), _item("MISSED", hour=20), _item("TAKEN", hour=12)]
    reply = _build_schedule_reply(items, time_range=tr, now=_AFTER_ALL_ITEMS)
    assert "2/3" in reply
    assert "còn 1 liều chưa hoàn thành" in reply.lower()


def test_reply_lists_real_drug_names_and_times_not_guessed():
    tr = _time_range(date(2026, 8, 21), date(2026, 8, 21), relation=TimeRelation.PAST)
    items = [_item("TAKEN", names=("Metformin", "Losartan"))]
    reply = _build_schedule_reply(items, time_range=tr, now=_AFTER_ALL_ITEMS)
    assert "Metformin" in reply and "Losartan" in reply


def test_past_history_reply_uses_local_time_for_a_utc_midnight_crossing():
    tr = _time_range(date(2026, 8, 22), date(2026, 8, 22), relation=TimeRelation.PAST)
    items = [{
        "id": "dose-local", "prescription_id": "rx-1",
        "scheduled_at": "2026-08-21T19:00:00+00:00",
        "window_start": "2026-08-21T18:30:00+00:00",
        "window_end": "2026-08-21T19:30:00+00:00",
        "status": "TAKEN", "expected_items": [{"ten_thuoc": "Panadol"}], "occurrence_ids": ["occ-1"],
    }]
    reply = _build_schedule_reply(items, time_range=tr, now=_AFTER_ALL_ITEMS)

    assert "đã hoàn thành đầy đủ" in reply.lower()
    assert "02:00 ngày 22/08" in reply


def test_future_range_never_uses_past_tense_or_guesses_status():
    """BUILD-28 §6: Future -- show scheduled, never past-tense, never a
    guessed completed/missed status."""
    tr = _time_range(date(2026, 8, 24), date(2026, 8, 24), relation=TimeRelation.FUTURE)
    items = [_item("PENDING", hour=8)]
    items[0]["scheduled_at"] = "2026-08-24T01:00:00+00:00"  # 08:00 ICT, after NOW
    reply = _build_schedule_reply(items, time_range=tr, now=NOW)

    assert "đã hoàn thành" not in reply.lower()
    assert "bỏ lỡ" not in reply.lower()
    assert "dự kiến" in reply.lower()


def test_present_range_reports_already_due_items_and_flags_upcoming_ones_separately():
    """A range spanning "now" (e.g. "hôm nay") mixes already-due items (real
    status) with not-yet-due ones (never reported as taken/missed) -- BUILD-28's
    per-item tense determination, not just the overall relation."""
    tr = _time_range(TODAY, TODAY, relation=TimeRelation.PRESENT)
    items = [
        {**_item("TAKEN", hour=1), "scheduled_at": "2026-08-22T00:00:00+00:00"},  # 07:00 ICT -- already due
        {**_item("PENDING", hour=20), "scheduled_at": "2026-08-22T14:00:00+00:00"},  # 21:00 ICT -- not due yet
    ]
    reply = _build_schedule_reply(items, time_range=tr, now=NOW)

    assert "đã hoàn thành 1/1" in reply.lower()
    assert "1 liều sắp tới" in reply.lower()
    assert "dự kiến" in reply.lower()  # the not-yet-due item's own line


def test_more_than_max_detail_rows_switches_to_day_grouped_counts():
    tr = _time_range(date(2026, 8, 1), date(2026, 8, 31), relation=TimeRelation.PAST)
    items = [
        {**_item("TAKEN"), "scheduled_at": f"2026-08-{day:02d}T01:00:00+00:00"}
        for day in range(1, 32)
    ]
    reply = _build_schedule_reply(items, time_range=tr, now=_AFTER_ALL_ITEMS)

    assert len(items) > 30
    # Bounded: one line per day, never one per dose, for a range this long.
    assert reply.count("\n- ") == 31
    assert "01/08/2026" in reply and "31/08/2026" in reply


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
    assert result_aug22["items"][0]["scheduled_at"] == "2026-08-22T02:00:00+07:00"
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
# 4. Orchestrator integration -- BUILD-28: past/today/future all bypass the
#    model entirely; Main Model calls for a schedule-only query are always 0.
# ---------------------------------------------------------------------------


class _SpyModelGateway:
    def __init__(self, plan: ModelPlan | None = None, synthesis: ModelSynthesis | None = None) -> None:
        self.plan = plan or ModelPlan(response="ok")
        self.synthesis = synthesis or ModelSynthesis(free_prose="synthesized: " + (self.plan.response or "ok"))
        self.plan_calls: list[dict] = []
        self.synthesis_calls: list[dict] = []

    def plan_read_only(self, *, message: str, actor_role: str) -> ModelPlan:
        self.plan_calls.append({"message": message, "actor_role": actor_role})
        return self.plan

    def synthesize_read_only(
        self, *, message: str, actor_role: str, evidence: tuple[SynthesisEvidence, ...], policy=None, fact_slots=None
    ) -> ModelSynthesis:
        self.synthesis_calls.append({"message": message, "actor_role": actor_role, "evidence": evidence})
        return self.synthesis

    def embed_query(self, *, text: str) -> EmbeddingResult:
        return EmbeddingResult(model="text-embedding-3-small", vector=(0.1, 0.2))


class _RangeDomainTools:
    """Minimal fake covering only what this build's own tests exercise --
    BUILD-28: every schedule intent now calls ``get_doses_for_range`` only,
    never ``get_today_doses``/``get_upcoming_doses``."""

    def __init__(self, *, range_items: list[dict] | None = None) -> None:
        self.calls: list[tuple] = []
        self._range_items = range_items if range_items is not None else []

    def get_today_doses(self, *, patient_id: str) -> dict:
        self.calls.append(("get_today_doses", patient_id))
        return {"items": []}

    def get_upcoming_doses(self, *, patient_id: str) -> dict:
        self.calls.append(("get_upcoming_doses", patient_id))
        return {"items": []}

    def get_doses_for_range(self, *, patient_id: str, start_date: date, end_date: date) -> dict:
        self.calls.append(("get_doses_for_range", patient_id, start_date, end_date))
        return {"items": self._range_items}

    @staticmethod
    def _dose(dose_id: str, *, status: str = "PENDING", scheduled_at: str = "2026-08-24T08:00:00+00:00") -> dict:
        return {
            "id": dose_id, "prescription_id": "rx-1",
            "scheduled_at": scheduled_at,
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
    assert "chưa có đơn thuốc" in result.response.lower()
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
    assert "bỏ lỡ toàn bộ" in result.response.lower()
    assert "Panadol" in result.response
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []


def test_future_explicit_range_also_bypasses_the_model_entirely():
    """BUILD-28: unlike BUILD-27B, a future range (even one beyond
    get_upcoming_doses's own default window) no longer reaches the Main
    Model at all -- it goes through the same deterministic composer as
    past/today, via get_doses_for_range only."""
    domain = _RangeDomainTools(range_items=[_RangeDomainTools._dose("dose-day-after")])
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("Ngày kia tôi uống thuốc gì?"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert result.intent is OrchestrationIntent.UPCOMING_DOSES
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []
    assert domain.calls == [("get_doses_for_range", "patient-1", date(2026, 8, 24), date(2026, 8, 24))]
    assert "dự kiến" in result.response.lower()


def test_future_empty_range_gets_the_deterministic_no_data_reply():
    domain = _RangeDomainTools(range_items=[])
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("Ngày kia tôi uống thuốc gì?"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert "chưa có đơn thuốc" in result.response.lower()
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []


def test_today_also_bypasses_the_model_via_get_doses_for_range():
    """BUILD-28: TODAY_DOSES joined MEDICATION_HISTORY/UPCOMING_DOSES in
    being fully deterministic -- get_today_doses is no longer called for
    this intent at all."""
    domain = _RangeDomainTools(range_items=[])
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("Hôm nay tôi uống thuốc gì?"), tools=_tools(domain))

    assert result.intent is OrchestrationIntent.TODAY_DOSES
    assert result.status is RunStatus.COMPLETED
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []
    assert domain.calls == [("get_doses_for_range", "patient-1", TODAY, TODAY)]


def test_schedule_queries_never_call_the_model_worst_case_regimen():
    """BUILD-28 §8: a busy real-world chronic regimen (several times daily,
    a full month range) still makes zero Main Model calls and cannot hit
    BUDGET_EXCEEDED -- this is the exact production bug shape ("tuần sau",
    a 15-item week) verified at a larger (31-day/month) scale."""
    items = [
        {**_RangeDomainTools._dose(f"d{day}-{hour}", scheduled_at=f"2026-08-{day:02d}T0{hour}:00:00+00:00")}
        for day in range(1, 32) for hour in range(1, 5)
    ]
    domain = _RangeDomainTools(range_items=items)
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(_request("tháng trước tôi uống thuốc gì"), tools=_tools(domain))

    assert result.status is RunStatus.COMPLETED
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []
    assert result.metrics.token_total == 0


# ---------------------------------------------------------------------------
# TASK-V2.5-002: "các ngày còn lại thì sao" -- range-remainder follow-up.
# TR01 lượt 8->9 (golden sheet): "tuần tới tôi có lịch uống thuốc không?"
# rồi "các ngày còn lại thì sao" phải kế thừa đúng range đã lập, không
# misroute thành GENERAL_MEDICAL_INFORMATION.
# ---------------------------------------------------------------------------


def _request_with_prior_range(message: str, *, prior_active_schedule_range) -> OrchestrationRequest:
    return OrchestrationRequest(
        message=message, actor_id="actor-1", actor_role="patient", patient_id="patient-1",
        conversation_id="conv-1", session_id="session-1",
        prior_active_schedule_range=prior_active_schedule_range,
        followup_capability_enabled=True,
    )


def test_range_remainder_followup_is_inert_when_the_capability_flag_is_off():
    """Default-off flag: even with a valid stored range, the message must
    fall through to the pre-existing (misrouted) behavior unchanged --
    proves the flag actually gates this path rather than being decorative."""
    domain = _RangeDomainTools(range_items=[])
    orchestrator, gateway = _orchestrator()
    request = OrchestrationRequest(
        message="các ngày còn lại thì sao", actor_id="actor-1", actor_role="patient", patient_id="patient-1",
        conversation_id="conv-1", session_id="session-1",
        prior_active_schedule_range=(date(2026, 8, 24), date(2026, 8, 30)),
        # followup_capability_enabled defaults to False -- not set here.
    )
    result = orchestrator.run(request, tools=_tools(domain))

    assert domain.calls == []  # get_doses_for_range is never reached
    assert result.intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION


def test_range_remainder_followup_resolves_from_the_stored_range_never_the_model():
    """With a valid active_schedule_range from the prior turn, 'các ngày còn
    lại thì sao' must resolve via get_doses_for_range using that stored
    range -- never fall through to GENERAL_MEDICAL_INFORMATION/the model."""
    domain = _RangeDomainTools(range_items=[_RangeDomainTools._dose("dose-in-range")])
    orchestrator, gateway = _orchestrator()
    stored_range = (date(2026, 8, 24), date(2026, 8, 30))
    result = orchestrator.run(
        _request_with_prior_range("các ngày còn lại thì sao", prior_active_schedule_range=stored_range),
        tools=_tools(domain),
    )

    assert result.status is RunStatus.COMPLETED
    assert result.intent is not OrchestrationIntent.GENERAL_MEDICAL_INFORMATION
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []
    assert domain.calls == [("get_doses_for_range", "patient-1", stored_range[0], stored_range[1])]


def test_range_remainder_followup_without_a_stored_range_asks_need_more_info():
    """No prior active_schedule_range (new session, expired, already
    consumed) -- must ask which date/range, never silently answer as a
    general medical question and never call get_doses_for_range with a
    guessed range."""
    domain = _RangeDomainTools(range_items=[])
    orchestrator, gateway = _orchestrator()
    result = orchestrator.run(
        _request_with_prior_range("các ngày còn lại thì sao", prior_active_schedule_range=None),
        tools=_tools(domain),
    )

    assert result.status is RunStatus.COMPLETED
    assert result.intent is not OrchestrationIntent.GENERAL_MEDICAL_INFORMATION
    assert result.answerability_decision is not None
    assert result.answerability_decision.outcome is AnswerabilityOutcome.NEED_MORE_INFO
    assert result.answerability_decision.reason_code is AnswerabilityReasonCode.MISSING_SCHEDULE_CONTEXT
    assert gateway.plan_calls == [] and gateway.synthesis_calls == []
    assert domain.calls == []
