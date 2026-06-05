from fastapi import APIRouter, Depends, HTTPException, Query

from core.config import BENCHMARK_TICKERS
from dependencies import get_index_trade_repo, get_portfolio_service, get_statistics_service
from repositories.index_trade_repository import IndexTradeRepository
from schemas import BenchmarkComparison, PortfolioStatistics, PortfolioSummary
from services.portfolio_service import PortfolioService
from services.statistics_service import StatisticsService

router = APIRouter()


@router.get("/api/portfolio", response_model=PortfolioSummary)
def get_portfolio(portfolio_svc: PortfolioService = Depends(get_portfolio_service)):
    return portfolio_svc.build_summary()


@router.get("/api/index-portfolio", response_model=PortfolioSummary)
def get_index_portfolio(
    index_trade_repo: IndexTradeRepository = Depends(get_index_trade_repo),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    trades = index_trade_repo.get_all_ordered()
    return portfolio_svc.build_index_summary(trades)


@router.get("/api/statistics", response_model=PortfolioStatistics)
def get_statistics(statistics_svc: StatisticsService = Depends(get_statistics_service)):
    return statistics_svc.compute()


@router.get("/api/benchmark", response_model=BenchmarkComparison)
def get_benchmark(
    ticker: str = Query("SPY", description="Benchmark index to compare against"),
    statistics_svc: StatisticsService = Depends(get_statistics_service),
):
    normalized = ticker.upper()
    if normalized not in BENCHMARK_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported benchmark '{ticker}'. Choose one of: {', '.join(sorted(BENCHMARK_TICKERS))}.",
        )
    return statistics_svc.compute_benchmark(normalized)
