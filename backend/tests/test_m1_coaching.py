"""Tests for M1: Coaching persona + behavioral brief injected into system prompt."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from domain.finance import ClosedLot
from services.chat_context_service import COACHING_PERSONA, ChatContextService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lot(pnl: float, hold_days: int, ticker: str = "AAPL") -> ClosedLot:
    open_date = date(2024, 1, 1)
    close_date = date(2024, 1, 1 + hold_days)
    cost_basis = abs(pnl) * 2 if pnl != 0 else 100.0
    return ClosedLot(
        ticker=ticker,
        pnl=pnl,
        open_date=open_date,
        close_date=close_date,
        quantity=10.0,
        cost_basis=cost_basis,
    )


# ---------------------------------------------------------------------------
# COACHING_PERSONA constant
# ---------------------------------------------------------------------------

class TestCoachingPersona:
    def test_persona_is_string(self):
        assert isinstance(COACHING_PERSONA, str)

    def test_persona_is_not_concise_assistant(self):
        assert "concise portfolio assistant" not in COACHING_PERSONA

    def test_persona_contains_coach_language(self):
        lower = COACHING_PERSONA.lower()
        assert any(word in lower for word in ("coach", "pattern", "behavioral", "trader"))


# ---------------------------------------------------------------------------
# AnalyticsService.get_behavioral_red_flags()
# ---------------------------------------------------------------------------

class TestGetBehavioralRedFlags:
    """Unit-tests the flag computation logic directly via AnalyticsService."""

    def _call_flags(self, closed_lots: list[ClosedLot]) -> list[str]:
        """Call get_behavioral_red_flags() with a controlled set of closed lots.

        We inject a fake trade per lot (one trade per unique ticker) so the
        by_ticker loop iterates, then patch fifo_closed_lots to return all the
        lots for any ticker (the lots already carry the correct ticker field).
        """
        from models import Trade
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService.__new__(AnalyticsService)

        # Build one fake trade per ticker so the by_ticker grouping works
        tickers = list(dict.fromkeys(lot.ticker for lot in closed_lots))
        fake_trades: list[MagicMock] = []
        for ticker in tickers:
            t = MagicMock(spec=Trade)
            t.ticker = ticker
            fake_trades.append(t)

        svc._trade_repo = MagicMock()
        svc._trade_repo.get_excluding.return_value = fake_trades
        svc._portfolio_service = MagicMock()
        svc._statistics_service = MagicMock()
        svc._price_service = MagicMock()

        # Patch fifo_closed_lots so it returns the lots belonging to the requested ticker
        def fake_fifo(trades, ticker):
            return [lot for lot in closed_lots if lot.ticker == ticker]

        with patch("services.analytics_service.fifo_closed_lots", side_effect=fake_fifo):
            return svc.get_behavioral_red_flags()

    def test_returns_empty_list_below_threshold(self):
        lots = [_make_lot(10.0, 5) for _ in range(4)]
        result = self._call_flags(lots)
        assert result == []

    def test_returns_empty_list_with_exactly_5_lots_no_signal(self):
        # 5 winners with identical hold times — no asymmetry, no early-exit majority
        lots = [_make_lot(10.0, 5) for _ in range(5)]
        result = self._call_flags(lots)
        # No losers, no asymmetry flag; disposition flag requires >50% early exits
        # With all identical hold times, 0 are < avg, so early_exit_pct = 0
        assert result == []

    def test_holding_asymmetry_flag_when_losers_held_much_longer(self):
        # Winners: 5 days avg. Losers: 20 days avg → ratio 4.0x
        winners = [_make_lot(10.0, 5) for _ in range(5)]
        losers = [_make_lot(-10.0, 20) for _ in range(5)]
        result = self._call_flags(winners + losers)
        assert len(result) >= 1
        first = result[0]
        assert "longer" in first.lower() or "x" in first
        assert "days" in first.lower()
        # Should contain actual numbers
        assert "4.0x" in first or "20" in first

    def test_no_asymmetry_flag_when_ratio_below_1_5(self):
        # Winners: 10 days, Losers: 12 days — ratio 1.2x (below 1.5 threshold)
        winners = [_make_lot(10.0, 10) for _ in range(5)]
        losers = [_make_lot(-10.0, 12) for _ in range(5)]
        result = self._call_flags(winners + losers)
        # Asymmetry flag should NOT be present
        asymmetry_flags = [f for f in result if "longer" in f.lower()]
        assert asymmetry_flags == []

    def test_disposition_effect_flag_when_majority_exit_early(self):
        # avg win hold = 10 days; make 8/10 winners close before that
        lots = (
            [_make_lot(10.0, 3) for _ in range(8)]   # 8 early exits (< 10 avg)
            + [_make_lot(10.0, 20) for _ in range(2)] # 2 late exits (> 10 avg)
            + [_make_lot(-5.0, 10) for _ in range(5)]  # losers
        )
        result = self._call_flags(lots)
        # 80% early exit — should trigger disposition flag
        disposition_flags = [f for f in result if "disposition" in f.lower() or "cutting" in f.lower() or "%" in f]
        assert len(disposition_flags) >= 1

    def test_returns_at_most_2_flags(self):
        # Create a scenario that would trigger both flags
        winners = [_make_lot(10.0, 2) for _ in range(8)] + [_make_lot(10.0, 20) for _ in range(2)]
        losers = [_make_lot(-10.0, 30) for _ in range(5)]
        result = self._call_flags(winners + losers)
        assert len(result) <= 2

    def test_flags_contain_actual_numbers(self):
        winners = [_make_lot(10.0, 5) for _ in range(5)]
        losers = [_make_lot(-10.0, 20) for _ in range(5)]
        result = self._call_flags(winners + losers)
        if result:
            import re
            numbers = re.findall(r"\d+\.?\d*", result[0])
            assert len(numbers) >= 1, "Flag must contain actual numbers"

    def test_returns_empty_on_exception(self):
        from services.analytics_service import AnalyticsService

        svc = AnalyticsService.__new__(AnalyticsService)
        svc._trade_repo = MagicMock()
        svc._trade_repo.get_excluding.side_effect = RuntimeError("DB error")
        svc._portfolio_service = MagicMock()
        svc._statistics_service = MagicMock()
        svc._price_service = MagicMock()

        result = svc.get_behavioral_red_flags()
        assert result == []


# ---------------------------------------------------------------------------
# ChatContextService._build_behavioral_brief()
# ---------------------------------------------------------------------------

class TestBuildBehavioralBrief:
    def _make_ccs(self, flags: list[str]) -> ChatContextService:
        analytics_mock = MagicMock()
        analytics_mock.get_behavioral_red_flags.return_value = flags

        svc = ChatContextService.__new__(ChatContextService)
        svc._trade_repo = MagicMock()
        svc._portfolio_service = MagicMock()
        svc._analytics_service = analytics_mock
        return svc

    def test_returns_empty_string_when_no_flags(self):
        svc = self._make_ccs([])
        assert svc._build_behavioral_brief() == ""

    def test_returns_empty_string_when_analytics_is_none(self):
        svc = ChatContextService.__new__(ChatContextService)
        svc._analytics_service = None
        assert svc._build_behavioral_brief() == ""

    def test_includes_flag_text(self):
        svc = self._make_ccs(["You hold losers 3.0x longer (losers: 18 days, winners: 6 days)."])
        brief = svc._build_behavioral_brief()
        assert "3.0x" in brief
        assert "losers" in brief.lower()

    def test_capped_at_350_chars(self):
        long_flag = "X" * 400
        svc = self._make_ccs([long_flag, long_flag])
        brief = svc._build_behavioral_brief()
        assert len(brief) <= 350

    def test_returns_empty_on_exception(self):
        svc = ChatContextService.__new__(ChatContextService)
        analytics_mock = MagicMock()
        analytics_mock.get_behavioral_red_flags.side_effect = RuntimeError("boom")
        svc._analytics_service = analytics_mock
        assert svc._build_behavioral_brief() == ""

    def test_uses_at_most_2_flags(self):
        flags = ["Flag 1.", "Flag 2.", "Flag 3."]
        svc = self._make_ccs(flags)
        brief = svc._build_behavioral_brief()
        assert "Flag 3" not in brief
        assert "Flag 1" in brief
        assert "Flag 2" in brief


# ---------------------------------------------------------------------------
# ChatContextService system prompt integration
# ---------------------------------------------------------------------------

class TestSystemPromptIntegration:
    def _make_full_ccs(self, flags: list[str]) -> ChatContextService:
        """Build a ChatContextService with enough mocks to call _build_context()."""
        analytics_mock = MagicMock()
        analytics_mock.get_behavioral_red_flags.return_value = flags

        portfolio_mock = MagicMock()
        summary = MagicMock()
        summary.positions = []
        summary.total_market_value = 10000.0
        summary.total_unrealized_pnl = 200.0
        summary.total_realized_pnl = 500.0
        portfolio_mock.build_summary.return_value = summary

        trade_repo_mock = MagicMock()
        trade_repo_mock.get_excluding.return_value = []

        svc = ChatContextService.__new__(ChatContextService)
        svc._trade_repo = trade_repo_mock
        svc._portfolio_service = portfolio_mock
        svc._analytics_service = analytics_mock
        return svc

    def test_system_prompt_uses_coaching_persona(self):
        svc = self._make_full_ccs([])
        with patch("services.chat_context_service.fifo_closed_lots", return_value=[]):
            prompt = svc._build_context()
        assert "concise portfolio assistant" not in prompt
        # Coaching persona content should be present
        assert "coach" in prompt.lower() or "pattern" in prompt.lower()

    def test_behavioral_brief_injected_when_flags_present(self):
        flag = "You hold losers 3.2x longer (losers: 18 days avg, winners: 5.6 days avg)."
        svc = self._make_full_ccs([flag])
        with patch("services.chat_context_service.fifo_closed_lots", return_value=[]):
            prompt = svc._build_context()
        assert "3.2x" in prompt
        assert "BEHAVIORAL" in prompt

    def test_behavioral_brief_absent_when_no_flags(self):
        svc = self._make_full_ccs([])
        with patch("services.chat_context_service.fifo_closed_lots", return_value=[]):
            prompt = svc._build_context()
        assert "BEHAVIORAL" not in prompt

    def test_portfolio_data_still_present(self):
        svc = self._make_full_ccs([])
        with patch("services.chat_context_service.fifo_closed_lots", return_value=[]):
            prompt = svc._build_context()
        assert "PORTFOLIO SUMMARY" in prompt
        assert "OPEN POSITIONS" in prompt
        assert "RECENT TRADES" in prompt
        assert "CLOSED LOTS" in prompt
