import asyncio
from types import SimpleNamespace

from backend.agents.v2.evaluation_v2 import EvaluationPath, FallbackClassification, MetricStatus, dispatch_evaluation
from backend.agents.v2.retrieval_eval import hit_at_k, mrr_at_k, ndcg_at_k
from backend.api import rag_monitoring_routes


def _result(*, intent, status="COMPLETED", tools=(), citations=(), safety=None, handoff=None):
    return SimpleNamespace(
        intent=SimpleNamespace(value=intent),
        status=SimpleNamespace(value=status),
        tool_results=tools,
        citations=citations,
        safety_decision=safety,
        handoff_result=handoff,
    )


def test_rag_with_ground_truth_capable_contract_marks_live_ir_unavailable_not_zero():
    evaluation = dispatch_evaluation(result=_result(intent="GENERAL_MEDICAL_INFORMATION", citations=(object(),)))

    assert evaluation.path is EvaluationPath.RAG
    assert evaluation.metrics["hit_rate_at_10"].status is MetricStatus.NOT_AVAILABLE
    assert evaluation.metrics["mrr_at_10"].status is MetricStatus.NOT_AVAILABLE
    assert evaluation.metrics["ndcg_at_10"].status is MetricStatus.NOT_AVAILABLE
    assert evaluation.metrics["faithfulness"].source == "heuristic"


def test_real_ir_formulas_are_independent_at_rank_two():
    retrieved, relevant = ("A", "B", "C"), {"B"}
    assert hit_at_k(retrieved, relevant, k=3) == 1.0
    assert mrr_at_k(retrieved, relevant, k=3) == 0.5
    assert 0 < ndcg_at_k(retrieved, relevant, k=3) < 1.0


def test_schedule_tool_safety_handoff_fallback_and_general_choose_own_evaluators():
    schedule = dispatch_evaluation(result=_result(intent="TODAY_DOSES"))
    tool = dispatch_evaluation(result=_result(intent="PRESCRIPTION_INFORMATION", tools=(SimpleNamespace(name="get_today_doses"),)))
    drug = dispatch_evaluation(result=_result(intent="DRUG_INFORMATION", tools=(SimpleNamespace(name="get_drug_info"),)))
    safety = dispatch_evaluation(result=_result(intent="ACUTE_DANGER_ESCALATION", safety=object()))
    handoff = dispatch_evaluation(result=_result(intent="DOCTOR_REVIEW", handoff=object()))
    fallback = dispatch_evaluation(result=_result(intent="GENERAL_CONVERSATION", status="FAILED"))
    general = dispatch_evaluation(result=_result(intent="GENERAL_CONVERSATION"))

    assert schedule.path is EvaluationPath.DETERMINISTIC_SCHEDULE
    assert schedule.metrics["mrr_at_10"].status is MetricStatus.NOT_APPLICABLE
    assert tool.path is EvaluationPath.DETERMINISTIC_TOOL
    assert drug.path is EvaluationPath.DRUG_LOOKUP
    assert safety.path is EvaluationPath.SAFETY
    assert handoff.path is EvaluationPath.HANDOFF
    assert fallback.path is EvaluationPath.FALLBACK
    assert fallback.fallback_classification is FallbackClassification.FALLBACK_NOT_EVALUATED
    assert general.path is EvaluationPath.GENERAL_MODEL


def test_safety_evidence_wins_when_safety_escalates_to_handoff():
    evaluation = dispatch_evaluation(
        result=_result(intent="ACUTE_DANGER_ESCALATION", safety=object(), handoff=object())
    )

    assert evaluation.path is EvaluationPath.SAFETY
    assert evaluation.metrics["safety_path_completion"].status is MetricStatus.AVAILABLE


def test_out_of_scope_fallback_is_explicitly_expected():
    evaluation = dispatch_evaluation(result=_result(intent="OUT_OF_SCOPE_REQUEST"))

    assert evaluation.path is EvaluationPath.OUT_OF_SCOPE
    assert evaluation.fallback_classification is FallbackClassification.FALLBACK_EXPECTED


def test_aggregation_uses_available_metric_denominator_not_total_traffic():
    applicable_rag = SimpleNamespace(
        metadata={"evaluation_v2": {"metrics": {"faithfulness": {"status": "AVAILABLE"}}}},
        scores={"answer_faithfulness": 0.8},
    )
    schedule_with_zero_like_score = SimpleNamespace(
        metadata={"evaluation_v2": {"metrics": {"faithfulness": {"status": "NOT_APPLICABLE"}}}},
        scores={"answer_faithfulness": 0.0},
    )
    safety = SimpleNamespace(metadata={"evaluation_v2": {"metrics": {}}}, scores={})

    assert rag_monitoring_routes._available_metric_scores(
        [applicable_rag, schedule_with_zero_like_score, safety], "faithfulness"
    ) == [0.8]


