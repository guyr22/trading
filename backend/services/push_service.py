"""Web Push delivery via VAPID.

Keys are read from the environment so the private key never lives in code:
- VAPID_PUBLIC_KEY   base64url uncompressed P-256 point (also handed to the browser)
- VAPID_PRIVATE_KEY  base64url raw 32-byte P-256 scalar
- VAPID_SUBJECT      contact URI for the push service (mailto:/https:), optional

When the keys are absent the service reports enabled=False and send() is a no-op,
so alerts still save and surface in-app — only the push is skipped.
"""
import json
import os

from sqlalchemy.orm import Session

from core.logging import get_logger
from repositories.push_repository import PushSubscriptionRepository

logger = get_logger(__name__)

_PUSH_TTL = 12 * 3600  # seconds the push service holds an undelivered message


class PushService:
    def __init__(self) -> None:
        self._public_key = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
        self._private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
        subject = os.environ.get("VAPID_SUBJECT", "").strip()
        if not subject:
            admin = os.environ.get("ADMIN_EMAIL", "").strip()
            subject = f"mailto:{admin}" if admin else "mailto:alerts@portfolio.app"
        self._subject = subject
        if self.enabled:
            logger.info("Push service enabled (VAPID configured)")
        else:
            logger.warning("Push service disabled — VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY not set")

    @property
    def enabled(self) -> bool:
        return bool(self._public_key and self._private_key)

    @property
    def public_key(self) -> str | None:
        return self._public_key or None

    def send_to_user(self, db: Session, user_id: int, title: str, body: str, url: str = "/alerts") -> int:
        """Send a notification to every device subscribed by `user_id`.

        Returns the number of successful sends. Dead subscriptions (404/410) are
        pruned so they aren't retried.
        """
        if not self.enabled:
            return 0
        subs = PushSubscriptionRepository.for_user(db, user_id)
        if not subs:
            return 0

        payload = json.dumps({"title": title, "body": body, "url": url})
        sent = 0
        dead: list = []
        for sub in subs:
            if self._send_one(sub.endpoint, sub.p256dh, sub.auth, payload):
                sent += 1
            else:
                dead.append(sub)

        if dead:
            for sub in dead:
                db.delete(sub)
            db.commit()
            logger.info("Pruned %d dead push subscription(s) for user %d", len(dead), user_id)
        return sent

    def _send_one(self, endpoint: str, p256dh: str, auth: str, payload: str) -> bool:
        """Send one push. Returns False (and signals pruning) only when the
        subscription is permanently gone; transient errors are logged, not pruned."""
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                data=payload,
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
                ttl=_PUSH_TTL,
            )
            return True
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                return False  # subscription gone — caller prunes it
            logger.warning("Push send failed (status=%s): %s", status, e)
            return True  # keep the subscription; likely transient
        except Exception as e:  # noqa: BLE001 — never let a bad push break the loop
            logger.warning("Unexpected push error: %s", e)
            return True


# Module-level singleton — one config shared across requests and the background checker.
push_service = PushService()


def get_push_service() -> PushService:
    return push_service
