from sqlalchemy.orm import Session

from models import IndexTrade
from domain.finance import fifo_full
from repositories.split_repository import SplitRepository


class IndexTradeRepository:
    def __init__(self, db: Session, user_id: int) -> None:
        self._db = db
        self._user_id = user_id

    def _q(self):
        return self._db.query(IndexTrade).filter(IndexTrade.user_id == self._user_id)

    def get_all_ordered(self) -> list[IndexTrade]:
        return self._q().order_by(IndexTrade.executed_at, IndexTrade.id).all()

    def get_all_desc(self) -> list[IndexTrade]:
        return self._q().order_by(IndexTrade.executed_at.desc(), IndexTrade.id.desc()).all()

    def get_by_id(self, trade_id: int) -> IndexTrade | None:
        return self._q().filter(IndexTrade.id == trade_id).first()

    def shares_held(self, ticker: str) -> float:
        return fifo_full(self.get_all_ordered(), ticker,
                         self.get_splits()).quantity

    def get_splits(self):
        return SplitRepository(self._db, self._user_id).get_all()

    def shares_held_on_platform(self, ticker: str, platform: str | None, *, through_date=None) -> float:
        trades = [t for t in self.get_all_ordered() if through_date is None or t.executed_at <= through_date]
        splits = [s for s in self.get_splits()
                  if through_date is None or s.executed_at <= through_date]
        return fifo_full(trades, ticker, splits).quantities_by_platform.get(platform, 0.0)

    def add(self, trade: IndexTrade) -> IndexTrade:
        self._db.add(trade)
        self._db.commit()
        self._db.refresh(trade)
        return trade
