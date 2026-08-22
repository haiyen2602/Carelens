import pytest

from backend.agents.v2.deepeval_judge import (
    JudgeEvaluationInput,
    JudgeMetricName,
    PublicContextReference,
    TrackingGPT4oJudge,
    score_metrics,
)


class _Metric:
    def __init__(self, score=0.8, cost=0.01, fails=False):
        self.score = score
        self.evaluation_cost = cost
        self.fails = fails

    def measure(self, _case):
        if self.fails:
            raise RuntimeError("provider failure")


def _input(*, contexts=("public medicine context",), expected_no_result=False):
    return JudgeEvaluationInput(
        case_id="case-1",
        query="Agiclovir dùng để làm gì?",
        answer="Thông tin dựa trên nguồn thuốc công khai.",
        context_references=tuple(PublicContextReference(f"chunk-{index}", "drug-1", "cong_dung") for index, _ in enumerate(contexts)),
        contexts=contexts,
        expected_no_result=expected_no_result,
    )


def _metrics(**overrides):
    return {name: overrides.get(name, _Metric()) for name in JudgeMetricName}


def test_scores_all_required_metrics_and_retains_costs():
    scores = score_metrics(_input(), test_case=object(), metrics=_metrics())
    assert [item.metric for item in scores] == list(JudgeMetricName)
    assert all(item.status == "SCORED" and item.score == 0.8 and item.evaluation_cost_usd == 0.01 for item in scores)


def test_missing_context_is_not_a_pass_for_expected_evidence_but_is_explicitly_not_applicable_for_no_result():
    failed = score_metrics(_input(contexts=()), test_case=object(), metrics=_metrics())
    no_result = score_metrics(_input(contexts=(), expected_no_result=True), test_case=object(), metrics=_metrics())
    assert {item.status for item in failed} == {"FAILED_MISSING_CONTEXT"}
    assert {item.status for item in no_result} == {"NOT_APPLICABLE_NO_EVIDENCE"}


def test_pii_phi_and_judge_failures_are_fail_closed():
    with pytest.raises(ValueError, match="JUDGE_PII_PHI_INPUT_REJECTED"):
        _input(contexts=("contact a@b.com",))
    scores = score_metrics(_input(), test_case=object(), metrics=_metrics(**{JudgeMetricName.FAITHFULNESS: _Metric(fails=True)}))
    assert next(item for item in scores if item.metric is JudgeMetricName.FAITHFULNESS).status == "FAILED_RUNTIMEERROR"


def test_transport_oserror_is_explicit_and_never_a_score():
    class _TransportFailure:
        score = 0.0
        evaluation_cost = None

        def measure(self, _case):
            raise OSError("transport handle unavailable")

    scores = score_metrics(
        _input(),
        test_case=object(),
        metrics=_metrics(**{JudgeMetricName.FAITHFULNESS: _TransportFailure()}),
    )
    failed = next(item for item in scores if item.metric is JudgeMetricName.FAITHFULNESS)
    assert (failed.status, failed.score, failed.evaluation_cost_usd) == ("FAILED_TRANSPORT_OSERROR", None, None)


def test_tracking_judge_is_a_native_deepeval_gpt_model_without_making_a_request():
    from deepeval.metrics.utils import is_native_model

    judge = TrackingGPT4oJudge(api_key="test-key", model="gpt-4o")
    assert is_native_model(judge) is True


def test_tracking_judge_reuses_and_closes_one_sdk_client(monkeypatch):
    seen = {"created": 0, "closed": 0}

    class _Client:
        def close(self):
            seen["closed"] += 1

    def create_client(**_kwargs):
        seen["created"] += 1
        return _Client()

    monkeypatch.setattr("backend.agents.v2.deepeval_judge.openai.OpenAI", create_client)
    judge = TrackingGPT4oJudge(api_key="test-key", model="gpt-4o")
    assert judge.load_model() is judge.load_model()
    assert seen == {"created": 1, "closed": 0}
    judge.close()
    assert seen == {"created": 1, "closed": 1}


def test_single_judge_round_reports_variance_as_unavailable_not_zero():
    from scripts.agent_v2.run_deepeval_rag_judge import _variance

    assert _variance([]) is None
    assert _variance([0.5]) is None
    assert _variance([0.4, 0.6]) == pytest.approx(0.01)
