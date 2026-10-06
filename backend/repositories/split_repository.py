from sqlalchemy.orm import Session

from models import StockSplit


class SplitRepository:
    def __init__(self, db: Session, user_id: int) -> None:
        self._db = db
        self._user_id = user_id

    def _q(self):
        return self._db.query(StockSplit).filter(StockSplit.user_id == self._user_id)

    def get_all(self) -> list[StockSplit]:
        return self._q().order_by(StockSplit.executed_at, StockSplit.id).all()

    def get_by_id(self, split_id: int) -> StockSplit | None:
        return self._q().filter(StockSplit.id == split_id).first()

    def add(self, split: StockSplit) -> StockSplit:
        self._db.add(split)
        self._db.commit()
        self._db.refresh(split)
        return split

    def delete(self, split: StockSplit) -> None:
        self._db.delete(split)
        self._db.commit()
