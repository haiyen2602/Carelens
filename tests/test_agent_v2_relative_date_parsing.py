"""BUILD-27D: general relative date parsing ("N ngày/hôm/tuần trước/nữa/tới",
"cách đây N ngày", digits and common Vietnamese number words).

Production bug this fixes: "ba hôm trước tôi đã uống gì" matched no existing
keyword, reached the Main Model, which called get_doses_for_range with no
range ever resolved (ToolExecutionError("DATE_RANGE_NOT_RESOLVED")) and
failed closed to "Agent khong the thuc hien yeu cau nay." (see
backend/agents/v2/runtime.py's ValueError handler). Fixed by extending the
deterministic router, not by hardcoding this one phrase.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from backend.agents.v2.orchestrator import OrchestrationIntent, classify_intent

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)  # 16:00 Asia/Ho_Chi_Minh, Saturday


# ---------------------------------------------------------------------------
# Required tests -- exact phrases from the instruction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected_date",
    [
        ("ba hôm trước tôi đã uống gì", date(2026, 8, 19)),
        ("3 ngày trước tôi uống thuốc gì", date(2026, 8, 19)),
        ("cách đây 5 ngày tôi uống gì", date(2026, 8, 17)),
        ("2 tuần trước tôi uống gì", date(2026, 8, 8)),  # a single day 14 days back, not a week range
    ],
)
def test_relative_past_phrases_resolve_to_the_exact_day(message, expected_date):
    decision = classify_intent(message, now=NOW)
    assert decision.intent is OrchestrationIntent.MEDICATION_HISTORY
    assert decision.date_range == (expected_date, expected_date)


@pytest.mark.parametrize(
    "message,expected_date",
    [
        ("3 ngày nữa tôi uống thuốc gì", date(2026, 8, 25)),
        ("ba hôm nữa tôi uống gì", date(2026, 8, 25)),
    ],
)
def test_relative_future_phrases_resolve_to_the_exact_day(message, expected_date):
    decision = classify_intent(message, now=NOW)
    assert decision.intent is OrchestrationIntent.UPCOMING_DOSES
    assert decision.date_range == (expected_date, expected_date)


def test_the_exact_production_bug_phrase_now_resolves():
    """"ba hôm trước tôi đã uống gì" -- the literal reported production bug."""
    decision = classify_intent("ba hôm trước tôi đã uống gì", now=NOW)
    assert decision.intent is OrchestrationIntent.MEDICATION_HISTORY
    assert decision.date_range == (date(2026, 8, 19), date(2026, 8, 19))


# ---------------------------------------------------------------------------
# Vietnamese number words (digits already covered above)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "word,expected_n",
    [
        ("một", 1), ("mot", 1), ("hai", 2), ("ba", 3), ("bốn", 4), ("bon", 4),
        ("năm", 5), ("nam", 5), ("sáu", 6), ("sau", 6), ("bảy", 7), ("bay", 7),
        ("tám", 8), ("tam", 8), ("chín", 9), ("chin", 9), ("mười", 10), ("muoi", 10),
    ],
)
def test_vietnamese_number_words_resolve_correctly(word, expected_n):
    decision = classify_intent(f"{word} ngày trước tôi uống thuốc gì", now=NOW)
    assert decision.intent is OrchestrationIntent.MEDICATION_HISTORY
    expected = date(2026, 8, 22) - timedelta(days=expected_n)
    assert decision.date_range == (expected, expected)


# ---------------------------------------------------------------------------
# Date boundary crossing
# ---------------------------------------------------------------------------


def test_relative_past_crosses_a_month_boundary():
    now = datetime(2026, 9, 2, 7, 0, tzinfo=UTC)  # 14:00 ICT, Sep 2
    decision = classify_intent("5 ngày trước tôi uống thuốc gì", now=now)
    assert decision.date_range == (date(2026, 8, 28), date(2026, 8, 28))


def test_relative_past_crosses_a_year_boundary():
    now = datetime(2027, 1, 2, 7, 0, tzinfo=UTC)
    decision = classify_intent("5 ngày trước tôi uống thuốc gì", now=now)
    assert decision.date_range == (date(2026, 12, 28), date(2026, 12, 28))


def test_relative_future_crosses_a_month_boundary():
    now = datetime(2026, 8, 29, 7, 0, tzinfo=UTC)
    decision = classify_intent("5 ngày nữa tôi uống thuốc gì", now=now)
    assert decision.date_range == (date(2026, 9, 3), date(2026, 9, 3))


def test_relative_future_crosses_a_year_boundary():
    now = datetime(2026, 12, 29, 7, 0, tzinfo=UTC)
    decision = classify_intent("5 ngày nữa tôi uống thuốc gì", now=now)
    assert decision.date_range == (date(2027, 1, 3), date(2027, 1, 3))


def test_absurdly_large_offset_does_not_crash_the_router():
    decision = classify_intent("999999999 ngày trước tôi uống thuốc gì", now=NOW)
    # Rejected by the sanity cap -- falls through to ordinary handling,
    # never raises OverflowError out of the deterministic router.
    assert decision.intent is not OrchestrationIntent.MEDICATION_HISTORY


# ---------------------------------------------------------------------------
# Negative / regression -- every phrase this build must NOT change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected_intent,expected_range",
    [
        ("hôm qua tôi uống thuốc gì", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 21), date(2026, 8, 21))),
        ("hôm kia tôi uống thuốc gì", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 20), date(2026, 8, 20))),
        ("hôm nay tôi uống thuốc gì", OrchestrationIntent.TODAY_DOSES, None),
        ("ngày mai tôi uống thuốc gì", OrchestrationIntent.UPCOMING_DOSES, None),
        ("ngày kia tôi uống thuốc gì", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 24), date(2026, 8, 24))),
        ("tuần trước tôi uống thuốc gì", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 10), date(2026, 8, 16))),
        ("tuần tới tôi uống thuốc gì", OrchestrationIntent.UPCOMING_DOSES, (date(2026, 8, 24), date(2026, 8, 30))),
        ("ngày 20/08 tôi uống thuốc gì", OrchestrationIntent.MEDICATION_HISTORY, (date(2026, 8, 20), date(2026, 8, 20))),
    ],
)
def test_pre_existing_time_phrases_unchanged(message, expected_intent, expected_range):
    decision = classify_intent(message, now=NOW)
    assert decision.intent is expected_intent
    assert decision.date_range == expected_range


def test_acute_danger_still_outranks_a_relative_date_phrase():
    decision = classify_intent("3 ngày trước tôi vừa uống một lúc 15 viên panadol", now=NOW)
    assert decision.intent is OrchestrationIntent.ACUTE_DANGER_ESCALATION


def test_missed_dose_still_outranks_a_relative_date_phrase():
    decision = classify_intent("3 ngày trước tôi quên uống thuốc", now=NOW)
    assert decision.intent is OrchestrationIntent.MISSED_DOSE


def test_ordinary_drug_info_unaffected():
    decision = classify_intent("Panadol Extra dùng sao", now=NOW)
    assert decision.intent is OrchestrationIntent.DRUG_INFORMATION
    assert decision.date_range is None
