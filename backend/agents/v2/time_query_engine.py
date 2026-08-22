"""BUILD-28: Unified Time Query Engine for medication schedule/history.

Replaces the scattered, keyword-by-keyword time logic BUILD-27B/C/D added
incrementally to ``orchestrator.py`` (each one fixing exactly one reported
phrase -- "ngày mai", then "ba hôm trước", then still missing "một tháng
trước"/"tuần sau" budget blowups) with one general parser and one canonical
contract every time-scoped medication question resolves to before any tool
is ever called.

Design invariants (unchanged from BUILD-27B/C/D, now centralized here):
  - Deterministic only. No LLM call decides or computes a date/range --
    every expression here is resolved by explicit parsing, in
    ``Asia/Ho_Chi_Minh``, before the Main Model (if reached at all) sees
    the request.
  - Calendar-correct. A month is never treated as "30 days" -- see
    ``add_months`` for real calendar arithmetic (leap years, short months,
    year rollover all handled by ``calendar.monthrange``, not a fixed
    day-count).
  - Fail open, not fail loud. An expression this engine doesn't recognize
    returns ``None`` -- the caller falls through to ordinary handling
    (still safe; see ``backend/agents/v2/orchestrator.py``), never raises.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

# BUILD-27B: duplicated from backend.services.scheduling.write_path.
# DEFAULT_TIMEZONE (same value) rather than imported -- backend/agents/v2/*
# has never depended on backend.services.scheduling.*, and that package has
# a real circular import back through backend.services.prescription that
# only surfaces depending on import order elsewhere in the app. A plain
# string constant is not worth risking that fragility for.
PATIENT_TIMEZONE = "Asia/Ho_Chi_Minh"
_TZ = ZoneInfo(PATIENT_TIMEZONE)


class TimeGranularity(StrEnum):
    """How the expression named its span -- not necessarily the width of
    the resolved range: "một tháng trước" (month-*counted*) still resolves
    to a single DAY (see module docstring's calendar-correct invariant and
    ``TimeRange``'s own field docs)."""

    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    EXPLICIT = "EXPLICIT"


class TimeRelation(StrEnum):
    PAST = "PAST"
    PRESENT = "PRESENT"
    FUTURE = "FUTURE"


@dataclass(frozen=True)
class TimeRange:
    """The one canonical contract every time-scoped medication question
    resolves to before any tool call (BUILD-28 §2). Every field is
    deterministic -- resolved here, never guessed downstream by a model.
    """

    start_datetime: datetime  # tz-aware, Asia/Ho_Chi_Minh, local 00:00:00 of the first day
    end_datetime: datetime  # tz-aware, Asia/Ho_Chi_Minh, local 23:59:59.999999 of the last day
    timezone: str
    granularity: TimeGranularity
    relation: TimeRelation
    is_past: bool
    is_future: bool
    label: str

    @property
    def start_date(self) -> date:
        return self.start_datetime.date()

    @property
    def end_date(self) -> date:
        return self.end_datetime.date()


def _make_range(
    start_date: date, end_date: date, *, granularity: TimeGranularity, relation: TimeRelation, label: str
) -> TimeRange:
    start_dt = datetime.combine(start_date, time.min, tzinfo=_TZ)
    end_dt = datetime.combine(end_date, time.max, tzinfo=_TZ)
    return TimeRange(
        start_datetime=start_dt,
        end_datetime=end_dt,
        timezone=PATIENT_TIMEZONE,
        granularity=granularity,
        relation=relation,
        is_past=relation is TimeRelation.PAST,
        is_future=relation is TimeRelation.FUTURE,
        label=label,
    )


def local_today(now: datetime) -> date:
    """"Today" in the single timezone this app assumes for every patient --
    the router has no per-patient timezone to look up (it runs before any
    DB access), same assumption every scheduling module already makes."""

    as_utc = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return as_utc.astimezone(_TZ).date()


def add_months(d: date, months: int) -> date:
    """Real calendar-month arithmetic -- never ``months * 30`` (BUILD-28 §3
    explicit requirement). Clamps the day-of-month to the target month's own
    last day (``calendar.monthrange``, which already knows leap years) so
    e.g. 31/01 minus 1 month lands on a real Feb 28/29, not an invalid date
    or an overflow into March.
    """

    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day_of_month))


