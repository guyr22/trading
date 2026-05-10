from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.logging import get_logger
from database import Base, SessionLocal, engine
from repositories.etf_repository import EtfRepository
from services.price_service import price_service
from startup.seed_data import SEED_LEVERAGED_ETFS

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating database tables if needed")
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready")

    with SessionLocal() as db:
        etf_repo = EtfRepository(db)
        for entry in SEED_LEVERAGED_ETFS:
            if not etf_repo.find_by_ticker(entry["ticker"]):
                from models import LeveragedEtf
                db.add(LeveragedEtf(**entry))
        db.commit()
    logger.info("Leveraged ETF seed complete")

    price_service.start_background_refresh(SessionLocal)

    yield

    logger.info("Shutting down — stopping price refresh thread")
    price_service.stop_background_refresh()
