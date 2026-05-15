from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models import IndexTrade, TradeAction


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
        result = self._db.query(
            func.coalesce(func.sum(
                case(
                    (IndexTrade.action == TradeAction.BUY, IndexTrade.quantity),
                    else_=-IndexTrade.quantity,
                )
            ), 0)
        ).filter(IndexTrade.user_id == self._user_id, IndexTrade.ticker == ticker).scalar()
        return float(result)

    def add(self, trade: IndexTrade) -> IndexTrade:
        self._db.add(trade)
        self._db.commit()
        self._db.refresh(trade)
        return trade
