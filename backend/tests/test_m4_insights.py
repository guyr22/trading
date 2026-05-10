"""Tests for M4: GET /api/chat/insights — logic tested via a thin helper that
mirrors the route implementation without importing the full router module
(which would trigger the google.generativeai import chain).
"""
from __future__ import annotations

from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Mirror of the route logic (kept in sync with routers/chat.py)
# We test the business logic, not FastAPI wiring.
# ---------------------------------------------------------------------------

def _insights_logic(analytics) -> dict:
    """Reproduces the body of chat_insights_endpoint() for unit testing."""
    try:
        flags = analytics.get_behavioral_red_flags()
        disposition_summary = None
        try:
            disposition_raw = analytics.get_disposition_effect()
            all_closed_count = disposition_raw.get("total_closed_lots", 0)
            if all_closed_count >= 5 and "error" not in disposition_raw:
                disposition_summary = {
                    "hold_ratio": disposition_raw["hold_ratio"],
                    "avg_winner_hold_days": disposition_raw["avg_winner_hold_days"],
                    "avg_loser_hold_days": disposition_raw["avg_loser_hold_days"],
                    "interpretation": disposition_raw["interpretation"],
                }
        except Exception:
            disposition_summary = None
        return {
            "flags": flags[:2],
            "has_insights": len(flags) > 0,
            "disposition_summary": disposition_summary,
        }
    except Exception:
        return {"flags": [], "has_insights": False, "disposition_summary": None}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analytics_svc(
    flags: list[str] | None = None,
    disposition_result: dict | None = None,
    raise_on_flags: bool = False,
    raise_on_disposition: bool = False,
) -> MagicMock:
    from services.analytics_service import AnalyticsService

    svc = MagicMock(spec=AnalyticsService)

    if raise_on_flags:
        svc.get_behavioral_red_flags.side_effect = RuntimeError("flags boom")
    else:
        svc.get_behavioral_red_flags.return_value = flags if flags is not None else []

    if raise_on_disposition:
        svc.get_disposition_effect.side_effect = RuntimeError("disposition boom")
    else:
        svc.get_disposition_effect.return_value = (
            disposition_result
            if disposition_result is not None
            else {"error": "Insufficient data: fewer than 5 closed lots"}
        )

    return svc