def iso_week_range(anchor: date) -> tuple[date, date]:
    """Monday-Sunday range containing ``anchor`` (Vietnamese week convention)."""

    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def month_range(anchor: date) -> tuple[date, date]:
    """First-to-last-day range of the calendar month containing ``anchor``."""

    start = anchor.replace(day=1)
    end = anchor.replace(day=calendar.monthrange(anchor.year, anchor.month)[1])
    return start, end


def _relation_for(resolved: date, *, today: date) -> TimeRelation:
    if resolved < today:
        return TimeRelation.PAST
    if resolved == today:
        return TimeRelation.PRESENT
    return TimeRelation.FUTURE


def _relation_for_range(start: date, end: date, *, today: date) -> TimeRelation:
    if end < today:
        return TimeRelation.PAST
    if start > today:
        return TimeRelation.FUTURE
    return TimeRelation.PRESENT  # spans today (e.g. "tuần này"/"tháng này")


# ---------------------------------------------------------------------------
# Vietnamese number words -- digits and these words only (BUILD-27D/28's own
# stated minimum scope). Compound word-numbers ("hai mươi", "mười lăm") are a
# deliberate, documented gap -- see the module docstring at the bottom of
# this file's test suite and report 58/6x's own "out of scope" list. Real
# chat usage overwhelmingly uses digits for anything above ten; a caller
# that types a compound word simply falls through to the model's ordinary
# handling, same fail-open behavior as any other unmatched phrase.
# ---------------------------------------------------------------------------
_VN_NUMBER_WORDS: dict[str, int] = {
    "mười": 10, "muoi": 10,
    "một": 1, "mot": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4, "bon": 4, "tư": 4, "tu": 4,
    "năm": 5, "nam": 5,
    "sáu": 6, "sau": 6,
    "bảy": 7, "bay": 7,
    "tám": 8, "tam": 8,
    "chín": 9, "chin": 9,
}
_NUMBER_WORD_ALTERNATION = "|".join(re.escape(word) for word in sorted(_VN_NUMBER_WORDS, key=len, reverse=True))
_NUMBER_GROUP = rf"(\d{{1,4}}|{_NUMBER_WORD_ALTERNATION})"


def parse_number(token: str) -> int | None:
    lowered = token.casefold()
    if lowered.isdigit():
        return int(lowered)
    return _VN_NUMBER_WORDS.get(lowered)


# Sanity cap only -- large-but-real values (a chronic patient asking about a
# dose from a year ago) still resolve correctly; this just stops a
# pathological input from building a ``date``/``add_months`` call outside
# year 1-9999.
_MAX_RELATIVE_DAYS = 3650
_MAX_RELATIVE_MONTHS = 120

