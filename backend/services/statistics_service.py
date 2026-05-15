from sqlalchemy.orm import Session

from domain.finance import ClosedLot, fifo_closed_lots
from repositories.etf_repository import EtfRepository
from repositories.trade_repository import TradeRepository
from schemas import ClosedLotResponse, CumulativePoint, MonthlyPnl, PortfolioStatistics, TickerStat
from services.portfolio_service import PortfolioService


class StatisticsService:
    def __init__(self, db: Session, portfolio_service: PortfolioService, etf_repo: EtfRepository) -> None:
        self._trade_repo = TradeRepository(db)
        self._portfolio_service = portfolio_service
        self._etf_repo = etf_repo

    def compute(self) -> PortfolioStatistics:
        all_trades = self._trade_repo.get_all_ordered()
        etf_map = self._etf_repo.get_map()  # ticker -> LeveragedEtf

        def effective_ticker(t: str) -> str:
            return etf_map[t].underlying if t in etf_map else t

        # Run FIFO per actual traded ticker (PTIR and PLTR are separate instruments)
        actual_tickers = list(dict.fromkeys(t.ticker for t in all_trades))
        raw: dict[str, dict] = {}
        for ticker in actual_tickers:
            t_trades = [t for t in all_trades if t.ticker == ticker]
            closed = fifo_closed_lots(t_trades, ticker)
            raw[ticker] = {
                "closed": closed,
                "realized": sum(l.pnl for l in closed),
                "fees": sum(float(t.fees or 0) for t in t_trades),
                "wins": sum(1 for l in closed if l.pnl > 0),
                "trades_count": len(t_trades),
            }

        # Aggregate under effective (underlying) tickers
        eff_tickers = list(dict.fromkeys(effective_ticker(t) for t in actual_tickers))
        all_closed: list[ClosedLot] = []
        ticker_stats: list[TickerStat] = []

        for eff in eff_tickers:
            contributors = [t for t in actual_tickers if effective_ticker(t) == eff]
            merged_closed: list[ClosedLot] = []
            total_realized = total_fees = 0.0
            total_trades = total_wins = 0
            for t in contributors:
                s = raw[t]
                merged_closed.extend(s["closed"])
                total_realized += s["realized"]
                total_fees += s["fees"]
                total_trades += s["trades_count"]
                total_wins += s["wins"]
            all_closed.extend(merged_closed)
            win_rate = total_wins / len(merged_closed) * 100 if merged_closed else 0.0
            ticker_stats.append(TickerStat(
                ticker=eff,
                realized_pnl=round(total_realized, 2),
                total_fees=round(total_fees, 2),
                win_rate=round(win_rate, 1),
                trades_count=len(merged_closed),
            ))

        ticker_stats.sort(key=lambda x: x.realized_pnl, reverse=True)

        pnls = [l.pnl for l in all_closed]
        wins_pnl = [p for p in pnls if p > 0]
        losses_pnl = [p for p in pnls if p < 0]
        win_rate = len(wins_pnl) / len(pnls) * 100 if pnls else 0.0
        avg_win = sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0.0
        avg_loss = sum(losses_pnl) / len(losses_pnl) if losses_pnl else 0.0
        profit_factor = sum(wins_pnl) / abs(sum(losses_pnl)) if losses_pnl else 0.0
        best_trade = max(pnls) if pnls else 0.0
        worst_trade = min(pnls) if pnls else 0.0

        positions = self._portfolio_service.build_positions()
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_pnl = sum(pnls) + total_unrealized

        total_trades = len(all_trades)
        total_fees = sum(float(t.fees or 0) for t in all_trades)
        avg_fees_per_trade = total_fees / total_trades if total_trades else 0.0
        ticker_counts: dict[str, int] = {}
        for t in all_trades:
            eff = effective_ticker(t.ticker)
            ticker_counts[eff] = ticker_counts.get(eff, 0) + 1
        most_traded = max(ticker_counts, key=lambda k: ticker_counts[k]) if ticker_counts else ""

        sorted_closed = sorted(all_closed, key=lambda l: (l.close_date, 0))
        cum = peak = max_drawdown = 0.0
        for lot in sorted_closed:
            cum += lot.pnl
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_drawdown:
                max_drawdown = dd

        holding_days = [(l.close_date - l.open_date).days for l in all_closed]
        avg_holding_days = sum(holding_days) / len(holding_days) if holding_days else 0.0

        total_mv = sum(p.market_value for p in positions)
        largest_position_pct = (
            max((abs(p.market_value) / total_mv * 100 for p in positions), default=0.0)
            if total_mv else 0.0
        )

        monthly: dict[str, float] = {}
        for lot in sorted_closed:
            key = lot.close_date.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0.0) + lot.pnl
        monthly_pnl = [MonthlyPnl(month=k, realized_pnl=round(v, 2)) for k, v in sorted(monthly.items())]

        daily: dict[str, float] = {}
        running = 0.0
        for lot in sorted_closed:
            running += lot.pnl
            daily[lot.close_date.strftime("%Y-%m-%d")] = running
        cumulative_pnl = [CumulativePoint(date=k, cumulative_pnl=round(v, 2)) for k, v in sorted(daily.items())]

        closed_lot_responses = [
            ClosedLotResponse(
                ticker=l.ticker,
                open_date=l.open_date,
                close_date=l.close_date,
                quantity=round(l.quantity, 6),
                cost_basis=round(l.cost_basis, 2),
                avg_buy_price=round(l.avg_buy_price, 4),
                avg_sell_price=round(l.avg_sell_price, 4),
                pnl=round(l.pnl, 2),
                pnl_pct=round(l.pnl / l.cost_basis * 100, 2) if l.cost_basis else 0.0,
            )
            for l in sorted(all_closed, key=lambda x: (x.close_date, 0), reverse=True)
        ]

        return PortfolioStatistics(
            total_pnl=round(total_pnl, 2),
            win_rate=round(win_rate, 1),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            profit_factor=round(profit_factor, 2),
            best_trade=round(best_trade, 2),
            worst_trade=round(worst_trade, 2),
            max_drawdown=round(max_drawdown, 2),
            avg_holding_days=round(avg_holding_days, 1),
            largest_position_pct=round(largest_position_pct, 1),
            total_trades=total_trades,
            total_fees=round(total_fees, 2),
            avg_fees_per_trade=round(avg_fees_per_trade, 2),
            most_traded_ticker=most_traded,
            ticker_stats=ticker_stats,
            monthly_pnl=monthly_pnl,
            cumulative_pnl=cumulative_pnl,
            closed_lots=closed_lot_responses,
        )
