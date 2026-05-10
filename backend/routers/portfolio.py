from fastapi import APIRouter, Depends

from dependencies import get_portfolio_service, get_statistics_service
from schemas import PortfolioStatistics, PortfolioSummary
from services.portfolio_service import PortfolioService
from services.statistics_service import StatisticsService

router = APIRouter()


@router.get("/api/portfolio", response_model=PortfolioSummary)
def get_portfolio(portfolio_svc: PortfolioService = Depends(get_portfolio_service)):
    return portfolio_svc.build_summary()


@router.get("/api/statistics", response_model=PortfolioStatistics)
def get_statistics(statistics_svc: StatisticsService = Depends(get_statistics_service)):
    return statistics_svc.compute()
