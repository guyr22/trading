"""Dispatches tool names to AnalyticsService methods.

Adding a new tool: add an entry to _DISPATCH — nothing else changes.
"""
import json

from core.logging import get_logger
from services.analytics_service import AnalyticsService

logger = get_logger(__name__)


class ToolExecutor:
    def __init__(self, analytics: AnalyticsService) -> None:
        self._analytics = analytics
        self._dispatch: dict = {
            "get_portfolio_statistics":  lambda a: analytics.get_portfolio_statistics(),
            "get_ticker_analysis":       lambda a: analytics.get_ticker_analysis(a.get("ticker", "")),
            "get_behavioral_patterns":   lambda a: analytics.get_behavioral_patterns(),
            "get_post_exit_prices":      lambda a: analytics.get_post_exit_prices(a.get("ticker", ""), a.get("close_date", "")),
            "get_current_prices":        lambda a: analytics.get_current_prices(),
            "get_sector_concentration":  lambda a: analytics.get_sector_concentration(),
            "get_correlation_analysis":  lambda a: analytics.get_correlation_analysis(),
            "get_entry_timing_analysis": lambda a: analytics.get_entry_timing_analysis(a.get("ticker", "")),
            "get_risk_metrics":          lambda a: analytics.get_risk_metrics(),
            "get_similar_past_setups":   lambda a: analytics.get_similar_past_setups(a.get("ticker", "")),
            "get_fee_impact_report":          lambda a: analytics.get_fee_impact_report(),
            "compare_to_benchmark":           lambda a: analytics.compare_to_benchmark(a.get("benchmark", "SPY")),
            "get_disposition_effect":         lambda a: analytics.get_disposition_effect(),
            "get_revenge_trading_indicators": lambda a: analytics.get_revenge_trading_indicators(
                a.get("loss_threshold_pct", 5.0),
                a.get("window_hours", 48),
            ),
            "get_coaching_summary":           lambda a: analytics.get_coaching_summary(),
        }

    def execute(self, name: str, args: dict) -> str:
        logger.info("Executing chat tool: %s(%s)", name, args)
        fn = self._dispatch.get(name)
        if fn is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        return json.dumps(fn(args), default=str)
