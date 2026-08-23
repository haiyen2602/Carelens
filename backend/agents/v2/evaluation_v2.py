"""Pipeline-aware, evidence-only Evaluation V2 classification.

This module has no Agent control-flow authority.  It classifies an already
completed run and describes which metrics are applicable; callers decide how
to persist or present the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EvaluationPath(StrEnum):
    RAG = "RAG"
    DETERMINISTIC_SCHEDULE = "DETERMINISTIC_SCHEDULE"
    DETERMINISTIC_TOOL = "DETERMINISTIC_TOOL"
    DRUG_LOOKUP = "DRUG_LOOKUP"
    SAFETY = "SAFETY"
    HANDOFF = "HANDOFF"
    GENERAL_MODEL = "GENERAL_MODEL"
    FALLBACK = "FALLBACK"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class MetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class FallbackClassification(StrEnum):
    FALLBACK_EXPECTED = "FALLBACK_EXPECTED"
    FALLBACK_SUSPECT = "FALLBACK_SUSPECT"
    FALLBACK_NOT_EVALUATED = "FALLBACK_NOT_EVALUATED"


@dataclass(frozen=True)
class MetricDisposition:
    status: MetricStatus
    source: str
    reason: str | None = None

    def as_dict(self) -> dict[str, str]:
        value = {"status": self.status.value, "source": self.source}
        if self.reason:
            value["reason"] = self.reason
        return value


@dataclass(frozen=True)
class EvaluationResult:
    path: EvaluationPath
    metrics: dict[str, MetricDisposition]
    fallback_classification: FallbackClassification | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "evaluator_version": "evaluation-v2",
            "execution_path": self.path.value,
            "metrics": {name: disposition.as_dict() for name, disposition in self.metrics.items()},
        }
        if self.fallback_classification is not None:
            payload["fallback_classification"] = self.fallback_classification.value
        return payload


_SCHEDULE_INTENTS = {"MEDICATION_HISTORY", "TODAY_DOSES", "UPCOMING_DOSES", "DOSE_STATUS"}


def dispatch_evaluation(*, result: Any) -> EvaluationResult:
    """Classify only from completed-run evidence, never user message text."""
    intent = getattr(getattr(result, "intent", None), "value", getattr(result, "intent", ""))
    status = getattr(getattr(result, "status", None), "value", getattr(result, "status", ""))
    tools = tuple(getattr(result, "tool_results", ()) or ())
    citations = tuple(getattr(result, "citations", ()) or ())
    safety = getattr(result, "safety_decision", None)
    handoff = getattr(result, "handoff_result", None)
    tool_names = {str(getattr(item, "name", "")) for item in tools}

    # A safety decision is the controlling execution evidence even when its
    # prescribed outcome created a handoff. A standalone doctor-review
    # handoff (without a safety decision) remains a HANDOFF evaluation.
    if safety is not None or intent in {"ACUTE_DANGER_ESCALATION", "MISSED_DOSE", "DELAYED_DOSE"}:
        path = EvaluationPath.SAFETY
    elif handoff is not None:
        path = EvaluationPath.HANDOFF
    elif intent in _SCHEDULE_INTENTS:
        path = EvaluationPath.DETERMINISTIC_SCHEDULE
    elif intent == "OUT_OF_SCOPE_REQUEST":
        path = EvaluationPath.OUT_OF_SCOPE
    elif intent == "DRUG_INFORMATION" and tool_names:
        path = EvaluationPath.DRUG_LOOKUP
    elif intent == "GENERAL_MEDICAL_INFORMATION" and citations:
        path = EvaluationPath.RAG
    elif tool_names:
        path = EvaluationPath.DETERMINISTIC_TOOL
    elif status != "COMPLETED":
        path = EvaluationPath.FALLBACK
    else:
        path = EvaluationPath.GENERAL_MODEL

    not_applicable = MetricDisposition(MetricStatus.NOT_APPLICABLE, "operational", "execution_path_not_retrieval")
    not_available = MetricDisposition(MetricStatus.NOT_AVAILABLE, "golden", "no_relevance_ground_truth")
    metrics: dict[str, MetricDisposition] = {
        name: not_applicable
        for name in ("hit_rate_at_10", "mrr_at_10", "ndcg_at_10", "precision_at_10")
    }
    metrics["faithfulness"] = not_applicable
    metrics["answer_relevance"] = not_applicable

    fallback_classification: FallbackClassification | None = None
    if path is EvaluationPath.RAG:
        for name in ("hit_rate_at_10", "mrr_at_10", "ndcg_at_10", "precision_at_10"):
            metrics[name] = not_available
        metrics["faithfulness"] = MetricDisposition(MetricStatus.AVAILABLE, "heuristic")
        metrics["answer_relevance"] = MetricDisposition(MetricStatus.AVAILABLE, "heuristic")
    elif path in {EvaluationPath.DETERMINISTIC_SCHEDULE, EvaluationPath.DETERMINISTIC_TOOL, EvaluationPath.DRUG_LOOKUP}:
        metrics["tool_correctness"] = MetricDisposition(MetricStatus.AVAILABLE, "operational")
    elif path is EvaluationPath.SAFETY:
        metrics["safety_path_completion"] = MetricDisposition(MetricStatus.AVAILABLE, "operational")
    elif path is EvaluationPath.HANDOFF:
        metrics["handoff_created"] = MetricDisposition(MetricStatus.AVAILABLE, "operational")
    elif path is EvaluationPath.FALLBACK:
        metrics["fallback_classification"] = MetricDisposition(MetricStatus.AVAILABLE, "operational")
        fallback_classification = (
            FallbackClassification.FALLBACK_SUSPECT
            if intent in {"GENERAL_MEDICAL_INFORMATION", "DRUG_INFORMATION", "PRESCRIPTION_INFORMATION"}
            else FallbackClassification.FALLBACK_NOT_EVALUATED
        )
    elif path is EvaluationPath.OUT_OF_SCOPE:
        metrics["fallback_classification"] = MetricDisposition(MetricStatus.AVAILABLE, "operational")
        fallback_classification = FallbackClassification.FALLBACK_EXPECTED
    elif path is EvaluationPath.GENERAL_MODEL:
        metrics["answer_relevance"] = MetricDisposition(MetricStatus.AVAILABLE, "heuristic")

    return EvaluationResult(path, metrics, fallback_classification)
