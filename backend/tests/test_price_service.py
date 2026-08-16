"""Tests for PriceService's rate-limit defences.

These cover the failure mode that took live prices down in production: a Yahoo 429
left no cache entry behind, so every caller counted the ticker as a miss and
refetched it immediately, and the app hammered upstream harder while broken than
while healthy. The guarantees asserted here are (a) a failed ticker is not retried
straight away, (b) one rejection pauses the whole service instead of N-1 more
doomed requests, and (c) cached prices keep being served throughout.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from core.config import BREAKER_BASE_COOLDOWN
from services.price_service import PriceService, _is_rate_limited


RATE_LIMIT = Exception("Too Many Requests. Rate limited. Try after a while.")


def _fake_tickers(prices: dict[str, float | Exception]):
    """Stand in for yf.Tickers — .tickers[t].fast_info['lastPrice'] per ticker."""
    holder = MagicMock()
    holder.tickers = {}
    for ticker, outcome in prices.items():
        entry = MagicMock()
        if isinstance(outcome, Exception):
            entry.fast_info.__getitem__.side_effect = outcome
        else:
            entry.fast_info.__getitem__.return_value = outcome
        holder.tickers[ticker] = entry
    return holder


@pytest.fixture
def svc() -> PriceService:
    return PriceService()


class TestRateLimitDetection:
    @pytest.mark.parametrize("msg", [
        "Too Many Requests. Rate limited. Try after a while.",
        "429 Client Error",
        "YFRateLimitError: rate-limit exceeded",
    ])
    def test_recognises_rate_limit(self, msg):
        assert _is_rate_limited(Exception(msg)) is True

    def test_ignores_unrelated_errors(self):
        assert _is_rate_limited(Exception("Connection reset by peer")) is False


class TestNegativeCaching:
    def test_failed_ticker_is_not_immediately_retried(self, svc):
        with patch("services.price_service.yf.Tickers") as yft:
            yft.return_value = _fake_tickers({"AAA": RATE_LIMIT})
            svc.get_live_prices(["AAA"])
            assert yft.call_count == 1

            # Second pass: still inside the cool-off, so no upstream call at all.
            svc.get_live_prices(["AAA"])
            assert yft.call_count == 1

    def test_retries_once_the_cool_off_expires(self, svc):
        with patch("services.price_service.yf.Tickers") as yft:
            yft.return_value = _fake_tickers({"AAA": RATE_LIMIT})
            svc.get_live_prices(["AAA"])

            # Age both the per-ticker cool-off and the service-wide cooldown out.
            svc._failed_at["AAA"] -= 10_000
            svc._cooldown_until = 0.0

            yft.return_value = _fake_tickers({"AAA": 12.5})
            assert svc.get_live_prices(["AAA"]) == {"AAA": 12.5}
            assert yft.call_count == 2

    def test_success_clears_the_failure_marker(self, svc):
        with patch("services.price_service.yf.Tickers") as yft:
            yft.return_value = _fake_tickers({"AAA": RATE_LIMIT})
            svc.get_live_prices(["AAA"])
            assert "AAA" in svc._failed_at

            svc._failed_at["AAA"] -= 10_000
            svc._cooldown_until = 0.0
            yft.return_value = _fake_tickers({"AAA": 30.0})
            svc.get_live_prices(["AAA"])
            assert "AAA" not in svc._failed_at


class TestCircuitBreaker:
    def test_first_rejection_aborts_the_rest_of_the_pass(self, svc):
        tickers = ["AAA", "BBB", "CCC", "DDD"]
        holder = _fake_tickers({t: RATE_LIMIT for t in tickers})

        with patch("services.price_service.yf.Tickers", return_value=holder):
            svc.get_live_prices(tickers)

        # Only the first ticker should have been asked for; the breaker opened
        # and the remaining three were skipped rather than each firing a request.
        attempted = [t for t in tickers if holder.tickers[t].fast_info.__getitem__.called]
        assert attempted == ["AAA"]

    def test_open_breaker_blocks_further_fetches(self, svc):
        with patch("services.price_service.yf.Tickers") as yft:
            yft.return_value = _fake_tickers({"AAA": RATE_LIMIT})
            svc.get_live_prices(["AAA"])
            assert svc._breaker_open() is True

            # A different, never-failed ticker is still blocked — the pause is
            # service-wide because the limit is enforced per IP, not per symbol.
            svc.get_live_prices(["ZZZ"])
            assert yft.call_count == 1

    def test_stale_prices_are_served_while_the_breaker_is_open(self, svc):
        with patch("services.price_service.yf.Tickers") as yft:
            yft.return_value = _fake_tickers({"AAA": 100.0})
            assert svc.get_live_prices(["AAA"]) == {"AAA": 100.0}

            # Age the cached price past its TTL, then start failing.
            svc._price_cache["AAA"] = (100.0, time.time() - 10_000)
            yft.return_value = _fake_tickers({"AAA": RATE_LIMIT})

            # The dashboard keeps the last known price instead of falling back to
            # avg cost, which is the whole point of degrading rather than failing.
            assert svc.get_live_prices(["AAA"]) == {"AAA": 100.0}
            assert svc.get_live_prices(["AAA"]) == {"AAA": 100.0}

    def test_backoff_escalates_once_per_pass_not_once_per_ticker(self, svc):
        tickers = ["AAA", "BBB", "CCC"]
        with patch("services.price_service.yf.Tickers",
                   return_value=_fake_tickers({t: RATE_LIMIT for t in tickers})):
            svc.get_live_prices(tickers)

        # Three rejected tickers in one pass must not compound to BASE * 2^3.
        assert svc._cooldown_secs == BREAKER_BASE_COOLDOWN

    def test_backoff_doubles_across_separate_passes(self, svc):
        with patch("services.price_service.yf.Tickers",
                   return_value=_fake_tickers({"AAA": RATE_LIMIT})):
            svc.get_live_prices(["AAA"])
            assert svc._cooldown_secs == BREAKER_BASE_COOLDOWN

            # Let the cooldown lapse and fail again — the pause should widen.
            svc._cooldown_until = 0.0
            svc._failed_at.clear()
            svc.get_live_prices(["AAA"])
            assert svc._cooldown_secs == BREAKER_BASE_COOLDOWN * 2

    def test_success_resets_the_backoff(self, svc):
        with patch("services.price_service.yf.Tickers") as yft:
            yft.return_value = _fake_tickers({"AAA": RATE_LIMIT})
            svc.get_live_prices(["AAA"])

            svc._cooldown_until = 0.0
            svc._failed_at.clear()
            yft.return_value = _fake_tickers({"AAA": 55.0})
            svc.get_live_prices(["AAA"])

            assert svc._cooldown_secs == 0
            assert svc._breaker_open() is False


class TestTickHandling:
    """What the refresh thread decides to fetch on a given tick."""

    _CLOSE_TS = 1_700_000_000.0

    def _open(self, flag: bool):
        return patch("services.price_service.is_market_open", return_value=flag)

    def _close_at(self):
        close = MagicMock()
        close.timestamp.return_value = self._CLOSE_TS
        return patch("services.price_service.last_session_close", return_value=close)

    def test_during_the_session_everything_is_due(self, svc):
        with self._open(True):
            assert svc._due_this_tick(["AAA", "BBB"]) == ["AAA", "BBB"]

    def test_ticker_priced_after_the_close_is_left_alone(self, svc):
        svc._price_cache["AAA"] = (10.0, self._CLOSE_TS + 60)
        with self._open(False), self._close_at():
            assert svc._due_this_tick(["AAA"]) == []

    def test_ticker_priced_before_the_close_is_warmed_once(self, svc):
        # A user opening the site in the evening should see today's close,
        # not the price from whenever they were last active.
        svc._price_cache["AAA"] = (10.0, self._CLOSE_TS - 10_000)
        with self._open(False), self._close_at():
            assert svc._due_this_tick(["AAA"]) == ["AAA"]
            # ...once per closed period, even if the fetch failed.
            assert svc._due_this_tick(["AAA"]) == []

    def test_never_priced_ticker_is_warmed_once_while_closed(self, svc):
        with self._open(False), self._close_at():
            # A cold cache (out-of-hours deploy) still gets one pass, so the
            # dashboard shows the last close rather than avg cost.
            assert svc._due_this_tick(["AAA"]) == ["AAA"]
            # ...but only one, however long the market stays shut.
            assert svc._due_this_tick(["AAA"]) == []
            assert svc._due_this_tick(["AAA"]) == []

    def test_ticker_appearing_while_closed_is_also_warmed(self, svc):
        with self._open(False):
            assert svc._due_this_tick(["AAA"]) == ["AAA"]
            # A user logging in overnight brings new holdings into the set.
            assert svc._due_this_tick(["AAA", "BBB"]) == ["BBB"]

    def test_reopening_resumes_normal_refreshing(self, svc):
        with self._open(False):
            svc._due_this_tick(["AAA"])
        with self._open(True):
            assert svc._due_this_tick(["AAA"]) == ["AAA"]
        # The one-shot record resets, so the next close warms afresh if needed.
        assert svc._warmed_while_closed == set()

    def test_empty_set_stays_empty(self, svc):
        with self._open(False):
            assert svc._due_this_tick([]) == []
        with self._open(True):
            assert svc._due_this_tick([]) == []


class TestCachedReads:
    def test_get_cached_prices_never_hits_the_network(self, svc):
        svc._price_cache["AAA"] = (42.0, time.time() - 10_000)
        with patch("services.price_service.yf.Tickers") as yft:
            assert svc.get_cached_prices(["AAA", "BBB"]) == {"AAA": 42.0, "BBB": None}
            yft.assert_not_called()


class TestTickerInfo:
    def test_rate_limited_info_is_not_cached_permanently(self, svc):
        handle = MagicMock()
        type(handle).info = PropertyMock(side_effect=RATE_LIMIT)
        with patch("services.price_service.yf.Ticker", return_value=handle):
            assert svc.get_ticker_info("AAA") == {"sector": "", "marketCap": 0}

        # A blank result must not have been memoised, or the ticker would show no
        # sector or market cap until the process restarts.
        assert "AAA" not in svc._ticker_info_cache

    def test_ordinary_failure_is_cached_to_avoid_refetching(self, svc):
        handle = MagicMock()
        type(handle).info = PropertyMock(side_effect=Exception("no such symbol"))
        with patch("services.price_service.yf.Ticker", return_value=handle):
            assert svc.get_ticker_info("AAA") == {"sector": "", "marketCap": 0}

        assert svc._ticker_info_cache["AAA"] == {"sector": "", "marketCap": 0}
