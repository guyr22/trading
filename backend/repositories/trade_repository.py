from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models import Trade, TradeAction


class TradeRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all_ordered(self) -> list[Trade]:
        return self._db.query(Trade).order_by(Trade.executed_at, Trade.id).all()

    def get_all_desc(self) -> list[Trade]:
        return self._db.query(Trade).order_by(Trade.executed_at.desc(), Trade.id.desc()).all()

    def get_by_ticker(self, ticker: str) -> list[Trade]:
        return (
            self._db.query(Trade)
            .filter(Trade.ticker == ticker)
            .order_by(Trade.executed_at, Trade.id)
            .all()
        )

    def get_buy_trades_for_ticker(self, ticker: str) -> list[Trade]:
        return (
            self._db.query(Trade)
            .filter(Trade.ticker == ticker, Trade.action == TradeAction.BUY)
            .order_by(Trade.executed_at, Trade.id)
            .all()
        )

    def get_excluding(self, exclude: set[str] | frozenset[str]) -> list[Trade]:
        return (
            self._db.query(Trade)
            .filter(Trade.ticker.notin_(exclude))
            .order_by(Trade.executed_at, Trade.id)
            .all()
        )

    def get_recent_excluding(self, exclude: set[str] | frozenset[str], limit: int = 20) -> list[Trade]:
        return (
            self._db.query(Trade)
            .filter(Trade.ticker.notin_(exclude))
            .order_by(Trade.executed_at.desc(), Trade.id.desc())
            .limit(limit)
            .all()
        )

    def get_open_tickers(self) -> list[str]:
        """Return tickers that still have a net-positive quantity."""
        rows = self._db.query(
            Trade.ticker,
            func.sum(
                case(
                    (Trade.action == TradeAction.BUY, Trade.quantity),
                    else_=-Trade.quantity,
                )
            ).label("net_qty"),
        ).group_by(Trade.ticker).all()
        return [row.ticker for row in rows if (row.net_qty or 0) > 0]

    def shares_held(self, ticker: str) -> float:
        result = self._db.query(
            func.coalesce(func.sum(
                case(
                    (Trade.action == TradeAction.BUY, Trade.quantity),
                    else_=-Trade.quantity,
                )
            ), 0)
        ).filter(Trade.ticker == ticker).scalar()
        return float(result)

    def get_count_and_max_id(self) -> tuple[int, int]:
        count, max_id = self._db.query(func.count(Trade.id), func.max(Trade.id)).one()
        return count or 0, max_id or 0

    def get_by_id(self, trade_id: int) -> Trade | None:
        return self._db.query(Trade).filter(Trade.id == trade_id).first()

    def has_later_opposite_trade(
        self,
        ticker: str,
        action: TradeAction,
        executed_at,
        trade_id: int,
    ) -> bool:
        """Return True if a trade of the opposite action exists for the same ticker
        at a later position (executed_at > executed_at, or same date with id > trade_id).
        """
        opposite = TradeAction.SELL if action == TradeAction.BUY else TradeAction.BUY
        from sqlalchemy import or_, and_
        return self._db.query(Trade).filter(
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
        """Compute net shares held for a ticker, excluding a specific trade id.

        Clamped to 0.0 so that net-short scenarios never produce a negative
        value that would cause spurious SELL rejections.
        """
        result = self._db.query(
            func.coalesce(func.sum(
                case(
                    (Trade.action == TradeAction.BUY, Trade.quantity),
                    else_=-Trade.quantity,
                )
            ), 0)
        ).filter(Trade.ticker == ticker, Trade.id != exclude_id).scalar()
        return max(float(result), 0.0)

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
