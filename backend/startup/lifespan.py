import os
import traceback
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import inspect, text

from core.config import INDEX_TICKERS_SET
from core.logging import get_logger
from database import SessionLocal, engine
from repositories.etf_repository import EtfRepository
from services.price_service import price_service
from startup.seed_data import SEED_LEVERAGED_ETFS

logger = get_logger(__name__)

_ALEMBIC_INI = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
_INDEX_TICKERS_SQL = ", ".join(f"'{t}'" for t in INDEX_TICKERS_SET)


def _migrate_index_trades_if_needed() -> None:
    """Move any lingering index-ticker rows from trades -> index_trades (one-time, idempotent)."""
    with SessionLocal() as db:
        remaining = db.execute(
            text(f"SELECT COUNT(*) FROM trades WHERE ticker IN ({_INDEX_TICKERS_SQL})")
        ).scalar()
        if not remaining:
            return
        logger.info("Migrating %d index trade(s) from trades -> index_trades", remaining)
        db.execute(text(f"""
            INSERT INTO index_trades (action, ticker, quantity, price, fees, platform, executed_at)
            SELECT action, ticker, quantity, price, fees, platform, executed_at
            FROM trades
            WHERE ticker IN ({_INDEX_TICKERS_SQL})
        """))
        db.execute(text(f"DELETE FROM trades WHERE ticker IN ({_INDEX_TICKERS_SQL})"))
        db.commit()
        logger.info("Index trade migration complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — preparing database schema")
    alembic_cfg = Config(_ALEMBIC_INI)
    existing_tables = inspect(engine).get_table_names()

    if "alembic_version" not in existing_tables and existing_tables:
        # Pre-existing DB created by create_all before Alembic was introduced.
        # Stamp to head without running any migrations.
        logger.info("Existing DB without Alembic tracking — stamping to head")
        command.stamp(alembic_cfg, "head")

    elif "trades" in existing_tables and "index_trades" not in existing_tables:
        # index_trades is missing on an existing DB (Railway upgrade path).
        # Alembic's migration for this table crashes the process silently on
        # Railway — bypass it by creating the table directly with SQLAlchemy
        # (create_type=False on the IndexTrade model prevents re-creating the
        # tradeaction enum that already exists), then stamp to head.
        logger.info("index_trades missing — creating directly and stamping to head")
        from models import IndexTrade
        IndexTrade.__table__.create(bind=engine, checkfirst=True)
        command.stamp(alembic_cfg, "head")
        logger.info("index_trades created and stamped")

    else:
        try:
            command.upgrade(alembic_cfg, "head")
        except BaseException:
            logger.error("Alembic migration failed:\n%s", traceback.format_exc())
            raise

    logger.info("Database ready")

    try:
        _migrate_index_trades_if_needed()
    except Exception:
        logger.error("Index trade data migration failed:\n%s", traceback.format_exc())
        raise

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
