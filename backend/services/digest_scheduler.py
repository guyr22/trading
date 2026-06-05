"""Background scheduler for the weekly digest email.

Wakes periodically and sends the batch once per ISO week, on/after the configured
weekday + hour in the configured timezone. The last-sent ISO week is persisted in
AppConfig so a restart (or a second worker) can't double-send.
"""
import threading
from datetime import datetime

from core.config import (
    DIGEST_CHECK_INTERVAL,
    DIGEST_SEND_HOUR,
    DIGEST_SEND_WEEKDAY,
    DIGEST_TIMEZONE,
)
from core.logging import get_logger
from repositories.config_repository import ConfigRepository
from services.digest_service import DigestService
from services.email_service import EmailService

logger = get_logger(__name__)

_LAST_SENT_KEY = "weekly_digest_last_sent_week"


class DigestScheduler:
    def __init__(self, digest_service: DigestService, email_service: EmailService) -> None:
        self._digest_service = digest_service
        self._email_service = email_service
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def start(self, session_factory) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._loop,
            args=(session_factory, self._stop_event),
            daemon=True,
            name="digest-scheduler",
        )
        self._thread.start()
        logger.info(
            "Digest scheduler started (weekday=%d hour=%d tz=%s)",
            DIGEST_SEND_WEEKDAY, DIGEST_SEND_HOUR, DIGEST_TIMEZONE,
        )

    def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    @staticmethod
    def _now() -> datetime:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(DIGEST_TIMEZONE))
        except Exception as e:  # noqa: BLE001 — fall back to server-local time if tz data missing
            logger.warning("Digest timezone %s unavailable (%s); using server time", DIGEST_TIMEZONE, e)
            return datetime.now()

    def _loop(self, session_factory, stop_event: threading.Event) -> None:
        stop_event.wait(20)  # let startup settle
        while not stop_event.is_set():
            try:
                if self._email_service.enabled:
                    with session_factory() as db:
                        self.maybe_send(db)
            except Exception as e:  # noqa: BLE001 — keep the loop alive
                logger.warning("Digest scheduler pass failed: %s", e)
            stop_event.wait(DIGEST_CHECK_INTERVAL)

    def maybe_send(self, db) -> bool:
        """Send the weekly batch if we're in the send window and haven't this ISO week."""
        now = self._now()
        if now.weekday() != DIGEST_SEND_WEEKDAY or now.hour < DIGEST_SEND_HOUR:
            return False

        iso_year, iso_week, _ = now.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        config = ConfigRepository(db)
        last = config.get(_LAST_SENT_KEY)
        if last and last.value == week_key:
            return False  # already sent this week

        logger.info("Weekly digest window reached (%s) — sending batch", week_key)
        self._digest_service.send_weekly_batch(db)
        config.set(_LAST_SENT_KEY, week_key)
        return True


# Module-level singleton, wired to the shared digest/email singletons.
from services.digest_service import digest_service  # noqa: E402
from services.email_service import email_service  # noqa: E402

digest_scheduler = DigestScheduler(digest_service, email_service)
