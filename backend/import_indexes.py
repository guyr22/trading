"""Import monthly index purchases from the מדדים spreadsheet.
Does NOT delete existing trades — only inserts the index trades.

Usage (Docker): docker compose exec backend python import_indexes.py
"""

from datetime import datetime
from database import SessionLocal, engine, Base
from models import Trade, TradeAction

Base.metadata.create_all(bind=engine)


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%y").date()


# (ticker, date, shares, price)
INDEX_TRADES = [
    # VOO
    ("VOO", "5.3.26",  0.47, 627.40),
    # QQQ
    ("QQQ", "20.8.25", 9.31, 567.01),
    ("QQQ", "5.9.25",  1.12, 576.35),
    ("QQQ", "6.11.25", 0.76, 613.64),
    ("QQQ", "3.12.25", 1.45, 621.54),
    ("QQQ", "8.1.26",  0.91, 620.57),
    ("QQQ", "6.2.26",  1.46, 600.95),
    ("QQQ", "5.3.26",  1.20, 610.02),
    # IBIT
    ("IBIT", "20.8.25", 33.0, 64.29),
    ("IBIT", "5.9.25",   4.0, 63.11),
    ("IBIT", "3.12.25",  7.0, 52.39),
    ("IBIT", "8.1.26",   4.0, 51.38),
    ("IBIT", "6.2.26",   9.0, 38.66),
    # ETHA
    ("ETHA", "20.8.25", 33.0, 31.78),
    ("ETHA", "5.9.25",   8.0, 32.92),
    ("ETHA", "3.12.25",  7.0, 23.32),
    ("ETHA", "8.1.26",   6.0, 23.42),
    ("ETHA", "6.2.26",  11.0, 14.92),
    # SPY
    ("SPY", "20.8.25", 3.29, 638.66),
    ("SPY", "5.9.25",  0.18, 646.87),
    ("SPY", "3.12.25", 0.52, 682.66),
    ("SPY", "8.1.26",  0.33, 689.98),
    ("SPY", "6.2.26",  0.52, 684.67),
]


def main():
    db = SessionLocal()

    # Remove any previously imported index trades to avoid duplicates
    from sqlalchemy import and_
    index_tickers = {"VOO", "QQQ", "IBIT", "ETHA", "SPY"}
    db.query(Trade).filter(Trade.ticker.in_(index_tickers)).delete(synchronize_session=False)
    db.commit()

    trades = [
        Trade(
            action=TradeAction.BUY,
            ticker=ticker,
            quantity=shares,
            price=price,
            fees=0.0,
            platform=None,
            executed_at=parse_date(date_str),
        )
        for ticker, date_str, shares, price in INDEX_TRADES
    ]

    db.add_all(trades)
    db.commit()
    print(f"Imported {len(trades)} index trades.")
    db.close()


if __name__ == "__main__":
    main()
