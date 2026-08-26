"""BUILD-42: Answerability Gate.

Structured, deterministic decision between three outcomes -- ANSWERABLE,
NEED_MORE_INFO, NEED_DOCTOR -- for the cases where the existing pipeline
today either silently declines (Cluster B honest-decline, BUILD-38) or asks
the same fixed clarification forever with no bounded escalation.

Explicitly NOT decided here: whether Safety must handle a message at all
(ACUTE_DANGER_ESCALATION/POSSIBLE_OVERDOSE/dose-unresolved keep their own,
unrelated code path in orchestrator.py and are never routed through this
module -- see BUILD-42 report SS3/SS4). This module has no model call and no
knowledge of "confidence scores" -- every decision is derived from
already-computed, structured evidence the caller passes in (grounding
result, tool-result shape, a durable per-conversation attempt counter, and a
deterministic keyword match on the raw message for an explicit request).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

# Bounded clarification attempts before escalating to NEED_DOCTOR (BUILD-42
# SS8). 2 is the smallest number that still lets a genuinely resolvable
# ambiguity (one focused follow-up) succeed before giving up -- a threshold
# of 1 would hand off after the very first clarification question ever asked,
# never giving the user a real chance to answer it.
MAX_CLARIFICATION_ATTEMPTS = 2


class AnswerabilityOutcome(StrEnum):
    ANSWERABLE = "ANSWERABLE"
    NEED_MORE_INFO = "NEED_MORE_INFO"
    NEED_DOCTOR = "NEED_DOCTOR"


class AnswerabilityReasonCode(StrEnum):
    GROUNDING_INSUFFICIENT = "GROUNDING_INSUFFICIENT"
    UNRESOLVED_ENTITY = "UNRESOLVED_ENTITY"
    AMBIGUOUS_MEDICAL_REQUEST = "AMBIGUOUS_MEDICAL_REQUEST"
    MISSING_REQUIRED_CONTEXT = "MISSING_REQUIRED_CONTEXT"
    REPEATED_CLARIFICATION = "REPEATED_CLARIFICATION"
    UNSUPPORTED_MEDICAL_QUESTION = "UNSUPPORTED_MEDICAL_QUESTION"
    EXPLICIT_DOCTOR_REQUEST = "EXPLICIT_DOCTOR_REQUEST"
    TOOL_DATA_INSUFFICIENT = "TOOL_DATA_INSUFFICIENT"
    MAX_ATTEMPTS_REACHED = "MAX_ATTEMPTS_REACHED"


class HandoffType(StrEnum):
    """Derived, never persisted as its own column -- see BUILD-42 report
    SS4/SS9: fully computable from the existing ``reason_code`` string, so no
    migration is needed. SAFETY covers every reason code the pre-existing
    Safety-Domain-sourced pipeline already produces (ACUTE_DANGER_DETECTED,
    POSSIBLE_OVERDOSE_REPORTED, DOSE_UNRESOLVED, DOCTOR_REVIEW_REQUESTED --
    that last one predates this build and is intentionally left as-is, see
    report SS3). USER_REQUEST and UNCERTAINTY are the two new, non-safety
    categories this build introduces, both created via the new
    ``DoctorHandoffGateway.create_for_uncertainty`` path that never touches
    the Safety Domain or ``AgentSafetyEvent`` (SS17: must not inflate
    safety_trigger_rate)."""

    SAFETY = "SAFETY"
    UNCERTAINTY = "UNCERTAINTY"
    USER_REQUEST = "USER_REQUEST"


def handoff_type_for(*, reason_code: str | None, risk_disposition: str) -> HandoffType:
    if risk_disposition != "UNCERTAINTY_HANDOFF":
        return HandoffType.SAFETY
    if reason_code == AnswerabilityReasonCode.EXPLICIT_DOCTOR_REQUEST.value:
        return HandoffType.USER_REQUEST
    return HandoffType.UNCERTAINTY


@dataclass(frozen=True)
class AnswerabilityDecision:
    outcome: AnswerabilityOutcome
    reason_code: AnswerabilityReasonCode | None
    provenance: str
    attempt_count: int


def _ascii_fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return folded.replace("đ", "d").replace("Đ", "d")


# BUILD-42 SS10: a generic "connect me to a doctor" request, distinct from
# the pre-existing OrchestrationIntent.DOCTOR_REVIEW keyword set
# (_DOCTOR_REVIEW_KEYWORDS in orchestrator.py), which only matches a specific
# dosage-change/stop-medication request ("đổi liều", "ngừng thuốc", ...) --
# that existing intent/path is untouched by this build (SS3 of the audit).
# Matched on the ascii-folded, unaccented message so both accented and
# unaccented input work, same convention as every other keyword check in
# this package.
_EXPLICIT_DOCTOR_REQUEST_RE = re.compile(
    r"(noi chuyen|noi\b).{0,12}\bbac si\b"
    r"|\bgap\b.{0,6}\bbac si\b"
    r"|chuyen\b.{0,20}\bcho\s+bac si\b"
    r"|chuyen\b.{0,20}\bbac si\s+(xem|tu van)\b"
    r"|ket noi\b.{0,10}\bbac si\b"
    r"|\btu van\b.{0,10}\bbac si\b.{0,10}\btruc tiep\b",
    re.IGNORECASE,
)


def is_explicit_doctor_request(message: str) -> bool:
    """Deterministic keyword match only -- no model call, no confidence
    score (BUILD-42 SS3: "must not be 'LLM says confidence is low'")."""

    return bool(_EXPLICIT_DOCTOR_REQUEST_RE.search(_ascii_fold(message)))


def evaluate_grounding_answerability(
    *, attempt_count: int, provenance: str, has_ambiguous_candidates: bool
) -> AnswerabilityDecision:
    """Called only for the personalized-medication-shaped grounding-required
    intents (DRUG_INFORMATION/PRESCRIPTION_INFORMATION/DOSE_STATUS) whose
    reply has zero tool evidence and zero citations -- i.e. exactly the case
    ``_enforce_medical_grounding`` already detects (orchestrator.py). The
    general-medical/ambiguous-topic intents (GENERAL_MEDICAL_INFORMATION,
    UNKNOWN_OR_AMBIGUOUS) are NEVER passed through this function -- BUILD-42
    SS23 keeps their existing honest-decline-with-no-handoff behavior
    completely unchanged ("general educational question with no evidence:
    honest decline may be acceptable"), so this function has no ANSWERABLE
    branch: a caller for whom the general-medical carve-out applies simply
    never calls it at all.
    """

    if attempt_count >= MAX_CLARIFICATION_ATTEMPTS:
        return AnswerabilityDecision(
            outcome=AnswerabilityOutcome.NEED_DOCTOR,
            reason_code=AnswerabilityReasonCode.REPEATED_CLARIFICATION
            if attempt_count > MAX_CLARIFICATION_ATTEMPTS
            else AnswerabilityReasonCode.MAX_ATTEMPTS_REACHED,
            provenance=provenance,
            attempt_count=attempt_count,
        )
    return AnswerabilityDecision(
        outcome=AnswerabilityOutcome.NEED_MORE_INFO,
        reason_code=AnswerabilityReasonCode.UNRESOLVED_ENTITY
        if has_ambiguous_candidates
        else AnswerabilityReasonCode.MISSING_REQUIRED_CONTEXT,
        provenance=provenance,
        attempt_count=attempt_count + 1,
    )


def evaluate_clinical_clarification_answerability(*, attempt_count: int, provenance: str) -> AnswerabilityDecision:
    """Called for the existing PERSONAL_SYMPTOM/MEDICATION_DOSE_SAFETY
    triage-clarification reply (``_clinical_clarification_reply`` in
    orchestrator.py) -- bounds its previously-unbounded "always ask again"
    behavior (BUILD-42 SS8/SS21) without changing the clarification text
    itself for the first attempt.
    """

    if attempt_count >= MAX_CLARIFICATION_ATTEMPTS:
        return AnswerabilityDecision(
            outcome=AnswerabilityOutcome.NEED_DOCTOR,
            reason_code=AnswerabilityReasonCode.REPEATED_CLARIFICATION,
            provenance=provenance,
            attempt_count=attempt_count,
        )
    return AnswerabilityDecision(
        outcome=AnswerabilityOutcome.NEED_MORE_INFO,
        reason_code=None,  # the existing fixed clarification text is unchanged; nothing new to tag
        provenance=provenance,
        attempt_count=attempt_count + 1,
    )


__all__ = [
    "MAX_CLARIFICATION_ATTEMPTS",
    "AnswerabilityDecision",
    "AnswerabilityOutcome",
    "AnswerabilityReasonCode",
    "HandoffType",
    "evaluate_clinical_clarification_answerability",
    "evaluate_grounding_answerability",
    "handoff_type_for",
    "is_explicit_doctor_request",
]
