from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from domain.finance import ClosedLot, fifo_closed_lots
from models import Trade
from repositories.trade_repository import TradeRepository
from schemas import PositionResponse
from services.portfolio_service import PortfolioService

if TYPE_CHECKING:
    from services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

COACHING_PERSONA = (
    "You are a trading coach and portfolio analyst. Your role is not just to answer questions "
    "but to proactively surface behavioral patterns, challenge assumptions, and help the user "
    "grow as a trader. Be direct, specific, and always reference actual numbers from the portfolio. "
    "When you notice a pattern — especially a recurring mistake — name it clearly."
)

# Tools are EXPENSIVE (each call is a separate model round-trip and counts against the
# provider's request quota). The full portfolio snapshot + key statistics below already
# contain everything needed for general analysis, so the model must answer from context
# first and reserve tools for data that is genuinely not shown.
DATA_USAGE_INSTRUCTIONS = (
    "USING YOUR DATA (read carefully):\n"
    "  • The PORTFOLIO SUMMARY, KEY STATISTICS, OPEN POSITIONS, RECENT TRADES and CLOSED LOTS "
    "below are the user's COMPLETE, up-to-date data. Answer directly from them.\n"
    "  • For general questions — overall performance, win rate, best/worst trades, behavioral "
    "patterns, what to improve, current positions — DO NOT call any tool. Everything you need "
    "is already above. Calling a tool to re-fetch this data is wrong and slow.\n"
    "  • Only call a tool when the user needs something NOT shown here, e.g. one ticker's full "
    "trade-by-trade history, live price correlations, a benchmark comparison, post-exit price "
    "movement, entry-timing ranges, or a per-platform fee breakdown.\n"
    "  • Never call more than 2 tools to answer a single question. Prefer 0."
)

FOLLOW_UP_INSTRUCTIONS = (
    "FOLLOW-UP QUESTIONS RULE:\n"
    "After any response that involved analysis or pattern findings (i.e. you called a tool or "
    "performed non-trivial analysis), append exactly this block at the end of your response:\n\n"
    "You might also ask:\n"
    '- "<question referencing a specific number, ticker, or metric from the data>"\n'
    '- "<question referencing a specific number, ticker, or metric from the data>"\n\n'
    "Constraints:\n"
    "  • Exactly 2 questions — never fewer, never more.\n"
    "  • Every question must reference at least one specific number, ticker, or metric "
    "from the actual portfolio data (e.g. a P&L figure, a ticker symbol, a percentage, "
    "a date range) — no generic questions.\n"
    "  • Do NOT append the section for simple factual lookups such as 'what is my current "
    "portfolio value?' or 'how many shares of X do I hold?' — only include it when the "
    "response involved analysis, pattern detection, or multi-step reasoning.\n"
    "  • Keep each question short (one line each)."
)

# Cache keyed on (user_id, trade_count, max_trade_id) — invalidates automatically when a trade is added.
_context_cache: dict[tuple[int, int, int], str] = {}


