from datetime import date, datetime
from typing import Optional

from sqlalchemy import Float, Index, Integer, String, Date, DateTime, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

import enum


class AppConfig(Base):
    __tablename__ = "app_configs"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class LeveragedEtf(Base):
    __tablename__ = "leveraged_etfs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String, unique=True, index=True)
    underlying: Mapped[str] = mapped_column(String)
    leverage_factor: Mapped[float] = mapped_column(Float)
    name: Mapped[str] = mapped_column(String, nullable=True)


class TradeAction(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_date_id", "executed_at", "id"),
        Index("ix_trades_ticker_date_id", "ticker", "executed_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    action: Mapped[str] = mapped_column(SAEnum(TradeAction))
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[Optional[float]] = mapped_column(Float, nullable=True, server_default="0")
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    executed_at: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
