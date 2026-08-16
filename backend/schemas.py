from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from models import AlertCondition, TradeAction


class TradeCreate(BaseModel):
    action: TradeAction
    ticker: str = Field(..., min_length=1, max_length=10)
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    fees: float = 0.0
    platform: Optional[str] = None
    executed_at: Optional[date] = None


class TradeUpdate(BaseModel):
    action: Optional[TradeAction] = None
    ticker: Optional[str] = Field(default=None, min_length=1, max_length=10)
    quantity: Optional[float] = Field(default=None, gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    fees: Optional[float] = None
    platform: Optional[str] = None
    executed_at: Optional[date] = None


class TradeResponse(BaseModel):
    id: int
    action: TradeAction
    ticker: str
    quantity: float
    price: float
    fees: float = 0.0
    platform: Optional[str] = None
    executed_at: date
    created_at: datetime

    model_config = {"from_attributes": True}


class LeveragedEtfCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    underlying: str = Field(..., min_length=1, max_length=10)
    leverage_factor: float
    name: Optional[str] = None


class LeveragedEtfResponse(BaseModel):
    id: int
    ticker: str
    underlying: str
    leverage_factor: float
    name: Optional[str] = None

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    leveraged_underlying: Optional[str] = None
    leverage_factor: Optional[float] = None


class PortfolioSummary(BaseModel):
    total_market_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    positions: list[PositionResponse]


class ClosedLotResponse(BaseModel):
    ticker: str
    open_date: date
    close_date: date
    quantity: float
    cost_basis: float
    avg_buy_price: float
    avg_sell_price: float
    pnl: float
    pnl_pct: float


class TickerStat(BaseModel):
    ticker: str
    realized_pnl: float
    total_fees: float
    win_rate: float
    trades_count: int


class MonthlyPnl(BaseModel):
    month: str
    realized_pnl: float


class CumulativePoint(BaseModel):
    date: str
    cumulative_pnl: float


class BenchmarkPoint(BaseModel):
    date: str
    your_pnl: float
    benchmark_pnl: float


class BenchmarkComparison(BaseModel):
    benchmark_ticker: str
    your_realized_pnl: float       # your cumulative realized P&L on closed lots
    benchmark_pnl: float           # what the same capital made in the benchmark over the same holding windows
    alpha: float                   # your_realized_pnl - benchmark_pnl
    lots_total: int                # number of closed lots compared
    lots_beat: int                 # closed lots whose return beat the benchmark over the same window
    beat_rate: float               # lots_beat / lots_total as a percentage
    cumulative: list[BenchmarkPoint]
    available: bool                # False when there are no closed lots or price data could not be fetched


class AlertCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    condition: AlertCondition
    target_price: float = Field(..., gt=0)
    note: Optional[str] = Field(default=None, max_length=200)


class AlertUpdate(BaseModel):
    # Used to pause/resume or re-arm a one-shot alert.
    active: bool


class AlertResponse(BaseModel):
    id: int
    ticker: str
    condition: AlertCondition
    target_price: float
    note: Optional[str] = None
    active: bool
    current_price: Optional[float] = None
    triggered_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushKeys


class VapidKeyResponse(BaseModel):
    public_key: Optional[str] = None
    enabled: bool


class PortfolioStatistics(BaseModel):
    total_pnl: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    best_trade: float
    worst_trade: float
    max_drawdown: float
    avg_holding_days: float
    largest_position_pct: float
    total_trades: int
    total_fees: float
    avg_fees_per_trade: float
    most_traded_ticker: str
    ticker_stats: list[TickerStat]
    monthly_pnl: list[MonthlyPnl]
    cumulative_pnl: list[CumulativePoint]
    closed_lots: list[ClosedLotResponse]
