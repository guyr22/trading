"""Tests for StatisticsService.compute_benchmark — benchmarking closed lots vs an index.

Uses the real FIFO engine but a mocked price series so the suite stays hermetic
(no yfinance network calls). See _make_stats_svc for the construction pattern.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from models import Trade, TradeAction


def _trade(
    ticker: str,
    action: TradeAction,
    executed_at: date,
    price: float,
    quantity: float = 100.0,
    fees: float = 0.0,
) -> MagicMock:
    t = MagicMock(spec=Trade)
    t.ticker = ticker
    t.action = action
    t.executed_at = executed_at
    t.price = price
    t.quantity = quantity
    t.fees = fees
    t.platform = None
    return t


def _make_stats_svc(trades: list[MagicMock], series: list[tuple[str, float]]):
    """Build a StatisticsService that runs real FIFO over `trades` and returns
    `series` as the benchmark price history (bypassing the network)."""
    from services.statistics_service import StatisticsService

    svc = StatisticsService.__new__(StatisticsService)
    svc._trade_repo = MagicMock()
    svc._trade_repo.get_all_ordered.return_value = trades
    svc._portfolio_service = MagicMock()
    svc._etf_repo = MagicMock()
    svc._price_service = MagicMock()
    svc._price_service.get_historical_closes.return_value = series
    return svc


class TestComputeBenchmark:
    def test_alpha_beat_rate_and_cumulative(self):
        # X: +50% winner that beats SPY's +10% over its window.
        # Y: -10% loser that trails SPY's +20% over its window.
        trades = [
            _trade("X", TradeAction.BUY, date(2024, 1, 2), 100.0),
            _trade("X", TradeAction.SELL, date(2024, 2, 1), 150.0),
            _trade("Y", TradeAction.BUY, date(2024, 1, 2), 100.0),
            _trade("Y", TradeAction.SELL, date(2024, 3, 1), 90.0),
        ]
        series = [("2024-01-02", 100.0), ("2024-02-01", 110.0), ("2024-03-01", 120.0)]
        r = _make_stats_svc(trades, series).compute_benchmark("SPY")

        assert r.available is True
        assert r.benchmark_ticker == "SPY"
        assert r.your_realized_pnl == 4000.0       # +5000 - 1000
        assert r.benchmark_pnl == 3000.0           # 10000*0.10 + 10000*0.20
        assert r.alpha == 1000.0                   # 4000 - 3000
        assert r.lots_total == 2
        assert r.lots_beat == 1                     # only X beats its window
        assert r.beat_rate == 50.0

    def test_cumulative_curve_is_ordered_and_aligned(self):
        trades = [
            _trade("X", TradeAction.BUY, date(2024, 1, 2), 100.0),
            _trade("X", TradeAction.SELL, date(2024, 2, 1), 150.0),
            _trade("Y", TradeAction.BUY, date(2024, 1, 2), 100.0),
            _trade("Y", TradeAction.SELL, date(2024, 3, 1), 90.0),
        ]
        series = [("2024-01-02", 100.0), ("2024-02-01", 110.0), ("2024-03-01", 120.0)]
        r = _make_stats_svc(trades, series).compute_benchmark("SPY")

        dates = [p.date for p in r.cumulative]
        assert dates == sorted(dates)
        assert dates == ["2024-02-01", "2024-03-01"]
        # Running totals accumulate by close date.
        assert (r.cumulative[0].your_pnl, r.cumulative[0].benchmark_pnl) == (5000.0, 1000.0)
        assert (r.cumulative[1].your_pnl, r.cumulative[1].benchmark_pnl) == (4000.0, 3000.0)
        # Final cumulative point matches the headline totals.
        assert r.cumulative[-1].your_pnl == r.your_realized_pnl
        assert r.cumulative[-1].benchmark_pnl == r.benchmark_pnl

    def test_asof_falls_back_to_prior_trading_day(self):
        # Close date 2024-02-19 (Presidents' Day) is absent from the series;
        # the as-of lookup should use the prior trading day's close (110.0).
        trades = [
            _trade("X", TradeAction.BUY, date(2024, 1, 2), 100.0),
            _trade("X", TradeAction.SELL, date(2024, 2, 19), 100.0),
        ]
        series = [("2024-01-02", 100.0), ("2024-02-16", 110.0), ("2024-02-20", 130.0)]
        r = _make_stats_svc(trades, series).compute_benchmark("SPY")

        # SPY return over window uses 110.0 (prior trading day), not 130.0.
        assert r.benchmark_pnl == 1000.0           # 10000 * (110/100 - 1)

    def test_no_closed_lots_is_unavailable(self):
        trades = [_trade("X", TradeAction.BUY, date(2024, 1, 2), 100.0)]  # open only
        r = _make_stats_svc(trades, [("2024-01-02", 100.0)]).compute_benchmark("SPY")

        assert r.available is False
        assert r.lots_total == 0
        assert r.cumulative == []

    def test_missing_price_data_is_unavailable_but_keeps_realized(self):
        trades = [
            _trade("X", TradeAction.BUY, date(2024, 1, 2), 100.0),
            _trade("X", TradeAction.SELL, date(2024, 2, 1), 150.0),
        ]
        r = _make_stats_svc(trades, []).compute_benchmark("SPY")  # price fetch failed

        assert r.available is False
        assert r.your_realized_pnl == 5000.0       # realized P&L still surfaced
        assert r.benchmark_pnl == 0.0
