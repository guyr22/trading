from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from core.config import INDEX_TICKERS_SET
from core.logging import get_logger
from dependencies import get_index_trade_repo
from models import IndexTrade, TradeAction
from repositories.index_trade_repository import IndexTradeRepository
from schemas import TradeCreate, TradeResponse

router = APIRouter()
logger = get_logger(__name__)


@router.post("/api/index-trades", response_model=TradeResponse, status_code=201)
def create_index_trade(
    trade_in: TradeCreate,
    repo: IndexTradeRepository = Depends(get_index_trade_repo),
):
    ticker = trade_in.ticker.upper()

    if ticker not in INDEX_TICKERS_SET:
        raise HTTPException(
            status_code=400,
            detail=f"{ticker} is not a recognised index fund — use POST /api/trades instead",
        )

    if trade_in.action == TradeAction.SELL:
        held = repo.shares_held(ticker)
        if held < trade_in.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot sell {trade_in.quantity} shares of {ticker} — only {held} held",
            )

    trade = IndexTrade(
        action=trade_in.action,
        ticker=ticker,
        quantity=trade_in.quantity,
        price=trade_in.price,
        fees=trade_in.fees,
        platform=trade_in.platform,
        executed_at=trade_in.executed_at or date.today(),
    )
    trade = repo.add(trade)
    logger.info(
        "Index trade recorded  %s %s %s @ $%.2f",
        trade.action, trade.quantity, ticker, trade.price,
    )
    return trade


@router.get("/api/index-trades", response_model=list[TradeResponse])
def list_index_trades(repo: IndexTradeRepository = Depends(get_index_trade_repo)):
    return repo.get_all_desc()
