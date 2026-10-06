import math

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from core.config import INDEX_TICKERS_SET
from database import get_db
from domain.finance import fifo_full
from domain.validation import introduces_oversell
from models import StockSplit, User
from repositories.index_trade_repository import IndexTradeRepository
from repositories.split_repository import SplitRepository
from repositories.trade_repository import TradeRepository
from schemas import StockSplitCreate, StockSplitResponse

router = APIRouter()


def ticker_trades(db, user_id, ticker):
    repo = IndexTradeRepository(db, user_id) if ticker in INDEX_TICKERS_SET else TradeRepository(db, user_id)
    return [t for t in repo.get_all_ordered() if t.ticker == ticker]


@router.get("/api/splits", response_model=list[StockSplitResponse])
def list_splits(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(reversed(SplitRepository(db, user.id).get_all()))


@router.post("/api/splits", response_model=StockSplitResponse, status_code=201)
def create_split(split_in: StockSplitCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repo = SplitRepository(db, user.id)
    splits = repo.get_all()
    ticker = split_in.ticker
    if any(s.ticker == ticker and s.executed_at == split_in.executed_at for s in splits):
        raise HTTPException(status_code=409, detail="A split is already recorded for this ticker and date")
    trades = ticker_trades(db, user.id, ticker)
    prior = fifo_full([t for t in trades if t.executed_at < split_in.executed_at], ticker,
                      [s for s in splits if s.executed_at < split_in.executed_at])
    if not any(abs(qty) > 1e-9 for qty in prior.quantities_by_platform.values()):
        raise HTTPException(status_code=400, detail=f"No {ticker} shares were held before the split date")
    split = StockSplit(user_id=user.id, **split_in.model_dump())
    updated = splits + [split]
    result = fifo_full(trades, ticker, updated)
    if not math.isfinite(result.quantity) or not math.isfinite(result.avg_cost):
        raise HTTPException(status_code=400, detail="Split ratio is too large or too small for these holdings")
    if introduces_oversell(trades, splits, trades, updated, ticker):
        raise HTTPException(status_code=409, detail="This split would leave a recorded sale with insufficient shares on its platform")
    try:
        return repo.add(split)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A split is already recorded for this ticker and date")


@router.delete("/api/splits/{split_id}", status_code=204)
def delete_split(split_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repo = SplitRepository(db, user.id)
    split = repo.get_by_id(split_id)
    if split is None:
        raise HTTPException(status_code=404, detail="Split not found")
    trades = ticker_trades(db, user.id, split.ticker)
    splits = repo.get_all()
    if introduces_oversell(trades, splits, trades, [s for s in splits if s.id != split_id], split.ticker):
        raise HTTPException(status_code=409, detail="Cannot remove this split: a recorded sale depends on the additional shares")
    repo.delete(split)
