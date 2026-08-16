"""FastAPI Depends providers — one place to wire the dependency graph."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database import get_db
from models import User
from repositories.etf_repository import EtfRepository
from repositories.index_trade_repository import IndexTradeRepository
from repositories.push_repository import PushSubscriptionRepository
from repositories.trade_repository import TradeRepository
from services.alert_service import AlertService
from services.portfolio_service import PortfolioService
from services.price_service import PriceService, get_price_service
from services.statistics_service import StatisticsService


def get_trade_repo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TradeRepository:
    return TradeRepository(db, current_user.id)


def get_index_trade_repo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IndexTradeRepository:
    return IndexTradeRepository(db, current_user.id)


def get_etf_repo(db: Session = Depends(get_db)) -> EtfRepository:
    return EtfRepository(db)


def get_portfolio_service(
    db: Session = Depends(get_db),
    price_svc: PriceService = Depends(get_price_service),
    current_user: User = Depends(get_current_user),
) -> PortfolioService:
    return PortfolioService(db, price_svc, current_user.id)


def get_statistics_service(
    db: Session = Depends(get_db),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    etf_repo: EtfRepository = Depends(get_etf_repo),
    price_svc: PriceService = Depends(get_price_service),
    current_user: User = Depends(get_current_user),
) -> StatisticsService:
    return StatisticsService(db, portfolio_svc, etf_repo, price_svc, current_user.id)


def get_alert_service(
    db: Session = Depends(get_db),
    price_svc: PriceService = Depends(get_price_service),
    current_user: User = Depends(get_current_user),
) -> AlertService:
    return AlertService(db, price_svc, current_user.id)


def get_push_repo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PushSubscriptionRepository:
    return PushSubscriptionRepository(db, current_user.id)
