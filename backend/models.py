from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Date, DateTime, Enum as SAEnum, func
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


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    used_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TradeAction(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_date_id", "executed_at", "id"),
        Index("ix_trades_ticker_date_id", "ticker", "executed_at", "id"),
        Index("ix_trades_user_id_date_id", "user_id", "executed_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(SAEnum(TradeAction))
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[Optional[float]] = mapped_column(Float, nullable=True, server_default="0")
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    executed_at: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=lambda: datetime.now())


class IndexTrade(Base):
    __tablename__ = "index_trades"
    __table_args__ = (
        Index("ix_index_trades_ticker_date_id", "ticker", "executed_at", "id"),
        Index("ix_index_trades_user_id_date_id", "user_id", "executed_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(SAEnum(TradeAction, create_type=False))
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[Optional[float]] = mapped_column(Float, nullable=True, server_default="0")
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    executed_at: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=lambda: datetime.now())