def _default_disposition(
    hold_ratio: float = 2.5,
    avg_winner: float = 5.0,
    avg_loser: float = 12.5,
    interpretation: str = "You hold losers 2.5x longer.",
    total_closed_lots: int = 10,
) -> dict:
    return {
        "total_closed_lots": total_closed_lots,
        "winning_lots": 5,
        "losing_lots": 5,
        "avg_winner_hold_days": avg_winner,
        "avg_loser_hold_days": avg_loser,
        "hold_ratio": hold_ratio,
        "winners_closed_early_pct": 60.0,
        "interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChatInsightsLogic:

    # --- schema ---------------------------------------------------------------

    def test_response_has_required_keys(self):
        svc = _make_analytics_svc(flags=["Flag A"], disposition_result=_default_disposition())
        result = _insights_logic(svc)
        assert "flags" in result
        assert "has_insights" in result
        assert "disposition_summary" in result

    # --- flags ----------------------------------------------------------------

    def test_flags_is_empty_list_when_no_red_flags(self):
        svc = _make_analytics_svc(flags=[])
        result = _insights_logic(svc)
        assert result["flags"] == []

    def test_has_insights_false_when_no_flags(self):
        svc = _make_analytics_svc(flags=[])
        result = _insights_logic(svc)
        assert result["has_insights"] is False

    def test_has_insights_true_when_flags_present(self):
        svc = _make_analytics_svc(flags=["Flag A"])
        result = _insights_logic(svc)
        assert result["has_insights"] is True

    def test_at_most_2_flags_returned(self):
        svc = _make_analytics_svc(flags=["Flag A", "Flag B", "Flag C"])
        result = _insights_logic(svc)
        assert len(result["flags"]) <= 2

    def test_exactly_2_flags_when_3_available(self):
        svc = _make_analytics_svc(flags=["Flag A", "Flag B", "Flag C"])
        result = _insights_logic(svc)
        assert len(result["flags"]) == 2
        assert result["flags"] == ["Flag A", "Flag B"]

    def test_flags_are_strings(self):
        svc = _make_analytics_svc(flags=["You hold losers 2x longer."])
        result = _insights_logic(svc)
        assert all(isinstance(f, str) for f in result["flags"])

    # --- disposition_summary --------------------------------------------------

    def test_disposition_summary_null_when_insufficient_data_error_key(self):
        svc = _make_analytics_svc(
            flags=["Flag A"],
            disposition_result={"error": "Insufficient data: fewer than 5 closed lots"},
        )
        result = _insights_logic(svc)
        assert result["disposition_summary"] is None

    def test_disposition_summary_null_when_fewer_than_5_lots(self):
        svc = _make_analytics_svc(
            flags=[],
            disposition_result={
                "total_closed_lots": 3,
                "winning_lots": 2,
                "losing_lots": 1,
                "avg_winner_hold_days": 5.0,
                "avg_loser_hold_days": 10.0,
                "hold_ratio": 2.0,
                "winners_closed_early_pct": 50.0,
                "interpretation": "Not enough data.",
            },
        )
        result = _insights_logic(svc)
        # total_closed_lots < 5 → must be None
        assert result["disposition_summary"] is None

    def test_disposition_summary_populated_when_sufficient_data(self):
        svc = _make_analytics_svc(
            flags=["Flag A"],
            disposition_result=_default_disposition(),
        )
        result = _insights_logic(svc)
        ds = result["disposition_summary"]
        assert ds is not None
        assert "hold_ratio" in ds
        assert "avg_winner_hold_days" in ds
        assert "avg_loser_hold_days" in ds
        assert "interpretation" in ds

    def test_disposition_summary_correct_values(self):
        disp = _default_disposition(hold_ratio=3.1, avg_winner=4.0, avg_loser=12.4, interpretation="Test interp")
        svc = _make_analytics_svc(flags=["Flag A"], disposition_result=disp)
        result = _insights_logic(svc)
        ds = result["disposition_summary"]
        assert ds["hold_ratio"] == 3.1
        assert ds["avg_winner_hold_days"] == 4.0
        assert ds["avg_loser_hold_days"] == 12.4
        assert ds["interpretation"] == "Test interp"

    def test_disposition_summary_has_no_extra_keys(self):
        svc = _make_analytics_svc(flags=["Flag A"], disposition_result=_default_disposition())
        result = _insights_logic(svc)
        ds = result["disposition_summary"]
        assert set(ds.keys()) == {"hold_ratio", "avg_winner_hold_days", "avg_loser_hold_days", "interpretation"}

    # --- error fallback -------------------------------------------------------

    def test_returns_safe_fallback_when_flags_raises(self):
        svc = _make_analytics_svc(raise_on_flags=True)
        result = _insights_logic(svc)
        assert result == {"flags": [], "has_insights": False, "disposition_summary": None}

    def test_returns_null_disposition_when_disposition_raises(self):
        svc = _make_analytics_svc(flags=["Flag A"], raise_on_disposition=True)
        result = _insights_logic(svc)
        assert result["flags"] == ["Flag A"]
        assert result["has_insights"] is True
        assert result["disposition_summary"] is None

    # --- edge cases -----------------------------------------------------------

    def test_single_flag_returned_as_list(self):
        svc = _make_analytics_svc(flags=["Only one flag."])
        result = _insights_logic(svc)
        assert isinstance(result["flags"], list)
        assert len(result["flags"]) == 1

    def test_disposition_summary_null_when_analytics_returns_error_key(self):
        svc = _make_analytics_svc(
            flags=[],
            disposition_result={"error": "some other error"},
        )
        result = _insights_logic(svc)
        assert result["disposition_summary"] is None

    def test_exactly_5_closed_lots_includes_disposition(self):
        disp = _default_disposition(total_closed_lots=5)
        svc = _make_analytics_svc(flags=["Flag A"], disposition_result=disp)
        result = _insights_logic(svc)
        assert result["disposition_summary"] is not None

    def test_has_insights_false_is_bool(self):
        svc = _make_analytics_svc(flags=[])
        result = _insights_logic(svc)
        assert isinstance(result["has_insights"], bool)

    def test_has_insights_true_is_bool(self):
        svc = _make_analytics_svc(flags=["Flag A"])
        result = _insights_logic(svc)
        assert isinstance(result["has_insights"], bool)
