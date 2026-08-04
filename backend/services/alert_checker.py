"""Background worker that evaluates active price alerts and sends push notifications.

Runs as its own daemon thread (mirroring PriceService's refresh thread). Each pass
loads every active alert, prices their tickers in one batch, and fires on a genuine
*crossing* of the target — comparing the last observed price against the new one —
so an alert never re-fires while the price merely lingers past the threshold. Firing
is one-shot: the alert is deactivated and stamped with triggered_at.
"""
import threading
from datetime import datetime

from core.config import ALERT_CHECK_INTERVAL
from core.logging import get_logger
from core.market_hours import is_market_open
from models import AlertCondition, PriceAlert
from repositories.alert_repository import AlertRepository
from services.price_service import PriceService
from services.push_service import PushService

logger = get_logger(__name__)


class AlertChecker:
    def __init__(self, price_service: PriceService, push_service: PushService) -> None:
        self._price_service = price_service
        self._push_service = push_service
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    # ---- lifecycle ----------------------------------------------------------

    def start(self, session_factory) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._loop,
            args=(session_factory, self._stop_event),
            daemon=True,
            name="alert-checker",
        )
        self._thread.start()
        logger.info("Alert checker thread started")

    def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self, session_factory, stop_event: threading.Event) -> None:
        stop_event.wait(10)  # let startup settle before the first pass
        while not stop_event.is_set():
            try:
                # A price can't cross a target while the market is shut, so
                # evaluating outside the session only burns cycles.
                if is_market_open():
                    with session_factory() as db:
                        self.check_once(db)
            except Exception as e:  # noqa: BLE001 — keep the loop alive
                logger.warning("Alert check pass failed: %s", e)
            stop_event.wait(ALERT_CHECK_INTERVAL)

    # ---- evaluation ---------------------------------------------------------

    def check_once(self, db) -> int:
        """Evaluate all active alerts once. Returns the number fired."""
        alerts = AlertRepository.all_active(db)
        if not alerts:
            return 0

        tickers = list({a.ticker for a in alerts})
        # Read-only: the refresh thread owns fetching and always includes active
        # alert tickers, so this sees a price at most one refresh cycle old.
        # A ticker with no cached price yet is skipped below rather than fired on.
        prices = self._price_service.get_cached_prices(tickers)

        to_fire: list[tuple[PriceAlert, float]] = []
        for alert in alerts:
            price = prices.get(alert.ticker)
            if price is None:
                continue
            if self._crossed(alert, price):
                alert.active = False
                alert.triggered_at = datetime.now()
                alert.last_price = price
                to_fire.append((alert, price))
            else:
                alert.last_price = price

        # Persist fired state + refreshed baselines before sending anything, so a
        # crash mid-send can never double-fire a one-shot alert.
        db.commit()

        for alert, price in to_fire:
            self._notify(db, alert, price)
        return len(to_fire)

    @staticmethod
    def _crossed(alert: PriceAlert, price: float) -> bool:
        prev = alert.last_price
        if prev is None:
            return False  # first observation — seed only, never insta-fire
        if alert.condition == AlertCondition.ABOVE:
            return prev < alert.target_price <= price
        return prev > alert.target_price >= price

    def _notify(self, db, alert: PriceAlert, price: float) -> None:
        direction = "above" if alert.condition == AlertCondition.ABOVE else "below"
        title = f"{alert.ticker} crossed {direction} ${alert.target_price:,.2f}"
        body = f"{alert.ticker} is now ${price:,.2f}"
        if alert.note:
            body += f" — {alert.note}"
        try:
            sent = self._push_service.send_to_user(db, alert.user_id, title, body, url="/alerts")
            logger.info("Alert %d fired (user %d) — %d push(es) sent", alert.id, alert.user_id, sent)
        except Exception as e:  # noqa: BLE001
            logger.warning("Alert %d push delivery failed: %s", alert.id, e)


# Module-level singleton — wired to the shared price/push singletons and driven
# by the FastAPI lifespan.
from services.price_service import price_service  # noqa: E402
from services.push_service import push_service  # noqa: E402

alert_checker = AlertChecker(price_service, push_service)
