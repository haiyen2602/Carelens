"""BUILD-33: Judge eligibility + priority classification (pure, no I/O).

"Judge KHONG chay 100% traffic" (§3) -- most COMPLETED runs get evaluated by
none of these triggers and are never enqueued at all. Priority order for
queue PROCESSING (§3/worker pickup, lower number = processed first):

    ticket / golden (0) > safety anomaly (1) > error/fallback/empty reply (2)
    > low score (3) > random sample (4)

Ticket and golden are deliberate, explicit triggers raised by their own
call sites (``backend.services.agent_feedback.create_ticket``, and a future
BUILD-35 golden-set runner) -- ``evaluate_sampling_eligibility`` below only
ever decides among the other three (a run is never BOTH "ticket" and
"sampled"; the ticket call site enqueues directly and does not consult this
function).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.agents.v2.evaluation_v2 import EvaluationPath, EvaluationResult


class JudgeEligibilityReason(StrEnum):
    TICKET = "TICKET"
    GOLDEN = "GOLDEN"
    SAFETY_ANOMALY = "SAFETY_ANOMALY"
    ERROR_OR_FALLBACK = "ERROR_OR_FALLBACK"
    LOW_SCORE = "LOW_SCORE"
    RANDOM_SAMPLE = "RANDOM_SAMPLE"


PRIORITY_BY_REASON: dict[JudgeEligibilityReason, int] = {
    JudgeEligibilityReason.TICKET: 0,
    JudgeEligibilityReason.GOLDEN: 0,
    JudgeEligibilityReason.SAFETY_ANOMALY: 1,
    JudgeEligibilityReason.ERROR_OR_FALLBACK: 2,
    JudgeEligibilityReason.LOW_SCORE: 3,
    JudgeEligibilityReason.RANDOM_SAMPLE: 4,
}


@dataclass(frozen=True)
class JudgeEligibility:
    eligible: bool
    reason: JudgeEligibilityReason | None = None
    priority: int = PRIORITY_BY_REASON[JudgeEligibilityReason.RANDOM_SAMPLE]


def _explicit(reason: JudgeEligibilityReason) -> JudgeEligibility:
    return JudgeEligibility(eligible=True, reason=reason, priority=PRIORITY_BY_REASON[reason])


def ticket_eligibility() -> JudgeEligibility:
    """Always eligible -- a patient's own report is a deliberate trigger,
    never subject to sampling (BUILD-33 §3/§11)."""

    return _explicit(JudgeEligibilityReason.TICKET)


def golden_eligibility() -> JudgeEligibility:
    """Hook for BUILD-35's golden-set continuous-evaluation runner. Not
    invoked by anything in this build -- BUILD-35 is not yet implemented."""

    return _explicit(JudgeEligibilityReason.GOLDEN)


def evaluate_sampling_eligibility(
    *,
    result: Any,
    evaluation: EvaluationResult,
    heuristic_score: float | None,
    sampling_rate: float,
    low_score_threshold: float,
    sample_roll: float,
) -> JudgeEligibility:
    """Decide eligibility from real, already-computed execution evidence
    only -- never from user message text, and never twice for the same
    run+reason class (duplicate protection is enforced at the DB layer, see
    ``AgentRunJudge``'s unique index, not here).

    ``sample_roll`` is caller-supplied (real call sites pass
    ``random.random()``) so this stays a pure, deterministically-testable
    function -- same idiom as ``backend.services.escalation_reminder.
    is_reminder_due``.
    """

    if evaluation.path in (EvaluationPath.SAFETY, EvaluationPath.HANDOFF):
        return _explicit(JudgeEligibilityReason.SAFETY_ANOMALY)

    error_code = getattr(result, "error_code", None)
    # Same definition BUILD-32 stamps onto the durable `AgentRun.empty_reply`
    # column (backend.api.agent_v2_routes._persist_durable_trace) -- not
    # reimported from there to keep this module free of any agent_v2_routes
    # dependency, but deliberately identical logic.
    empty_reply = not str(getattr(result, "response", "") or "").strip()
    if error_code is not None or evaluation.path is EvaluationPath.FALLBACK or empty_reply:
        return _explicit(JudgeEligibilityReason.ERROR_OR_FALLBACK)

    if heuristic_score is not None and heuristic_score < low_score_threshold:
        return _explicit(JudgeEligibilityReason.LOW_SCORE)

    if sampling_rate > 0.0 and sample_roll < sampling_rate:
        return _explicit(JudgeEligibilityReason.RANDOM_SAMPLE)

    return JudgeEligibility(eligible=False)


__all__ = [
    "JudgeEligibility",
    "JudgeEligibilityReason",
    "PRIORITY_BY_REASON",
    "evaluate_sampling_eligibility",
    "golden_eligibility",
    "ticket_eligibility",
]
