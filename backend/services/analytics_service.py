"""All chat-tool computations, collected in one service."""
import time
from datetime import date, timedelta

import yfinance as yf
from sqlalchemy.orm import Session

from core.config import INDEX_TICKERS_SET
from domain.finance import ClosedLot, fifo_closed_lots, fifo_full
from models import Trade, TradeAction
from repositories.trade_repository import TradeRepository
from services.portfolio_service import PortfolioService
from services.price_service import PriceService
from services.statistics_service import StatisticsService

# Minimum early-exit % to surface the disposition-effect flag.
# ~50% is expected by definition (half below mean); only signal above this level.
_EARLY_EXIT_SIGNAL_THRESHOLD = 65

# Correlation data cache: (sorted_tickers, date_str) -> (result_dict, timestamp)
_corr_cache: dict[tuple, tuple[dict, float]] = {}
_CORR_CACHE_TTL = 3600.0  # 1 hour


class AnalyticsService:
    def __init__(
        self,
        db: Session,
        portfolio_service: PortfolioService,
        statistics_service: StatisticsService,
        price_service: PriceService,
    ) -> None:
        self._trade_repo = TradeRepository(db)
        self._portfolio_service = portfolio_service
        self._statistics_service = statistics_service
        self._price_service = price_service

    # ---- Tools ----------------------------------------------------------------

    def get_portfolio_statistics(self) -> dict:
        return self._statistics_service.compute().model_dump()

    def get_ticker_analysis(self, ticker: str) -> dict:
        ticker = ticker.upper()
        trades = self._trade_repo.get_by_ticker(ticker)
        if not trades:
            return {"error": f"No trades found for {ticker}"}

        fifo = fifo_full(trades, ticker)
        closed_lots = fifo.closed_lots
        avg_cost = fifo.avg_cost
        total_bought = sum(float(t.quantity) for t in trades if t.action == TradeAction.BUY)
        total_sold = sum(float(t.quantity) for t in trades if t.action == TradeAction.SELL)
        current_qty = total_bought - total_sold
        total_fees = sum(float(t.fees or 0) for t in trades)
        total_realized = sum(l.pnl for l in closed_lots)

        lots_data = []
        for l in closed_lots:
            holding_days = (l.close_date - l.open_date).days
            pnl_pct = round(l.pnl / l.cost_basis * 100, 1) if l.cost_basis else None
            lots_data.append({
                "open_date": str(l.open_date),
                "close_date": str(l.close_date),
                "quantity": float(l.quantity),
                "cost_basis": round(float(l.cost_basis), 2),
                "pnl": round(float(l.pnl), 2),
                "pnl_pct": pnl_pct,
                "holding_days": holding_days,
            })

        return {
            "ticker": ticker,
            "current_position": {
                "quantity": round(current_qty, 4),
                "avg_cost": round(float(avg_cost), 2) if current_qty > 0 else None,
            },
            "summary": {
                "total_trades": len(trades),
                "closed_lots": len(closed_lots),
                "total_realized_pnl": round(float(total_realized), 2),
                "total_fees": round(float(total_fees), 2),
                "fee_drag_pct": round(total_fees / abs(total_realized) * 100, 1) if total_realized else None,
            },
            "trades": [
                {
                    "date": str(t.executed_at),
                    "action": t.action.value,
                    "quantity": float(t.quantity),
                    "price": float(t.price),
                    "fees": float(t.fees or 0),
                }
                for t in trades
            ],
            "closed_lots": lots_data,
        }

    def get_behavioral_patterns(self) -> dict:
        all_trades = self._trade_repo.get_excluding(INDEX_TICKERS_SET)
        tickers = list(dict.fromkeys(t.ticker for t in all_trades))

        all_closed: list[ClosedLot] = []
        ticker_detail: list[dict] = []
        for ticker in tickers:
            t_trades = [t for t in all_trades if t.ticker == ticker]
            closed = fifo_closed_lots(t_trades, ticker)
            all_closed.extend(closed)
            fees = sum(float(t.fees or 0) for t in t_trades)
            realized = sum(l.pnl for l in closed)
            wins = [l for l in closed if l.pnl > 0]
            losses = [l for l in closed if l.pnl <= 0]
            if closed:
                ticker_detail.append({
                    "ticker": ticker,
                    "closed_lots": len(closed),
                    "win_rate": round(len(wins) / len(closed) * 100, 1),
                    "total_fees": round(fees, 2),
                    "realized_pnl": round(realized, 2),
                    "fee_drag_pct": round(fees / abs(realized) * 100, 1) if realized else None,
                    "avg_holding_days_winners": round(
                        sum((l.close_date - l.open_date).days for l in wins) / len(wins), 1
                    ) if wins else None,
                    "avg_holding_days_losers": round(
                        sum((l.close_date - l.open_date).days for l in losses) / len(losses), 1
                    ) if losses else None,
                })

        winners = [l for l in all_closed if l.pnl > 0]
        losers = [l for l in all_closed if l.pnl <= 0]

        def avg_hold(lots: list[ClosedLot]) -> float | None:
            if not lots:
                return None
            return round(sum((l.close_date - l.open_date).days for l in lots) / len(lots), 1)

        loss_pcts = [round(l.pnl / l.cost_basis * 100, 1) for l in losers if l.cost_basis]

        monthly_counts: dict[str, int] = {}
        for t in all_trades:
            key = t.executed_at.strftime("%Y-%m") if hasattr(t.executed_at, "strftime") else str(t.executed_at)[:7]
            monthly_counts[key] = monthly_counts.get(key, 0) + 1

        sorted_closed = sorted(all_closed, key=lambda l: l.close_date)
        max_w = max_l = cur_w = cur_l = 0
        for l in sorted_closed:
            if l.pnl > 0:
                cur_w += 1; cur_l = 0; max_w = max(max_w, cur_w)
            else:
                cur_l += 1; cur_w = 0; max_l = max(max_l, cur_l)

        return {
            "holding_period_analysis": {
                "avg_holding_days_winners": avg_hold(winners),
                "avg_holding_days_losers": avg_hold(losers),
                "note": "If losers > winners you tend to hold losers too long and cut winners too early.",
            },
            "loss_profile": {
                "avg_loss_pct_at_close": round(sum(loss_pcts) / len(loss_pcts), 1) if loss_pcts else None,
                "worst_loss_pct": round(min(loss_pcts), 1) if loss_pcts else None,
                "best_loss_pct": round(max(loss_pcts), 1) if loss_pcts else None,
                "total_losing_lots": len(losers),
            },
            "fee_drag_by_ticker": sorted(ticker_detail, key=lambda x: x.get("fee_drag_pct") or 0, reverse=True),
            "trade_frequency_by_month": [
                {"month": k, "trades": v} for k, v in sorted(monthly_counts.items())
            ],
            "streak_analysis": {
                "max_consecutive_wins": max_w,
                "max_consecutive_losses": max_l,
            },
        }

    def get_post_exit_prices(self, ticker: str, close_date: str) -> dict:
        ticker = ticker.upper()
        try:
            close_dt = date.fromisoformat(close_date)
        except ValueError:
            return {"error": f"Invalid date format: {close_date}. Use YYYY-MM-DD."}
        try:
            hist = yf.Ticker(ticker).history(
                start=str(close_dt), end=str(close_dt + timedelta(days=100))
            )
            if hist.empty:
                return {"error": f"No price data for {ticker} around {close_date}"}
            dates_available = hist.index.strftime("%Y-%m-%d").tolist()

            def price_on_or_after(target: date) -> float | None:
                for i in range(10):
                    key = (target + timedelta(days=i)).strftime("%Y-%m-%d")
                    if key in dates_available:
                        return round(float(hist.loc[hist.index.strftime("%Y-%m-%d") == key, "Close"].iloc[0]), 2)
                return None

            exit_price = price_on_or_after(close_dt)
            p30 = price_on_or_after(close_dt + timedelta(days=30))
            p60 = price_on_or_after(close_dt + timedelta(days=60))
            p90 = price_on_or_after(close_dt + timedelta(days=90))

            def pct(p: float | None) -> float | None:
                return round((p - exit_price) / exit_price * 100, 1) if p and exit_price else None

            return {
                "ticker": ticker,
                "exit_date": close_date,
                "exit_price": exit_price,
                "price_30d_after": p30,
                "price_60d_after": p60,
                "price_90d_after": p90,
                "change_30d_pct": pct(p30),
                "change_60d_pct": pct(p60),
                "change_90d_pct": pct(p90),
            }
        except Exception as e:
            return {"error": f"Failed to fetch price data: {e}"}

    def get_current_prices(self) -> dict:
        positions = self._portfolio_service.build_positions()
        non_index = [p for p in positions if p.ticker not in INDEX_TICKERS_SET]
        if not non_index:
            return {"positions": [], "note": "No open positions"}
        total_mv = sum(p.market_value for p in non_index)
        result = sorted(
            [
                {
                    "ticker": p.ticker,
                    "quantity": float(p.quantity),
                    "avg_cost": round(float(p.avg_cost), 2),
                    "current_price": round(float(p.current_price), 2),
                    "market_value": round(float(p.market_value), 2),
                    "unrealized_pnl": round(float(p.unrealized_pnl), 2),
                    "unrealized_pnl_pct": round(float(p.unrealized_pnl_pct), 2),
                    "weight_pct": round(abs(p.market_value) / total_mv * 100, 1) if total_mv else 0,
                }
                for p in non_index
            ],
            key=lambda x: x["market_value"],
            reverse=True,
        )
        return {
            "total_market_value": round(total_mv, 2),
            "total_unrealized_pnl": round(sum(p.unrealized_pnl for p in non_index), 2),
            "positions": result,
        }

    def get_sector_concentration(self) -> dict:
        positions = self._portfolio_service.build_positions()
        non_index = [p for p in positions if p.ticker not in INDEX_TICKERS_SET]
        if not non_index:
            return {"sectors": [], "note": "No open positions"}

        total_mv = sum(abs(p.market_value) for p in non_index)
        self._price_service.prefetch_ticker_info([p.ticker for p in non_index])

        sector_map: dict[str, list[dict]] = {}
        for p in non_index:
            info = self._price_service.get_ticker_info(p.ticker)
            sector = info.get("sector") or "Unknown"
            entry = {
                "ticker": p.ticker,
                "market_value": round(float(p.market_value), 2),
                "weight_pct": round(abs(p.market_value) / total_mv * 100, 1) if total_mv else 0,
            }
            sector_map.setdefault(sector, []).append(entry)

        sectors = sorted(
            [
                {
                    "sector": sector,
                    "total_market_value": round(sum(h["market_value"] for h in holdings), 2),
                    "weight_pct": round(
                        abs(sum(h["market_value"] for h in holdings)) / total_mv * 100, 1
                    ) if total_mv else 0,
                    "holdings": sorted(holdings, key=lambda x: abs(x["market_value"]), reverse=True),
                }
                for sector, holdings in sector_map.items()
            ],
            key=lambda x: abs(x["total_market_value"]),
            reverse=True,
        )
        return {
            "total_market_value": round(total_mv, 2),
            "sectors": sectors,
            "largest_sector": sectors[0]["sector"] if sectors else None,
            "largest_sector_weight_pct": sectors[0]["weight_pct"] if sectors else None,
        }

    def get_correlation_analysis(self) -> dict:
        positions = self._portfolio_service.build_positions()
        non_index = [p for p in positions if p.ticker not in INDEX_TICKERS_SET]
        tickers = [p.ticker for p in non_index]
        if len(tickers) < 2:
            return {"error": "Need at least 2 open positions to compute correlation"}

        cache_key = (tuple(sorted(tickers)), str(date.today()))
        cached = _corr_cache.get(cache_key)
        if cached and time.time() - cached[1] < _CORR_CACHE_TTL:
            return cached[0]

        try:
            end_dt = date.today()
            start_dt = end_dt - timedelta(days=180)
            raw = yf.download(tickers, start=str(start_dt), end=str(end_dt), auto_adjust=True, progress=False)
            if raw.empty:
                return {"error": "Could not fetch historical price data"}

            closes = (
                raw[["Close"]].copy().set_axis(tickers, axis=1)
                if len(tickers) == 1
                else (raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0))
            )
            returns = closes.dropna(how="all").pct_change().dropna()
            ticker_list = list(returns.columns)

            pairs = []
            for i in range(len(ticker_list)):
                for j in range(i + 1, len(ticker_list)):
                    a, b = ticker_list[i], ticker_list[j]
                    corr = returns[a].corr(returns[b])
                    if corr == corr:  # not NaN
                        pairs.append({
                            "pair": f"{a}/{b}",
                            "correlation": round(corr, 3),
                            "interpretation": (
                                "highly correlated — limited diversification" if corr > 0.7
                                else "moderately correlated" if corr > 0.4
                                else "low correlation — good diversification" if corr > -0.2
                                else "negatively correlated — hedge"
                            ),
                        })
            pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
            highly = [p for p in pairs if p["correlation"] > 0.7]
            result = {
                "lookback_days": 180,
                "tickers_analyzed": ticker_list,
                "pairs": pairs,
                "highly_correlated_pairs": highly,
                "risk_note": (
                    f"{len(highly)} pair(s) with correlation > 0.7 — these move together and don't reduce risk."
                    if highly else "No highly correlated pairs detected — good diversification."
                ),
            }
            _corr_cache[cache_key] = (result, time.time())
            return result
        except Exception as e:
            return {"error": f"Correlation analysis failed: {e}"}

    def get_entry_timing_analysis(self, ticker: str) -> dict:
        ticker = ticker.upper()
        trades = self._trade_repo.get_buy_trades_for_ticker(ticker)
        if not trades:
            return {"error": f"No buy trades found for {ticker}"}

        entry_dates = [
            t.executed_at if isinstance(t.executed_at, date) else t.executed_at.date()
            for t in trades
        ]
        # Single wide fetch covering all entry windows — N calls → 1 call
        fetch_start = min(entry_dates) - timedelta(days=20)
        fetch_end = max(entry_dates) + timedelta(days=21)
        try:
            hist = yf.Ticker(ticker).history(start=str(fetch_start), end=str(fetch_end))
        except Exception as e:
            return {"error": f"Failed to fetch price data for {ticker}: {e}"}

        if hist.empty:
            return {"error": f"No price data for {ticker}"}

        # Normalize index to date for slicing
        hist_dates = hist.index.date

        results = []
        for t, entry_dt in zip(trades, entry_dates):
            window_mask = (hist_dates >= entry_dt - timedelta(days=20)) & (hist_dates <= entry_dt + timedelta(days=20))
            window = hist[window_mask]
            if window.empty:
                results.append({"date": str(entry_dt), "error": "No price data in window"})
                continue
            period_high = round(float(window["High"].max()), 2)
            period_low = round(float(window["Low"].min()), 2)
            period_range = period_high - period_low
            entry_price = float(t.price)
            pct_from_low = round((entry_price - period_low) / period_range * 100, 1) if period_range else None
            pct_from_high = round((period_high - entry_price) / period_range * 100, 1) if period_range else None
            results.append({
                "date": str(entry_dt),
                "entry_price": round(entry_price, 2),
                "quantity": float(t.quantity),
                "period_low_20d": period_low,
                "period_high_20d": period_high,
                "pct_from_period_low": pct_from_low,
                "pct_from_period_high": pct_from_high,
                "timing_quality": (
                    "near low — good entry" if pct_from_low is not None and pct_from_low < 25
                    else "near high — poor entry" if pct_from_low is not None and pct_from_low > 75
                    else "mid-range entry"
                ),
            })

        if not results:
            return {"error": f"Could not fetch price data for {ticker}"}

        good = sum(1 for r in results if r.get("timing_quality") == "near low — good entry")
        poor = sum(1 for r in results if r.get("timing_quality") == "near high — poor entry")
        return {
            "ticker": ticker,
            "entries_analyzed": len(results),
            "good_timing_count": good,
            "poor_timing_count": poor,
            "entries": results,
        }

    def get_risk_metrics(self) -> dict:
        positions = self._portfolio_service.build_positions()
        non_index = [p for p in positions if p.ticker not in INDEX_TICKERS_SET]
        if not non_index:
            return {"note": "No open positions"}
        total_mv = sum(abs(p.market_value) for p in non_index)
        details = []
        for p in non_index:
            weight = abs(p.market_value) / total_mv * 100 if total_mv else 0
            details.append({
                "ticker": p.ticker,
                "quantity": float(p.quantity),
                "market_value": round(float(p.market_value), 2),
                "weight_pct": round(weight, 1),
                "unrealized_pnl": round(float(p.unrealized_pnl), 2),
                "unrealized_pnl_pct": round(float(p.unrealized_pnl_pct), 1),
                "risk_flag": "CONCENTRATED" if weight > 20 else ("LARGE" if weight > 10 else "OK"),
            })
        details.sort(key=lambda x: x["weight_pct"], reverse=True)
        concentrated = [d for d in details if d["risk_flag"] == "CONCENTRATED"]
        return {
            "total_market_value": round(total_mv, 2),
            "position_count": len(non_index),
            "positions": details,
            "concentrated_positions": concentrated,
            "herfindahl_index": round(
                sum((abs(p.market_value) / total_mv * 100) ** 2 for p in non_index) / 10000, 4
            ) if total_mv else None,
            "note": (
                "Herfindahl index near 1.0 = fully concentrated, near 0 = well diversified. "
                "Positions >20% of portfolio are flagged CONCENTRATED."
            ),
        }

    def get_similar_past_setups(self, ticker: str) -> dict:
        ticker = ticker.upper()
        all_trades = self._trade_repo.get_excluding(INDEX_TICKERS_SET)
        tickers = list(dict.fromkeys(t.ticker for t in all_trades))

        self._price_service.prefetch_ticker_info([ticker] + tickers)

        query_info = self._price_service.get_ticker_info(ticker)
        query_sector = query_info["sector"]
        query_market_cap = query_info["marketCap"]

        similar: list[dict] = []
        for t in tickers:
            if t == ticker:
                continue
            t_trades = [tr for tr in all_trades if tr.ticker == t]
            closed = fifo_closed_lots(t_trades, t)
            if not closed:
                continue
            t_info = self._price_service.get_ticker_info(t)
            t_sector = t_info["sector"]
            t_market_cap = t_info["marketCap"]

            same_sector = bool(query_sector and t_sector == query_sector)
            similar_cap = False
            if query_market_cap and t_market_cap:
                ratio = max(query_market_cap, t_market_cap) / min(query_market_cap, t_market_cap)
                similar_cap = ratio < 10

            if not (same_sector or similar_cap):
                continue

            realized = sum(l.pnl for l in closed)
            wins = [l for l in closed if l.pnl > 0]
            fees = sum(float(tr.fees or 0) for tr in t_trades)
            avg_hold = round(sum((l.close_date - l.open_date).days for l in closed) / len(closed), 1)
            similar.append({
                "ticker": t,
                "sector": t_sector,
                "same_sector": same_sector,
                "similar_market_cap": similar_cap,
                "closed_lots": len(closed),
                "win_rate_pct": round(len(wins) / len(closed) * 100, 1),
                "total_realized_pnl": round(realized, 2),
                "avg_holding_days": avg_hold,
                "total_fees": round(fees, 2),
                "outcome": "profitable" if realized > 0 else "loss",
            })

        similar.sort(key=lambda x: x["total_realized_pnl"], reverse=True)
        return {
            "query_ticker": ticker,
            "query_sector": query_sector,
            "similar_past_trades": similar,
            "note": "Matches stocks you've traded before in the same sector or similar market cap.",
        }

    def get_fee_impact_report(self) -> dict:
        all_trades = self._trade_repo.get_excluding(INDEX_TICKERS_SET)
        if not all_trades:
            return {"note": "No trades found"}

        by_platform: dict[str, dict] = {}
        for t in all_trades:
            platform = t.platform or "Unknown"
            if platform not in by_platform:
                by_platform[platform] = {"trades": 0, "total_fees": 0.0, "buy_fees": 0.0, "sell_fees": 0.0}
            by_platform[platform]["trades"] += 1
            fee = float(t.fees or 0)
            by_platform[platform]["total_fees"] += fee
            if t.action == TradeAction.BUY:
                by_platform[platform]["buy_fees"] += fee
            else:
                by_platform[platform]["sell_fees"] += fee

        total_fees = sum(float(t.fees or 0) for t in all_trades)

        by_ticker: dict[str, list[Trade]] = {}
        for t in all_trades:
            by_ticker.setdefault(t.ticker, []).append(t)
        gross_realized = sum(
            sum(l.pnl for l in fifo_closed_lots(trades, ticker))
            for ticker, trades in by_ticker.items()
        )

        platforms_out = sorted(
            [
                {
                    "platform": platform,
                    "trades": data["trades"],
                    "total_fees": round(data["total_fees"], 2),
                    "buy_fees": round(data["buy_fees"], 2),
                    "sell_fees": round(data["sell_fees"], 2),
                    "avg_fee_per_trade": round(data["total_fees"] / data["trades"], 2) if data["trades"] else 0,
                    "pct_of_total_fees": round(data["total_fees"] / total_fees * 100, 1) if total_fees else 0,
                }
                for platform, data in by_platform.items()
            ],
            key=lambda x: x["total_fees"],
            reverse=True,
        )

        return {
            "total_fees_paid": round(total_fees, 2),
            "gross_realized_pnl": round(gross_realized, 2),
            "fees_as_pct_of_gross_pnl": round(total_fees / abs(gross_realized) * 100, 2) if gross_realized else None,
            "total_trades": len(all_trades),
            "avg_fee_per_trade": round(total_fees / len(all_trades), 2),
            "by_platform": platforms_out,
            "note": "fees_as_pct_of_gross_pnl shows how much of your gross gains are eaten by fees.",
        }

    def get_behavioral_red_flags(self) -> list[str]:
        """Return up to 2 data-backed behavioral flag strings, or [] if insufficient data."""
        try:
            all_trades = self._trade_repo.get_excluding(INDEX_TICKERS_SET)
            by_ticker: dict[str, list[Trade]] = {}
            for t in all_trades:
                by_ticker.setdefault(t.ticker, []).append(t)

            all_closed: list[ClosedLot] = []
            for ticker, trades in by_ticker.items():
                all_closed.extend(fifo_closed_lots(trades, ticker))

            if len(all_closed) < 5:
                return []

            winners = [lot for lot in all_closed if lot.pnl > 0]
            losers = [lot for lot in all_closed if lot.pnl <= 0]

            flags: list[str] = []

            # Flag 1: Holding period asymmetry
            if winners and losers:
                avg_win_days = sum((lot.close_date - lot.open_date).days for lot in winners) / len(winners)
                avg_loss_days = sum((lot.close_date - lot.open_date).days for lot in losers) / len(losers)
                if avg_win_days > 0 and avg_loss_days / avg_win_days > 1.5:
                    ratio = round(avg_loss_days / avg_win_days, 1)
                    flags.append(
                        f"You hold losing trades {ratio}x longer than winning ones "
                        f"(losers: {avg_loss_days:.1f} days avg, winners: {avg_win_days:.1f} days avg)."
                    )

            # Flag 2: Disposition effect — ratio of early winner exits vs long loser holds
            if winners and losers and len(flags) < 2:
                avg_win_days = sum((lot.close_date - lot.open_date).days for lot in winners) / len(winners)
                early_exits = sum(
                    1 for lot in winners if (lot.close_date - lot.open_date).days < avg_win_days
                )
                early_exit_pct = round(early_exits / len(winners) * 100)
                if early_exit_pct > _EARLY_EXIT_SIGNAL_THRESHOLD:
                    flags.append(
                        f"Disposition effect: {early_exit_pct}% of your winning trades were closed "
                        f"before reaching your avg winner hold time ({avg_win_days:.1f} days) — "
                        f"you may be cutting winners short."
                    )

            return flags[:2]
        except Exception:
            return []

    def get_disposition_effect(self) -> dict:
        """Compute the disposition effect across all closed lots.

        Returns avg holding days for winners vs losers, the hold ratio, the
        percentage of winners closed before the average winner hold time, and
        a plain-English interpretation.  Requires at least 5 closed lots.
        """
        all_trades = self._trade_repo.get_excluding(INDEX_TICKERS_SET)
        by_ticker: dict[str, list[Trade]] = {}
        for trade in all_trades:
            by_ticker.setdefault(trade.ticker, []).append(trade)

        all_closed: list[ClosedLot] = []
        for ticker, trades in by_ticker.items():
            all_closed.extend(fifo_closed_lots(trades, ticker))

        if len(all_closed) < 5:
            return {"error": "Insufficient data: fewer than 5 closed lots"}

        winners = [lot for lot in all_closed if lot.pnl > 0]
        losers = [lot for lot in all_closed if lot.pnl <= 0]

        def _avg_days(lots: list[ClosedLot]) -> float:
            if not lots:
                return 0.0
            return sum((lot.close_date - lot.open_date).days for lot in lots) / len(lots)

        avg_winner_hold = _avg_days(winners)
        avg_loser_hold = _avg_days(losers)
        hold_ratio = round(avg_loser_hold / avg_winner_hold, 2) if avg_winner_hold > 0 else 0.0

        early_exits = sum(
            1 for lot in winners if (lot.close_date - lot.open_date).days < avg_winner_hold
        )
        winners_closed_early_pct = round(early_exits / len(winners) * 100, 1) if winners else 0.0

        # Build interpretation
        parts: list[str] = []
        if avg_winner_hold > 0 and avg_loser_hold > 0:
            if hold_ratio > 1.5:
                parts.append(
                    f"You hold losing trades {hold_ratio}x longer than winning ones "
                    f"({avg_loser_hold:.1f} days avg vs {avg_winner_hold:.1f} days for winners) — "
                    "a classic disposition effect."
                )
            else:
                parts.append(
                    f"Holding periods are relatively balanced: losers {avg_loser_hold:.1f} days, "
                    f"winners {avg_winner_hold:.1f} days (ratio {hold_ratio}x)."
                )
        if winners_closed_early_pct > _EARLY_EXIT_SIGNAL_THRESHOLD:
            parts.append(
                f"{winners_closed_early_pct}% of winning trades were closed before your avg winner "
                f"hold time ({avg_winner_hold:.1f} days) — you may be cutting winners short. "
                "(Note: ~50% is expected by definition; only >65% is a meaningful signal.)"
            )
        interpretation = " ".join(parts) if parts else "Insufficient data for a clear interpretation."

        return {
            "total_closed_lots": len(all_closed),
            "winning_lots": len(winners),
            "losing_lots": len(losers),
            "avg_winner_hold_days": round(avg_winner_hold, 1),
            "avg_loser_hold_days": round(avg_loser_hold, 1),
            "hold_ratio": hold_ratio,
            "winners_closed_early_pct": winners_closed_early_pct,
            "interpretation": interpretation,
        }

    def get_revenge_trading_indicators(
        self,
        loss_threshold_pct: float = 5.0,
        window_hours: int = 48,
    ) -> dict:
        """Detect potential revenge trading patterns.

        For each closed lot with a loss exceeding ``loss_threshold_pct`` of its
        cost basis, look for any BUY trade (any ticker) placed within
        ``window_hours`` hours after the close date.  Only surfaces the flag
        when at least 3 qualifying instances are found.
        """
        from datetime import datetime, timedelta as _timedelta

        all_trades = self._trade_repo.get_excluding(INDEX_TICKERS_SET)
        by_ticker: dict[str, list[Trade]] = {}
        for trade in all_trades:
            by_ticker.setdefault(trade.ticker, []).append(trade)

        all_closed: list[ClosedLot] = []
        for ticker, trades in by_ticker.items():
            all_closed.extend(fifo_closed_lots(trades, ticker))

        # Sort closed lots by close_date
        all_closed.sort(key=lambda lot: lot.close_date)

        # Collect trigger lots: losses > threshold
        threshold = loss_threshold_pct / 100.0
        triggers = [
            lot for lot in all_closed
            if lot.pnl < 0 and lot.cost_basis and abs(lot.pnl / lot.cost_basis) > threshold
        ]

        # All buy trades, normalised to datetime for comparison
        buy_trades = [t for t in all_trades if t.action == TradeAction.BUY]

        def _to_naive_datetime(val: date) -> datetime:
            """Convert date or datetime to a naive UTC-local datetime for comparison."""
            if isinstance(val, datetime):
                # Strip tzinfo to keep comparisons offset-naive
                return val.replace(tzinfo=None)
            return datetime(val.year, val.month, val.day)

        # One instance per trigger lot: record only the first BUY trade after the loss.
        # This prevents cartesian-product inflation when multiple buys follow one loss.
        instances = []
        for lot in triggers:
            trigger_dt = _to_naive_datetime(lot.close_date)
            window_end = trigger_dt + _timedelta(hours=window_hours)
            buy_trades_in_window = [
                bt for bt in buy_trades
                if trigger_dt < _to_naive_datetime(bt.executed_at) <= window_end
            ]
            if buy_trades_in_window:
                # Pick the earliest buy in the window
                first_bt = min(buy_trades_in_window, key=lambda bt: _to_naive_datetime(bt.executed_at))
                bt_dt = _to_naive_datetime(first_bt.executed_at)
                loss_pct = round(abs(lot.pnl / lot.cost_basis) * 100, 1)
                hours_after = round((bt_dt - trigger_dt).total_seconds() / 3600, 1)
                instances.append({
                    "loss_trade": f"{lot.ticker} closed {lot.close_date} (loss ${lot.pnl:.2f})",
                    "loss_pct": loss_pct,
                    "follow_on_buy": f"{first_bt.ticker} bought {first_bt.executed_at} @ ${float(first_bt.price):.2f}",
                    "hours_after": hours_after,
                })

        threshold_met = len(instances) >= 3
        return {
            "instances_found": len(instances),
            "threshold_met": threshold_met,
            "instances": instances,
            "note": (
                f"Flags any BUY trade placed within {window_hours}h of a realized loss "
                f"exceeding {loss_threshold_pct}% of cost basis. "
                "Result is only considered significant when 3+ instances are found."
            ),
        }

    def get_coaching_summary(self) -> dict:
        """Return a structured coaching brief.

        Aggregates behavioral flags from ``get_behavioral_red_flags()``, risk
        concentration from ``get_risk_metrics()``, and produces 3 focused
        improvement suggestions.
        """
        behavioral_flags = self.get_behavioral_red_flags()

        risk_data = self.get_risk_metrics()
        concentrated = risk_data.get("concentrated_positions", [])
        herfindahl = risk_data.get("herfindahl_index")
        if concentrated:
            tickers_str = ", ".join(p["ticker"] for p in concentrated[:3])
            top_risk = (
                f"{len(concentrated)} position(s) exceed 20% of portfolio: {tickers_str}."
            )
        elif herfindahl is not None and herfindahl > 0.25:
            top_risk = (
                f"Portfolio is moderately concentrated (Herfindahl {herfindahl:.2f}); "
                "consider spreading across more positions."
            )
        else:
            top_risk = "No severe concentration risk detected in current open positions."

        # Derive focus areas from flags + risk
        focus: list[str] = []
        for flag in behavioral_flags[:2]:
            flag_lower = flag.lower()
            if "longer" in flag_lower or "hold" in flag_lower:
                focus.append(
                    "Practice predefined exit rules: set a stop-loss level before entry and "
                    "stick to it to avoid holding losers beyond their thesis."
                )
            elif "disposition" in flag_lower or "cutting" in flag_lower or "%" in flag_lower:
                focus.append(
                    "Let winners run: before selling a profitable position, ask whether the "
                    "original thesis is still intact rather than locking in a small gain."
                )
        if concentrated:
            focus.append(
                f"Reduce concentration in {concentrated[0]['ticker']} "
                f"({concentrated[0]['weight_pct']}% of portfolio) to limit single-stock risk."
            )
        # Pad to exactly 3 suggestions if needed
        defaults = [
            "Review your position-sizing rules: aim for no single position to exceed 15% of portfolio.",
            "Track your win/loss ratio monthly to spot deteriorating edge before it compounds.",
            "After each closed trade, note whether the exit matched your original plan.",
        ]
        for default in defaults:
            if len(focus) >= 3:
                break
            focus.append(default)

        return {
            "behavioral_flags": behavioral_flags,
            "top_risk": top_risk,
            "suggested_focus": focus[:3],
        }

    def compare_to_benchmark(self, benchmark: str = "SPY") -> dict:
        benchmark = benchmark.upper()
        all_trades = self._trade_repo.get_excluding(INDEX_TICKERS_SET)
        if not all_trades:
            return {"error": "No trades found"}

        by_ticker: dict[str, list[Trade]] = {}
        for t in all_trades:
            by_ticker.setdefault(t.ticker, []).append(t)

        all_closed: list[ClosedLot] = []
        for ticker, trades in by_ticker.items():
            all_closed.extend(fifo_closed_lots(trades, ticker))
        if not all_closed:
            return {"error": "No closed lots yet — nothing to compare"}

        all_closed.sort(key=lambda l: l.close_date)
        first_date = all_closed[0].close_date
        last_date = all_closed[-1].close_date

        running = 0.0
        for lot in all_closed:
            running += lot.pnl

        total_deployed = sum(
            float(t.quantity) * float(t.price) for t in all_trades if t.action == TradeAction.BUY
        )

        try:
            hist = yf.Ticker(benchmark).history(
                start=str(first_date), end=str(last_date + timedelta(days=1))
            )
            if hist.empty:
                return {"error": f"Could not fetch {benchmark} price history"}

            bench_start = round(float(hist["Close"].iloc[0]), 2)
            bench_end = round(float(hist["Close"].iloc[-1]), 2)
            bench_return_pct = round((bench_end - bench_start) / bench_start * 100, 2)
            bench_pnl = round(total_deployed * bench_return_pct / 100, 2)
            portfolio_return_pct = round(running / total_deployed * 100, 2) if total_deployed else None

            monthly_bench: dict[str, float] = {}
            prev_price = None
            for dt, price in hist["Close"].resample("ME").last().items():
                key = dt.strftime("%Y-%m")
                if prev_price is not None:
                    monthly_bench[key] = round((float(price) - float(prev_price)) / float(prev_price) * 100, 2)
                prev_price = price

            monthly_portfolio: dict[str, float] = {}
            for lot in all_closed:
                key = lot.close_date.strftime("%Y-%m")
                monthly_portfolio[key] = monthly_portfolio.get(key, 0.0) + lot.pnl

            all_months = sorted(set(list(monthly_bench) + list(monthly_portfolio)))
            monthly_comparison = [
                {
                    "month": m,
                    "portfolio_realized_pnl": round(monthly_portfolio.get(m, 0.0), 2),
                    "benchmark_return_pct": monthly_bench.get(m),
                    "benchmark_equivalent_pnl": round(total_deployed * (monthly_bench.get(m, 0) / 100), 2),
                }
                for m in all_months
            ]

            return {
                "benchmark": benchmark,
                "period": f"{first_date} to {last_date}",
                "total_capital_deployed": round(total_deployed, 2),
                "your_realized_pnl": round(running, 2),
                "your_return_pct": portfolio_return_pct,
                "benchmark_return_pct": bench_return_pct,
                "benchmark_equivalent_pnl": bench_pnl,
                "alpha_pnl": round(running - bench_pnl, 2),
                "outperformed": running > bench_pnl,
                "monthly_comparison": monthly_comparison,
                "note": "Comparison uses total capital deployed (sum of all buy values) as the invested base.",
            }
        except Exception as e:
            return {"error": f"Benchmark comparison failed: {e}"}
