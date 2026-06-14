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


def _ensure_auth_schema() -> None:
    """Create auth tables and user_id columns if they are missing (idempotent).

    Runs after every migration path so that the local Docker case (where we stamp
    instead of running migrations) still gets the auth schema.
    """
    from sqlalchemy import inspect as sa_inspect, text

    inspector = sa_inspect(engine)
    existing = inspector.get_table_names()

    if "users" not in existing:
        from models import User
        User.__table__.create(bind=engine, checkfirst=True)
        logger.info("Created users table")

    if "invites" not in existing:
        from models import Invite
        Invite.__table__.create(bind=engine, checkfirst=True)
        logger.info("Created invites table")

    # Re-inspect after potential table creation
    inspector = sa_inspect(engine)

    trades_cols = {c["name"] for c in inspector.get_columns("trades")}
    if "user_id" not in trades_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE trades ADD COLUMN user_id INTEGER REFERENCES users(id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_user_id ON trades (user_id)"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_trades_user_id_date_id "
                "ON trades (user_id, executed_at, id)"
            ))
        logger.info("Added user_id column to trades")

    if "index_trades" in existing:
        index_cols = {c["name"] for c in inspector.get_columns("index_trades")}
        if "user_id" not in index_cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE index_trades ADD COLUMN user_id INTEGER REFERENCES users(id)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_index_trades_user_id ON index_trades (user_id)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_index_trades_user_id_date_id "
                    "ON index_trades (user_id, executed_at, id)"
                ))
            logger.info("Added user_id column to index_trades")


def _ensure_chat_schema() -> None:
    """Create chat_conversations table if missing (idempotent)."""
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(engine)
    if "chat_conversations" not in inspector.get_table_names():
        from models import ChatConversation
        ChatConversation.__table__.create(bind=engine, checkfirst=True)
        logger.info("Created chat_conversations table")


def _ensure_alerts_schema() -> None:
    """Create price_alerts / push_subscriptions tables if missing (idempotent).

    Production pins a logical Alembic head and skips migrations, so — like the
    auth and chat tables — the alert tables are also created defensively here.
    """
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(engine)
    existing = inspector.get_table_names()
    if "price_alerts" not in existing:
        from models import PriceAlert
        PriceAlert.__table__.create(bind=engine, checkfirst=True)
        logger.info("Created price_alerts table")
    if "push_subscriptions" not in existing:
        from models import PushSubscription
        PushSubscription.__table__.create(bind=engine, checkfirst=True)
        logger.info("Created push_subscriptions table")