def test_live_retrieval_api_returns_na_with_provenance_not_aliased_scores(monkeypatch):
    rag_trace = SimpleNamespace(
        metadata={"chatbot_version": "agent-v2", "evaluation_v2": {"execution_path": "RAG"}},
        scores={"answer_faithfulness": 0.9, "answer_relevance": 0.9},
        input={"message": "medical question"},
        status="success",
        start_time=0.0,
    )
    schedule_trace = SimpleNamespace(
        metadata={"chatbot_version": "agent-v2", "evaluation_v2": {"execution_path": "DETERMINISTIC_SCHEDULE"}},
        scores={}, input={"message": "today doses"}, status="success", start_time=0.0,
    )

    class _Query:
        def count(self):
            return 7

    class _Db:
        def query(self, _model):
            return _Query()

    monkeypatch.setattr(rag_monitoring_routes, "get_local_traces", lambda: [rag_trace, schedule_trace])
    payload = asyncio.run(
        rag_monitoring_routes.get_rag_retrieval(
            db=_Db(), admin=SimpleNamespace(), filters=("agent-v2", None, None)
        )
    )

    assert payload["metrics"]["evaluated_sample_count"] == 1
    assert payload["metrics"]["hit_rate_10"] is None
    assert payload["metrics"]["mrr_10"] is None
    assert payload["metrics"]["ndcg_10"] is None
    assert payload["metric_provenance"]["mrr_10"]["reason"] == "no_relevance_ground_truth"


def test_admin_overview_exposes_only_applicable_metric_denominators(monkeypatch):
    now = 1_700_000_000.0
    rag_trace = SimpleNamespace(
        metadata={
            "chatbot_version": "agent-v2",
            "evaluation_v2": {"metrics": {
                "faithfulness": {"status": "AVAILABLE"},
                "answer_relevance": {"status": "AVAILABLE"},
            }},
        },
        scores={"answer_faithfulness": 0.8, "answer_relevance": 0.6},
        duration_ms=10.0, start_time=now, status="success",
    )
    schedule_trace = SimpleNamespace(
        metadata={"chatbot_version": "agent-v2", "evaluation_v2": {"metrics": {
            "faithfulness": {"status": "NOT_APPLICABLE"},
            "answer_relevance": {"status": "NOT_APPLICABLE"},
        }}},
        scores={"answer_faithfulness": 0.0, "answer_relevance": 0.0},
        duration_ms=10.0, start_time=now, status="success",
    )
    safety_trace = SimpleNamespace(
        metadata={"chatbot_version": "agent-v2", "evaluation_v2": {"metrics": {}}},
        scores={}, duration_ms=10.0, start_time=now, status="success",
    )

    class _Query:
        def all(self):
            return []

    class _Scalars:
        def all(self):
            return []

    class _ExecuteResult:
        def scalars(self):
            return _Scalars()

    class _Db:
        def query(self, _model):
            return _Query()

        # BUILD-32: rag_monitoring_routes now also queries the durable
        # AgentRun table (backend.api.rag_monitoring_routes._agent_run_query)
        # for real cost/timeout aggregates -- this fake stands in for that
        # too, with no rows (same "no data yet" shape `_Query.all()` above
        # already models).
        def execute(self, _stmt):
            return _ExecuteResult()

    monkeypatch.setattr(rag_monitoring_routes, "get_local_traces", lambda: [rag_trace, schedule_trace, safety_trace])
    payload = asyncio.run(
        rag_monitoring_routes.get_rag_health(
            db=_Db(), admin=SimpleNamespace(), filters=("agent-v2", None, None)
        )
    )

    assert payload["sample_size"] == 3
    assert payload["kpis"]["faithfulness"] == 0.8
    assert payload["kpis"]["faithfulness_sample_count"] == 1
    assert payload["kpis"]["answer_relevance"] == 0.6
    assert payload["kpis"]["answer_relevance_sample_count"] == 1
    # No AgentRun rows in this fake -- honest NOT_AVAILABLE, never a
    # fabricated 0.0 (BUILD-32).
    assert payload["kpis"]["cost_per_query"] is None
    assert payload["metric_provenance"]["cost_per_query"]["status"] == "NOT_AVAILABLE"