class ChatContextService:
    def __init__(
        self,
        db: Session,
        portfolio_service: PortfolioService,
        analytics_service: AnalyticsService | None = None,
        user_id: int = 0,
    ) -> None:
        self._trade_repo = TradeRepository(db, user_id)
        self._portfolio_service = portfolio_service
        self._analytics_service = analytics_service
        self._user_id = user_id

    def _build_behavioral_brief(self) -> str:
        """Return top-2 behavioral flags as a concise string (capped ~350 chars). Empty on failure."""
        try:
            if self._analytics_service is None:
                logger.info("Behavioral brief skipped: no analytics service")
                return ""
            flags = self._analytics_service.get_behavioral_red_flags()
            if not flags:
                logger.info("Behavioral brief: no flags (insufficient data or no signal)")
                return ""
            brief = "BEHAVIORAL PATTERNS TO WATCH:\n" + "\n".join(f"  • {f}" for f in flags[:2])
            if len(brief) > 350:
                brief = brief[:347] + "..."
            logger.info("Behavioral brief injected (%d chars): %s", len(brief), brief)
            return brief
        except Exception:
            logger.info("Behavioral brief failed silently")
            return ""

    def _build_stats_brief(self) -> str:
        """Exact headline statistics so the model never needs a tool to fetch them. Empty on failure."""
        try:
            if self._analytics_service is None:
                return ""
            s = self._analytics_service.get_portfolio_statistics()
            if not s or s.get("total_trades", 0) == 0:
                return ""
            return (
                "KEY STATISTICS (exact, computed — quote these directly):\n"
                f"  Win Rate: {s['win_rate']:.1f}%   Profit Factor: {s['profit_factor']:.2f}\n"
                f"  Avg Win: ${s['avg_win']:,.2f}   Avg Loss: ${s['avg_loss']:,.2f}\n"
                f"  Best Trade: ${s['best_trade']:,.2f}   Worst Trade: ${s['worst_trade']:,.2f}\n"
                f"  Max Drawdown: ${s['max_drawdown']:,.2f}   Avg Holding: {s['avg_holding_days']:.1f} days\n"
                f"  Closed Trades: {s['total_trades']}   Largest Position: {s['largest_position_pct']:.1f}% of portfolio\n"
                f"  Total Fees: ${s['total_fees']:,.2f}   Avg Fee/Trade: ${s['avg_fees_per_trade']:,.2f}   "
                f"Most Traded: {s['most_traded_ticker']}"
            )
        except Exception:
            logger.info("Stats brief failed silently")
            return ""

    def build(self) -> str:
        count, max_id = self._trade_repo.get_count_and_max_id()
        key = (self._user_id, count, max_id)
        cached = _context_cache.get(key)
        if cached is not None:
            return cached
        result = self._build_context()
        _context_cache[key] = result
        return result

    def _build_context(self) -> str:
        # 1 DB fetch + 1 FIFO pass via build_summary
        summary = self._portfolio_service.build_summary()
        positions = summary.positions

        def _lev_note(p: PositionResponse) -> str:
            if p.leveraged_underlying and p.leverage_factor:
                effective = p.quantity * p.leverage_factor
                return (
                    f" [{p.leverage_factor:+.1f}x leveraged ETF tracking "
                    f"{p.leveraged_underlying}, effective exposure: "
                    f"{effective:.0f} shares of {p.leveraged_underlying}]"
                )
            return ""

        positions_text = "\n".join(
            f"  {p.ticker}: {p.quantity} shares, avg cost ${p.avg_cost:.2f}, "
            f"current ${p.current_price:.2f}, market value ${p.market_value:.2f}, "
            f"unrealized P&L ${p.unrealized_pnl:.2f} ({p.unrealized_pnl_pct:.1f}%){_lev_note(p)}"
            for p in positions
        ) or "  No open positions"

        all_trades = self._trade_repo.get_all_ordered()
        total_fees = sum(float(t.fees or 0) for t in all_trades)

        recent_trades = sorted(all_trades, key=lambda t: (t.executed_at, t.id), reverse=True)[:20]
        trades_text = "\n".join(
            f"  {t.executed_at} {t.action} {t.quantity} {t.ticker} @ ${t.price:.2f}"
            + (f" (fees ${t.fees:.2f})" if t.fees else "")
            for t in recent_trades
        ) or "  No trades yet"

        by_ticker: dict[str, list[Trade]] = {}
        for t in all_trades:
            by_ticker.setdefault(t.ticker, []).append(t)
        all_closed: list[ClosedLot] = []
        for ticker, trades in by_ticker.items():
            all_closed.extend(fifo_closed_lots(trades, ticker))
        all_closed.sort(key=lambda l: l.pnl, reverse=True)

        def _lot_pct(l: ClosedLot) -> str:
            return f" ({l.pnl / l.cost_basis * 100:+.1f}%)" if l.cost_basis else ""

        closed_text = "\n".join(
            f"  {l.ticker}  {l.quantity:.0f}sh  {l.open_date} → {l.close_date}  P&L ${l.pnl:+.2f}{_lot_pct(l)}"
            for l in all_closed
        ) or "  No closed lots yet"

        stats_brief = self._build_stats_brief()
        stats_section = f"{stats_brief}\n\n" if stats_brief else ""

        behavioral_brief = self._build_behavioral_brief()
        brief_section = f"\n\n{behavioral_brief}" if behavioral_brief else ""

        return (
            f"{COACHING_PERSONA} "
            f"Today's date is {date.today().strftime('%d/%m/%Y')}.\n\n"
            f"{DATA_USAGE_INSTRUCTIONS}\n\n"
            f"PORTFOLIO SUMMARY (excluding index funds):\n"
            f"  Total Market Value: ${summary.total_market_value:,.2f}\n"
            f"  Unrealized P&L: ${summary.total_unrealized_pnl:,.2f}\n"
            f"  Realized P&L: ${summary.total_realized_pnl:,.2f}\n"
            f"  Total Fees Paid: ${total_fees:,.2f}\n\n"
            f"{stats_section}"
            f"OPEN POSITIONS:\n{positions_text}\n\n"
            f"RECENT TRADES (last 20, excluding indexes):\n{trades_text}\n\n"
            f"CLOSED LOTS (all, sorted by P&L descending):\n{closed_text}"
            f"{brief_section}"
            f"\n\n{FOLLOW_UP_INSTRUCTIONS}"
        )
