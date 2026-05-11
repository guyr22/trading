"""
Copies all data from the local Docker database to Railway (or any other target DB).

Usage (from inside the backend container):
    docker compose exec -e DEST_DATABASE_URL=<railway-postgres-url> backend python migrate_to_railway.py

The script reads from DATABASE_URL (already set in the container) and writes to DEST_DATABASE_URL.
It clears the destination tables before inserting, so re-running is safe.
"""

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Trade, AppConfig, LeveragedEtf

SOURCE_URL = os.environ.get("DATABASE_URL")
DEST_URL = os.environ.get("DEST_DATABASE_URL")

if not SOURCE_URL:
    sys.exit("ERROR: DATABASE_URL is not set (should already be present in the container).")
if not DEST_URL:
    sys.exit("ERROR: DEST_DATABASE_URL is not set. Pass it via -e DEST_DATABASE_URL=<url>.")

src_engine = create_engine(SOURCE_URL)
dst_engine = create_engine(DEST_URL)

Base.metadata.create_all(bind=dst_engine)

SrcSession = sessionmaker(bind=src_engine)
DstSession = sessionmaker(bind=dst_engine)

src = SrcSession()
dst = DstSession()

try:
    # --- trades ---
    trades = src.query(Trade).order_by(Trade.id).all()
    dst.query(Trade).delete()
    dst.commit()
    for t in trades:
        dst.merge(Trade(
            id=t.id,
            action=t.action,
            ticker=t.ticker,
            quantity=t.quantity,
            price=t.price,
            fees=t.fees,
            platform=t.platform,
            executed_at=t.executed_at,
            created_at=t.created_at,
        ))
    dst.commit()
    print(f"Trades:          {len(trades)} rows copied")

    # --- app_configs ---
    configs = src.query(AppConfig).all()
    dst.query(AppConfig).delete()
    dst.commit()
    for c in configs:
        dst.merge(AppConfig(key=c.key, value=c.value))
    dst.commit()
    print(f"AppConfigs:      {len(configs)} rows copied")

    # --- leveraged_etfs ---
    etfs = src.query(LeveragedEtf).all()
    dst.query(LeveragedEtf).delete()
    dst.commit()
    for e in etfs:
        dst.merge(LeveragedEtf(
            id=e.id,
            ticker=e.ticker,
            underlying=e.underlying,
            leverage_factor=e.leverage_factor,
            name=e.name,
        ))
    dst.commit()
    print(f"LeveragedEtfs:   {len(etfs)} rows copied")

    # reset sequences so new inserts don't collide with copied IDs
    with dst_engine.connect() as conn:
        for table, col in [("trades", "id"), ("leveraged_etfs", "id")]:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                f"COALESCE(MAX({col}), 0) + 1, false) FROM {table}"
            ))
        conn.commit()

    print("Done. Sequences reset.")

finally:
    src.close()
    dst.close()