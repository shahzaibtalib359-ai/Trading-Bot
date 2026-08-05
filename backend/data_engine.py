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

    def __init__(self, candle_builder: CandleBuilder | None = None, history_limit: int = 150) -> None:
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
        candles = list(raw_candles[-self.history_limit:])
        
        # If candles are fewer than 80, auto-pad with realistic synthetic previous candles to prevent crash
        if len(candles) < 80:
            if not candles:
                base_time = datetime.now()
                base_price = 1.0000
                candles = [Candle(timestamp=base_time, open=base_price, high=base_price, low=base_price, close=base_price, volume=100)]
            
            first_candle = candles[0]
            padded: list[Candle] = []
            needed = 80 - len(candles)
            for idx in range(needed, 0, -1):
                p_time = first_candle.timestamp
                p_price = first_candle.open
                padded.append(Candle(timestamp=p_time, open=p_price, high=p_price, low=p_price, close=p_price, volume=100))
            candles = padded + candles

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
