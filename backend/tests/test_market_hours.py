"""Tests for the trading-session calendar that gates background price fetching.

The asymmetry that matters: wrongly reporting *open* costs one wasted upstream
request, while wrongly reporting *closed* freezes the dashboard for a whole
session. The unknown-year case is asserted to fail in the harmless direction.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from core.market_hours import is_market_open, is_trading_day

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def et(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=ET)


class TestTradingDay:
    def test_weekday_is_a_trading_day(self):
        assert is_trading_day(date(2026, 8, 4)) is True      # Tuesday

    @pytest.mark.parametrize("day", [date(2026, 8, 8), date(2026, 8, 9)])
    def test_weekend_is_not(self, day):
        assert is_trading_day(day) is False

    @pytest.mark.parametrize("day", [
        date(2026, 1, 1),    # New Year's Day
        date(2026, 4, 3),    # Good Friday
        date(2026, 7, 3),    # Independence Day observed (Jul 4 is a Saturday)
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),  # Christmas
    ])
    def test_holidays_are_not(self, day):
        assert is_trading_day(day) is False

    def test_day_after_thanksgiving_still_trades(self):
        # A half day, but open — the calendar must not treat it as a holiday.
        assert is_trading_day(date(2026, 11, 27)) is True

    def test_unknown_year_defaults_to_open(self):
        # Beyond the published table we assume every weekday trades. That wastes
        # a request on a holiday rather than blanking prices on a trading day.
        assert is_trading_day(date(2045, 12, 25)) is True


class TestSessionHours:
    def test_open_during_the_session(self):
        assert is_market_open(et(2026, 8, 4, 11, 0)) is True

    def test_closed_before_the_bell(self):
        assert is_market_open(et(2026, 8, 4, 9, 29)) is False

    def test_open_exactly_at_the_bell(self):
        assert is_market_open(et(2026, 8, 4, 9, 30)) is True

    def test_closed_at_and_after_the_close(self):
        assert is_market_open(et(2026, 8, 4, 16, 0)) is False
        assert is_market_open(et(2026, 8, 4, 16, 1)) is False

    def test_closed_on_a_weekend_midday(self):
        assert is_market_open(et(2026, 8, 8, 12, 0)) is False

    def test_closed_on_a_holiday_midday(self):
        assert is_market_open(et(2026, 12, 25, 12, 0)) is False


class TestTimezoneHandling:
    def test_utc_input_is_converted(self):
        # 14:30 UTC is 10:30 ET during daylight saving — mid-session.
        assert is_market_open(datetime(2026, 8, 4, 14, 30, tzinfo=UTC)) is True
        # 21:00 UTC is 17:00 ET — after the close.
        assert is_market_open(datetime(2026, 8, 4, 21, 0, tzinfo=UTC)) is False

    def test_winter_offset_is_handled(self):
        # In January ET is UTC-5, so 14:30 UTC is 09:30 ET — the open.
        assert is_market_open(datetime(2026, 1, 6, 14, 30, tzinfo=UTC)) is True
        assert is_market_open(datetime(2026, 1, 6, 13, 30, tzinfo=UTC)) is False

    def test_naive_input_is_read_as_eastern(self):
        assert is_market_open(datetime(2026, 8, 4, 11, 0)) is True
        assert is_market_open(datetime(2026, 8, 4, 20, 0)) is False
