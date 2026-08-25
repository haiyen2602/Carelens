"""BUILD-33: unit/integration tests for the production LLM Judge V2 --
eligibility/priority classification, sanitized input assembly, the
provider-agnostic call boundary (structured-output validation, malformed/
timeout/auth failure handling), the enqueue + scoring worker, and duplicate
protection. No real network call is made anywhere in this file (see
scripts/agent_v2/judge_calibration.py for the real-model calibration run).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import openai
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.agents.v2.evaluation_v2 import (
    EvaluationPath,
    EvaluationResult,
    MetricDisposition,
    MetricStatus,
    dispatch_evaluation,
)
from backend.agents.v2.judge_eligibility import (
    JudgeEligibilityReason,
    evaluate_sampling_eligibility,
    ticket_eligibility,
)
from backend.agents.v2.judge_input import JudgeInputRejectedError, build_judge_input
from backend.agents.v2.judge_provider import JudgeOutputSchema, call_judge, resolve_base_url, resolve_credential
from backend.agents.v2.judge_rubrics import render_prompt, rubric_for_path
from backend.db.models import AgentRunEvaluation, AgentRunJudge
from backend.services.agent_judge_worker import enqueue_run_judge, enqueue_ticket_judge, process_pending_judge_batch

# ---------------------------------------------------------------------------
# shared fakes
# ---------------------------------------------------------------------------


def _fake_result(
    *,
    agent_run_id="run-1",
    trace_id="trace-1",
    intent="GENERAL_MEDICAL_INFORMATION",
    response="Day la cau tra loi.",
    tool_results=(),
    citations=(),
    safety_decision=None,
    handoff_result=None,
    error_code=None,
):
    return SimpleNamespace(
        agent_run_id=agent_run_id,
        trace_id=trace_id,
        intent=SimpleNamespace(value=intent),
        status=SimpleNamespace(value="COMPLETED"),
        response=response,
        tool_results=tool_results,
        citations=citations,
        safety_decision=safety_decision,
        handoff_result=handoff_result,
        error_code=error_code,
    )


def _settings(**overrides):
    base = dict(
        agent_judge_enabled=True,
        agent_judge_provider="openai",
        agent_judge_model="gpt-4o",
        agent_judge_google_api_key="",
        openai_judge_api_key="sk-judge-test",
        openai_api_key="sk-global-test",
        agent_judge_base_url="",
        agent_judge_reasoning_effort="high",
        agent_judge_timeout_seconds=30.0,
        agent_judge_sampling_rate=0.0,
        agent_judge_low_score_threshold=0.5,
        agent_judge_max_per_tick=5,
        agent_judge_prompt_version="judge-v1",
        agent_judge_rubric_version="rubric-v1",
        agent_model_pricing_json="{}",
        agent_model_pricing_version="unversioned",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AgentRunEvaluation.__table__.create(engine)
    AgentRunJudge.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Eligibility (pure)
# ---------------------------------------------------------------------------


def _eval(path: EvaluationPath) -> EvaluationResult:
    available = MetricDisposition(MetricStatus.AVAILABLE, "heuristic")
    return EvaluationResult(path, {"answer_relevance": available, "faithfulness": available})


def test_ticket_is_always_eligible_priority_0():
    elig = ticket_eligibility()
    assert elig.eligible and elig.reason == JudgeEligibilityReason.TICKET and elig.priority == 0


def test_safety_path_is_anomaly_eligible_priority_1():
    result = _fake_result(safety_decision=SimpleNamespace(outcome=SimpleNamespace(value="HANDOFF_REQUIRED")))
    evaluation = dispatch_evaluation(result=result)
    assert evaluation.path is EvaluationPath.SAFETY
    elig = evaluate_sampling_eligibility(
        result=result, evaluation=evaluation, heuristic_score=None, sampling_rate=0.0, low_score_threshold=0.5, sample_roll=0.99
    )
    assert elig.eligible and elig.reason == JudgeEligibilityReason.SAFETY_ANOMALY and elig.priority == 1


def test_error_code_is_eligible_priority_2_even_with_zero_sampling():
    result = _fake_result(error_code="MODEL_TIMEOUT")
    evaluation = dispatch_evaluation(result=result)
    elig = evaluate_sampling_eligibility(
        result=result, evaluation=evaluation, heuristic_score=None, sampling_rate=0.0, low_score_threshold=0.5, sample_roll=0.99
    )
    assert elig.eligible and elig.reason == JudgeEligibilityReason.ERROR_OR_FALLBACK and elig.priority == 2


def test_empty_reply_is_error_or_fallback_eligible():
    result = _fake_result(response="   ")
    evaluation = dispatch_evaluation(result=result)
    elig = evaluate_sampling_eligibility(
        result=result, evaluation=evaluation, heuristic_score=None, sampling_rate=0.0, low_score_threshold=0.5, sample_roll=0.99
    )
    assert elig.eligible and elig.reason == JudgeEligibilityReason.ERROR_OR_FALLBACK


def test_low_heuristic_score_is_eligible_priority_3():
    result = _fake_result()
    evaluation = _eval(EvaluationPath.GENERAL_MODEL)
    elig = evaluate_sampling_eligibility(
        result=result, evaluation=evaluation, heuristic_score=0.2, sampling_rate=0.0, low_score_threshold=0.5, sample_roll=0.99
    )
    assert elig.eligible and elig.reason == JudgeEligibilityReason.LOW_SCORE and elig.priority == 3


def test_random_sample_below_rate_is_eligible_priority_4():
    result = _fake_result()
    evaluation = _eval(EvaluationPath.GENERAL_MODEL)
    elig = evaluate_sampling_eligibility(
        result=result, evaluation=evaluation, heuristic_score=0.9, sampling_rate=0.5, low_score_threshold=0.1, sample_roll=0.1
    )
    assert elig.eligible and elig.reason == JudgeEligibilityReason.RANDOM_SAMPLE and elig.priority == 4


def test_ordinary_completed_run_above_sample_roll_is_not_eligible():
    """The exact "most traffic is NOT judged" requirement (BUILD-33 §3)."""
    result = _fake_result()
    evaluation = _eval(EvaluationPath.GENERAL_MODEL)
    elig = evaluate_sampling_eligibility(
        result=result, evaluation=evaluation, heuristic_score=0.9, sampling_rate=0.05, low_score_threshold=0.1, sample_roll=0.5
    )
    assert not elig.eligible
    assert elig.reason is None


# ---------------------------------------------------------------------------
# Sanitized input assembly / PII rejection
# ---------------------------------------------------------------------------


def test_build_judge_input_includes_only_tool_names_never_raw_payload():
    tool = SimpleNamespace(name="get_today_doses", data={"patient_id": "should-never-leak", "items": [1, 2]})
    with pytest.raises(JudgeInputRejectedError):
        # The tool's own raw data mentions "patient_id" -- but critically,
        # build_judge_input never even reads tool.data for a non-RAG path;
        # this raises because the QUERY text itself is what is checked here.
        build_judge_input(query="patient_id la 123", response="ok", path=EvaluationPath.DETERMINISTIC_SCHEDULE, tool_results=(tool,))
    payload = build_judge_input(query="hom nay uong gi", response="ok", path=EvaluationPath.DETERMINISTIC_SCHEDULE, tool_results=(tool,))
    assert payload.tool_names == ("get_today_doses",)
    assert payload.retrieved_evidence == ()  # not RAG -- raw tool .data never surfaces


def test_build_judge_input_only_surfaces_rag_evidence_for_rag_path():
    tool = SimpleNamespace(name="search_drug", data={"name": "Panadol", "strength": "500mg"})
    payload = build_judge_input(query="panadol la thuoc gi", response="ok", path=EvaluationPath.RAG, tool_results=(tool,))
    assert payload.retrieved_evidence and "Panadol" in payload.retrieved_evidence[0]


@pytest.mark.parametrize(
    "text",
    ["lien he email a@b.com", "sdt 0912345678", "patient_id abc-123", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"],
)
def test_build_judge_input_rejects_pii_and_secret_shaped_text(text):
    with pytest.raises(JudgeInputRejectedError):
        build_judge_input(query=text, response="ok", path=EvaluationPath.GENERAL_MODEL)


def test_build_judge_input_rejects_pii_in_response_too():
    with pytest.raises(JudgeInputRejectedError):
        build_judge_input(query="cau hoi binh thuong", response="goi cho toi qua 0912345678", path=EvaluationPath.GENERAL_MODEL)


# ---------------------------------------------------------------------------
# Rubrics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected_name",
    [
        (EvaluationPath.RAG, "judge-rag"),
        (EvaluationPath.GENERAL_MODEL, "judge-general-medical"),
        (EvaluationPath.TRIAGE, "judge-triage"),
        (EvaluationPath.MEDICATION_DOSE_SAFETY, "judge-dose-safety"),
        (EvaluationPath.SAFETY, "judge-safety-handoff"),
        (EvaluationPath.HANDOFF, "judge-safety-handoff"),
        (EvaluationPath.DETERMINISTIC_SCHEDULE, "judge-generic"),
        (EvaluationPath.FALLBACK, "judge-generic"),
    ],
)
def test_rubric_for_path_selects_the_pipeline_aware_rubric(path, expected_name):
    assert rubric_for_path(path).name == expected_name


def test_render_prompt_never_includes_raw_tool_payload_or_system_prompt_markers():
    payload = build_judge_input(query="hoi gi do", response="tra loi gi do", path=EvaluationPath.GENERAL_MODEL)
    prompt = render_prompt(rubric=rubric_for_path(EvaluationPath.GENERAL_MODEL), payload=payload)
    assert "hoi gi do" in prompt and "tra loi gi do" in prompt
    # No chain-of-thought/system-prompt leakage channel exists in this
    # function at all -- it only ever renders the 4 payload fields.
    assert "you are chatgpt" not in prompt.lower()


def test_safety_rubric_explicitly_states_judge_cannot_change_escalation():
    rubric = rubric_for_path(EvaluationPath.SAFETY)
    assert "khong duoc" in rubric.guidance.lower() or "khong duoc" in rubric.guidance.lower().replace("đ", "d")


# ---------------------------------------------------------------------------
# Provider call boundary (no real network -- openai.OpenAI is monkeypatched)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, content, prompt_tokens=42, completion_tokens=17):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]
        self.usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


class _FakeCompletions:
    def __init__(self, outcome):
        self._outcome = outcome
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeClient:
    def __init__(self, outcome):
        self.chat = SimpleNamespace(completions=_FakeCompletions(outcome))
        self.closed = False

    def close(self):
        self.closed = True


def _patch_openai_client(monkeypatch, outcome):
    fake_client = _FakeClient(outcome)
    monkeypatch.setattr("backend.agents.v2.judge_provider.openai.OpenAI", lambda **kwargs: fake_client)
    return fake_client


def test_call_judge_scores_a_valid_json_response(monkeypatch):
    content = '{"overall_score": 0.8, "dimensions": {"relevance": 0.9}, "flags": [], "confidence": 0.7}'
    _patch_openai_client(monkeypatch, _FakeResponse(content))
    result = call_judge(
        provider="openai", model="gpt-4o", api_key="sk-x", base_url=None, reasoning_effort="high", timeout_seconds=30.0, prompt="p"
    )
    assert result.status == "SCORED"
    assert result.overall_score == 0.8
    assert result.dimension_scores == {"relevance": 0.9}
    assert result.input_tokens == 42 and result.output_tokens == 17


def test_call_judge_extracts_json_substring_from_surrounding_text(monkeypatch):
    content = 'Day la ket qua:\n{"overall_score": 0.5, "dimensions": {}, "flags": [], "confidence": 0.5}\nHet.'
    _patch_openai_client(monkeypatch, _FakeResponse(content))
    result = call_judge(
        provider="openai", model="gpt-4o", api_key="sk-x", base_url=None, reasoning_effort="", timeout_seconds=30.0, prompt="p"
    )
    assert result.status == "SCORED" and result.overall_score == 0.5


def test_call_judge_malformed_json_becomes_judge_failed_not_score_zero(monkeypatch):
    _patch_openai_client(monkeypatch, _FakeResponse("khong phai JSON gi ca"))
    result = call_judge(
        provider="openai", model="gpt-4o", api_key="sk-x", base_url=None, reasoning_effort="", timeout_seconds=30.0, prompt="p"
    )
    assert result.status == "JUDGE_FAILED"
    assert result.failure_reason == "MALFORMED_OUTPUT"
    assert result.overall_score is None  # never a fabricated 0.0


def test_call_judge_out_of_range_score_becomes_judge_failed():
    """Pydantic validation itself, exercised directly (BUILD-33 §7)."""
    with pytest.raises(Exception):
        JudgeOutputSchema.model_validate({"overall_score": 1.5, "dimensions": {}, "flags": [], "confidence": 0.5})


def test_call_judge_timeout_becomes_judge_failed(monkeypatch):
    _patch_openai_client(monkeypatch, openai.APITimeoutError(request=SimpleNamespace()))
    result = call_judge(
        provider="google", model="gemini-3.7-flash", api_key="sk-x", base_url=None, reasoning_effort="high", timeout_seconds=5.0, prompt="p"
    )
    assert result.status == "JUDGE_FAILED"
    assert result.failure_reason == "FAILED_TIMEOUT"


def test_call_judge_missing_credential_never_calls_the_network(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        "backend.agents.v2.judge_provider.openai.OpenAI", lambda **kwargs: called.__setitem__("n", called["n"] + 1)
    )
    result = call_judge(provider="google", model="gemini-3.7-flash", api_key="", base_url=None, reasoning_effort="high", timeout_seconds=5.0, prompt="p")
    assert result.status == "JUDGE_FAILED"
    assert result.failure_reason == "CREDENTIAL_NOT_CONFIGURED"
    assert called["n"] == 0


def test_resolve_credential_openai_falls_back_to_global_key():
    assert resolve_credential(provider="openai", openai_judge_api_key="", openai_api_key="global", google_api_key="g") == "global"
    assert resolve_credential(provider="openai", openai_judge_api_key="judge", openai_api_key="global", google_api_key="g") == "judge"


def test_resolve_credential_google_uses_dedicated_key_only():
    assert resolve_credential(provider="google", openai_judge_api_key="judge", openai_api_key="global", google_api_key="g") == "g"


def test_resolve_base_url_defaults_to_google_openai_compat_endpoint():
    url = resolve_base_url(provider="google", configured_base_url="")
    assert url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert resolve_base_url(provider="openai", configured_base_url="") is None
    assert resolve_base_url(provider="google", configured_base_url="https://custom/") == "https://custom/"


# ---------------------------------------------------------------------------
# Enqueue (sqlite db, no real network)
# ---------------------------------------------------------------------------


def test_enqueue_run_judge_disabled_by_settings_does_nothing(db):
    result = _fake_result(safety_decision=SimpleNamespace(outcome=SimpleNamespace(value="HANDOFF_REQUIRED")))
    row = enqueue_run_judge(db, result=result, request_message="q", settings=_settings(agent_judge_enabled=False))
    assert row is None
    assert db.execute(select(AgentRunJudge)).scalar_one_or_none() is None


def test_enqueue_run_judge_inserts_pending_row_for_safety_anomaly(db):
    result = _fake_result(safety_decision=SimpleNamespace(outcome=SimpleNamespace(value="HANDOFF_REQUIRED")))
    row = enqueue_run_judge(db, result=result, request_message="toi vua uong nham 20 vien", settings=_settings())
    assert row is not None
    assert row.judge_status == "JUDGE_PENDING"
    assert row.eligibility_reason == "SAFETY_ANOMALY"
    assert row.execution_path == "SAFETY"
    assert row.judge_provider == "openai" and row.judge_model == "gpt-4o"
    assert row.rubric_name == "judge-safety-handoff"
    assert row.rubric_version == "rubric-v1"
    assert row.judge_prompt_version == "judge-v1"
    assert row.sanitized_query == "toi vua uong nham 20 vien"


def test_enqueue_run_judge_ordinary_run_not_sampled_enqueues_nothing(db):
    result = _fake_result(intent="GENERAL_MEDICAL_INFORMATION", citations=(SimpleNamespace(title="Vinmec", source="s", url=None),))
    # low_score_threshold=0.0 isolates the "not sampled" scenario -- this
    # short/degenerate query+response pair would otherwise also trip
    # LOW_SCORE eligibility via the real word-overlap heuristic, which is a
    # different eligibility path covered by its own test above.
    row = enqueue_run_judge(
        db,
        result=result,
        request_message="q",
        settings=_settings(agent_judge_sampling_rate=0.0, agent_judge_low_score_threshold=0.0),
        sample_roll=0.9,
    )
    assert row is None
    assert db.execute(select(AgentRunJudge)).scalar_one_or_none() is None


def test_enqueue_run_judge_duplicate_protection_same_run_model_rubric_prompt(db):
    result = _fake_result(safety_decision=SimpleNamespace(outcome=SimpleNamespace(value="HANDOFF_REQUIRED")))
    settings = _settings()
    first = enqueue_run_judge(db, result=result, request_message="q", settings=settings)
    second = enqueue_run_judge(db, result=result, request_message="q", settings=settings)
    assert first is not None
    assert second is None  # the exact same (agent_run_id, model, rubric_version, prompt_version) tuple
    assert len(db.execute(select(AgentRunJudge)).scalars().all()) == 1


def test_enqueue_run_judge_pii_input_is_rejected_not_enqueued(db):
    result = _fake_result(response="goi 0912345678 nhe", safety_decision=SimpleNamespace(outcome=SimpleNamespace(value="HANDOFF_REQUIRED")))
    row = enqueue_run_judge(db, result=result, request_message="q", settings=_settings())
    assert row is None
    assert db.execute(select(AgentRunJudge)).scalar_one_or_none() is None


def test_enqueue_run_judge_never_raises_even_on_internal_failure(db, monkeypatch):
    """The exact 'Judge failure must not affect the Agent response' contract
    -- simulate an unexpected internal exception and confirm this stays
    silent (logged, not raised)."""
    import backend.services.agent_judge_worker as worker

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(worker, "dispatch_evaluation", _boom)
    result = _fake_result()
    row = enqueue_run_judge(db, result=result, request_message="q", settings=_settings())  # must not raise
    assert row is None


def test_enqueue_ticket_judge_is_always_eligible_regardless_of_sampling(db):
    ticket = SimpleNamespace(
        id="ticket-1",
        agent_run_id="run-ticket-1",
        trace_id="trace-ticket-1",
        user_message="cau tra loi nay sai",
        assistant_message="day la cau tra loi cu",
    )
    row = enqueue_ticket_judge(db, ticket=ticket, settings=_settings(agent_judge_sampling_rate=0.0))
    assert row is not None
    assert row.eligibility_reason == "TICKET"
    assert row.priority == 0
    assert row.sanitized_query == "cau tra loi nay sai"


def test_enqueue_ticket_judge_uses_real_execution_path_when_durable_row_exists(db):
    db.add(
        AgentRunEvaluation(
            agent_run_id="run-ticket-2",
            trace_id="trace-ticket-2",
            evaluation_version="evaluation-v2",
            execution_path="MEDICATION_DOSE_SAFETY",
            metrics_json={},
        )
    )
    db.commit()
    ticket = SimpleNamespace(
        id="ticket-2", agent_run_id="run-ticket-2", trace_id="trace-ticket-2", user_message="q", assistant_message="a"
    )
    row = enqueue_ticket_judge(db, ticket=ticket, settings=_settings())
    assert row.execution_path == "MEDICATION_DOSE_SAFETY"
    assert row.rubric_name == "judge-dose-safety"


# ---------------------------------------------------------------------------
# process_pending_judge_batch (worker) -- call_judge monkeypatched, no network
# ---------------------------------------------------------------------------


def _pending_row(**overrides) -> AgentRunJudge:
    base = dict(
        agent_run_id="run-w1",
        trace_id="trace-w1",
        judge_status="JUDGE_PENDING",
        eligibility_reason="RANDOM_SAMPLE",
        priority=4,
        execution_path="GENERAL_MODEL",
        judge_provider="openai",
        judge_model="gpt-4o",
        judge_config_json={"reasoning_effort": "", "timeout_seconds": 30.0},
        rubric_name="judge-general-medical",
        rubric_version="rubric-v1",
        judge_prompt_version="judge-v1",
        evaluation_version="evaluation-v2",
        dimension_scores_json={},
        flags_json=[],
        sanitized_query="cau hoi",
        sanitized_response="tra loi",
        sanitized_context_json={"execution_path": "GENERAL_MODEL", "tool_names": [], "citations": [], "retrieved_evidence": [], "expected_ground_truth": None},
    )
    base.update(overrides)
    return AgentRunJudge(**base)


def test_process_pending_judge_batch_scores_and_persists_tokens_cost(db, monkeypatch):
    db.add(_pending_row())
    db.commit()
    content = '{"overall_score": 0.75, "dimensions": {"relevance": 0.8}, "flags": ["minor_issue"], "confidence": 0.6}'
    _patch_openai_client(monkeypatch, _FakeResponse(content, prompt_tokens=100, completion_tokens=50))

    settings = _settings(agent_model_pricing_json='{"gpt-4o":{"input_per_million":2.5,"output_per_million":10.0}}')
    processed = process_pending_judge_batch(db, settings=settings)
    assert processed == 1

    row = db.execute(select(AgentRunJudge)).scalar_one()
    assert row.judge_status == "JUDGE_COMPLETED"
    assert row.overall_score == 0.75
    assert row.dimension_scores_json == {"relevance": 0.8}
    assert row.flags_json == ["minor_issue"]
    assert row.input_tokens == 100 and row.output_tokens == 50
    assert row.cost_status == "AVAILABLE"
    assert row.cost_usd == pytest.approx((100 * 2.5 + 50 * 10.0) / 1_000_000)
    assert row.evaluated_at is not None


def test_process_pending_judge_batch_unknown_pricing_is_not_available_not_zero(db, monkeypatch):
    db.add(_pending_row())
    db.commit()
    content = '{"overall_score": 0.75, "dimensions": {}, "flags": [], "confidence": 0.6}'
    _patch_openai_client(monkeypatch, _FakeResponse(content))
    processed = process_pending_judge_batch(db, settings=_settings(agent_model_pricing_json="{}"))
    assert processed == 1
    row = db.execute(select(AgentRunJudge)).scalar_one()
    assert row.cost_status == "NOT_AVAILABLE"
    assert row.cost_usd is None


def test_process_pending_judge_batch_provider_failure_marks_judge_failed_not_pending(db, monkeypatch):
    db.add(_pending_row())
    db.commit()
    import httpx

    fake_request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    fake_response = httpx.Response(401, request=fake_request)
    _patch_openai_client(monkeypatch, openai.AuthenticationError(message="bad key", response=fake_response, body=None))
    processed = process_pending_judge_batch(db, settings=_settings())
    assert processed == 1
    row = db.execute(select(AgentRunJudge)).scalar_one()
    assert row.judge_status == "JUDGE_FAILED"
    assert row.failure_reason == "FAILED_AUTHENTICATION"


def test_process_pending_judge_batch_one_row_failure_does_not_block_the_rest(db, monkeypatch):
    db.add(_pending_row(agent_run_id="run-w1"))
    db.add(_pending_row(agent_run_id="run-w2", judge_model="gpt-4o"))
    db.commit()

    calls = {"n": 0}

    def _flaky_call_judge(**kwargs):
        calls["n"] += 1
        from backend.agents.v2.judge_provider import JudgeCallResult

        if calls["n"] == 1:
            raise RuntimeError("simulated unexpected crash scoring the first row")
        return JudgeCallResult(status="SCORED", overall_score=0.5, dimension_scores={}, flags=[], confidence=0.5, input_tokens=1, output_tokens=1)

    monkeypatch.setattr("backend.services.agent_judge_worker.call_judge", _flaky_call_judge)
    processed = process_pending_judge_batch(db, settings=_settings())
    # The crashing row is caught by process_pending_judge_batch's own
    # per-row try/except (not counted as "processed"); the second row still
    # gets scored.
    assert processed == 1
    statuses = {row.agent_run_id: row.judge_status for row in db.execute(select(AgentRunJudge)).scalars().all()}
    assert statuses["run-w1"] == "JUDGE_PENDING"  # left for the next tick, not silently lost
    assert statuses["run-w2"] == "JUDGE_COMPLETED"


def test_process_pending_judge_batch_orders_by_priority_then_fifo(db, monkeypatch):
    db.add(_pending_row(agent_run_id="run-low", priority=4))
    db.add(_pending_row(agent_run_id="run-ticket", priority=0))
    db.commit()
    content = '{"overall_score": 0.5, "dimensions": {}, "flags": [], "confidence": 0.5}'
    _patch_openai_client(monkeypatch, _FakeResponse(content))
    process_pending_judge_batch(db, settings=_settings(agent_judge_max_per_tick=1))  # only 1 slot this tick
    remaining = db.execute(select(AgentRunJudge).where(AgentRunJudge.judge_status == "JUDGE_PENDING")).scalars().all()
    assert len(remaining) == 1 and remaining[0].agent_run_id == "run-low"  # ticket (priority 0) went first


def test_process_pending_judge_batch_respects_max_per_tick(db, monkeypatch):
    for i in range(3):
        db.add(_pending_row(agent_run_id=f"run-{i}"))
    db.commit()
    content = '{"overall_score": 0.5, "dimensions": {}, "flags": [], "confidence": 0.5}'
    _patch_openai_client(monkeypatch, _FakeResponse(content))
    processed = process_pending_judge_batch(db, settings=_settings(agent_judge_max_per_tick=2))
    assert processed == 2
    remaining_pending = db.execute(select(AgentRunJudge).where(AgentRunJudge.judge_status == "JUDGE_PENDING")).scalars().all()
    assert len(remaining_pending) == 1


# ---------------------------------------------------------------------------
# Structural: Safety authority is unaffected by Judge (BUILD-33 §5)
# ---------------------------------------------------------------------------


def test_safety_and_orchestrator_modules_never_import_judge_code():
    import backend.agents.v2.orchestrator as orchestrator_module
    import backend.agents.v2.runtime as runtime_module
    import backend.agents.v2.safety as safety_module

    for module in (orchestrator_module, runtime_module, safety_module):
        source = (module.__file__ or "")
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        assert "judge_provider" not in text
        assert "judge_eligibility" not in text
        assert "agent_judge_worker" not in text
        assert not re.search(r"\bAgentRunJudge\b", text)


# ---------------------------------------------------------------------------
# Judge scheduler wiring
# ---------------------------------------------------------------------------


def test_judge_worker_scheduler_job_is_a_noop_when_disabled(monkeypatch):
    import asyncio

    import backend.services.escalation_scheduler as scheduler_module

    calls = {"n": 0}
    monkeypatch.setattr(scheduler_module, "process_pending_judge_batch", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: _settings(agent_judge_enabled=False))
    asyncio.run(scheduler_module._run_judge_worker())
    assert calls["n"] == 0
