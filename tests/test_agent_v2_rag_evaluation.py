from backend.agents.v2.rag_evaluation import (
    GoldenRagCase,
    RagEvaluationGroup,
    RagEvaluationVersions,
    bleu_4,
    describe_latency,
    empirical_performance_gate,
    evaluate_embedding_drift,
    evaluate_golden_rag,
    evaluate_release_gate,
    rouge_l_f1,
)


def _versions():
    return RagEvaluationVersions(
        corpus_version="corpus-v1",
        corpus_manifest_hash="ABC",
        chunking_version="chunks-v1",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        index_version="pgvector-hnsw-cosine-v1",
        retrieval_version="lexical-pg-trgm-v1",
        generation_version="deterministic-grounded-template-v1",
        prompt_version="none-build-14",
    )


def test_golden_evaluation_scores_retrieval_generation_and_no_result_without_a_model():
    found = GoldenRagCase("found", RagEvaluationGroup.EXACT_DRUG, "drug", ("drug-1",), "found")
    missing = GoldenRagCase("missing", RagEvaluationGroup.NO_RESULT, "unknown", (), "no result", True)

    summary = evaluate_golden_rag(
        (found, missing),
        retrieve=lambda case: ("drug-1",) if case.case_id == "found" else (),
        generate=lambda case, _ids: case.expected_generation,
        latency_ms=lambda _case: 2.0,
        versions=_versions(),
    )

    assert summary.retrieval.hit_at_10 == 1.0
    assert summary.retrieval.mrr_at_10 == 1.0
    assert summary.retrieval.ndcg_at_10 == 1.0
    assert summary.retrieval.precision_at_k == 0.2
    assert summary.retrieval.map_at_10 == 1.0
    assert summary.generation.exact_match == 1.0
    assert summary.no_result_accuracy == 1.0
    assert summary.input_tokens == summary.output_tokens == 0
    assert summary.estimated_cost_usd == 0.0


def test_natural_language_paracetamol_regression_is_a_real_recall_failure_not_a_pass():
    paracetamol = GoldenRagCase(
        "natural-paracetamol-finding",
        RagEvaluationGroup.NATURAL_LANGUAGE,
        "Thuốc Paracetamol Kabi có tác dụng hạ sốt không?",
        ("paracetamol-kabi",),
        "Đã tìm thấy Paracetamol Kabi.",
    )
    summary = evaluate_golden_rag(
        (paracetamol,),
        retrieve=lambda _case: (),
        generate=lambda _case, _ids: "Không tìm thấy nguồn thuốc phù hợp.",
        versions=_versions(),
    )

    assert summary.retrieval.hit_at_10 == 0.0
    assert summary.generation.exact_match == 0.0
    assert summary.results[0].no_result_passed is False


def test_generation_metrics_are_dependency_free_and_deterministic():
    assert rouge_l_f1("Paracetamol Kabi", "Paracetamol Kabi") == 1.0
    assert bleu_4("Paracetamol Kabi", "Paracetamol Kabi") == 1.0
    assert 0 < rouge_l_f1("Paracetamol", "Paracetamol Kabi") < 1
    assert 0 < bleu_4("Paracetamol", "Paracetamol Kabi") < 1


def test_embedding_identity_drift_and_release_gate_fail_closed_against_measured_baseline():
    case = GoldenRagCase("found", RagEvaluationGroup.EXACT_DRUG, "drug", ("drug-1",), "found")
    baseline = evaluate_golden_rag(
        (case,), retrieve=lambda _case: ("drug-1",), generate=lambda item, _ids: item.expected_generation,
        latency_ms=lambda _case: 1.0, versions=_versions(),
    )
    regressed = evaluate_golden_rag(
        (case,), retrieve=lambda _case: (), generate=lambda _item, _ids: "not found",
        latency_ms=lambda _case: 2.0, versions=_versions(),
    )
    drifted = RagEvaluationVersions(**{**_versions().__dict__, "embedding_dimensions": 3072})

    assert evaluate_embedding_drift(_versions(), _versions()).passed is True
    assert evaluate_embedding_drift(_versions(), drifted).reason_codes == ("EMBEDDING_DIMENSION_DRIFT",)
    gate = evaluate_release_gate(baseline, regressed)
    assert gate.passed is False
    assert "HIT_AT_10_REGRESSION" in gate.failures


def test_measured_performance_envelope_distinguishes_noise_from_a_real_shift_without_a_guessed_margin():
    distribution = describe_latency((100.0, 110.0, 120.0, 130.0))
    assert distribution.p50_ms == 120.0
    assert distribution.p99_ms == 130.0
    assert distribution.spread_ms == 30.0
    assert distribution.variance_ms2 == 125.0

    stable = empirical_performance_gate(
        stored_baseline_p95_ms=120.0,
        baseline_run_p95_ms=(110.0, 120.0, 130.0),
        candidate_run_p95_ms=(115.0, 125.0, 135.0),
    )
    shifted = empirical_performance_gate(
        stored_baseline_p95_ms=120.0,
        baseline_run_p95_ms=(110.0, 120.0, 130.0),
        candidate_run_p95_ms=(160.0, 170.0, 180.0),
    )

    assert stable.passed is True
    assert shifted.passed is False
    assert "P95_COHORT_NO_OVERLAP" in shifted.failures
