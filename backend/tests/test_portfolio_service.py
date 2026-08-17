"""Tests for PortfolioService.price_available — positions whose ticker has no
cached price yet must say so, so the UI can render a skeleton instead of a
fake price (avg-cost fallback) and $0 P&L.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from models import Trade, TradeAction
from services.portfolio_service import PortfolioService


def _trade(
    ticker: str,
    action: TradeAction,
    executed_at: date,
    price: float,
    quantity: float = 10.0,
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


def _make_svc(trades: list[MagicMock], prices: dict[str, float | None]) -> PortfolioService:
    svc = PortfolioService.__new__(PortfolioService)
    svc._trade_repo = MagicMock()
    svc._trade_repo.get_all_ordered.return_value = trades
    svc._etf_repo = MagicMock()
    svc._etf_repo.get_map.return_value = {}
    svc._price_service = MagicMock()
    svc._price_service.get_cached_prices.side_effect = lambda tickers: {
        t: prices.get(t) for t in tickers
    }
    return svc


class TestPriceAvailable:
    def test_cached_price_marks_position_available(self):
        trades = [_trade("AAA", TradeAction.BUY, date(2024, 1, 2), 100.0)]
        [pos] = _make_svc(trades, {"AAA": 110.0}).build_positions()
        assert pos.price_available is True
        assert pos.current_price == 110.0
        assert pos.unrealized_pnl == 100.0

    def test_unpriced_ticker_flagged_and_falls_back_to_avg_cost(self):
        trades = [_trade("AAA", TradeAction.BUY, date(2024, 1, 2), 100.0)]
        [pos] = _make_svc(trades, {}).build_positions()
        assert pos.price_available is False
        # Fallback keeps totals finite: price = avg cost, so P&L reads zero.
        assert pos.current_price == 100.0
        assert pos.unrealized_pnl == 0.0

    def test_index_summary_flags_unpriced_ticker(self):
        trades = [
            _trade("VOO", TradeAction.BUY, date(2024, 1, 2), 400.0),
            _trade("QQQ", TradeAction.BUY, date(2024, 1, 2), 350.0),
        ]
        summary = _make_svc([], {"VOO": 410.0}).build_index_summary(trades)
        by_ticker = {p.ticker: p for p in summary.positions}
        assert by_ticker["VOO"].price_available is True
        assert by_ticker["QQQ"].price_available is False
