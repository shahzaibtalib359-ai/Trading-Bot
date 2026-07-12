from __future__ import annotations

from backend.models import SignalRequest, SignalResponse
from backend.strategy.signal_engine import SignalEngine


class AdvancedStrategyEngine:
    """Adapter for the advanced technical strategy implementation."""

    def __init__(self) -> None:
        self._engine = SignalEngine()

    def analyze(self, request: SignalRequest, snapshot) -> SignalResponse:
        signal = self._engine.analyze(request, snapshot.candles)
        signal.current_price = round(snapshot.latest_price, 5)
        signal.last_market_update = snapshot.latest_update
        signal.data_source = snapshot.data_source
        return signal
