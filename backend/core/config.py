import os

INDEX_TICKERS_SET: frozenset[str] = frozenset({"VOO", "SPY", "QQQ", "IBIT", "ETHA"})
# CACHE_TTL is the real upstream request rate: the refresh thread only issues a
# call for a ticker whose cached price has aged past it. PRICE_LOOP_TICK is just
# how often that thread wakes to look for work, so a newly-online user's holdings
# get priced within a tick rather than waiting out a full TTL.
CACHE_TTL: int = 180
PRICE_LOOP_TICK: int = 15
ALERT_CHECK_INTERVAL: int = 60    # background cadence for evaluating price alerts
ACTIVITY_WINDOW: int = 300        # a user counts as online this long after their last request
# A ticker whose fetch just failed is left alone this long. Without it a failing
# ticker never populates the cache, so every caller counts it as a miss and
# retries immediately — which is what turns one upstream 429 into a permanent one.
NEGATIVE_CACHE_TTL: int = 180
# On an upstream rate-limit response all fetching pauses for BASE seconds,
# doubling on each further rejection up to MAX. Cached prices are served
# throughout, so the dashboard degrades to "slightly stale" rather than "empty".
BREAKER_BASE_COOLDOWN: int = 300
BREAKER_MAX_COOLDOWN: int = 1800
MAX_TOOL_ROUNDS: int = 5          # max LLM ↔ tool iterations per chat request
HIST_CACHE_TTL: int = 6 * 3600    # seconds before a cached historical price series is stale
# Indexes a user can benchmark their trading against on the Performance tab.
BENCHMARK_TICKERS: frozenset[str] = frozenset({"SPY", "QQQ"})
