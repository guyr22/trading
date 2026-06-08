"""Builds and sends the weekly per-position portfolio digest email.

Reuses the existing analytics building blocks — PortfolioService for positions,
PriceService.get_historical_closes for each holding's 1-week move (the same method
the benchmark uses), FIFO closed lots for realized-this-week, and
AnalyticsService.get_behavioral_red_flags for the coaching lines.
"""
import bisect
import os
from datetime import date, timedelta

from sqlalchemy.orm import Session

from core.logging import get_logger
from domain.finance import fifo_closed_lots
from models import TradeAction, User
from repositories.etf_repository import EtfRepository
from repositories.trade_repository import TradeRepository
from services.analytics_service import AnalyticsService
from services.email_service import EmailService
from services.portfolio_service import PortfolioService
from services.price_service import PriceService
from services.statistics_service import StatisticsService

logger = get_logger(__name__)


def _money(n: float) -> str:
    return f"${n:,.0f}" if abs(n) >= 100 else f"${n:,.2f}"


def _signed(n: float) -> str:
    return f"+{_money(n)}" if n >= 0 else f"-{_money(abs(n))}"


def _arrow(n: float) -> str:
    return "▲" if n >= 0 else "▼"


def _color(n: float) -> str:
    return "#16a34a" if n >= 0 else "#dc2626"