def _ensure_admin_user() -> None:
    """Create the admin user from env vars on first startup and assign orphaned trades to them."""
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()

    if not admin_email or not admin_password:
        logger.warning(
            "ADMIN_EMAIL / ADMIN_PASSWORD not set — skipping admin user creation. "
            "Set these env vars to enable login."
        )
        return

    from auth.utils import hash_password
    from models import User

    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == admin_email).first()
        if existing:
            admin_id = existing.id
            logger.info("Admin user already exists: %s (id=%d)", admin_email, admin_id)
        else:
            admin = User(
                email=admin_email,
                password_hash=hash_password(admin_password),
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            admin_id = admin.id
            logger.info("Admin user created: %s (id=%d)", admin_email, admin_id)

        # Assign all orphaned trades (user_id IS NULL) to the admin user.
        orphaned_trades = db.execute(
            text("SELECT COUNT(*) FROM trades WHERE user_id IS NULL")
        ).scalar() or 0
        orphaned_index = db.execute(
            text("SELECT COUNT(*) FROM index_trades WHERE user_id IS NULL")
        ).scalar() or 0

        if orphaned_trades:
            db.execute(text(f"UPDATE trades SET user_id = {admin_id} WHERE user_id IS NULL"))
            logger.info("Assigned %d orphaned trade(s) to admin (id=%d)", orphaned_trades, admin_id)

        if orphaned_index:
            db.execute(text(f"UPDATE index_trades SET user_id = {admin_id} WHERE user_id IS NULL"))
            logger.info("Assigned %d orphaned index trade(s) to admin (id=%d)", orphaned_index, admin_id)

        if orphaned_trades or orphaned_index:
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — preparing database schema")
    alembic_cfg = Config(_ALEMBIC_INI)
    existing_tables = inspect(engine).get_table_names()

    # Create auth tables first — other tables (e.g. index_trades) now FK to users.
    if "users" not in existing_tables:
        from models import User, Invite
        User.__table__.create(bind=engine, checkfirst=True)
        Invite.__table__.create(bind=engine, checkfirst=True)
        existing_tables = inspect(engine).get_table_names()
        logger.info("Auth tables pre-created before migration paths")

    # Read the current Alembic version (if any) to decide the migration path.
    _HEAD = "b2c3d4e5f6a7"
    _current_version: str | None = None
    if "alembic_version" in existing_tables:
        with engine.connect() as _conn:
            _current_version = _conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()

    if "alembic_version" not in existing_tables and existing_tables:
        # Pre-existing DB without Alembic tracking — stamp by direct SQL insert.
        logger.info("Existing DB without Alembic tracking — stamping to head directly")
        with engine.begin() as _conn:
            _conn.execute(text(
                "INSERT INTO alembic_version (version_num) VALUES (:v) "
                "ON CONFLICT DO NOTHING"
            ), {"v": _HEAD})

    elif "trades" in existing_tables and "index_trades" not in existing_tables:
        # index_trades is missing on an existing DB (Railway upgrade path).
        logger.info("index_trades missing — creating directly and stamping to head")
        from models import IndexTrade
        IndexTrade.__table__.create(bind=engine, checkfirst=True)
        with engine.begin() as _conn:
            _conn.execute(text(
                "UPDATE alembic_version SET version_num = :v"
            ), {"v": _HEAD})
        logger.info("index_trades created and version stamped")

    elif _current_version == _HEAD:
        # Already at head — nothing to do, skip all Alembic commands.
        logger.info("Database already at head revision %s — skipping Alembic", _HEAD)

    elif _current_version in ("e920117ef5cf", "a1b2c3d4e5f6"):
        # Known older versions — bypass hanging Alembic migrations, stamp to head directly.
        # _ensure_auth_schema() and _ensure_chat_schema() apply the actual DDL.
        logger.info("Bypassing Alembic migration from %s — updating version directly", _current_version)
        with engine.begin() as _conn:
            _conn.execute(text(
                "UPDATE alembic_version SET version_num = :v"
            ), {"v": _HEAD})
        logger.info("Alembic version updated to %s", _HEAD)

    else:
        try:
            command.upgrade(alembic_cfg, "head")
        except BaseException:
            logger.error("Alembic migration failed:\n%s", traceback.format_exc())
            raise

    logger.info("Database ready")

    try:
        _ensure_auth_schema()
    except Exception:
        logger.error("Auth schema setup failed:\n%s", traceback.format_exc())
        raise

    try:
        _ensure_chat_schema()
    except Exception:
        logger.error("Chat schema setup failed:\n%s", traceback.format_exc())
        raise

    try:
        _ensure_alerts_schema()
    except Exception:
        logger.error("Alerts schema setup failed:\n%s", traceback.format_exc())
        raise

    try:
        _migrate_index_trades_if_needed()
    except Exception:
        logger.error("Index trade data migration failed:\n%s", traceback.format_exc())
        raise

    try:
        _ensure_admin_user()
    except Exception:
        logger.error("Admin user setup failed:\n%s", traceback.format_exc())
        raise

    with SessionLocal() as db:
        deleted = db.execute(text("DELETE FROM app_configs WHERE key = 'ta_system_prompt'"))
        if deleted.rowcount:
            db.commit()
            logger.info("Removed ta_system_prompt from app_configs")

    with SessionLocal() as db:
        etf_repo = EtfRepository(db)
        for entry in SEED_LEVERAGED_ETFS:
            if not etf_repo.find_by_ticker(entry["ticker"]):
                from models import LeveragedEtf
                db.add(LeveragedEtf(**entry))
        db.commit()
    logger.info("Leveraged ETF seed complete")

    price_service.start_background_refresh(SessionLocal)

    from services.alert_checker import alert_checker
    alert_checker.start(SessionLocal)

    yield

    logger.info("Shutting down — stopping background threads")
    price_service.stop_background_refresh()
    alert_checker.stop()
