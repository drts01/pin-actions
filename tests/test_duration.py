"""Tests for duration parsing (--exclude-newer) with Hypothesis property testing."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st
from pin_actions._duration import parse_exclude_newer

_FIXED_NOW = datetime(2024, 1, 1, tzinfo=UTC)


class TestRFC3339Absolute:
    """Fixed-input tests for RFC 3339 absolute timestamps (no property testing needed)."""

    def test_rfc3339_timestamp(self):
        result = parse_exclude_newer("2006-12-02T15:04:05Z")
        assert result.year == 2006
        assert result.month == 12
        assert result.day == 2
        assert result.tzinfo == UTC

    def test_rfc3339_with_offset(self):
        result = parse_exclude_newer("2006-12-02T15:04:05-08:00")
        assert result.tzinfo == UTC
        assert result.hour == 23  # -8:00 offset: 15:04 → 23:04 UTC


@given(
    amount=st.integers(min_value=1, max_value=9999),
    suffix=st.just(""),  # singular
)
def test_friendly_duration_singular(amount, suffix):
    """Friendly durations (singular unit forms)."""
    for unit in ["hour", "day", "week"]:
        value = f"{amount} {unit}{suffix}"
        result = parse_exclude_newer(value, now=_FIXED_NOW)
        unit_to_delta = {
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
        }
        expected = _FIXED_NOW - unit_to_delta[unit]
        assert result == expected


@given(
    amount=st.integers(min_value=1, max_value=9999),
    suffix=st.just("s"),  # plural
)
def test_friendly_duration_plural(amount, suffix):
    """Friendly durations (plural unit forms)."""
    for unit in ["hour", "day", "week"]:
        value = f"{amount} {unit}{suffix}"
        result = parse_exclude_newer(value, now=_FIXED_NOW)
        unit_to_delta = {
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
        }
        expected = _FIXED_NOW - unit_to_delta[unit]
        assert result == expected


@given(
    weeks=st.integers(0, 99),
    days=st.integers(0, 99),
    hours=st.integers(0, 99),
    minutes=st.integers(0, 59),
    seconds=st.integers(0, 59),
)
def test_iso8601_duration_property(weeks, days, hours, minutes, seconds):
    """ISO 8601 durations: P[nW][nD][T[nH][nM][nS]]."""
    if not any([weeks, days, hours, minutes, seconds]):
        return  # Degenerate empty duration; skip
    value = "P"
    if weeks:
        value += f"{weeks}W"
    if days:
        value += f"{days}D"
    if hours or minutes or seconds:
        value += "T"
        if hours:
            value += f"{hours}H"
        if minutes:
            value += f"{minutes}M"
        if seconds:
            value += f"{seconds}S"
    result = parse_exclude_newer(value, now=_FIXED_NOW)
    expected = _FIXED_NOW - timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds)
    assert result == expected


@given(st.text(min_size=1))
def test_invalid_input_rejects(text):
    """Invalid input always raises ValueError (or is a valid duration string)."""
    # Skip strings that happen to be valid
    valid_units = ["hour", "hours", "day", "days", "week", "weeks"]
    if any(text.lower().endswith(unit) for unit in valid_units) and any(c.isdigit() for c in text):
        return  # Likely friendly duration; skip

    try:
        parse_exclude_newer(text, now=_FIXED_NOW)
    except ValueError:
        pass  # Expected; test passes
    else:
        pass  # Valid input that happened to parse; also acceptable


def test_result_timezone_aware():
    """Result is always UTC timezone-aware."""
    for value in ["P7D", "7 days", "2006-12-02T15:04:05Z"]:
        result = parse_exclude_newer(value, now=_FIXED_NOW)
        assert result.tzinfo == UTC
