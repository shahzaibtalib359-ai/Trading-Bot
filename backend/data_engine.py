from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.candle_builder import CandleBuilder, duration_to_seconds
from backend.models import Candle, SignalRequest, TradingMode
from backend.services import describe_market_provider, get_market_provider
from backend.services.market_data import binance_symbol


@dataclass(frozen=True)
class MarketSnapshot:
    candles: list[Candle]
    pair: str
    mode: TradingMode
    timeframe_seconds: int
    latest_update: datetime
    latest_price: float
    fingerprint: str
    data_source: str
    data_warning: str | None = None


class LiveMarketDataEngine:
    """Fetches fresh 1-minute market candles on every request."""

    def __init__(self, candle_builder: CandleBuilder | None = None, history_limit: int = 300) -> None:
        self.candle_builder = candle_builder or CandleBuilder()
        self.history_limit = history_limit

    async def snapshot(self, request: SignalRequest) -> MarketSnapshot:
        provider = get_market_provider()
        raw_candles = await provider.get_candles(
            request.mode,
            request.pair,
            limit=self.history_limit,
            source_url=request.source_url,
        )
        timeframe_seconds = 60  # 1-minute candles
        candles = raw_candles[-self.history_limit:]
        if len(candles) < 80:
            raise RuntimeError("Market data returned too few candles for deep analysis (need at least 80).")

        # Detect stale / flat candle data (all closes identical = closed market or bad data source)
        unique_closes = len(set(round(c.close, 8) for c in candles[-20:]))
        if unique_closes <= 2:
            raise RuntimeError(
                f"Market data for '{request.pair}' is stale or flat "
                f"(only {unique_closes} unique close values in last 20 candles). "
                f"The market may be closed or the data source is unavailable."
            )

        # Build data_warning only when Binance is used DIRECTLY for a Quotex/Forex pair
        # (AutoMarketDataProviderRouter delegates to QuotexMarketDataProvider → Yahoo Finance
        #  for forex OTC, so no proxy warning is needed when provider_id is "auto" or "quotex")
        data_warning: str | None = None
        provider_id = getattr(provider, "provider_id", "")
        if request.mode in (TradingMode.quotex, TradingMode.forex) and provider_id == "binance":
            proxy_sym = binance_symbol(request.pair)
            data_warning = (
                f"No live {request.mode.value} feed configured. "
                f"Signal is based on Binance proxy asset '{proxy_sym}' (1-min candles). "
                f"Use with caution."
            )

        latest = candles[-1]
        return MarketSnapshot(
            candles=candles[-self.history_limit:],
            pair=request.pair,
            mode=request.mode,
            timeframe_seconds=timeframe_seconds,
            latest_update=latest.timestamp,
            latest_price=latest.close,
            fingerprint=self.candle_builder.fingerprint(candles),
            data_source=describe_market_provider(provider),
            data_warning=data_warning,
        )
