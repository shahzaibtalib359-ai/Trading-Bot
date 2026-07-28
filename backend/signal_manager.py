"""
Signal Manager — Fast Single-Pass Analysis System
===================================================
Fast and responsive signal generation using all 11 technical indicators
in a single pass. Optimized for speed while maintaining accuracy.

- Single data fetch → instant analysis → immediate signal
- All 11 indicators still applied (EMA, RSI, MACD, ADX, etc.)
- No confirmation delay — faster signals, more UP/DOWN results
"""
from __future__ import annotations

import logging

from backend.data_engine import LiveMarketDataEngine
from backend.models import SignalRequest, SignalResponse
from backend.strategy.signal_engine import SignalEngine

logger = logging.getLogger(__name__)


class SignalManager:
    """
    Fast single-pass signal generator.
    Fetches market data once, runs full 11-indicator analysis, returns result immediately.
    """

    def __init__(
        self,
        data_engine: LiveMarketDataEngine | None = None,
        signal_engine: SignalEngine | None = None,
    ) -> None:
        self.data_engine   = data_engine   or LiveMarketDataEngine()
        self.signal_engine = signal_engine or SignalEngine()

    async def generate(self, request: SignalRequest) -> SignalResponse:
        """
        Generate a signal using single-pass market analysis.
        Fast, responsive, uses all 11 indicators.
        """
        # ── Single Pass ──────────────────────────────────────────────────
        snapshot = await self.data_engine.snapshot(request)
        response = self.signal_engine.analyze(request, snapshot.candles)

        # Enrich with live market data
        try:
            response.current_price      = round(snapshot.latest_price, 5)
            response.data_source        = snapshot.data_source
            response.last_market_update = snapshot.latest_update
            response.data_warning       = snapshot.data_warning
        except Exception:
            pass

        logger.info(
            "[Signal] %s — %s | %s | conf=%s%%",
            response.signal.value, request.pair, request.mode.value, response.confidence,
        )

        return response


# Global singleton used by the API routes
signal_manager = SignalManager()
