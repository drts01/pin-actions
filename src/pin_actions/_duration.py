"""Parse exclude-newer values into UTC cutoff datetimes."""

import re
from datetime import UTC, datetime, timedelta

_ISO_DURATION_PATTERN = re.compile(r"^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")
_FRIENDLY_PATTERN = re.compile(r"^(\d+)\s*(hour|day|week)s?$", re.IGNORECASE)


def parse_exclude_newer(value: str, *, now: datetime | None = None) -> datetime:
    """Parse exclude-newer value into UTC cutoff datetime.

    Supports three formats (tried in order):
    - RFC 3339 timestamp: '2006-12-02T02:07:43Z' → absolute cutoff
    - ISO 8601 duration: 'P7D', 'PT24H', 'P1W' → cutoff = now - duration
    - Friendly duration: '24 hours', '1 week', '30 days' → cutoff = now - duration

    Args:
        value: Exclude-newer value string.
        now: Reference time for relative durations (defaults to ``datetime.now(UTC)``).
            Primary use: testing hook for deterministic assertions.

    Returns:
        UTC datetime representing the cutoff (tags after this are excluded).

    Raises:
        ValueError: If value doesn't match any accepted format.
    """
    _now = now or datetime.now(UTC)

    # Try RFC 3339 timestamp first
    try:
        dt = datetime.fromisoformat(value)
        # Ensure UTC aware; if naive, assume UTC
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except ValueError:
        pass

    # Try ISO 8601 duration
    match = _ISO_DURATION_PATTERN.match(value)
    if match:
        weeks, days, hours, minutes, seconds = match.groups()
        delta = timedelta(
            weeks=int(weeks or 0),
            days=int(days or 0),
            hours=int(hours or 0),
            minutes=int(minutes or 0),
            seconds=float(seconds or 0),
        )
        return _now - delta

    # Try friendly duration
    match = _FRIENDLY_PATTERN.match(value)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        unit_map = {"hour": "hours", "day": "days", "week": "weeks"}
        delta = timedelta(**{unit_map[unit]: amount})
        return _now - delta

    msg = (
        f"Invalid exclude-newer format: {value!r}. Accepted formats: RFC 3339 timestamp (e.g., 2006-12-02T02:07:43Z)"
        ", ISO 8601 duration (e.g., P7D, PT24H), or friendly duration (e.g., 7 days, 24 hours, 1 week)"
    )
    raise ValueError(msg)
