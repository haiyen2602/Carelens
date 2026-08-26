"""BUILD-40: Router Quality Improvement Loop -- dedicated regression set for
CANDIDATE-01 (BUILD-39 report §16): disease/symptom questions misrouted to
DRUG_INFORMATION.

Root cause (see backend/agents/v2/orchestrator.py's own BUILD-40 comments):
``classify_intent()``'s terminal fallback silently defaulted every
unclassified message to ``DRUG_INFORMATION`` -- a message never had to
*resemble* a drug question to end up there, it just had to fail every
earlier, more specific check. Real production evidence: 6/9 real disease/
symptom questions ("huyết áp cao có dấu hiệu nào", "viêm gan B lây qua
đường nào", ...) fell through to this default.

Fix, in order of how much of the router it touches:
1. Terminal fallback now assigns ``UNKNOWN_OR_AMBIGUOUS`` (an existing,
   already-wired-up, already-grounding-required intent) instead of
   presuming DRUG_INFORMATION -- the actual root-cause fix.
2. ``_GENERAL_MEDICAL_QUESTION_FORM_RE`` generalizes the existing "là gì"
   keyword to also catch "là [1-2 words] gì" ("là bệnh gì"/"là tình trạng
   gì"), a real Vietnamese question-form, not a per-disease phrase list.
3. ``_UNAMBIGUOUS_MEDICATION_MARKERS`` recognizes "dùng để [làm gì]" and
   "tác dụng phụ" as sufficient evidence for DRUG_INFORMATION on their own
   (a disease is never "used for" anything and has no "side effects") --
   found because the *fix* for (1) newly exposed a real, pre-existing gap:
   a named drug WITHOUT the generic word "thuốc" ("Paracetamol dùng để làm
   gì") was never recognized either, previously "working" only by
   accident of the wrong default this build removes.

No new model call, no new router, no change to Safety/dose-safety/
schedule/out-of-scope precedence (all checked earlier in classify_intent()
than every branch this build touches) -- see
test_precedence_still_wins_over_general_medical_router_changes below.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.agents.v2.orchestrator import OrchestrationIntent, classify_intent

_NOW = datetime(2026, 8, 26, tzinfo=UTC)


def _intent(message: str, **kwargs) -> OrchestrationIntent:
    return classify_intent(message, now=_NOW, **kwargs).intent


# ---------------------------------------------------------------------------
# A. General disease/condition questions -> GENERAL_MEDICAL_INFORMATION
# (spec §7 dataset, verbatim + accent-stripped variants)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "gan nhiễm mỡ là gì",
        "gan nhiem mo la gi",
        "nguyên nhân tăng huyết áp",
        "nguyen nhan tang huyet ap",
        "tiểu đường có nguy hiểm không",
        "dấu hiệu viêm phổi",
        # BUILD-40's own regex generalization ("là [1-2 words] gì"), not
        # covered by the pre-existing "là gì" keyword.
        "Viêm khớp dạng thấp là bệnh gì?",
        "Trào ngược dạ dày thực quản là bệnh gì?",
    ],
)
def test_general_disease_question_routes_to_general_medical(query):
    assert _intent(query) is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION


# ---------------------------------------------------------------------------
# B. Personal symptom reports -> PERSONAL_SYMPTOM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    ["tôi bị đau đầu", "toi bi dau dau", "tôi thấy chóng mặt", "tôi đang buồn nôn"],
)
def test_personal_symptom_report_routes_to_personal_symptom(query):
    assert _intent(query) is OrchestrationIntent.PERSONAL_SYMPTOM


# ---------------------------------------------------------------------------
# C. Named-drug questions -> DRUG_INFORMATION
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Vitamin C có tác dụng gì",
        "Vitamin C co tac dung gi",
        "Paracetamol dùng để làm gì",
        "tác dụng phụ của amoxicillin",
    ],
)
def test_named_drug_question_routes_to_drug_information(query):
    """The last 2 cases are a real regression BUILD-40's own fallback fix
    would otherwise have introduced -- neither contains the generic word
    "thuốc", so before `_UNAMBIGUOUS_MEDICATION_MARKERS` they matched
    nothing and fell to the terminal fallback (previously "correct" only
    by accident of that fallback defaulting to DRUG_INFORMATION)."""

    assert _intent(query) is OrchestrationIntent.DRUG_INFORMATION


# ---------------------------------------------------------------------------
# D. Ambiguous / bare terms -> UNKNOWN_OR_AMBIGUOUS, never a false drug
# presumption (spec §5: "Honest general-medical routing is better than a
# false drug match" -- generalized here to "honest ambiguity" for terms with
# no question form attached at all).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    ["aspirin", "thuốc đau đầu", "thuốc huyết áp", "gan", "vitamin"],
)
def test_ambiguous_bare_term_does_not_falsely_presume_drug(query):
    assert _intent(query) is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS


# ---------------------------------------------------------------------------
# E. Out-of-scope -- unaffected by this build's router changes
# ---------------------------------------------------------------------------


def test_out_of_scope_unaffected():
    assert _intent("bạn là ai") is OrchestrationIntent.OUT_OF_SCOPE_REQUEST


# ---------------------------------------------------------------------------
# F. CANDIDATE-01's exact 6 real production examples (BUILD-39 report),
# paraphrase-safe (these were already my own synthetic canary-account test
# queries, not real patient data -- no de-identification needed, but still
# not copied verbatim from any patient-facing transcript).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Huyết áp cao có những dấu hiệu nào cần chú ý?",
        "Viêm gan B lây qua những đường nào?",
        "Suy thận mạn có những giai đoạn nào?",
        "Đau dạ dày kéo dài có phải là dấu hiệu ung thư không?",
    ],
)
def test_candidate_01_production_examples_no_longer_presume_drug(query):
    """These 4 don't match any GENERAL_MEDICAL_INFORMATION keyword/pattern
    either (a distinct grammar each: "có những X nào", "có phải là X
    không") -- the fix that resolves them is specifically the fallback
    default (A), not the "là gì" generalization (B), which is why they're
    asserted separately from the 2 "là bệnh gì" cases in group A above."""

    intent = _intent(query)
    assert intent is not OrchestrationIntent.DRUG_INFORMATION
    assert intent is OrchestrationIntent.UNKNOWN_OR_AMBIGUOUS


# ---------------------------------------------------------------------------
# G. Precedence -- Safety/dose-safety/schedule/out-of-scope must still win
# regardless of this build's changes (spec §6). All of these are decided by
# branches earlier in classify_intent() than every branch BUILD-40 touched.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Tôi vừa nôn ra máu", OrchestrationIntent.ACUTE_DANGER_ESCALATION),
        ("Tôi vừa uống nhầm 20 viên thuốc rồi", OrchestrationIntent.POSSIBLE_OVERDOSE),
        ("Tôi có thể uống 10 viên vitamin C để tăng sức đề kháng được không?", OrchestrationIntent.MEDICATION_DOSE_SAFETY),
        ("Hôm nay tôi uống thuốc gì?", OrchestrationIntent.TODAY_DOSES),
        ("Ngày mai tôi uống thuốc gì?", OrchestrationIntent.UPCOMING_DOSES),
        ("Hôm qua tôi đã uống đủ thuốc chưa?", OrchestrationIntent.MEDICATION_HISTORY),
    ],
)
def test_precedence_still_wins_over_general_medical_router_changes(query, expected):
    assert _intent(query) is expected


# ---------------------------------------------------------------------------
# H. Multi-turn: an explicit new-topic switch to a general medical question
# must not be dragged into DRUG_INFORMATION by the (removed) old default,
# even when the new-topic question is short (spec §8's own concern, applied
# to the fallback fix rather than to conversation-state machinery this
# build does not touch).
# ---------------------------------------------------------------------------


def test_short_general_medical_follow_up_never_falls_back_to_drug_information():
    """A short, standalone health question that matches no keyword/pattern
    must land on the honest UNKNOWN_OR_AMBIGUOUS fallback, never the old
    DRUG_INFORMATION default -- regardless of message length. (Whether a
    short message is additionally treated as a context-dependent follow-up
    fragment is separate, pre-existing conversation-state machinery this
    build does not touch -- see BUILD-40 report's Known Limitations.)"""

    assert _intent("Thế còn tăng huyết áp?") is not OrchestrationIntent.DRUG_INFORMATION