class DigestService:
    def __init__(self, price_service: PriceService, email_service: EmailService) -> None:
        self._price_service = price_service
        self._email_service = email_service

    # ---- public API ---------------------------------------------------------

    def send_for_user(self, db: Session, user: User, *, skip_if_empty: bool = False) -> bool:
        data = self._collect(db, user)
        if skip_if_empty and not data["positions"] and data["realized_week"] == 0.0:
            return False
        subject, html = self._render(data)
        return self._email_service.send_html(user.email, subject, html)

    def send_weekly_batch(self, db: Session) -> int:
        users = db.query(User).filter(User.digest_opt_in.is_(True)).all()
        sent = 0
        for user in users:
            try:
                if self.send_for_user(db, user, skip_if_empty=True):
                    sent += 1
            except Exception as e:  # noqa: BLE001 — one bad user shouldn't stop the batch
                logger.warning("Digest build/send failed for user %d: %s", user.id, e)
        logger.info("Weekly digest batch: sent %d email(s)", sent)
        return sent

    # ---- data collection ----------------------------------------------------

    def _week_ago_price(self, ticker: str, week_ago: date) -> float | None:
        series = self._price_service.get_historical_closes(ticker, week_ago - timedelta(days=21))
        if not series:
            return None
        dates = [d for d, _ in series]
        prices = [p for _, p in series]
        i = bisect.bisect_right(dates, week_ago.strftime("%Y-%m-%d")) - 1
        return prices[i] if i >= 0 else None

    def _collect(self, db: Session, user: User) -> dict:
        today = date.today()
        cutoff = today - timedelta(days=7)

        portfolio_svc = PortfolioService(db, self._price_service, user.id)
        positions = portfolio_svc.build_positions()

        rows = []
        for p in positions:
            wk = self._week_ago_price(p.ticker, cutoff)
            wk_pct = ((p.current_price - wk) / wk * 100) if wk else None
            rows.append({
                "ticker": p.ticker,
                "quantity": p.quantity,
                "current_price": p.current_price,
                "week_pct": wk_pct,
                "market_value": p.market_value,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
            })

        total_mv = sum(p.market_value for p in positions)
        total_unrealized = sum(p.unrealized_pnl for p in positions)

        # Realized P&L + fees over the last 7 days.
        trade_repo = TradeRepository(db, user.id)
        all_trades = trade_repo.get_all_ordered()
        by_ticker: dict = {}
        for t in all_trades:
            by_ticker.setdefault(t.ticker, []).append(t)
        realized_week = 0.0
        closed_week: list[dict] = []
        for ticker, trades in by_ticker.items():
            for lot in fifo_closed_lots(trades, ticker):
                if lot.close_date >= cutoff:
                    realized_week += lot.pnl
                    closed_week.append({
                        "ticker": lot.ticker,
                        "close_date": lot.close_date,
                        "quantity": lot.quantity,
                        "pnl": lot.pnl,
                        "pnl_pct": (lot.pnl / lot.cost_basis * 100) if lot.cost_basis else 0.0,
                    })
        lots_week = len(closed_week)
        # Most recent first, then largest moves.
        closed_week.sort(key=lambda r: (r["close_date"], abs(r["pnl"])), reverse=True)
        fees_week = sum(float(t.fees or 0) for t in all_trades if t.executed_at >= cutoff)

        # Movers — open positions (by 1-week price move) plus lots closed this
        # week (by realized return), so the week's biggest win/loss reflects both.
        movers = [
            {"ticker": r["ticker"], "pct": r["week_pct"], "kind": "held"}
            for r in rows if r["week_pct"] is not None
        ]
        movers += [
            {"ticker": c["ticker"], "pct": c["pnl_pct"], "kind": "closed"}
            for c in closed_week
        ]
        best = max(movers, key=lambda m: m["pct"], default=None)
        worst = min(movers, key=lambda m: m["pct"], default=None)

        # Behavioral red flags (best-effort; returns [] when insufficient data).
        flags: list[str] = []
        try:
            etf_repo = EtfRepository(db)
            stats_svc = StatisticsService(db, portfolio_svc, etf_repo, self._price_service, user.id)
            analytics_svc = AnalyticsService(db, portfolio_svc, stats_svc, self._price_service, user.id)
            flags = analytics_svc.get_behavioral_red_flags()
        except Exception as e:  # noqa: BLE001
            logger.warning("Red-flag computation failed for user %d: %s", user.id, e)

        # Money gained/lost this week, flow-adjusted so buying or selling during
        # the week isn't mistaken for a gain or loss. Per ticker:
        #   contribution = current_value - value_at_week_start - net_invested
        # where net_invested is cash put in via buys (incl. fees) minus proceeds
        # taken out via sells (net of fees) this week. Shares bought this week net
        # to ~0 (bought and valued at the same price); shares sold are measured
        # from their week-start value to their actual proceeds. Summed over all
        # tickers this equals realized + unrealized P&L for the week — computed
        # from trades + historical prices only, no cash balance required.
        emv_by_ticker = {p.ticker: p.market_value for p in positions}
        weekly_pnl = 0.0
        for ticker, trades in by_ticker.items():
            qty_start = sum(
                (t.quantity if t.action == TradeAction.BUY else -t.quantity)
                for t in trades if t.executed_at < cutoff
            )
            bmv = 0.0
            if qty_start:
                wk = self._week_ago_price(ticker, cutoff)
                if wk is None:
                    continue  # can't value week-start holdings → leave ticker out
                bmv = qty_start * wk
            net_invested = sum(
                (t.quantity * t.price + float(t.fees or 0))
                if t.action == TradeAction.BUY
                else -(t.quantity * t.price - float(t.fees or 0))
                for t in trades if t.executed_at >= cutoff
            )
            weekly_pnl += emv_by_ticker.get(ticker, 0.0) - bmv - net_invested

        return {
            "today": today,
            "positions": rows,
            "total_mv": total_mv,
            "total_unrealized": total_unrealized,
            "weekly_pnl": weekly_pnl,
            "realized_week": realized_week,
            "lots_week": lots_week,
            "closed_week": closed_week,
            "fees_week": fees_week,
            "best": best,
            "worst": worst,
            "flags": flags,
        }

    # ---- rendering ----------------------------------------------------------

    def _render(self, d: dict) -> tuple[str, str]:
        wpnl = d["weekly_pnl"]
        subject = f"Your weekly portfolio digest — {_arrow(wpnl)} {_money(abs(wpnl))} this week"

        frontend = os.environ.get("FRONTEND_URL", "").rstrip("/")
        date_str = d["today"].strftime("%b %d, %Y")

        if d["positions"]:
            position_rows = "".join(
                f"""
                <tr>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;"><strong>{r['ticker']}</strong></td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;">{r['quantity']:g}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;">${r['current_price']:,.2f}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;color:{_color(r['week_pct']) if r['week_pct'] is not None else '#888'};">
                    {(_arrow(r['week_pct']) + ' ' + format(abs(r['week_pct']), '.1f') + '%') if r['week_pct'] is not None else '—'}
                  </td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;">{_money(r['market_value'])}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;color:{_color(r['unrealized_pnl'])};">
                    {_signed(r['unrealized_pnl'])} ({r['unrealized_pnl_pct']:+.0f}%)
                  </td>
                </tr>"""
                for r in d["positions"]
            )
            positions_block = f"""
            <h3 style="margin:24px 0 8px;font-size:15px;color:#111;">Your positions</h3>
            <table style="width:100%;border-collapse:collapse;font-size:13px;color:#333;">
              <tr style="color:#888;text-align:left;">
                <th style="padding:6px;font-weight:600;">Ticker</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Shares</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Price</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Stock 1-wk</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Mkt value</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Unreal. P&amp;L</th>
              </tr>
              {position_rows}
            </table>"""
        else:
            positions_block = '<p style="color:#888;font-size:14px;margin:24px 0;">No open positions this week.</p>'

        movers_block = ""
        if d["best"] and d["worst"]:
            b, w = d["best"], d["worst"]
            b_tag = " (closed)" if b["kind"] == "closed" else ""
            w_tag = " (closed)" if w["kind"] == "closed" else ""
            movers_block = f"""
            <h3 style="margin:24px 0 8px;font-size:15px;color:#111;">This week</h3>
            <p style="font-size:14px;color:#333;margin:4px 0;">
              🏆 Biggest gainer <strong>{b['ticker']}</strong>
              <span style="color:{_color(b['pct'])};">{_arrow(b['pct'])} {abs(b['pct']):.1f}%{b_tag}</span>
              &nbsp;&nbsp;·&nbsp;&nbsp;
              📉 Biggest drag <strong>{w['ticker']}</strong>
              <span style="color:{_color(w['pct'])};">{_arrow(w['pct'])} {abs(w['pct']):.1f}%{w_tag}</span>
            </p>"""

        realized_block = f"""
            <p style="font-size:14px;color:#333;margin:4px 0;">
              Realized P&amp;L (last 7d)
              <strong style="color:{_color(d['realized_week'])};">{_signed(d['realized_week'])}</strong>
              across {d['lots_week']} closed lot{'s' if d['lots_week'] != 1 else ''}
              · fees {_money(d['fees_week'])}
            </p>"""

        closed_block = ""
        if d["closed_week"]:
            closed_rows = "".join(
                f"""
                <tr>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;"><strong>{c['ticker']}</strong></td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;color:#888;">{c['close_date'].strftime('%b %d')}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;">{c['quantity']:g}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:right;color:{_color(c['pnl'])};">
                    {_signed(c['pnl'])} ({c['pnl_pct']:+.1f}%)
                  </td>
                </tr>"""
                for c in d["closed_week"]
            )
            closed_block = f"""
            <h3 style="margin:24px 0 8px;font-size:15px;color:#111;">Closed this week</h3>
            <table style="width:100%;border-collapse:collapse;font-size:13px;color:#333;">
              <tr style="color:#888;text-align:left;">
                <th style="padding:6px;font-weight:600;">Ticker</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Closed</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Qty</th>
                <th style="padding:6px;text-align:right;font-weight:600;">Realized P&amp;L</th>
              </tr>
              {closed_rows}
            </table>"""

        flags_block = ""
        if d["flags"]:
            items = "".join(f'<li style="margin:4px 0;">{f}</li>' for f in d["flags"])
            flags_block = f"""
            <h3 style="margin:24px 0 8px;font-size:15px;color:#111;">Worth a look</h3>
            <ul style="font-size:14px;color:#333;padding-left:20px;margin:4px 0;">{items}</ul>"""

        button = (
            f'<a href="{frontend}" style="display:inline-block;background:#2563eb;color:#fff;'
            f'text-decoration:none;padding:10px 18px;border-radius:6px;font-size:14px;">Open dashboard</a>'
            if frontend else ""
        )
        manage = (
            f'<a href="{frontend}/alerts" style="color:#888;font-size:12px;">Manage email preferences</a>'
            if frontend else '<span style="color:#888;font-size:12px;">Manage preferences in the app</span>'
        )

        html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:620px;margin:0 auto;padding:24px;">
    <div style="background:#fff;border-radius:10px;padding:28px;border:1px solid #eee;">
      <p style="margin:0 0 2px;color:#888;font-size:12px;">{date_str}</p>
      <h2 style="margin:0 0 16px;font-size:20px;color:#111;">📈 Your weekly portfolio digest</h2>

      <div style="font-size:14px;color:#333;line-height:1.6;">
        <div>Portfolio <strong>{_money(d['total_mv'])}</strong>
          &nbsp;<span style="color:{_color(d['weekly_pnl'])};">
            {_arrow(d['weekly_pnl'])} {_money(abs(d['weekly_pnl']))} this week</span>
        </div>
        <div>Unrealized P&amp;L <strong style="color:{_color(d['total_unrealized'])};">{_signed(d['total_unrealized'])}</strong>
          &nbsp;·&nbsp; Realized this week <strong style="color:{_color(d['realized_week'])};">{_signed(d['realized_week'])}</strong>
        </div>
      </div>

      {positions_block}
      {movers_block}
      {realized_block}
      {closed_block}
      {flags_block}

      <div style="margin-top:28px;">{button}</div>
    </div>
    <p style="text-align:center;margin:16px 0;">{manage}</p>
  </div>
</body></html>"""

        return subject, html


# Module-level singleton, wired to the shared price/email singletons.
from services.email_service import email_service  # noqa: E402
from services.price_service import price_service  # noqa: E402

digest_service = DigestService(price_service, email_service)


def get_digest_service() -> DigestService:
    return digest_service
