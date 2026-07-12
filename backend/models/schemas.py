from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class TradingMode(str, Enum):
    forex = "Forex"
    quotex = "Quotex"
    crypto = "Crypto"


class SignalAction(str, Enum):
    buy = "UP"
    sell = "DOWN"
    wait = "WAIT"


class TradeDuration(str, Enum):
    seconds_5 = "5 Seconds"
    seconds_10 = "10 Seconds"
    seconds_15 = "15 Seconds"
    seconds_30 = "30 Seconds"
    minute_1 = "1 Minute"
    minutes_5 = "5 Minutes"
    minutes_15 = "15 Minutes"


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class Tick(BaseModel):
    timestamp: datetime
    price: float
    volume: float = 0.0


class SignalRequest(BaseModel):
    mode: TradingMode
    pair: str = Field(min_length=3, max_length=40)
    duration: TradeDuration
    source_url: str | None = Field(default=None, max_length=500)


class SignalResponse(BaseModel):
    mode: TradingMode
    pair: str
    current_price: float
    signal: SignalAction
    confidence: int = Field(ge=0, le=100)
    duration: TradeDuration
    market_trend: str
    status: str
    analysis: list[str]
    data_source: str = "Binance public live candles"
    data_warning: str | None = None
    last_market_update: datetime | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = (
        "Signals are probabilistic estimates only and do not guarantee profit or winning trades."
    )


class MarketDataRefreshResponse(BaseModel):
    mode: TradingMode
    pair: str
    current_price: float
    data_source: str
    last_market_update: datetime | None = None
    data_warning: str | None = None
    status: str


class HistoryRecord(BaseModel):
    id: int
    created_at: datetime
    mode: TradingMode
    pair: str
    signal: SignalAction
    confidence: int
    duration: TradeDuration
    market_trend: str
    outcome: str | None = None


class OutcomeUpdate(BaseModel):
    outcome: str = Field(pattern="^(WIN|LOSS|BREAKEVEN)$")


class StatisticsResponse(BaseModel):
    total_signals: int
    wins: int
    losses: int
    breakeven: int
    tracked_win_rate: float
    average_confidence: float
