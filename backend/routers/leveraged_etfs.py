from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from core.logging import get_logger
from dependencies import get_etf_repo
from models import LeveragedEtf
from repositories.etf_repository import EtfRepository
from schemas import LeveragedEtfCreate, LeveragedEtfResponse

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = get_logger(__name__)


@router.get("/api/leveraged-etfs", response_model=list[LeveragedEtfResponse])
def list_leveraged_etfs(etf_repo: EtfRepository = Depends(get_etf_repo)):
    return etf_repo.get_all_ordered()


@router.post("/api/leveraged-etfs", response_model=LeveragedEtfResponse, status_code=201)
def create_leveraged_etf(
    etf_in: LeveragedEtfCreate,
    etf_repo: EtfRepository = Depends(get_etf_repo),
):
    ticker = etf_in.ticker.upper()
    underlying = etf_in.underlying.upper()
    if etf_repo.find_by_ticker(ticker):
        raise HTTPException(status_code=409, detail=f"{ticker} is already mapped")
    etf = etf_repo.add(LeveragedEtf(
        ticker=ticker,
        underlying=underlying,
        leverage_factor=etf_in.leverage_factor,
        name=etf_in.name,
    ))
    logger.info("Leveraged ETF added  %s → %s (%.1fx)", ticker, underlying, etf_in.leverage_factor)
    return etf


@router.delete("/api/leveraged-etfs/{ticker}", status_code=204)
def delete_leveraged_etf(
    ticker: str,
    etf_repo: EtfRepository = Depends(get_etf_repo),
):
    ticker = ticker.upper()
    etf = etf_repo.find_by_ticker(ticker)
    if not etf:
        raise HTTPException(status_code=404, detail=f"{ticker} not found")
    etf_repo.delete(etf)
    logger.info("Leveraged ETF removed  %s", ticker)
