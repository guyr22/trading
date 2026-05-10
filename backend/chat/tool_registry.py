"""Central registry for all chat tool definitions.

Adding a new tool means adding one entry to _TOOL_DEFS — no other file changes.
"""

_TOOL_DEFS: list[dict] = [
    {
        "name": "get_portfolio_statistics",
        "description": (
            "Returns overall portfolio statistics: win rate, profit factor, avg win/loss, "
            "max drawdown, avg holding days, per-ticker stats, monthly P&L timeseries. "
            "Call this for any question about overall performance metrics."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_ticker_analysis",
        "description": (
            "Returns the complete trade and closed-lot history for a single ticker: "
            "all entry/exit dates, holding periods, P&L per lot, fees, fee drag. "
            "Call this when the user asks about a specific stock."
        ),
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol, e.g. TSLA"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_behavioral_patterns",
        "description": (
            "Returns behavioural trading patterns: avg holding days for winners vs losers, "
            "fee drag per ticker, monthly trade frequency, streak analysis, loss profile. "
            "Call this when the user asks what mistakes they make or how to improve."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_post_exit_prices",
        "description": (
            "Given a ticker and exit date, returns the stock price at exit and 30/60/90 days later "
            "so you can assess whether the exit was premature. "
            "Call this when the user asks about a specific exit or 'did I sell too early'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "close_date": {"type": "string", "description": "Exit date in YYYY-MM-DD format"},
            },
            "required": ["ticker", "close_date"],
        },
    },
    {
        "name": "get_current_prices",
        "description": (
            "Returns live prices, market values, unrealized P&L and portfolio weight for all open positions. "
            "Call this when the user asks about current prices or the current state of the portfolio."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_sector_concentration",
        "description": (
            "Groups all open positions by market sector and shows the weight of each sector. "
            "Call this when the user asks about diversification, sector exposure, or concentration risk."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_correlation_analysis",
        "description": (
            "Computes pairwise 180-day return correlations between all open positions. "
            "Flags pairs with correlation > 0.7 as concentrated risk. "
            "Call this when the user asks if their positions are correlated or diversified."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_entry_timing_analysis",
        "description": (
            "For each buy trade on a ticker, shows where the entry price fell in the 20-day high/low range "
            "assessing whether entries were near lows (good) or highs (poor). "
            "Call this when the user asks about entry quality or timing for a specific stock."
        ),
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol, e.g. TSLA"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_risk_metrics",
        "description": (
            "Returns position sizing as % of portfolio, flags concentrated positions (>20%), "
            "and computes a Herfindahl concentration index. "
            "Call this when the user asks about risk, position sizing, or over-concentration."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_similar_past_setups",
        "description": (
            "Given a ticker, finds past closed trades in the same sector or similar market cap "
            "and shows their outcomes. "
            "Call this when the user asks 'how did I do with similar stocks' or is considering a new trade."
        ),
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol to find similar past setups for"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_fee_impact_report",
        "description": (
            "Breaks down total fees paid by platform, avg fee per trade, and fees as a % of gross realized P&L. "
            "Call this when the user asks about fees, broker costs, or how much fees are hurting returns."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "compare_to_benchmark",
        "description": (
            "Compares the user's realized P&L against a buy-and-hold benchmark (default SPY) "
            "over the same period, showing alpha and monthly breakdowns. "
            "Call this when the user asks how they compare to the market or a specific index."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "benchmark": {
                    "type": "string",
                    "description": "Benchmark ticker, e.g. SPY, QQQ, IWM. Defaults to SPY.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_disposition_effect",
        "description": (
            "Computes the disposition effect: ratio of winning trades closed early vs losing trades "
            "held long. Returns avg holding days for winners vs losers, early-exit count, and an "
            "interpretation. Call this when the user asks about their tendency to cut winners or "
            "hold losers."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_revenge_trading_indicators",
        "description": (
            "Detects potential revenge trading: trades placed within 48 hours of a realized loss "
            "exceeding 5% of the lot's cost basis. Returns matching instances with their context. "
            "Call this when the user asks whether they trade emotionally or make impulsive decisions "
            "after losses."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "loss_threshold_pct": {
                    "type": "number",
                    "description": "Loss size threshold as a percentage of cost basis to qualify as a trigger (default 5.0).",
                },
                "window_hours": {
                    "type": "integer",
                    "description": "Hours after the trigger loss within which a follow-on buy is flagged (default 48).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_coaching_summary",
        "description": (
            "Returns a structured coaching brief: top 2 behavioral flags, current risk metrics "
            "summary, and 3 suggested focus areas for improvement. Call this when the user asks "
            "for an overall coaching assessment or 'what should I work on'."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


class ToolRegistry:
    def __init__(self, definitions: list[dict]) -> None:
        self._defs = definitions

    @property
    def claude_format(self) -> list[dict]:
        return [
            {"name": d["name"], "description": d["description"], "input_schema": d["parameters"]}
            for d in self._defs
        ]

    @property
    def openai_format(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": d["name"],
                    "description": d["description"],
                    "parameters": d["parameters"],
                },
            }
            for d in self._defs
        ]

    @property
    def gemini_format(self) -> list[dict]:
        return [
            {
                "function_declarations": [
                    {"name": d["name"], "description": d["description"], "parameters": d["parameters"]}
                    for d in self._defs
                ]
            }
        ]


TOOL_REGISTRY = ToolRegistry(_TOOL_DEFS)