# ---------------------------------------------------------------------------
# Day group
# ---------------------------------------------------------------------------
_YESTERDAY_KEYWORDS = ("hôm qua", "hom qua")
_DAY_BEFORE_YESTERDAY_KEYWORDS = ("hôm kia", "hom kia")
_TOMORROW_KEYWORDS = ("ngày mai", "ngay mai")
_DAY_AFTER_TOMORROW_KEYWORDS = ("ngày kia", "ngay kia")
_DAY_UNIT_GROUP = r"(ngày|ngay|hôm|hom)"
_RELATIVE_DAY_PAST_RE = re.compile(rf"{_NUMBER_GROUP}\s*{_DAY_UNIT_GROUP}\s*(?:trước|truoc)", re.IGNORECASE)
_RELATIVE_DAY_FUTURE_RE = re.compile(rf"{_NUMBER_GROUP}\s*{_DAY_UNIT_GROUP}\s*(?:nữa|nua|tới|toi)", re.IGNORECASE)
_CACH_DAY_RE = re.compile(rf"(?:cách\s*đây|cach\s*day)\s*{_NUMBER_GROUP}\s*ng[aà]y", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Week group
# ---------------------------------------------------------------------------
_THIS_WEEK_KEYWORDS = ("tuần này", "tuan nay")
_LAST_WEEK_KEYWORDS = ("tuần trước", "tuan truoc")
_NEXT_WEEK_KEYWORDS = ("tuần tới", "tuan toi", "tuần sau", "tuan sau")
_WEEK_UNIT_GROUP = r"(tuần|tuan)"
_RELATIVE_WEEK_PAST_RE = re.compile(rf"{_NUMBER_GROUP}\s*{_WEEK_UNIT_GROUP}\s*(?:trước|truoc)", re.IGNORECASE)
_RELATIVE_WEEK_FUTURE_RE = re.compile(rf"{_NUMBER_GROUP}\s*{_WEEK_UNIT_GROUP}\s*(?:nữa|nua|tới|toi)", re.IGNORECASE)
_CACH_DAY_WEEK_RE = re.compile(rf"(?:cách\s*đây|cach\s*day)\s*{_NUMBER_GROUP}\s*(?:tuần|tuan)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Month group (BUILD-28 new -- the production gap that triggered this build)
# ---------------------------------------------------------------------------
_THIS_MONTH_KEYWORDS = ("tháng này", "thang nay")
_LAST_MONTH_KEYWORDS = ("tháng trước", "thang truoc")
_NEXT_MONTH_KEYWORDS = ("tháng tới", "thang toi", "tháng sau", "thang sau")
_MONTH_UNIT_GROUP = r"(tháng|thang)"
_RELATIVE_MONTH_PAST_RE = re.compile(rf"{_NUMBER_GROUP}\s*{_MONTH_UNIT_GROUP}\s*(?:trước|truoc)", re.IGNORECASE)
_RELATIVE_MONTH_FUTURE_RE = re.compile(rf"{_NUMBER_GROUP}\s*{_MONTH_UNIT_GROUP}\s*(?:nữa|nua|tới|toi)", re.IGNORECASE)
_CACH_DAY_MONTH_RE = re.compile(rf"(?:cách\s*đây|cach\s*day)\s*{_NUMBER_GROUP}\s*(?:tháng|thang)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Explicit date group
# ---------------------------------------------------------------------------
# "ngày DD/MM" or "ngày DD-MM", optionally with a year. The "ngày"/"hôm" word
# is deliberately REQUIRED, not optional -- a bare "20/08" collides with
# plausible dosage phrasing in this app ("uống 1/2 viên" = half a tablet),
# but "ngày 20/08"/"hôm 20/08" never means a fraction.
_EXPLICIT_SLASH_DATE_RE = re.compile(r"(?:ng[aà]y|h[oô]m)\s*(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{4}))?", re.IGNORECASE)
# "ngày DD tháng MM [năm YYYY]" -- BUILD-28 new explicit form.
_EXPLICIT_WORDED_DATE_RE = re.compile(
    r"(?:ngày|ngay)\s*(\d{1,2})\s*(?:tháng|thang)\s*(\d{1,2})(?:\s*(?:năm|nam)\s*(\d{4}))?", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Vague signal phrases -- no explicit number/date, just a today-ish or
# upcoming-ish hint. Kept as the deliberately narrow, evidence-based fallback
# BUILD-24G/27B already built (moved here unchanged) for when no hard
# expression above matched anything.
# ---------------------------------------------------------------------------
# BUILD-24G (golden query_id 26/28/31): "hôm nay"/"today" alone missed every
# bare time-of-day phrasing ("buổi sáng tôi cần uống thuốc gì") -- none of
# these say "hôm nay" explicitly, but in ordinary usage a bare "buổi
# sáng/trưa/chiều/tối [uống gì]" question asks about *today's* schedule.
_VAGUE_TODAY_KEYWORDS = (
    "hôm nay", "hom nay", "today",
    "buổi sáng", "buoi sang", "sáng nay", "sang nay",
    "buổi trưa", "buoi trua", "trưa nay", "trua nay",
    "buổi chiều", "buoi chieu", "chiều nay", "chieu nay",
    "buổi tối", "buoi toi", "tối nay", "toi nay",
)
# "liều tiếp theo" (next dose) needs no special range -- the default forward
# window comfortably covers "the next dose" for any real dosing schedule.
_VAGUE_UPCOMING_KEYWORDS = (
    "sắp tới", "sap toi", "lịch uống", "lich uong", "upcoming", "sắp đến", "sap den",
    "liều tiếp theo", "lieu tiep theo", "liều kế tiếp", "lieu ke tiep",
)


def _matches(message_lowered: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in message_lowered for keyword in keywords)


def resolve_time_query(message: str, *, today: date, default_upcoming_window_days: int = 1) -> TimeRange | None:
    """The single entry point every time-scoped medication question goes
    through (BUILD-28 §1/§4). Tries each group in order -- numbered/explicit
    expressions before their same-wording bare phrase (a numbered
    expression's substring can contain the bare phrase's own keywords, e.g.
    "2 tuần trước" contains "tuần trước" -- found the hard way in BUILD-27D,
    fixed generically here by always checking numbered forms first within
    each group). Returns ``None`` when nothing here matched at all -- the
    caller falls through to its own remaining keyword checks unchanged.
    """

    lowered = message.casefold()

    # -- cách đây N ngày/tuần/tháng (always PAST, checked once per unit) ----
    for pattern, unit_kind in ((_CACH_DAY_RE, "day"), (_CACH_DAY_WEEK_RE, "week"), (_CACH_DAY_MONTH_RE, "month")):
        match = pattern.search(message)
        if match is None:
            continue
        number = parse_number(match.group(1))
        if number is None or number <= 0:
            continue
        return _resolve_counted(number, unit_kind, relation=TimeRelation.PAST, today=today, label_suffix="cách đây")

    # -- N ngày/hôm trước/nữa/tới (single day, day-counted) -----------------
    for pattern, relation in ((_RELATIVE_DAY_PAST_RE, TimeRelation.PAST), (_RELATIVE_DAY_FUTURE_RE, TimeRelation.FUTURE)):
        match = pattern.search(message)
        if match is not None:
            number = parse_number(match.group(1))
            if number is not None and number > 0:
                return _resolve_counted(number, "day", relation=relation, today=today, label_suffix="trước" if relation is TimeRelation.PAST else "nữa/tới")

    # -- N tuần trước/nữa/tới (single day, N*7 offset) ----------------------
    for pattern, relation in ((_RELATIVE_WEEK_PAST_RE, TimeRelation.PAST), (_RELATIVE_WEEK_FUTURE_RE, TimeRelation.FUTURE)):
        match = pattern.search(message)
        if match is not None:
            number = parse_number(match.group(1))
            if number is not None and number > 0:
                return _resolve_counted(number, "week", relation=relation, today=today, label_suffix="trước" if relation is TimeRelation.PAST else "nữa/tới")

    # -- N tháng trước/nữa/tới (single day, calendar-correct month offset) --
    for pattern, relation in ((_RELATIVE_MONTH_PAST_RE, TimeRelation.PAST), (_RELATIVE_MONTH_FUTURE_RE, TimeRelation.FUTURE)):
        match = pattern.search(message)
        if match is not None:
            number = parse_number(match.group(1))
            if number is not None and number > 0:
                return _resolve_counted(number, "month", relation=relation, today=today, label_suffix="trước" if relation is TimeRelation.PAST else "nữa/tới")

    # -- bare day phrases (checked after every numbered form above) --------
    if _matches(lowered, _YESTERDAY_KEYWORDS):
        d = today - timedelta(days=1)
        return _make_range(d, d, granularity=TimeGranularity.DAY, relation=TimeRelation.PAST, label="hôm qua")
    if _matches(lowered, _DAY_BEFORE_YESTERDAY_KEYWORDS):
        d = today - timedelta(days=2)
        return _make_range(d, d, granularity=TimeGranularity.DAY, relation=TimeRelation.PAST, label="hôm kia")
    if _matches(lowered, _TOMORROW_KEYWORDS):
        d = today + timedelta(days=1)
        return _make_range(d, d, granularity=TimeGranularity.DAY, relation=TimeRelation.FUTURE, label="ngày mai")
    if _matches(lowered, _DAY_AFTER_TOMORROW_KEYWORDS):
        d = today + timedelta(days=2)
        return _make_range(d, d, granularity=TimeGranularity.DAY, relation=TimeRelation.FUTURE, label="ngày kia")

    # -- bare week phrases (whole calendar week, not a single day) ----------
    if _matches(lowered, _THIS_WEEK_KEYWORDS):
        start, end = iso_week_range(today)
        return _make_range(start, end, granularity=TimeGranularity.WEEK, relation=_relation_for_range(start, end, today=today), label="tuần này")
    if _matches(lowered, _LAST_WEEK_KEYWORDS):
        start, end = iso_week_range(today - timedelta(days=7))
        return _make_range(start, end, granularity=TimeGranularity.WEEK, relation=TimeRelation.PAST, label="tuần trước")
    if _matches(lowered, _NEXT_WEEK_KEYWORDS):
        start, end = iso_week_range(today + timedelta(days=7))
        return _make_range(start, end, granularity=TimeGranularity.WEEK, relation=TimeRelation.FUTURE, label="tuần tới")

    # -- bare month phrases (whole calendar month) --------------------------
    if _matches(lowered, _THIS_MONTH_KEYWORDS):
        start, end = month_range(today)
        return _make_range(start, end, granularity=TimeGranularity.MONTH, relation=_relation_for_range(start, end, today=today), label="tháng này")
    if _matches(lowered, _LAST_MONTH_KEYWORDS):
        start, end = month_range(add_months(today.replace(day=1), -1))
        return _make_range(start, end, granularity=TimeGranularity.MONTH, relation=TimeRelation.PAST, label="tháng trước")
    if _matches(lowered, _NEXT_MONTH_KEYWORDS):
        start, end = month_range(add_months(today.replace(day=1), 1))
        return _make_range(start, end, granularity=TimeGranularity.MONTH, relation=TimeRelation.FUTURE, label="tháng sau")

    # -- explicit calendar date (either written form) -----------------------
    explicit = _resolve_explicit_date(lowered, today=today)
    if explicit is not None:
        relation = _relation_for(explicit, today=today)
        return _make_range(explicit, explicit, granularity=TimeGranularity.EXPLICIT, relation=relation, label=explicit.isoformat())

    # -- vague signal phrases (no number/date at all) -----------------------
    if _matches(lowered, _VAGUE_TODAY_KEYWORDS):
        return _make_range(today, today, granularity=TimeGranularity.DAY, relation=TimeRelation.PRESENT, label="hôm nay")
    if _matches(lowered, _VAGUE_UPCOMING_KEYWORDS):
        horizon = today + timedelta(days=default_upcoming_window_days)
        return _make_range(today, horizon, granularity=TimeGranularity.DAY, relation=TimeRelation.FUTURE, label="sắp tới")

    return None


def _resolve_counted(number: int, unit_kind: str, *, relation: TimeRelation, today: date, label_suffix: str) -> TimeRange | None:
    """A single resolved DAY, offset by ``number`` day/week/month units --
    "một tháng trước" reads naturally as "the same calendar date one month
    earlier" (a point in time), not "the whole previous calendar month"
    (that reading is what the bare "tháng trước"/"tháng này"/"tháng sau"
    phrases already cover, unchanged, as a real range).
    """

    sign = -1 if relation is TimeRelation.PAST else 1
    try:
        if unit_kind == "day":
            if number > _MAX_RELATIVE_DAYS:
                return None
            resolved = today + timedelta(days=sign * number)
            granularity = TimeGranularity.DAY
        elif unit_kind == "week":
            if number * 7 > _MAX_RELATIVE_DAYS:
                return None
            resolved = today + timedelta(days=sign * number * 7)
            granularity = TimeGranularity.WEEK
        else:  # "month"
            if number > _MAX_RELATIVE_MONTHS:
                return None
            resolved = add_months(today, sign * number)
            granularity = TimeGranularity.MONTH
    except OverflowError:
        return None
    return _make_range(resolved, resolved, granularity=granularity, relation=relation, label=f"{number} {unit_kind} {label_suffix}")


def _resolve_explicit_date(message_lowered: str, *, today: date) -> date | None:
    """"ngày 20/08", "hôm 20/8/2026", or "ngày 20 tháng 8 [năm 2026]" -> a
    real calendar date, or None. Assumes the current year when none is
    given. An invalid combination (e.g. "ngày 31/02") is treated as no
    match rather than raising -- a typo here should fall through to the
    model's own ordinary handling rather than crash the deterministic router.
    """

    for pattern in (_EXPLICIT_SLASH_DATE_RE, _EXPLICIT_WORDED_DATE_RE):
        match = pattern.search(message_lowered)
        if match is None:
            continue
        day_str, month_str, year_str = match.groups()
        try:
            day, month = int(day_str), int(month_str)
            year = int(year_str) if year_str else today.year
            return date(year, month, day)
        except ValueError:
            continue
    return None


__all__ = [
    "PATIENT_TIMEZONE",
    "TimeGranularity",
    "TimeRange",
    "TimeRelation",
    "add_months",
    "iso_week_range",
    "local_today",
    "month_range",
    "parse_number",
    "resolve_time_query",
]
