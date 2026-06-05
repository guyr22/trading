from sqlalchemy.orm import Session

from models import PriceAlert


class AlertRepository:
    """Per-user access to price alerts."""

    def __init__(self, db: Session, user_id: int) -> None:
        self._db = db
        self._user_id = user_id

    def _q(self):
        return self._db.query(PriceAlert).filter(PriceAlert.user_id == self._user_id)

    def get_all(self) -> list[PriceAlert]:
        # Active alerts first, then most recently created.
        return self._q().order_by(PriceAlert.active.desc(), PriceAlert.created_at.desc()).all()

    def get_by_id(self, alert_id: int) -> PriceAlert | None:
        return self._q().filter(PriceAlert.id == alert_id).first()

    def add(self, alert: PriceAlert) -> PriceAlert:
        self._db.add(alert)
        self._db.commit()
        self._db.refresh(alert)
        return alert

    def update(self, alert: PriceAlert, **fields) -> PriceAlert:
        for key, value in fields.items():
            setattr(alert, key, value)
        self._db.commit()
        self._db.refresh(alert)
        return alert

    def delete(self, alert: PriceAlert) -> None:
        self._db.delete(alert)
        self._db.commit()

    @staticmethod
    def all_active(db: Session) -> list[PriceAlert]:
        """Every active alert across all users — used by the background checker."""
        return db.query(PriceAlert).filter(PriceAlert.active.is_(True)).all()
