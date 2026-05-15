from sqlalchemy.orm import Session

from domain.finance import FifoResult, fifo_full
from models import TradeAction
from repositories.etf_repository import EtfRepository
from repositories.trade_repository import TradeRepository
from schemas import PortfolioSummary, PositionResponse
from services.price_service import PriceService


class PortfolioService:
    def __init__(self, db: Session, price_service: PriceService) -> None:
        self._trade_repo = TradeRepository(db)
        self._etf_repo = EtfRepository(db)
        self._price_service = price_service

    def _compute_positions_and_realized(self) -> tuple[list[PositionResponse], float]:
        all_trades = self._trade_repo.get_all_ordered()
        if not all_trades:
            return [], 0.0

        by_ticker: dict = {}
        for t in all_trades:
            by_ticker.setdefault(t.ticker, []).append(t)

        held: list[tuple[str, float, float]] = []
        total_realized = 0.0

        for ticker, trades in by_ticker.items():
            buys = sum(t.quantity for t in trades if t.action == TradeAction.BUY)
            sells = sum(t.quantity for t in trades if t.action == TradeAction.SELL)
            qty = buys - sells
            result: FifoResult = fifo_full(trades, ticker)
            total_realized += result.realized_pnl
            if qty == 0:
                continue
            held.append((ticker, qty, result.avg_cost))

        if not held:
            return [], total_realized

        prices = self._price_service.get_live_prices([t for t, _, _ in held])
        lev_map = self._etf_repo.get_map()

        positions: list[PositionResponse] = []
        for ticker, qty, avg in held:
            current_price = prices.get(ticker) or avg
            market_value = qty * current_price
            cost_basis = qty * avg
            unrealized = market_value - cost_basis
            unrealized_pct = (unrealized / cost_basis * 100) if cost_basis else 0.0
            lev = lev_map.get(ticker)
            positions.append(PositionResponse(
                ticker=ticker,
                quantity=qty,
                avg_cost=round(avg, 2),
                current_price=round(current_price, 2),
                market_value=round(market_value, 2),
                unrealized_pnl=round(unrealized, 2),
                unrealized_pnl_pct=round(unrealized_pct, 2),
                leveraged_underlying=lev.underlying if lev else None,
                leverage_factor=lev.leverage_factor if lev else None,
            ))
        return positions, total_realized

    def build_positions(self) -> list[PositionResponse]:
        positions, _ = self._compute_positions_and_realized()
        return positions

    def total_realized_pnl(self, exclude: set[str] | frozenset[str] | None = None) -> float:
        all_trades = self._trade_repo.get_all_ordered()
        if exclude:
            all_trades = [t for t in all_trades if t.ticker not in exclude]
        by_ticker: dict = {}
        for t in all_trades:
            by_ticker.setdefault(t.ticker, []).append(t)
        return sum(fifo_full(trades, ticker).realized_pnl for ticker, trades in by_ticker.items())

    def build_summary(self) -> PortfolioSummary:
        positions, total_realized = self._compute_positions_and_realized()
        return PortfolioSummary(
            total_market_value=round(sum(p.market_value for p in positions), 2),
            total_unrealized_pnl=round(sum(p.unrealized_pnl for p in positions), 2),
            total_realized_pnl=round(total_realized, 2),
            positions=positions,
        )

    def build_index_summary(self, index_trades: list) -> PortfolioSummary:
        if not index_trades:
            return PortfolioSummary(
                total_market_value=0.0,
                total_unrealized_pnl=0.0,
                total_realized_pnl=0.0,
                positions=[],
            )

        by_ticker: dict = {}
        for t in index_trades:
            by_ticker.setdefault(t.ticker, []).append(t)

        held: list[tuple[str, float, float]] = []
        total_realized = 0.0

        for ticker, trades in by_ticker.items():
            buys = sum(t.quantity for t in trades if t.action == TradeAction.BUY)
            sells = sum(t.quantity for t in trades if t.action == TradeAction.SELL)
            qty = buys - sells
            result: FifoResult = fifo_full(trades, ticker)
            total_realized += result.realized_pnl
            if qty == 0:
                continue
            held.append((ticker, qty, result.avg_cost))

        if not held:
            return PortfolioSummary(
                total_market_value=0.0,
                total_unrealized_pnl=0.0,
                total_realized_pnl=round(total_realized, 2),
                positions=[],
            )

        prices = self._price_service.get_live_prices([t for t, _, _ in held])
        positions: list[PositionResponse] = []
        for ticker, qty, avg in held:
            current_price = prices.get(ticker) or avg
            market_value = qty * current_price
            cost_basis = qty * avg
            unrealized = market_value - cost_basis
            unrealized_pct = (unrealized / cost_basis * 100) if cost_basis else 0.0
            positions.append(PositionResponse(
                ticker=ticker,
                quantity=qty,
                avg_cost=round(avg, 2),
                current_price=round(current_price, 2),
                market_value=round(market_value, 2),
                unrealized_pnl=round(unrealized, 2),
                unrealized_pnl_pct=round(unrealized_pct, 2),
                leveraged_underlying=None,
                leverage_factor=None,
            ))

        return PortfolioSummary(
            total_market_value=round(sum(p.market_value for p in positions), 2),
            total_unrealized_pnl=round(sum(p.unrealized_pnl for p in positions), 2),
            total_realized_pnl=round(total_realized, 2),
            positions=positions,
        )
