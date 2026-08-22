"""BUILD-24G (V2 RC hardening, Phase 1 item 3): router remediation.

Found in BUILD-24C's golden set (report 35, section 4, item 8): 5 intent-
misrouting cases where the tool actually used and the content returned were
accurate, but the router's own keyword classifier picked the wrong
``OrchestrationIntent``. Traced to their exact root causes here, not
assumed:

- query_id 2 ("Vitamin C uống bao nhiêu viên 1 ngày") and query_id 54 ("sau
  khi uống thuốc em thấy da hơi đỏ ửng") were both misrouted to
  GENERAL_CONVERSATION. Root cause: the bare 2-letter English greeting
  keyword "hi" matched as a plain substring inside ordinary Vietnamese words
  -- "bao **nhi**êu" (how many) and "sau **kh**i" (after) both contain "hi".
  Fixed by matching "hi"/"hello" as whole words only (``_GREETING_WORD_RE``,
  ``\\b(hi|hello)\\b``); every other greeting phrase stays plain substring
  matching (already long/specific enough not to collide).
- query_id 26/28/31 ("buổi sáng tôi cần uống thuốc gì", "buổi tối nay uống
  gì", "buổi trưa uống thuốc gì") were all misrouted to DRUG_INFORMATION
  instead of TODAY_DOSES. Root cause: ``_TODAY_KEYWORDS`` only recognized
  the literal phrase "hôm nay"/"today", not a bare time-of-day reference
  ("buổi sáng/trưa/chiều/tối", with or without a "nay" suffix), which in
  ordinary usage implies *today* unless a different day is named explicitly
  (compare BUILD-24D report 36 query_id 33, "lịch uống thuốc ngày mai của
  tôi", which already correctly routes to UPCOMING_DOSES because it names
  "ngày mai"). Fixed by adding all four time-of-day phrases, bare and with
  "nay", to ``_TODAY_KEYWORDS``.

No semantic/embedding-based routing fallback was added: both root causes
were fully addressed with plain deterministic keyword coverage, so the
"semantic intent fallback" this build's own instructions call optional
("có thể thêm... khi deterministic rules không đủ") was not needed --
avoiding it keeps the Safety-relevant router's only inputs a fixed,
auditable keyword/regex list, consistent with every other trigger in this
module (see the module docstring's "Router... is a deterministic keyword
classifier, not a model call").
"""

from __future__ import annotations

import pytest

from backend.agents.v2.orchestrator import OrchestrationIntent, classify_intent

_MISROUTING_GOLDEN_CASES = [
    (2, "Vitamin C uống bao nhiêu viên 1 ngày", OrchestrationIntent.DRUG_INFORMATION),
    (26, "buổi sáng tôi cần uống thuốc gì", OrchestrationIntent.TODAY_DOSES),
    (28, "buổi tối nay uống gì", OrchestrationIntent.TODAY_DOSES),
    (31, "buổi trưa uống thuốc gì", OrchestrationIntent.TODAY_DOSES),
    (54, "sau khi uống thuốc em thấy da hơi đỏ ửng", OrchestrationIntent.DRUG_INFORMATION),
]


@pytest.mark.parametrize(
    "query_id,query,expected", _MISROUTING_GOLDEN_CASES, ids=[str(c[0]) for c in _MISROUTING_GOLDEN_CASES]
)
def test_golden_misrouting_cases_now_route_correctly(query_id, query, expected):
    got = classify_intent(query).intent
    assert got is expected, f"query_id {query_id} ({query!r}) routed to {got}, expected {expected}"
    assert got is not OrchestrationIntent.GENERAL_CONVERSATION


# ---------------------------------------------------------------------------
# "hi"/"hello" false-positive substring bug -- targeted regression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Vitamin C uống bao nhiêu viên 1 ngày",  # "nhiêu" contains "hi"
        "sau khi uống thuốc em thấy da hơi đỏ ửng",  # "khi" contains "hi"
        "thuốc này uống khi nào",  # "khi" again, different message
        "nghi ngờ có tác dụng phụ không",  # "nghi" contains "hi"
    ],
)
def test_hi_substring_no_longer_false_positives_into_general_conversation(query):
    assert classify_intent(query).intent is not OrchestrationIntent.GENERAL_CONVERSATION


@pytest.mark.parametrize("query", ["hi", "Hi", "hello", "Hello there", "hi bạn"])
def test_genuine_hi_hello_greetings_still_route_to_general_conversation(query):
    assert classify_intent(query).intent is OrchestrationIntent.GENERAL_CONVERSATION


def test_other_greeting_phrases_are_unaffected():
    for query in ("xin chào", "chào bạn", "cảm ơn"):
        assert classify_intent(query).intent is OrchestrationIntent.GENERAL_CONVERSATION


# ---------------------------------------------------------------------------
# Time-of-day keywords don't override higher-priority triggers (MISSED_DOSE,
# DELAYED_DOSE) when both a time-of-day phrase and a real trigger keyword
# are present in the same message -- priority order preserved.
# ---------------------------------------------------------------------------


def test_time_of_day_phrase_does_not_override_missed_dose():
    decision = classify_intent("Toi quen uong thuoc sang nay")
    assert decision.intent is OrchestrationIntent.MISSED_DOSE


def test_time_of_day_phrase_does_not_override_delayed_dose():
    decision = classify_intent("Toi uong tre gio thuoc buoi trua")
    assert decision.intent is OrchestrationIntent.DELAYED_DOSE


def test_time_of_day_phrase_does_not_override_acute_danger():
    # A time-of-day phrase alone must never mask a genuine acute-danger signal.
    decision = classify_intent("sáng nay tôi vừa uống một lúc 15 viên panadol")
    assert decision.intent is OrchestrationIntent.ACUTE_DANGER_ESCALATION


@pytest.mark.parametrize(
    "query",
    [
        "buổi chiều tôi cần uống thuốc gì",
        "buổi tối uống thuốc gì",
        "chiều nay uống gì",
    ],
)
def test_additional_time_of_day_phrasings_route_to_today_doses(query):
    assert classify_intent(query).intent is OrchestrationIntent.TODAY_DOSES
