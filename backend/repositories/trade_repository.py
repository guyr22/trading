from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from models import Trade, TradeAction
from domain.finance import fifo_full
from repositories.split_repository import SplitRepository


class TradeRepository:
    def __init__(self, db: Session, user_id: int) -> None:
        self._db = db
        self._user_id = user_id

    def _q(self):
        return self._db.query(Trade).filter(Trade.user_id == self._user_id)

    def get_all_ordered(self) -> list[Trade]:
        return self._q().order_by(Trade.executed_at, Trade.id).all()

    def get_all_desc(self) -> list[Trade]:
        return self._q().order_by(Trade.executed_at.desc(), Trade.id.desc()).all()

    def get_by_ticker(self, ticker: str) -> list[Trade]:
        return (
            self._q()
            .filter(Trade.ticker == ticker)
            .order_by(Trade.executed_at, Trade.id)
            .all()
        )

    def get_buy_trades_for_ticker(self, ticker: str) -> list[Trade]:
        return (
            self._q()
            .filter(Trade.ticker == ticker, Trade.action == TradeAction.BUY)
            .order_by(Trade.executed_at, Trade.id)
            .all()
        )

    def get_excluding(self, exclude: set[str] | frozenset[str]) -> list[Trade]:
        return (
            self._q()
            .filter(Trade.ticker.notin_(exclude))
            .order_by(Trade.executed_at, Trade.id)
            .all()
        )

    def get_recent_excluding(self, exclude: set[str] | frozenset[str], limit: int = 20) -> list[Trade]:
        return (
            self._q()
            .filter(Trade.ticker.notin_(exclude))
            .order_by(Trade.executed_at.desc(), Trade.id.desc())
            .limit(limit)
            .all()
        )

    def get_splits(self):
        return SplitRepository(self._db, self._user_id).get_all()

    def get_open_tickers(self) -> list[str]:
        trades = self.get_all_ordered()
        splits = self.get_splits()
        return [ticker for ticker in dict.fromkeys(t.ticker for t in trades)
                if fifo_full(trades, ticker, splits).quantity > 1e-9]

    def shares_held(self, ticker: str) -> float:
        return fifo_full(self.get_by_ticker(ticker), ticker, self.get_splits()).quantity

    def shares_held_on_platform(self, ticker: str, platform: str | None, *,
                                through_date=None, exclude_id=None) -> float:
        trades = [t for t in self.get_by_ticker(ticker)
                  if t.id != exclude_id and (through_date is None or t.executed_at <= through_date)]
        splits = [s for s in self.get_splits()
                  if through_date is None or s.executed_at <= through_date]
        return fifo_full(trades, ticker, splits).quantities_by_platform.get(platform, 0.0)

    def get_count_and_max_id(self) -> tuple[int, int]:
        count, max_id = self._db.query(func.count(Trade.id), func.max(Trade.id)).filter(
            Trade.user_id == self._user_id
        ).one()
        return count or 0, max_id or 0

    def get_by_id(self, trade_id: int) -> Trade | None:
        return self._q().filter(Trade.id == trade_id).first()

    def has_later_opposite_trade(
        self,
        ticker: str,
        action: TradeAction,
        executed_at,
        trade_id: int,
    ) -> bool:
        opposite = TradeAction.SELL if action == TradeAction.BUY else TradeAction.BUY
        return self._q().filter(
            Trade.ticker == ticker,
            Trade.action == opposite,
            or_(
                Trade.executed_at > executed_at,
                and_(
                    Trade.executed_at == executed_at,
                    Trade.id > trade_id,
                ),
            ),
        ).first() is not None

    def shares_held_excluding(self, ticker: str, exclude_id: int) -> float:
        trades = [t for t in self.get_by_ticker(ticker) if t.id != exclude_id]
        return max(fifo_full(trades, ticker, self.get_splits()).quantity, 0.0)

    def shares_held_on_platform_excluding(
        self, ticker: str, platform: str | None, exclude_id: int, *, through_date=None
    ) -> float:
        return max(self.shares_held_on_platform(ticker, platform, through_date=through_date,
                                              exclude_id=exclude_id), 0.0)

    def update(self, trade: Trade, **fields) -> Trade:
        for key, value in fields.items():
            setattr(trade, key, value)
        self._db.commit()
        self._db.refresh(trade)
        return trade

    def delete(self, trade: Trade) -> None:
        self._db.delete(trade)
        self._db.commit()

    def add(self, trade: Trade) -> Trade:
        self._db.add(trade)
        self._db.commit()
        self._db.refresh(trade)
        return trade
