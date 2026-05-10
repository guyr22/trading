INDEX_TICKERS_SET: frozenset[str] = frozenset({"VOO", "SPY", "QQQ", "IBIT", "ETHA"})
CACHE_TTL: int = 60               # seconds before a cached price is stale
PRICE_REFRESH_INTERVAL: int = 55  # background thread refresh cadence
MAX_TOOL_ROUNDS: int = 5          # max LLM ↔ tool iterations per chat request
