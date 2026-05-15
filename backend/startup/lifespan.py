import os
import traceback
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import inspect

from core.logging import get_logger
from database import SessionLocal, engine
from repositories.etf_repository import EtfRepository
from services.price_service import price_service
from startup.seed_data import SEED_LEVERAGED_ETFS

logger = get_logger(__name__)

_ALEMBIC_INI = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — running Alembic migrations")
    alembic_cfg = Config(_ALEMBIC_INI)
    existing_tables = inspect(engine).get_table_names()
    if "alembic_version" not in existing_tables and existing_tables:
        # Pre-existing database (created by create_all before Alembic was added).
        # Stamp to head so future migrations run incrementally without re-creating tables.
        logger.info("Existing DB without Alembic tracking — stamping to head")
        command.stamp(alembic_cfg, "head")
    else:
        try:
            command.upgrade(alembic_cfg, "head")
        except Exception:
            logger.error("Alembic migration failed:\n%s", traceback.format_exc())
            raise
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
