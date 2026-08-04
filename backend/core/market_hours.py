"""US equity market session calendar.

The background price refresh consults this so it stays idle outside trading
hours. Prices don't move when the market is shut, and the market is shut for
roughly 80% of the wall-clock week — fetching through it was spending the bulk
of our upstream quota to re-read the same closing price.

Holidays are an explicit table rather than a computed calendar. Good Friday
needs an Easter calculation, and the weekend-observance rules carry exceptions
(a Saturday New Year's Day is *not* pulled back to the preceding Friday, unlike
every other holiday). A year missing from the table is treated as having no
holidays at all, which errs towards fetching on a closed market — one wasted
request — rather than towards treating a trading day as closed, which would
leave the dashboard stale for a whole session.

Early closes (1pm ET the day after Thanksgiving, Christmas Eve) are ignored:
trading past them costs one extra fetch that returns the same closing price.
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_SESSION_OPEN = time(9, 30)
_SESSION_CLOSE = time(16, 0)


def _days(*iso: str) -> frozenset[date]:
    return frozenset(date.fromisoformat(d) for d in iso)


# NYSE holiday observances. Extend as further years are published.
_HOLIDAYS: dict[int, frozenset[date]] = {
    2026: _days(
        "2026-01-01",  # New Year's Day
        "2026-01-19",  # Martin Luther King Jr. Day
        "2026-02-16",  # Washington's Birthday
        "2026-04-03",  # Good Friday
        "2026-05-25",  # Memorial Day
        "2026-06-19",  # Juneteenth
        "2026-07-03",  # Independence Day (Jul 4 falls on Saturday)
        "2026-09-07",  # Labor Day
        "2026-11-26",  # Thanksgiving
        "2026-12-25",  # Christmas
    ),
    2027: _days(
        "2027-01-01",
        "2027-01-18",
        "2027-02-15",
        "2027-03-26",  # Good Friday
        "2027-05-31",
        "2027-06-18",  # Juneteenth (Jun 19 falls on Saturday)
        "2027-07-05",  # Independence Day (Jul 4 falls on Sunday)
        "2027-09-06",
        "2027-11-25",
        "2027-12-24",  # Christmas (Dec 25 falls on Saturday)
    ),
    2028: _days(
        # No New Year's observance: Jan 1 falls on Saturday and the exchange
        # does not close the preceding Friday for it.
        "2028-01-17",
        "2028-02-21",
        "2028-04-14",  # Good Friday
        "2028-05-29",
        "2028-06-19",
        "2028-07-04",
        "2028-09-04",
        "2028-11-23",
        "2028-12-25",
    ),
}


def is_trading_day(day: date) -> bool:
    if day.weekday() >= 5:  # Saturday / Sunday
        return False
    return day not in _HOLIDAYS.get(day.year, frozenset())


def is_market_open(now: datetime | None = None) -> bool:
    """True during the regular US equities session. A naive `now` is read as ET."""
    if now is None:
        now = datetime.now(tz=_ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=_ET)
    et = now.astimezone(_ET)
    if not is_trading_day(et.date()):
        return False
    return _SESSION_OPEN <= et.time() < _SESSION_CLOSE
