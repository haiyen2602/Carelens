"""BUILD-28: exhaustive property/table-driven tests for the unified Time
Query Engine (backend.agents.v2.time_query_engine) -- the single general
parser + canonical ``TimeRange`` contract every time-scoped medication
question resolves to before any tool is called.

Covers §9's required matrix: Past/Present/Future x Day/Week/Month/Explicit
date x Digit/Vietnamese-number-word x month/year/leap boundaries, plus
determinism/boundedness property checks for the parser itself. Routing
through ``classify_intent`` (priority ordering, safety precedence, the
deterministic composer) is covered separately in
``test_agent_v2_time_aware_schedule.py`` and
``test_agent_v2_relative_date_parsing.py`` -- this file is scoped to the
parser/contract alone, with no orchestrator/DB dependency.
"""

from __future__ import annotations

import calendar
from datetime import date

import pytest

from backend.agents.v2.time_query_engine import (
    PATIENT_TIMEZONE,
    TimeGranularity,
    TimeRelation,
    add_months,
    iso_week_range,
    local_today,
    month_range,
    parse_number,
    resolve_time_query,
)

TODAY = date(2026, 8, 22)  # a Saturday


# ---------------------------------------------------------------------------
# add_months -- calendar-correct month arithmetic (never N*30 days)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "start,months,expected",
    [
        (date(2026, 1, 31), -1, date(2025, 12, 31)),
        (date(2026, 3, 31), -1, date(2026, 2, 28)),  # non-leap Feb
        (date(2028, 3, 31), -1, date(2028, 2, 29)),  # leap Feb
        (date(2026, 12, 15), 1, date(2027, 1, 15)),  # year rollover forward
        (date(2027, 1, 15), -1, date(2026, 12, 15)),  # year rollover backward
        (date(2026, 8, 31), 1, date(2026, 9, 30)),  # 31 -> 30-day month, clamped
        (date(2024, 2, 29), 12, date(2025, 2, 28)),  # leap day, +1 year -> non-leap
        (date(2026, 8, 22), 0, date(2026, 8, 22)),  # identity
    ],
)
def test_add_months_is_calendar_correct(start, months, expected):
    assert add_months(start, months) == expected


def test_add_months_never_uses_a_fixed_30_day_step():
    # 31/01 minus "1 month" via naive 30-day subtraction would land on
    # 01/01, not the real calendar answer (31/12).
    assert add_months(date(2026, 1, 31), -1) != date(2026, 1, 31) - __import__("datetime").timedelta(days=30)
    assert add_months(date(2026, 1, 31), -1) == date(2025, 12, 31)


# ---------------------------------------------------------------------------
# parse_number -- digits and the documented Vietnamese number words
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token,expected",
    [
        ("1", 1), ("31", 31), ("mot", 1), ("một", 1), ("hai", 2), ("ba", 3),
        ("bon", 4), ("bốn", 4), ("tu", 4), ("tư", 4), ("nam", 5), ("năm", 5),
        ("sau", 6), ("sáu", 6), ("bay", 7), ("bảy", 7), ("tam", 8), ("tám", 8),
        ("chin", 9), ("chín", 9), ("muoi", 10), ("mười", 10),
    ],
)
def test_parse_number_digits_and_words(token, expected):
    assert parse_number(token) == expected


def test_parse_number_rejects_unsupported_compound_words():
    # Deliberate, documented gap (BUILD-27D/28's own stated minimum scope):
    # no full Vietnamese numeral parser for compounds like "hai mươi ba".
    assert parse_number("hai mươi ba") is None


