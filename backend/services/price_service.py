import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import yfinance as yf

from core.config import (
    ACTIVITY_WINDOW,
    BREAKER_BASE_COOLDOWN,
    BREAKER_MAX_COOLDOWN,
    CACHE_TTL,
    HIST_CACHE_TTL,
    NEGATIVE_CACHE_TTL,
    PRICE_LOOP_TICK,
)
from core.logging import get_logger
from core.market_hours import is_market_open

logger = get_logger(__name__)

# Yahoo surfaces a rate-limit rejection as a plain exception through yfinance
# rather than a typed error, so it has to be recognised from the message.
_RATE_LIMIT_MARKERS = ("too many requests", "rate limit", "rate-limit", "429")


def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _RATE_LIMIT_MARKERS)


class PriceService:
    def __init__(self) -> None:
        self._price_cache: dict[str, tuple[float, float]] = {}
        self._ticker_info_cache: dict[str, dict] = {}
        # ticker -> (sorted [(YYYY-MM-DD, close)], fetched_at, covered_from)
        self._hist_cache: dict[str, tuple[list[tuple[str, float]], float, date]] = {}
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        # Rate-limit defences. _failed_at holds the last failure per ticker;
        # _cooldown_until is a service-wide pause covering every upstream call.
        self._lock = threading.RLock()
        self._failed_at: dict[str, float] = {}
        self._cooldown_until: float = 0.0
        self._cooldown_secs: int = 0
        # Tickers already given their one out-of-hours warm attempt.
        self._warmed_while_closed: set[str] = set()

    # ---- Rate-limit breaker -------------------------------------------------

    def _breaker_open(self, now: float | None = None) -> bool:
        with self._lock:
            return (now or time.time()) < self._cooldown_until

    def _note_rate_limit(self) -> None:
        """Open (or extend) the cooldown. Idempotent while already open, so a pass
        that gets rejected on ten tickers escalates the backoff once, not ten times."""
        with self._lock:
            now = time.time()
            if now < self._cooldown_until:
                return
            self._cooldown_secs = (
                min(self._cooldown_secs * 2, BREAKER_MAX_COOLDOWN)
                if self._cooldown_secs
                else BREAKER_BASE_COOLDOWN
            )
            self._cooldown_until = now + self._cooldown_secs
            logger.warning(
                "Upstream rate limit hit — pausing all price fetches for %ds (serving cached prices)",
                self._cooldown_secs,
            )

    def _note_success(self) -> None:
        with self._lock:
            if self._cooldown_secs:
                logger.info("Upstream price fetches recovered — cooldown cleared")
            self._cooldown_secs = 0
            self._cooldown_until = 0.0

    def _recently_failed(self, ticker: str, now: float) -> bool:
        with self._lock:
            failed_at = self._failed_at.get(ticker)
        return failed_at is not None and now - failed_at < NEGATIVE_CACHE_TTL

    def _record_success(self, ticker: str, price: float) -> None:
        with self._lock:
            self._price_cache[ticker] = (price, time.time())
            self._failed_at.pop(ticker, None)
        self._note_success()

    def _record_failure(self, ticker: str, exc: Exception) -> None:
        with self._lock:
            self._failed_at[ticker] = time.time()
        logger.warning("Price fetch failed for %s: %s", ticker, exc)
        if _is_rate_limited(exc):
            self._note_rate_limit()

    # ---- Live prices --------------------------------------------------------

    def get_cached_prices(self, tickers: list[str]) -> dict[str, float | None]:
        """Last known price per ticker, ignoring staleness and never touching the
        network. Request handlers use this so page loads can't drive upstream traffic."""
        with self._lock:
            return {t: (self._price_cache[t][0] if t in self._price_cache else None) for t in tickers}

    def get_live_price(self, ticker: str) -> float | None:
        now = time.time()
        cached = self._price_cache.get(ticker)
        if cached and now - cached[1] < CACHE_TTL:
            return cached[0]

        stale = cached[0] if cached else None
        if self._recently_failed(ticker, now) or self._breaker_open(now):
            return stale
        try:
            price = float(yf.Ticker(ticker).fast_info["lastPrice"])
        except Exception as e:
            self._record_failure(ticker, e)
            return stale
        self._record_success(ticker, price)
        logger.info("Price fetched  %s = $%.2f", ticker, price)
        return price

    def get_live_prices(self, tickers: list[str]) -> dict[str, float | None]:
        now = time.time()
        results: dict[str, float | None] = {}
        to_fetch: list[str] = []

        for t in tickers:
            cached = self._price_cache.get(t)
            if cached and now - cached[1] < CACHE_TTL:
                results[t] = cached[0]
                continue
            # Stale or absent: serve the last known price and queue a refetch,
            # unless this ticker just failed and is still in its cool-off.
            results[t] = cached[0] if cached else None
            if not self._recently_failed(t, now):
                to_fetch.append(t)

        if not to_fetch or self._breaker_open(now):
            return results

        logger.info("Fetching live prices for: %s", ", ".join(to_fetch))
        try:
            data = yf.Tickers(" ".join(to_fetch))
        except Exception as e:
            logger.warning("Batch price fetch failed: %s", e)
            if _is_rate_limited(e):
                self._note_rate_limit()
            return results

        for t in to_fetch:
            # yfinance issues one HTTP call per ticker here, so re-check the
            # breaker each time: the first 429 aborts the rest of the pass
            # instead of firing another N doomed requests at Yahoo.
            if self._breaker_open():
                logger.warning("Aborting price pass after rate limit — %s not fetched", t)
                break
            try:
                price = float(data.tickers[t].fast_info["lastPrice"])
            except Exception as e:
                self._record_failure(t, e)
                continue
            self._record_success(t, price)
            results[t] = price

        return results

    # ---- Historical closes (for benchmarking) -------------------------------

    def get_historical_closes(self, ticker: str, start: date) -> list[tuple[str, float]]:
        """Return a chronologically sorted list of (YYYY-MM-DD, close) for `ticker`
        from `start` to today. Cached per ticker; a cached series is reused when it
        is fresh and already reaches back at least as far as `start`. Returns the
        last known series (or []) on fetch failure so callers degrade gracefully.
        """
        now = time.time()
        cached = self._hist_cache.get(ticker)
        if cached and now - cached[1] < HIST_CACHE_TTL and cached[2] <= start:
            return cached[0]
        if self._breaker_open(now):
            return cached[0] if cached else []
        try:
            df = yf.Ticker(ticker).history(start=start.isoformat())
            series = [(idx.strftime("%Y-%m-%d"), float(row["Close"])) for idx, row in df.iterrows()]
            if series:
                self._hist_cache[ticker] = (series, now, start)
                logger.info("Historical closes fetched %s: %d days from %s", ticker, len(series), start)
                return series
            logger.warning("Historical closes empty for %s from %s", ticker, start)
        except Exception as e:
            logger.warning("Historical close fetch failed for %s: %s", ticker, e)
            if _is_rate_limited(e):
                self._note_rate_limit()
        return cached[0] if cached else []

    # ---- Ticker info (sector / market cap) ----------------------------------

    _EMPTY_INFO = {"sector": "", "marketCap": 0}

    def get_ticker_info(self, ticker: str) -> dict:
        if ticker in self._ticker_info_cache:
            return self._ticker_info_cache[ticker]
        if self._breaker_open():
            return dict(self._EMPTY_INFO)
        try:
            info = yf.Ticker(ticker).info
        except Exception as e:
            if _is_rate_limited(e):
                # Don't cache a rate-limited miss — that would blank out the
                # ticker's sector and market cap for the lifetime of the process.
                self._note_rate_limit()
                return dict(self._EMPTY_INFO)
            self._ticker_info_cache[ticker] = dict(self._EMPTY_INFO)
            return self._ticker_info_cache[ticker]
        self._ticker_info_cache[ticker] = {
            "sector": info.get("sector", ""),
            "marketCap": info.get("marketCap", 0) or 0,
        }
        return self._ticker_info_cache[ticker]

    def prefetch_ticker_info(self, tickers: list[str]) -> None:
        """Fetch .info for all uncached tickers in parallel (up to 10 threads)."""
        to_fetch = [t for t in tickers if t not in self._ticker_info_cache]
        if not to_fetch or self._breaker_open():
            return
        with ThreadPoolExecutor(max_workers=min(len(to_fetch), 10)) as pool:
            futures = {pool.submit(self.get_ticker_info, t): t for t in to_fetch}
            for f in as_completed(futures):
                f.result()

    # ---- Background refresh -------------------------------------------------

    def start_background_refresh(self, session_factory) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._refresh_loop,
            args=(session_factory, self._stop_event),
            daemon=True,
            name="price-refresh",
        )
        self._thread.start()
        logger.info("Background price refresh thread started")

    def stop_background_refresh(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    @staticmethod
    def tickers_to_refresh(db) -> list[str]:
        """The set worth pricing right now: every active alert's ticker, plus the
        open positions of users who have used the app recently.

        Alert tickers are unconditional — an alert has to fire whether or not
        anyone is logged in. Holdings are activity-scoped, so an idle deployment
        makes no upstream calls at all.
        """
        from core.activity import activity_tracker
        from models import PriceAlert, Trade, TradeAction
        from sqlalchemy import case, func

        tickers = {
            row[0] for row in
            db.query(PriceAlert.ticker).filter(PriceAlert.active.is_(True)).distinct()
        }

        active_users = activity_tracker.active_users(ACTIVITY_WINDOW)
        if active_users:
            # Grouped per user as well as per ticker: aggregating across users
            # would let one account's short position cancel out another's long
            # and drop a genuinely held ticker from the refresh set.
            rows = db.query(
                Trade.user_id,
                Trade.ticker,
                func.sum(
                    case(
                        (Trade.action == TradeAction.BUY, Trade.quantity),
                        else_=-Trade.quantity,
                    )
                ).label("net_qty"),
            ).filter(Trade.user_id.in_(active_users)).group_by(Trade.user_id, Trade.ticker).all()
            tickers.update(row.ticker for row in rows if (row.net_qty or 0) > 0)

        return sorted(tickers)

    def _due_this_tick(self, tickers: list[str]) -> list[str]:
        """Which of `tickers` to hand to get_live_prices on this tick.

        During the session: all of them — get_live_prices filters by cache age,
        so CACHE_TTL sets the real request rate.

        Outside it: nothing, except tickers that have never been priced at all.
        The cache is in-memory, so without that exception a deploy outside
        trading hours — or a user logging in overnight — would show avg cost
        instead of the last close. One attempt per ticker, tracked so it can't
        turn into a loop, and reset when the market next opens.
        """
        if is_market_open():
            self._warmed_while_closed.clear()
            return tickers
        pending = [
            t for t in tickers
            if t not in self._price_cache and t not in self._warmed_while_closed
        ]
        self._warmed_while_closed.update(pending)
        return pending

    def _refresh_loop(self, session_factory, stop_event: threading.Event) -> None:
        stop_event.wait(5)
        # None rather than [] so the first pass always logs, including the idle
        # case — otherwise "no upstream calls" and "thread wedged" look identical.
        last_set: list[str] | None = None
        while not stop_event.is_set():
            try:
                with session_factory() as db:
                    tickers = self.tickers_to_refresh(db)
                if tickers != last_set:
                    logger.info("Price refresh set: %s", ", ".join(tickers) or "(idle)")
                    last_set = tickers
                due = self._due_this_tick(tickers)
                if due:
                    self.get_live_prices(due)
            except Exception as e:
                logger.warning("Background price refresh error: %s", e)
            stop_event.wait(PRICE_LOOP_TICK)


# Module-level singleton — one cache shared across all requests
price_service = PriceService()


def get_price_service() -> PriceService:
    return price_service
