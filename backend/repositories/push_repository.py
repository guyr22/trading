from sqlalchemy.orm import Session

from models import PushSubscription


class PushSubscriptionRepository:
    """Per-user access to Web Push subscriptions (one row per device/browser)."""

    def __init__(self, db: Session, user_id: int) -> None:
        self._db = db
        self._user_id = user_id

    def upsert(self, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
        """Store a subscription, refreshing keys if the endpoint already exists.

        Endpoints are globally unique, so an endpoint that re-registers under a
        different user is reassigned to the current user.
        """
        sub = self._db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
        if sub:
            sub.user_id = self._user_id
            sub.p256dh = p256dh
            sub.auth = auth
        else:
            sub = PushSubscription(user_id=self._user_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
            self._db.add(sub)
        self._db.commit()
        self._db.refresh(sub)
        return sub

    def delete_by_endpoint(self, endpoint: str) -> None:
        self._db.query(PushSubscription).filter(
            PushSubscription.endpoint == endpoint,
            PushSubscription.user_id == self._user_id,
        ).delete()
        self._db.commit()

    def get_all(self) -> list[PushSubscription]:
        return self._db.query(PushSubscription).filter(
            PushSubscription.user_id == self._user_id
        ).all()

    @staticmethod
    def for_user(db: Session, user_id: int) -> list[PushSubscription]:
        return db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
