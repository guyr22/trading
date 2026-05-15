from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from core.config import INDEX_TICKERS_SET
from core.logging import get_logger
from dependencies import get_etf_repo, get_trade_repo
from models import Trade, TradeAction, User
from repositories.etf_repository import EtfRepository
from repositories.trade_repository import TradeRepository
from schemas import TradeCreate, TradeResponse, TradeUpdate

router = APIRouter()
logger = get_logger(__name__)


@router.post("/api/trades", response_model=TradeResponse, status_code=201)
def create_trade(
    trade_in: TradeCreate,
    trade_repo: TradeRepository = Depends(get_trade_repo),
    current_user: User = Depends(get_current_user),
):
    ticker = trade_in.ticker.upper()

    if ticker in INDEX_TICKERS_SET:
        raise HTTPException(
            status_code=400,
            detail=f"{ticker} is an index fund — use POST /api/index-trades instead",
        )

    if trade_in.action == TradeAction.SELL:
        held = trade_repo.shares_held(ticker)
        if held < trade_in.quantity:
            logger.warning(
                "Rejected sell: %s shares of %s requested, only %.4f held",
                trade_in.quantity, ticker, held,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Cannot sell {trade_in.quantity} shares of {ticker} — only {held} held",
            )

    trade = Trade(
        user_id=current_user.id,
        action=trade_in.action,
        ticker=ticker,
        quantity=trade_in.quantity,
        price=trade_in.price,
        fees=trade_in.fees,
        platform=trade_in.platform,
        executed_at=trade_in.executed_at or date.today(),
    )
    trade = trade_repo.add(trade)
    logger.info(
        "Trade recorded  %s %s %s @ $%.2f (fees=$%.2f)",
        trade.action, trade.quantity, ticker, trade.price, trade.fees or 0,
    )
    return trade


@router.get("/api/trades", response_model=list[TradeResponse])
def list_trades(trade_repo: TradeRepository = Depends(get_trade_repo)):
    return trade_repo.get_all_desc()


@router.put("/api/trades/{trade_id}", response_model=TradeResponse)
def update_trade(
    trade_id: int,
    trade_in: TradeUpdate,
    trade_repo: TradeRepository = Depends(get_trade_repo),
):
    trade = trade_repo.get_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    # Build the set of fields to apply (only those explicitly provided)
    updates: dict = {}
    if trade_in.action is not None:
        updates["action"] = trade_in.action
    if trade_in.ticker is not None:
        updates["ticker"] = trade_in.ticker.upper()
    if trade_in.quantity is not None:
        updates["quantity"] = trade_in.quantity
    if trade_in.price is not None:
        updates["price"] = trade_in.price
    if trade_in.fees is not None:
        updates["fees"] = trade_in.fees
    if trade_in.platform is not None:
        updates["platform"] = trade_in.platform
    if trade_in.executed_at is not None:
        updates["executed_at"] = trade_in.executed_at

    # Determine the effective action/ticker/quantity after the update FIRST,
    # so both the lock check and the sell-quantity check use post-edit values.
    effective_action = updates.get("action", trade.action)
    effective_ticker = updates.get("ticker", trade.ticker)
    effective_quantity = updates.get("quantity", trade.quantity)
    effective_executed_at = updates.get("executed_at", trade.executed_at)

    if trade_repo.has_later_opposite_trade(
        effective_ticker, effective_action, effective_executed_at, trade.id
    ):
        logger.warning(
            "Rejected edit of trade %s: a later opposite trade exists for %s",
            trade_id, effective_ticker,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot edit trade {trade_id} — a later "
                f"{'sell' if effective_action == TradeAction.BUY else 'buy'} "
                f"trade exists for {effective_ticker} that depends on it"
            ),
        )

    if effective_action == TradeAction.SELL:
        held = trade_repo.shares_held_excluding(effective_ticker, trade_id)
        if held < effective_quantity:
            logger.warning(
                "Rejected edit of trade %s: sell %s shares of %s but only %.4f held (excluding self)",
                trade_id, effective_quantity, effective_ticker, held,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot sell {effective_quantity} shares of {effective_ticker} "
                    f"— only {held} held (excluding this trade)"
                ),
            )

    trade = trade_repo.update(trade, **updates)
    logger.info(
        "Trade %s updated: %s %s %s @ $%.2f",
        trade.id, trade.action, trade.quantity, trade.ticker, trade.price,
    )
    return trade


@router.delete("/api/trades/{trade_id}", status_code=204)
def delete_trade(
    trade_id: int,
    trade_repo: TradeRepository = Depends(get_trade_repo),
):
    trade = trade_repo.get_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    if trade_repo.has_later_opposite_trade(
        trade.ticker, trade.action, trade.executed_at, trade.id
    ):
        logger.warning(
            "Rejected delete of trade %s: a later opposite trade exists for %s",
            trade_id, trade.ticker,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete trade {trade_id} — a later "
                f"{'sell' if trade.action == TradeAction.BUY else 'buy'} "
                f"trade exists for {trade.ticker} that depends on it"
            ),
        )

    trade_repo.delete(trade)
    logger.info("Trade %s deleted (%s %s %s)", trade_id, trade.action, trade.quantity, trade.ticker)
    # FastAPI returns 204 No Content automatically with no body
