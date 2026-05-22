"""Pure FIFO accounting engine — no framework dependencies."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from models import Trade, TradeAction


@dataclass
class ClosedLot:
    ticker: str
    pnl: float
    open_date: date
    close_date: date
    quantity: float
    cost_basis: float = field(default=0.0)
    avg_buy_price: float = field(default=0.0)
    avg_sell_price: float = field(default=0.0)
    platform: Optional[str] = field(default=None)


@dataclass
class FifoResult:
    avg_cost: float
    realized_pnl: float
    closed_lots: list[ClosedLot]


def fifo_full(ticker_trades: list[Trade], ticker: str) -> FifoResult:
    """Single FIFO pass — returns avg cost, realized P&L, and all closed lots.

    Lots are partitioned by platform: buys and sells on one platform never
    match against lots on another. NULL platform forms its own bucket so
    legacy trades stay internally consistent. Handles long and short
    positions; fees are deducted proportionally per share as lots consume.
    """
    long_by_platform: dict[Optional[str], list[list]] = {}
    short_by_platform: dict[Optional[str], list[list]] = {}
    closed: list[ClosedLot] = []
    realized = 0.0

    for t in ticker_trades:
        qty = float(t.quantity)
        price = float(t.price)
        fps = float(t.fees or 0.0) / qty if qty else 0.0
        tdate = t.executed_at
        platform = t.platform

        long_lots = long_by_platform.setdefault(platform, [])
        short_lots = short_by_platform.setdefault(platform, [])

        if t.action == TradeAction.BUY:
            remaining = qty
            while remaining > 0 and short_lots:
                lot_qty, lot_price, lot_fps, lot_date = short_lots[0]
                consumed = min(lot_qty, remaining)
                pnl = (lot_price - price) * consumed - lot_fps * consumed - fps * consumed
                realized += pnl
                closed.append(ClosedLot(ticker, pnl, lot_date, tdate, consumed, lot_price * consumed, avg_buy_price=price, avg_sell_price=lot_price, platform=platform))
                short_lots[0][0] -= consumed
                remaining -= consumed
                if short_lots[0][0] == 0:
                    short_lots.pop(0)
            if remaining > 0:
                long_lots.append([remaining, price, fps, tdate])
        else:
            remaining = qty
            while remaining > 0 and long_lots:
                lot_qty, lot_price, lot_fps, lot_date = long_lots[0]
                consumed = min(lot_qty, remaining)
                pnl = (price - lot_price) * consumed - lot_fps * consumed - fps * consumed
                realized += pnl
                closed.append(ClosedLot(ticker, pnl, lot_date, tdate, consumed, lot_price * consumed, avg_buy_price=lot_price, avg_sell_price=price, platform=platform))
                long_lots[0][0] -= consumed
                remaining -= consumed
                if long_lots[0][0] == 0:
                    long_lots.pop(0)
            if remaining > 0:
                short_lots.append([remaining, price, fps, tdate])

    all_long_lots = [lot for lots in long_by_platform.values() for lot in lots]
    all_short_lots = [lot for lots in short_by_platform.values() for lot in lots]
    long_qty = sum(lot[0] for lot in all_long_lots)
    short_qty = sum(lot[0] for lot in all_short_lots)
    net_qty = long_qty - short_qty

    if net_qty > 0:
        avg_cost = sum(lot[0] * lot[1] for lot in all_long_lots) / long_qty
    elif net_qty < 0:
        avg_cost = sum(lot[0] * lot[1] for lot in all_short_lots) / short_qty
    else:
        avg_cost = 0.0

    return FifoResult(avg_cost=avg_cost, realized_pnl=realized, closed_lots=closed)


def fifo_avg_cost_and_realized(trades: list[Trade], ticker: str) -> tuple[float, float]:
    """Return (avg_cost_of_remaining_shares, total_realized_pnl) via FIFO."""
    r = fifo_full(trades, ticker)
    return r.avg_cost, r.realized_pnl


def fifo_closed_lots(ticker_trades: list[Trade], ticker: str) -> list[ClosedLot]:
    """FIFO matching — returns every lot closure as a ClosedLot."""
    return fifo_full(ticker_trades, ticker).closed_lots
