"""Tests for M3: get_disposition_effect, get_revenge_trading_indicators, get_coaching_summary."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from domain.finance import ClosedLot
from models import Trade, TradeAction


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _lot(
    pnl: float,
    hold_days: int,
    ticker: str = "AAPL",
    close_year: int = 2024,
    close_month: int = 6,
    close_day: int = 1,
) -> ClosedLot:
    close_date = date(close_year, close_month, close_day)
    # Avoid day=0 by computing open_date safely
    from datetime import timedelta
    open_date = close_date - timedelta(days=hold_days)
    cost_basis = max(abs(pnl) * 2, 100.0)
    return ClosedLot(
        ticker=ticker,
        pnl=pnl,
        open_date=open_date,
        close_date=close_date,
        quantity=10.0,
        cost_basis=cost_basis,
    )


def _make_trade(
    ticker: str = "AAPL",
    action: TradeAction = TradeAction.BUY,
    executed_at: date = date(2024, 6, 2),
    price: float = 100.0,
    quantity: float = 10.0,
    fees: float = 1.0,
) -> MagicMock:
    t = MagicMock(spec=Trade)
    t.ticker = ticker
    t.action = action
    t.executed_at = executed_at
    t.price = price
    t.quantity = quantity
    t.fees = fees
    return t


def _make_analytics_svc(
    closed_lots_by_ticker: dict[str, list[ClosedLot]],
    all_trades: list[MagicMock] | None = None,
):
    """Build an AnalyticsService instance with patched repo and FIFO."""
    from services.analytics_service import AnalyticsService

    svc = AnalyticsService.__new__(AnalyticsService)
    svc._portfolio_service = MagicMock()
    svc._statistics_service = MagicMock()
    svc._price_service = MagicMock()

    # Build one fake Trade per ticker so the by_ticker grouping works
    fake_trades: list[MagicMock] = []
    for ticker in closed_lots_by_ticker:
        fake_trades.append(_make_trade(ticker=ticker))

    if all_trades is not None:
        fake_trades = all_trades

    svc._trade_repo = MagicMock()
    svc._trade_repo.get_excluding.return_value = fake_trades

    def fake_fifo(trades, ticker):
        return closed_lots_by_ticker.get(ticker, [])

    return svc, fake_fifo


# ---------------------------------------------------------------------------
# get_disposition_effect
# ---------------------------------------------------------------------------

class TestGetDispositionEffect:
    def _call(self, lots_by_ticker: dict[str, list[ClosedLot]]):
        svc, fake_fifo = _make_analytics_svc(lots_by_ticker)
        with patch("services.analytics_service.fifo_closed_lots", side_effect=fake_fifo):
            return svc.get_disposition_effect()

    def test_insufficient_data_below_5_lots(self):
        result = self._call({"AAPL": [_lot(10.0, 5) for _ in range(4)]})
        assert "error" in result
        assert "fewer than 5" in result["error"]

    def test_exactly_5_lots_no_error(self):
        result = self._call({"AAPL": [_lot(10.0, 5) for _ in range(5)]})
        assert "error" not in result
        assert result["total_closed_lots"] == 5

    def test_schema_keys_present(self):
        lots = [_lot(10.0, 5) for _ in range(3)] + [_lot(-5.0, 15) for _ in range(3)]
        result = self._call({"AAPL": lots})
        expected_keys = {
            "total_closed_lots",
            "winning_lots",
            "losing_lots",
            "avg_winner_hold_days",
            "avg_loser_hold_days",
            "hold_ratio",
            "winners_closed_early_pct",
            "interpretation",
        }
        assert expected_keys == set(result.keys())

    def test_winner_loser_counts(self):
        lots = [_lot(10.0, 5) for _ in range(4)] + [_lot(-5.0, 15) for _ in range(3)]
        result = self._call({"AAPL": lots})
        assert result["winning_lots"] == 4
        assert result["losing_lots"] == 3

    def test_hold_ratio_high_when_losers_held_much_longer(self):
        # Winners: 5 days. Losers: 30 days. Ratio = 6.0
        lots = [_lot(10.0, 5) for _ in range(5)] + [_lot(-5.0, 30) for _ in range(5)]
        result = self._call({"AAPL": lots})
        assert result["hold_ratio"] >= 5.0
        assert "longer" in result["interpretation"].lower() or "x" in result["interpretation"]

    def test_hold_ratio_near_1_when_balanced(self):
        lots = [_lot(10.0, 10) for _ in range(5)] + [_lot(-5.0, 11) for _ in range(5)]
        result = self._call({"AAPL": lots})
        assert result["hold_ratio"] < 1.5

    def test_winners_closed_early_pct_when_majority_exit_early(self):
        # avg winner hold will be (8*3 + 2*20)/10 = 4.4 days
        # 8 winners close at 3 days (< 4.4) → 80% early exits
        lots = (
            [_lot(10.0, 3) for _ in range(8)]
            + [_lot(10.0, 20) for _ in range(2)]
            + [_lot(-5.0, 10) for _ in range(5)]
        )
        result = self._call({"AAPL": lots})
        assert result["winners_closed_early_pct"] >= 50.0

    def test_interpretation_is_non_empty_string(self):
        lots = [_lot(10.0, 5) for _ in range(5)] + [_lot(-5.0, 20) for _ in range(5)]
        result = self._call({"AAPL": lots})
        assert isinstance(result["interpretation"], str)
        assert len(result["interpretation"]) > 0

    def test_works_across_multiple_tickers(self):
        lots_by_ticker = {
            "AAPL": [_lot(10.0, 5) for _ in range(3)],
            "TSLA": [_lot(-5.0, 20) for _ in range(3)],
        }
        result = self._call(lots_by_ticker)
        assert result["total_closed_lots"] == 6
        assert result["winning_lots"] == 3
        assert result["losing_lots"] == 3


# ---------------------------------------------------------------------------
# get_revenge_trading_indicators
# ---------------------------------------------------------------------------

class TestGetRevengeTradingIndicators:
    def _call(
        self,
        lots_by_ticker: dict[str, list[ClosedLot]],
        all_trades: list[MagicMock],
        loss_threshold_pct: float = 5.0,
        window_hours: int = 48,
    ):
        svc, fake_fifo = _make_analytics_svc(lots_by_ticker, all_trades=all_trades)
        with patch("services.analytics_service.fifo_closed_lots", side_effect=fake_fifo):
            return svc.get_revenge_trading_indicators(loss_threshold_pct, window_hours)

    def _trigger_loss_lot(
        self,
        close_year: int = 2024,
        close_month: int = 6,
        close_day: int = 1,
        pnl: float = -50.0,
        cost_basis: float = 500.0,
    ) -> ClosedLot:
        """A lot that qualifies as a trigger: loss > 5% of cost_basis."""
        from datetime import timedelta
        close_dt = date(close_year, close_month, close_day)
        return ClosedLot(
            ticker="AAPL",
            pnl=pnl,
            open_date=close_dt - timedelta(days=10),
            close_date=close_dt,
            quantity=5.0,
            cost_basis=cost_basis,
        )

    def test_schema_keys_present(self):
        # No triggers, no follow-on buys
        lots_by_ticker: dict[str, list[ClosedLot]] = {}
        trades = [_make_trade(ticker="AAPL", action=TradeAction.BUY)]
        result = self._call(lots_by_ticker, trades)
        assert "instances_found" in result
        assert "threshold_met" in result
        assert "instances" in result
        assert "note" in result

    def test_no_instances_when_no_qualifying_losses(self):
        # Only small losses (1% of basis) — below 5% threshold
        small_loss_lot = ClosedLot(
            ticker="AAPL",
            pnl=-1.0,
            open_date=date(2024, 5, 20),
            close_date=date(2024, 6, 1),
            quantity=10.0,
            cost_basis=200.0,  # 0.5% loss — below threshold
        )
        lots_by_ticker = {"AAPL": [small_loss_lot]}
        trades = [
            _make_trade(ticker="TSLA", action=TradeAction.BUY, executed_at=date(2024, 6, 2)),
        ]
        result = self._call(lots_by_ticker, trades)
        assert result["instances_found"] == 0
        assert result["threshold_met"] is False

    def test_detects_follow_on_buy_within_window(self):
        trigger_lot = self._trigger_loss_lot(close_day=1)
        follow_trade = _make_trade(
            ticker="TSLA",
            action=TradeAction.BUY,
            executed_at=date(2024, 6, 2),  # 1 day = 24h after loss close
        )
        # Also need a SELL trade (to build by_ticker for AAPL)
        sell_trade = _make_trade(ticker="AAPL", action=TradeAction.SELL, executed_at=date(2024, 6, 1))
        lots_by_ticker = {"AAPL": [trigger_lot]}
        result = self._call(lots_by_ticker, [sell_trade, follow_trade])
        assert result["instances_found"] >= 1
        assert result["instances"][0]["hours_after"] <= 48.0

    def test_does_not_flag_buy_outside_window(self):
        trigger_lot = self._trigger_loss_lot(close_day=1)
        # Buy 72h after → outside 48h window
        late_trade = _make_trade(
            ticker="TSLA",
            action=TradeAction.BUY,
            executed_at=date(2024, 6, 4),  # 72h after
        )
        sell_trade = _make_trade(ticker="AAPL", action=TradeAction.SELL, executed_at=date(2024, 6, 1))
        lots_by_ticker = {"AAPL": [trigger_lot]}
        result = self._call(lots_by_ticker, [sell_trade, late_trade])
        assert result["instances_found"] == 0

    def test_threshold_met_true_when_3_or_more_instances(self):
        # Create 3 trigger lots on different days with follow-on buys
        from datetime import timedelta as _td
        lots = []
        trades: list[MagicMock] = []
        # Include an AAPL trade so by_ticker contains AAPL and fake_fifo is called for it
        trades.append(_make_trade(ticker="AAPL", action=TradeAction.SELL, executed_at=date(2024, 5, 30)))
        for day in [1, 8, 15]:
            lot = self._trigger_loss_lot(close_day=day)
            lots.append(lot)
            # Follow-on buy 1 day later (24h, within 48h window)
            follow_date = date(2024, 6, day) + _td(days=1)
            trades.append(_make_trade(ticker="TSLA", action=TradeAction.BUY, executed_at=follow_date))
        lots_by_ticker = {"AAPL": lots}
        result = self._call(lots_by_ticker, trades)
        assert result["instances_found"] >= 3
        assert result["threshold_met"] is True

    def test_threshold_met_false_when_fewer_than_3(self):
        trigger_lot = self._trigger_loss_lot(close_day=1)
        follow_trade = _make_trade(ticker="TSLA", action=TradeAction.BUY, executed_at=date(2024, 6, 2))
        lots_by_ticker = {"AAPL": [trigger_lot]}
        result = self._call(lots_by_ticker, [follow_trade])
        # Only 1 instance — threshold NOT met
        assert result["threshold_met"] is False

    def test_instance_fields(self):
        trigger_lot = self._trigger_loss_lot(close_day=1)
        follow_trade = _make_trade(ticker="TSLA", action=TradeAction.BUY, executed_at=date(2024, 6, 2))
        sell_trade = _make_trade(ticker="AAPL", action=TradeAction.SELL, executed_at=date(2024, 6, 1))
        lots_by_ticker = {"AAPL": [trigger_lot]}
        result = self._call(lots_by_ticker, [sell_trade, follow_trade])
        assert result["instances_found"] >= 1
        inst = result["instances"][0]
        assert "loss_trade" in inst
        assert "loss_pct" in inst
        assert "follow_on_buy" in inst
        assert "hours_after" in inst
        assert inst["loss_pct"] > 0

    def test_note_field_describes_methodology(self):
        lots_by_ticker: dict[str, list[ClosedLot]] = {}
        result = self._call(lots_by_ticker, [])
        assert isinstance(result["note"], str)
        assert "5.0%" in result["note"] or "5%" in result["note"] or "48" in result["note"]

    def test_custom_threshold_and_window(self):
        # 10% threshold — the trigger lot loses 10% exactly (50/500)
        trigger_lot = self._trigger_loss_lot(pnl=-50.0, cost_basis=500.0, close_day=1)
        follow_trade = _make_trade(ticker="TSLA", action=TradeAction.BUY, executed_at=date(2024, 6, 2))
        # Include AAPL sell trade so by_ticker contains AAPL
        aapl_sell = _make_trade(ticker="AAPL", action=TradeAction.SELL, executed_at=date(2024, 6, 1))
        lots_by_ticker = {"AAPL": [trigger_lot]}
        # With default 5% threshold, lot qualifies (10% > 5%)
        result_default = self._call(lots_by_ticker, [aapl_sell, follow_trade], loss_threshold_pct=5.0)
        assert result_default["instances_found"] >= 1
        # With 15% threshold, lot does NOT qualify (10% < 15%)
        result_high = self._call(lots_by_ticker, [aapl_sell, follow_trade], loss_threshold_pct=15.0)
        assert result_high["instances_found"] == 0

    def test_handles_empty_trades(self):
        lots_by_ticker: dict[str, list[ClosedLot]] = {}
        result = self._call(lots_by_ticker, [])
        assert result["instances_found"] == 0
        assert result["threshold_met"] is False
        assert result["instances"] == []

    def test_one_instance_per_trigger_not_cartesian(self):
        """Multiple buys after one trigger lot should produce exactly one instance."""
        from datetime import timedelta as _td
        trigger_lot = self._trigger_loss_lot(close_day=1)
        sell_trade = _make_trade(ticker="AAPL", action=TradeAction.SELL, executed_at=date(2024, 6, 1))
        # Three buy trades all within the 48h window after the same trigger
        buy_trades = [
            _make_trade(ticker="MSFT", action=TradeAction.BUY, executed_at=date(2024, 6, 1) + _td(hours=6)),
            _make_trade(ticker="TSLA", action=TradeAction.BUY, executed_at=date(2024, 6, 1) + _td(hours=12)),
            _make_trade(ticker="NVDA", action=TradeAction.BUY, executed_at=date(2024, 6, 1) + _td(hours=24)),
        ]
        lots_by_ticker = {"AAPL": [trigger_lot]}
        result = self._call(lots_by_ticker, [sell_trade] + buy_trades)
        # Must be 1, not 3 (one per trigger, not cartesian)
        assert result["instances_found"] == 1

    def test_tz_aware_executed_at_does_not_raise(self):
        """tz-aware datetimes in executed_at must be handled without TypeError."""
        from datetime import datetime, timezone
        trigger_lot = self._trigger_loss_lot(close_day=1)
        sell_trade = _make_trade(ticker="AAPL", action=TradeAction.SELL, executed_at=date(2024, 6, 1))
        # tz-aware buy trade within window
        tz_buy = _make_trade(ticker="TSLA", action=TradeAction.BUY)
        tz_buy.executed_at = datetime(2024, 6, 2, 10, 0, tzinfo=timezone.utc)
        lots_by_ticker = {"AAPL": [trigger_lot]}
        result = self._call(lots_by_ticker, [sell_trade, tz_buy])
        assert result["instances_found"] >= 1  # should not raise


# ---------------------------------------------------------------------------
# get_coaching_summary
# ---------------------------------------------------------------------------

class TestGetCoachingSummary:
    def _make_svc_with_mocked_methods(
        self,
        behavioral_flags: list[str],
        risk_data: dict,
    ):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService.__new__(AnalyticsService)
        svc._trade_repo = MagicMock()
        svc._portfolio_service = MagicMock()
        svc._statistics_service = MagicMock()
        svc._price_service = MagicMock()

        # Patch the two sub-methods
        svc.get_behavioral_red_flags = MagicMock(return_value=behavioral_flags)
        svc.get_risk_metrics = MagicMock(return_value=risk_data)
        return svc

    def _default_risk(self) -> dict:
        return {
            "concentrated_positions": [],
            "herfindahl_index": 0.10,
            "positions": [],
            "total_market_value": 10000.0,
        }

    def test_schema_keys_present(self):
        svc = self._make_svc_with_mocked_methods([], self._default_risk())
        result = svc.get_coaching_summary()
        assert "behavioral_flags" in result
        assert "top_risk" in result
        assert "suggested_focus" in result

    def test_behavioral_flags_propagated(self):
        flags = ["You hold losers 3x longer.", "80% early winner exits."]
        svc = self._make_svc_with_mocked_methods(flags, self._default_risk())
        result = svc.get_coaching_summary()
        assert result["behavioral_flags"] == flags

    def test_suggested_focus_has_exactly_3_items(self):
        flags = ["You hold losers 3x longer.", "Disposition: 80% early exits."]
        svc = self._make_svc_with_mocked_methods(flags, self._default_risk())
        result = svc.get_coaching_summary()
        assert len(result["suggested_focus"]) == 3

    def test_top_risk_mentions_concentrated_tickers(self):
        risk = {
            "concentrated_positions": [{"ticker": "NVDA", "weight_pct": 45.0}],
            "herfindahl_index": 0.45,
            "positions": [],
            "total_market_value": 10000.0,
        }
        svc = self._make_svc_with_mocked_methods([], risk)
        result = svc.get_coaching_summary()
        assert "NVDA" in result["top_risk"]

    def test_top_risk_mentions_herfindahl_when_no_concentrated(self):
        risk = {
            "concentrated_positions": [],
            "herfindahl_index": 0.35,  # > 0.25 threshold
            "positions": [],
            "total_market_value": 10000.0,
        }
        svc = self._make_svc_with_mocked_methods([], risk)
        result = svc.get_coaching_summary()
        assert "0.35" in result["top_risk"] or "Herfindahl" in result["top_risk"]

    def test_top_risk_no_issue_when_low_herfindahl(self):
        svc = self._make_svc_with_mocked_methods([], self._default_risk())
        result = svc.get_coaching_summary()
        assert "No severe" in result["top_risk"] or "no severe" in result["top_risk"].lower()

    def test_holding_flag_produces_exit_rule_suggestion(self):
        flags = ["You hold losing trades 4.0x longer than winning ones."]
        svc = self._make_svc_with_mocked_methods(flags, self._default_risk())
        result = svc.get_coaching_summary()
        focus_text = " ".join(result["suggested_focus"]).lower()
        assert "stop" in focus_text or "exit" in focus_text or "loss" in focus_text

    def test_disposition_flag_produces_let_winners_run_suggestion(self):
        flags = ["Disposition: 75% early exits — you may be cutting winners short."]
        svc = self._make_svc_with_mocked_methods(flags, self._default_risk())
        result = svc.get_coaching_summary()
        focus_text = " ".join(result["suggested_focus"]).lower()
        assert "winner" in focus_text or "profitable" in focus_text or "run" in focus_text

    def test_all_suggested_focus_items_are_strings(self):
        svc = self._make_svc_with_mocked_methods([], self._default_risk())
        result = svc.get_coaching_summary()
        for item in result["suggested_focus"]:
            assert isinstance(item, str)
            assert len(item) > 0

    def test_no_flags_still_returns_3_focus_items(self):
        svc = self._make_svc_with_mocked_methods([], self._default_risk())
        result = svc.get_coaching_summary()
        assert len(result["suggested_focus"]) == 3

    def test_concentrated_risk_included_in_focus(self):
        risk = {
            "concentrated_positions": [{"ticker": "AAPL", "weight_pct": 55.0}],
            "herfindahl_index": 0.55,
            "positions": [],
            "total_market_value": 10000.0,
        }
        svc = self._make_svc_with_mocked_methods([], risk)
        result = svc.get_coaching_summary()
        focus_text = " ".join(result["suggested_focus"])
        assert "AAPL" in focus_text or "concentration" in focus_text.lower()
