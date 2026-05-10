import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

from core.config import CACHE_TTL, PRICE_REFRESH_INTERVAL
from core.logging import get_logger

logger = get_logger(__name__)


class PriceService:
    def __init__(self) -> None:
        self._price_cache: dict[str, tuple[float, float]] = {}
        self._ticker_info_cache: dict[str, dict] = {}
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    # ---- Live prices --------------------------------------------------------

    def get_live_price(self, ticker: str) -> float | None:
        now = time.time()
        cached = self._price_cache.get(ticker)
        if cached and now - cached[1] < CACHE_TTL:
            return cached[0]
        try:
            price = float(yf.Ticker(ticker).fast_info["lastPrice"])
            self._price_cache[ticker] = (price, now)
            logger.info("Price fetched  %s = $%.2f", ticker, price)
            return price
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", ticker, e)
            return cached[0] if cached else None

    def get_live_prices(self, tickers: list[str]) -> dict[str, float | None]:
        now = time.time()
        results: dict[str, float | None] = {}
        to_fetch: list[str] = []

        for t in tickers:
            cached = self._price_cache.get(t)
            if cached and now - cached[1] < CACHE_TTL:
                results[t] = cached[0]
            else:
                to_fetch.append(t)

        if to_fetch:
            logger.info("Fetching live prices for: %s", ", ".join(to_fetch))
            try:
                data = yf.Tickers(" ".join(to_fetch))
                for t in to_fetch:
                    try:
                        price = float(data.tickers[t].fast_info["lastPrice"])
                        self._price_cache[t] = (price, now)
                        results[t] = price
                    except Exception as e:
                        logger.warning("Price fetch failed for %s: %s", t, e)
                        cached = self._price_cache.get(t)
                        results[t] = cached[0] if cached else None
            except Exception as e:
                logger.warning("Batch price fetch failed: %s", e)
                for t in to_fetch:
                    cached = self._price_cache.get(t)
                    results[t] = cached[0] if cached else None

        return results

    # ---- Ticker info (sector / market cap) ----------------------------------

    def get_ticker_info(self, ticker: str) -> dict:
        if ticker not in self._ticker_info_cache:
            try:
                info = yf.Ticker(ticker).info
                self._ticker_info_cache[ticker] = {
                    "sector": info.get("sector", ""),
                    "marketCap": info.get("marketCap", 0) or 0,
                }
            except Exception:
                self._ticker_info_cache[ticker] = {"sector": "", "marketCap": 0}
        return self._ticker_info_cache[ticker]

    def prefetch_ticker_info(self, tickers: list[str]) -> None:
        """Fetch .info for all uncached tickers in parallel (up to 10 threads)."""
        to_fetch = [t for t in tickers if t not in self._ticker_info_cache]
        if not to_fetch:
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

    def _refresh_loop(self, session_factory, stop_event: threading.Event) -> None:
        from models import Trade, TradeAction
        from sqlalchemy import case, func

        stop_event.wait(5)
        while not stop_event.is_set():
            try:
                with session_factory() as db:
                    rows = db.query(
                        Trade.ticker,
                        func.sum(
                            case(
                                (Trade.action == TradeAction.BUY, Trade.quantity),
                                else_=-Trade.quantity,
                            )
                        ).label("net_qty"),
                    ).group_by(Trade.ticker).all()
                tickers = [row.ticker for row in rows if (row.net_qty or 0) > 0]
                if tickers:
                    logger.info("Background price refresh for: %s", ", ".join(tickers))
                    self.get_live_prices(tickers)
            except Exception as e:
                logger.warning("Background price refresh error: %s", e)
            stop_event.wait(PRICE_REFRESH_INTERVAL)


# Module-level singleton — one cache shared across all requests
price_service = PriceService()


def get_price_service() -> PriceService:
    return price_service
