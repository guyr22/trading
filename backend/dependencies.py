"""FastAPI Depends providers — one place to wire the dependency graph."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from repositories.config_repository import ConfigRepository
from repositories.etf_repository import EtfRepository
from repositories.trade_repository import TradeRepository
from services.analytics_service import AnalyticsService
from services.chat_context_service import ChatContextService
from services.portfolio_service import PortfolioService
from services.price_service import PriceService, get_price_service
from services.statistics_service import StatisticsService


def get_trade_repo(db: Session = Depends(get_db)) -> TradeRepository:
    return TradeRepository(db)


def get_etf_repo(db: Session = Depends(get_db)) -> EtfRepository:
    return EtfRepository(db)


def get_config_repo(db: Session = Depends(get_db)) -> ConfigRepository:
    return ConfigRepository(db)


def get_portfolio_service(
    db: Session = Depends(get_db),
    price_svc: PriceService = Depends(get_price_service),
) -> PortfolioService:
    return PortfolioService(db, price_svc)


def get_statistics_service(
    db: Session = Depends(get_db),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    etf_repo: EtfRepository = Depends(get_etf_repo),
) -> StatisticsService:
    return StatisticsService(db, portfolio_svc, etf_repo)


def get_analytics_service(
    db: Session = Depends(get_db),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    statistics_svc: StatisticsService = Depends(get_statistics_service),
    price_svc: PriceService = Depends(get_price_service),
) -> AnalyticsService:
    return AnalyticsService(db, portfolio_svc, statistics_svc, price_svc)


def get_chat_context_service(
    db: Session = Depends(get_db),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    analytics_svc: AnalyticsService = Depends(get_analytics_service),
) -> ChatContextService:
    return ChatContextService(db, portfolio_svc, analytics_svc)
