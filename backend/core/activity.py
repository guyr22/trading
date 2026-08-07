"""Tracks which users have recently made a request, and of what kind.

The price refresh loop consults this so it only prices holdings belonging to
people who are actually looking at them — an idle account's positions don't
need a live quote. Alerts are deliberately *not* gated on activity: the whole
point of an alert is to fire while nobody is watching.

Activity is recorded per scope. APP covers any authenticated request and gates
ordinary holdings. INDEXES is touched only by the index-portfolio endpoint,
because index funds are excluded from the dashboard entirely — they are worth
pricing while someone is on the Indexes page and at no other time.

Touched from request handlers, read from the refresh thread, so it is guarded
by a lock. Keyed by (scope, user id) and therefore bounded by the number of
accounts times the handful of scopes.
"""
import threading
import time

SCOPE_APP = "app"
SCOPE_INDEXES = "indexes"


class ActivityTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_seen: dict[tuple[str, int], float] = {}

    def touch(self, user_id: int, scope: str = SCOPE_APP) -> None:
        with self._lock:
            self._last_seen[(scope, user_id)] = time.time()

    def active_users(self, window: int, scope: str = SCOPE_APP) -> set[int]:
        """Ids of users seen in `scope` within the last `window` seconds."""
        cutoff = time.time() - window
        with self._lock:
            return {
                uid for (s, uid), seen in self._last_seen.items()
                if s == scope and seen >= cutoff
            }


# Module-level singleton — one view of activity shared by the API and the
# background threads.
activity_tracker = ActivityTracker()
