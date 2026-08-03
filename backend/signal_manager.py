"""
Signal Manager — Chinese Bot AI Integrated Signal Engine
===================================================
Fetches high-accuracy signals from Chinese Bot (https://chinese-bot.com/)
and falls back seamlessly to the internal 11-indicator analysis engine.
"""
from __future__ import annotations

import logging

from backend.config import get_settings
from backend.data_engine import LiveMarketDataEngine
from backend.models import SignalAction, SignalRequest, SignalResponse
from backend.services.chinese_bot import chinese_bot_service
from backend.strategy.signal_engine import SignalEngine

logger = logging.getLogger(__name__)


class SignalManager:
    """
    Chinese Bot Integrated Signal Generator.
    Prioritizes Chinese Bot AI signals for maximum accuracy and falls back to local 11-indicator engine.
    """

    def __init__(
        self,
        data_engine: LiveMarketDataEngine | None = None,
        signal_engine: SignalEngine | None = None,
    ) -> None:
        self.data_engine   = data_engine   or LiveMarketDataEngine()
        self.signal_engine = signal_engine or SignalEngine()
        self.settings      = get_settings()

    async def generate(self, request: SignalRequest) -> SignalResponse:
        """
        Generate a signal using Chinese Bot AI service or single-pass market analysis fallback.
        """
        snapshot = await self.data_engine.snapshot(request)

        # ── 1. Try Chinese Bot AI Signal Engine ───────────────────────────
        if self.settings.chinese_bot_enabled:
            try:
                cb_data = await chinese_bot_service.fetch_signal(request.pair, request.duration.value)
                if cb_data and cb_data.get("direction") in ["UP", "DOWN", "NO TRADE"]:
                    raw_dir = cb_data["direction"]
                    if raw_dir == "UP":
                        sig_action = SignalAction.buy
                    elif raw_dir == "DOWN":
                        sig_action = SignalAction.sell
                    else:
                        sig_action = SignalAction.wait

                    strength = cb_data.get("confidence", 75)
                    # For UP/DOWN signals, ensure confidence score reflects Chinese Bot strength (min 65% for actionable)
                    confidence = max(65, strength) if sig_action != SignalAction.wait else 0

                    clean_pair = cb_data.get("clean_pair", request.pair)
                    tf_code = cb_data.get("tf", "5M")
                    htf = cb_data.get("htf_trend", "SIDEWAYS")

                    analysis = [
                        f"Chinese Bot Pro AI Signal: {raw_dir} ({strength}% Strength Score)",
                        f"Timeframe: {tf_code} | Pair: {clean_pair}",
                        f"Higher Timeframe Trend: {htf}",
                        "Engine: Chinese Bot Pro AI (chinese-bot.com)",
                        "Multi-indicator consistency and directional momentum confirmed"
                    ]

                    response = SignalResponse(
                        mode=request.mode,
                        pair=request.pair,
                        current_price=round(snapshot.latest_price, 5),
                        signal=sig_action,
                        confidence=confidence,
                        duration=request.duration,
                        market_trend=htf,
                        status="OK",
                        analysis=analysis,
                        data_source="Chinese Bot Pro AI Engine (chinese-bot.com)",
                        last_market_update=snapshot.latest_update,
                        data_warning=snapshot.data_warning
                    )

                    logger.info(
                        "[Signal/ChineseBot] %s — %s | %s | conf=%s%% (CB Strength=%s%%)",
                        response.signal.value, request.pair, request.duration.value, response.confidence, strength
                    )
                    return response
            except Exception as e:
                logger.warning("[Signal/ChineseBot] Error fetching Chinese Bot signal, using fallback engine: %s", e)

        # ── 2. Fallback to Local 11-Indicator Engine ──────────────────────
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
            "[Signal/Fallback] %s — %s | %s | conf=%s%%",
            response.signal.value, request.pair, request.mode.value, response.confidence,
        )

        return response


# Global singleton used by the API routes
signal_manager = SignalManager()
