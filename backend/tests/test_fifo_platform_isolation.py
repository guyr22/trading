"""FIFO must partition lots by platform — a sell on platform A cannot
consume lots opened on platform B."""
from __future__ import annotations

from datetime import date

from domain.finance import fifo_closed_lots, fifo_full
from models import Trade, TradeAction


def _trade(action: TradeAction, qty: float, price: float, platform: str | None, day: int) -> Trade:
    return Trade(
        action=action,
        ticker="BULL",
        quantity=qty,
        price=price,
        fees=0.0,
        platform=platform,
        executed_at=date(2026, 5, day),
    )


class TestPlatformIsolation:
    def test_sell_on_one_platform_does_not_consume_other_platform_lot(self):
        # Mirrors the real bug: 510 BULL bought on IBI first, then 1130 BULL
        # on Interactive, then full 1130 sold on Interactive. Should produce
        # exactly one closed lot for 1130 shares on Interactive.
        trades = [
            _trade(TradeAction.BUY, 510, 10.0, "IBI", 1),
            _trade(TradeAction.BUY, 1130, 12.0, "Interactive", 2),
            _trade(TradeAction.SELL, 1130, 15.0, "Interactive", 3),
        ]

        lots = fifo_closed_lots(trades, "BULL")

        assert len(lots) == 1
        assert lots[0].quantity == 1130
        assert lots[0].platform == "Interactive"
        # PnL = (15 - 12) * 1130
        assert lots[0].pnl == 3 * 1130

    def test_ibi_lot_still_open_after_interactive_sell(self):
        trades = [
            _trade(TradeAction.BUY, 510, 10.0, "IBI", 1),
            _trade(TradeAction.BUY, 1130, 12.0, "Interactive", 2),
            _trade(TradeAction.SELL, 1130, 15.0, "Interactive", 3),
        ]

        result = fifo_full(trades, "BULL")

        # 510 shares of BULL remain open on IBI at cost basis $10
        assert result.avg_cost == 10.0
        assert result.realized_pnl == 3 * 1130

    def test_null_platform_is_its_own_bucket(self):
        # Legacy trades with platform=None must not match against named platforms.
        trades = [
            _trade(TradeAction.BUY, 100, 5.0, None, 1),
            _trade(TradeAction.BUY, 200, 8.0, "IBI", 2),
            _trade(TradeAction.SELL, 200, 10.0, "IBI", 3),
        ]

        lots = fifo_closed_lots(trades, "BULL")

        assert len(lots) == 1
        assert lots[0].quantity == 200
        assert lots[0].platform == "IBI"

    def test_interleaved_per_platform_fifo_within_bucket(self):
        # Two buys on the same platform should FIFO normally within that bucket.
        trades = [
            _trade(TradeAction.BUY, 100, 10.0, "IBI", 1),
            _trade(TradeAction.BUY, 100, 20.0, "Interactive", 2),
            _trade(TradeAction.BUY, 100, 30.0, "IBI", 3),
            _trade(TradeAction.SELL, 150, 40.0, "IBI", 4),
        ]

        lots = fifo_closed_lots(trades, "BULL")

        # Two closures on IBI: 100 @ $10 and 50 @ $30. Nothing on Interactive.
        assert len(lots) == 2
        assert all(lot.platform == "IBI" for lot in lots)
        assert lots[0].quantity == 100 and lots[0].avg_buy_price == 10.0
        assert lots[1].quantity == 50 and lots[1].avg_buy_price == 30.0
