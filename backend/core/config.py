import os

INDEX_TICKERS_SET: frozenset[str] = frozenset({"VOO", "SPY", "QQQ", "IBIT", "ETHA"})
CACHE_TTL: int = 60               # seconds before a cached price is stale
PRICE_REFRESH_INTERVAL: int = 55  # background thread refresh cadence
ALERT_CHECK_INTERVAL: int = 60    # background cadence for evaluating price alerts

# Weekly portfolio digest email (defaults: Sunday 6pm Israel time). All overridable
# via env so the schedule can change without a code deploy. Weekday: Mon=0 .. Sun=6.
DIGEST_TIMEZONE: str = os.environ.get("DIGEST_TIMEZONE", "Asia/Jerusalem")
DIGEST_SEND_WEEKDAY: int = int(os.environ.get("DIGEST_SEND_WEEKDAY", "6"))
DIGEST_SEND_HOUR: int = int(os.environ.get("DIGEST_SEND_HOUR", "18"))
DIGEST_CHECK_INTERVAL: int = 1800  # how often the scheduler thread re-checks the clock
MAX_TOOL_ROUNDS: int = 5          # max LLM ↔ tool iterations per chat request
HIST_CACHE_TTL: int = 6 * 3600    # seconds before a cached historical price series is stale
# Indexes a user can benchmark their trading against on the Performance tab.
BENCHMARK_TICKERS: frozenset[str] = frozenset({"SPY", "QQQ"})
