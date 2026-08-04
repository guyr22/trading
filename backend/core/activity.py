"""Tracks which users have recently made a request.

The price refresh loop consults this so it only prices holdings belonging to
people who are actually looking at them — an idle account's positions don't
need a live quote. Alerts are deliberately *not* gated on activity: the whole
point of an alert is to fire while nobody is watching.

Touched from the auth dependency, read from the refresh thread, so it is
guarded by a lock. The map is keyed by user id and therefore bounded by the
number of accounts.
"""
import threading
import time


class ActivityTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_seen: dict[int, float] = {}

    def touch(self, user_id: int) -> None:
        with self._lock:
            self._last_seen[user_id] = time.time()

    def active_users(self, window: int) -> set[int]:
        """Ids of users seen within the last `window` seconds."""
        cutoff = time.time() - window
        with self._lock:
            return {uid for uid, seen in self._last_seen.items() if seen >= cutoff}


# Module-level singleton — one view of activity shared by the API and the
# background threads.
activity_tracker = ActivityTracker()