# ---------------------------------------------------------------------------
# Day group: bare + N-day relative, digits and words, 1..31 days
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(1, 32))
def test_n_ngay_truoc_resolves_to_exactly_n_days_back(n):
    tr = resolve_time_query(f"{n} ngày trước tôi uống thuốc gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.PAST
    assert tr.start_date == tr.end_date == TODAY - __import__("datetime").timedelta(days=n)


@pytest.mark.parametrize("n", range(1, 32))
def test_n_ngay_nua_resolves_to_exactly_n_days_forward(n):
    tr = resolve_time_query(f"{n} ngày nữa tôi uống thuốc gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.FUTURE
    assert tr.start_date == tr.end_date == TODAY + __import__("datetime").timedelta(days=n)


@pytest.mark.parametrize(
    "message,expected_offset",
    [
        ("hôm qua tôi uống thuốc gì", -1),
        ("hôm kia tôi uống thuốc gì", -2),
        ("ngày mai tôi uống thuốc gì", 1),
        ("ngày kia tôi uống thuốc gì", 2),
    ],
)
def test_bare_day_phrases(message, expected_offset):
    tr = resolve_time_query(message, today=TODAY)
    assert tr is not None
    assert tr.granularity is TimeGranularity.DAY
    assert tr.start_date == tr.end_date == TODAY + __import__("datetime").timedelta(days=expected_offset)


def test_cach_day_n_ngay_is_always_past():
    tr = resolve_time_query("cách đây 5 ngày tôi uống gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.PAST
    assert tr.start_date == TODAY - __import__("datetime").timedelta(days=5)


# ---------------------------------------------------------------------------
# Week group: bare + N-week relative, digits and words, 1..8 weeks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(1, 9))
def test_n_tuan_truoc_resolves_to_exactly_n_times_7_days_back(n):
    tr = resolve_time_query(f"{n} tuần trước tôi uống thuốc gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.PAST
    assert tr.start_date == tr.end_date == TODAY - __import__("datetime").timedelta(days=7 * n)


@pytest.mark.parametrize("n", range(1, 9))
def test_n_tuan_nua_resolves_to_exactly_n_times_7_days_forward(n):
    tr = resolve_time_query(f"{n} tuần nữa tôi uống thuốc gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.FUTURE
    assert tr.start_date == tr.end_date == TODAY + __import__("datetime").timedelta(days=7 * n)


def test_numbered_week_phrase_wins_over_the_bare_substring_it_contains():
    """Regression (found in BUILD-27D): "2 tuần trước" textually contains
    the bare "tuần trước" substring -- must resolve to 14 days back (a
    single day), not the bare phrase's whole-calendar-week reading."""
    tr = resolve_time_query("2 tuần trước tôi uống gì", today=TODAY)
    assert tr.start_date == tr.end_date == TODAY - __import__("datetime").timedelta(days=14)


@pytest.mark.parametrize(
    "message,expected_relation",
    [
        ("tuần này tôi uống thuốc gì", TimeRelation.PRESENT),
        ("tuần trước tôi uống thuốc gì", TimeRelation.PAST),
        ("tuần tới tôi uống thuốc gì", TimeRelation.FUTURE),
        ("tuần sau tôi uống thuốc gì", TimeRelation.FUTURE),
    ],
)
def test_bare_week_phrases_resolve_to_a_full_calendar_week(message, expected_relation):
    tr = resolve_time_query(message, today=TODAY)
    assert tr is not None
    assert tr.granularity is TimeGranularity.WEEK
    assert tr.relation is expected_relation
    assert (tr.end_date - tr.start_date).days == 6
    assert tr.start_date.weekday() == 0  # Monday


def test_bare_tuan_nay_spans_today():
    tr = resolve_time_query("tuần này tôi uống thuốc gì", today=TODAY)
    assert tr.start_date <= TODAY <= tr.end_date


# ---------------------------------------------------------------------------
# Month group (BUILD-28 new): bare + N-month relative, 1..12 months
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(1, 13))
def test_n_thang_truoc_resolves_to_the_same_calendar_date_n_months_earlier(n):
    tr = resolve_time_query(f"{n} tháng trước tôi dùng thuốc gì", today=TODAY)
    assert tr is not None
    assert tr.granularity is TimeGranularity.MONTH
    assert tr.relation is TimeRelation.PAST
    assert tr.start_date == tr.end_date == add_months(TODAY, -n)


@pytest.mark.parametrize("n", range(1, 13))
def test_n_thang_nua_resolves_to_the_same_calendar_date_n_months_later(n):
    tr = resolve_time_query(f"{n} tháng nữa tôi uống gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.FUTURE
    assert tr.start_date == tr.end_date == add_months(TODAY, n)


def test_mot_thang_truoc_the_exact_production_bug():
    """"một tháng trước tôi dùng thuốc gì" -- reported production failure
    ("Agent khong the thuc hien yeu cau nay.") -- must now resolve, and to
    the real calendar date one month back, not a 30-day approximation."""
    tr = resolve_time_query("một tháng trước tôi dùng thuốc gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.PAST
    assert tr.start_date == tr.end_date == date(2026, 7, 22)


def test_tuan_sau_the_other_exact_production_bug():
    """"tuần sau tôi cần dùng thuốc gì không" -- reported production
    failure (BUDGET_EXCEEDED via the Main Model) -- must resolve to a real
    full future calendar week."""
    tr = resolve_time_query("tuần sau tôi cần dùng thuốc gì không", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.FUTURE
    assert tr.granularity is TimeGranularity.WEEK
    assert (tr.start_date, tr.end_date) == iso_week_range(TODAY + __import__("datetime").timedelta(days=7))


@pytest.mark.parametrize(
    "message,expected_relation",
    [
        ("tháng này tôi uống thuốc gì", TimeRelation.PRESENT),
        ("tháng trước lịch thuốc của tôi thế nào", TimeRelation.PAST),
        ("tháng sau tôi uống thuốc gì", TimeRelation.FUTURE),
        ("tháng tới tôi uống thuốc gì", TimeRelation.FUTURE),
    ],
)
def test_bare_month_phrases_resolve_to_a_full_calendar_month(message, expected_relation):
    tr = resolve_time_query(message, today=TODAY)
    assert tr is not None
    assert tr.granularity is TimeGranularity.MONTH
    assert tr.relation is expected_relation
    assert tr.start_date.day == 1
    assert tr.end_date == tr.start_date.replace(day=calendar.monthrange(tr.start_date.year, tr.start_date.month)[1])


def test_cach_day_n_thang_is_always_past_and_calendar_correct():
    tr = resolve_time_query("cách đây 2 tháng tôi uống gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.PAST
    assert tr.start_date == add_months(TODAY, -2)


def test_numbered_month_phrase_wins_over_the_bare_substring_it_contains():
    tr = resolve_time_query("2 tháng trước tôi dùng thuốc gì", today=TODAY)
    assert tr.start_date == tr.end_date == add_months(TODAY, -2)
    assert tr.granularity is TimeGranularity.MONTH


# ---------------------------------------------------------------------------
# Explicit date group -- DD/MM, DD-MM, ngày DD tháng MM [năm YYYY]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected_date",
    [
        ("ngày 20/08 tôi uống thuốc gì", date(2026, 8, 20)),
        ("hôm 20-08-2026 tôi uống thuốc gì", date(2026, 8, 20)),
        ("ngày 15 tháng 8 tôi uống thuốc gì", date(2026, 8, 15)),
        ("ngày 15 tháng 8 năm 2025 tôi uống thuốc gì", date(2025, 8, 15)),
    ],
)
def test_explicit_dates_resolve_correctly(message, expected_date):
    tr = resolve_time_query(message, today=TODAY)
    assert tr is not None
    assert tr.granularity is TimeGranularity.EXPLICIT
    assert tr.start_date == tr.end_date == expected_date


def test_explicit_date_assumes_current_year_when_omitted():
    tr = resolve_time_query("ngày 20/08 tôi uống thuốc gì", today=TODAY)
    assert tr.start_date.year == TODAY.year


def test_explicit_date_relation_depends_on_where_it_falls():
    assert resolve_time_query("ngày 20/08 tôi uống thuốc gì", today=TODAY).relation is TimeRelation.PAST
    assert resolve_time_query("ngày 22/08 tôi uống thuốc gì", today=TODAY).relation is TimeRelation.PRESENT
    assert resolve_time_query("ngày 25/08 tôi uống thuốc gì", today=TODAY).relation is TimeRelation.FUTURE


def test_invalid_explicit_date_falls_through_instead_of_raising():
    assert resolve_time_query("ngày 31/02 tôi uống thuốc gì", today=TODAY) is None


def test_bare_fraction_dosage_is_not_mistaken_for_a_date():
    # "uống 1/2 viên" (half a tablet) must never be parsed as a date -- the
    # "ngày"/"hôm" word is deliberately required.
    assert resolve_time_query("uống 1/2 viên panadol", today=TODAY) is None


# ---------------------------------------------------------------------------
# Vague signal fallback (no explicit number/date)
# ---------------------------------------------------------------------------


def test_vague_today_signal():
    tr = resolve_time_query("buổi sáng tôi cần uống thuốc gì", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.PRESENT
    assert tr.start_date == tr.end_date == TODAY


def test_vague_upcoming_signal():
    tr = resolve_time_query("liều tiếp theo lúc mấy giờ", today=TODAY)
    assert tr is not None
    assert tr.relation is TimeRelation.FUTURE
    assert tr.start_date == TODAY


def test_unrecognized_expression_returns_none():
    assert resolve_time_query("Panadol Extra dùng sao", today=TODAY) is None
    assert resolve_time_query("", today=TODAY) is None


# ---------------------------------------------------------------------------
# Calendar/timezone boundaries
# ---------------------------------------------------------------------------


def test_month_boundary_crossing_backward():
    tr = resolve_time_query("5 ngày trước tôi uống gì", today=date(2026, 9, 2))
    assert tr.start_date == date(2026, 8, 28)


def test_year_boundary_crossing_backward():
    tr = resolve_time_query("5 ngày trước tôi uống gì", today=date(2027, 1, 2))
    assert tr.start_date == date(2026, 12, 28)


def test_year_boundary_crossing_forward():
    tr = resolve_time_query("5 ngày nữa tôi uống gì", today=date(2026, 12, 29))
    assert tr.start_date == date(2027, 1, 3)


def test_month_arithmetic_dec_to_jan():
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert add_months(date(2027, 1, 15), -1) == date(2026, 12, 15)


def test_month_arithmetic_leap_year_end():
    assert add_months(date(2028, 1, 29), 1) == date(2028, 2, 29)  # 2028 is a leap year
    assert add_months(date(2027, 1, 29), 1) == date(2027, 2, 28)  # 2027 is not


def test_local_today_converts_utc_midnight_crossing_correctly():
    import datetime as dt

    # 19:00 UTC on Aug 21 is 02:00 ICT on Aug 22 -- must resolve to Aug 22.
    now_utc = dt.datetime(2026, 8, 21, 19, 0, tzinfo=dt.UTC)
    assert local_today(now_utc) == date(2026, 8, 22)


def test_iso_week_range_is_monday_to_sunday():
    start, end = iso_week_range(TODAY)  # a Saturday
    assert start.weekday() == 0
    assert end.weekday() == 6
    assert start <= TODAY <= end


def test_month_range_spans_the_whole_calendar_month():
    start, end = month_range(date(2026, 2, 15))
    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)  # 2026 is not a leap year


def test_month_range_leap_february():
    start, end = month_range(date(2028, 2, 15))
    assert end == date(2028, 2, 29)


# ---------------------------------------------------------------------------
# Determinism / boundedness properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "ba hôm trước tôi đã uống gì", "một tháng trước tôi dùng thuốc gì",
        "tuần sau tôi cần dùng thuốc gì không", "2 tháng nữa tôi uống gì",
        "ngày 15/08 tôi đã uống đủ chưa", "tháng trước lịch thuốc của tôi thế nào",
        "3 tuần tới tôi cần uống gì", "hôm nay tôi uống thuốc gì", "tuần này tôi uống thuốc gì",
    ],
)
def test_resolution_is_deterministic_for_the_same_inputs(message):
    first = resolve_time_query(message, today=TODAY)
    second = resolve_time_query(message, today=TODAY)
    assert first == second


@pytest.mark.parametrize(
    "message",
    [
        "999999999 ngày trước tôi uống thuốc gì",
        "999999999 tuần trước tôi uống thuốc gì",
        "999999999 tháng trước tôi uống thuốc gì",
        "999999999 ngày nữa tôi uống thuốc gì",
    ],
)
def test_absurd_offsets_never_crash_and_stay_bounded(message):
    # Rejected by the sanity caps -- returns None (falls through to ordinary
    # handling) rather than raising OverflowError/ValueError out of the
    # parser.
    assert resolve_time_query(message, today=TODAY) is None


def test_resolved_range_is_always_within_a_sane_span_for_every_supported_expression():
    """Boundedness: every expression this parser recognizes resolves to a
    range no wider than one calendar month (the widest granularity this
    engine ever produces is a single bare month) -- never an unbounded or
    multi-month span."""
    messages = [
        "hôm qua", "hôm kia", "ngày mai", "ngày kia", "3 ngày trước", "10 ngày nữa",
        "tuần này", "tuần trước", "tuần tới", "2 tuần trước", "tháng này", "tháng trước",
        "tháng sau", "3 tháng nữa", "ngày 20/08", "cách đây 5 ngày",
    ]
    for message in messages:
        tr = resolve_time_query(f"{message} tôi uống thuốc gì", today=TODAY)
        assert tr is not None, message
        assert (tr.end_date - tr.start_date).days <= 31, message


def test_timezone_field_is_always_the_patient_timezone():
    tr = resolve_time_query("hôm qua tôi uống thuốc gì", today=TODAY)
    assert tr.timezone == PATIENT_TIMEZONE == "Asia/Ho_Chi_Minh"


def test_start_datetime_and_end_datetime_are_timezone_aware_local_bounds():
    tr = resolve_time_query("hôm qua tôi uống thuốc gì", today=TODAY)
    assert tr.start_datetime.tzinfo is not None
    assert tr.end_datetime.tzinfo is not None
    assert tr.start_datetime.time().hour == 0 and tr.start_datetime.time().minute == 0
    assert tr.end_datetime.time().hour == 23 and tr.end_datetime.time().minute == 59
