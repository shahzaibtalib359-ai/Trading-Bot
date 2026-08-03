"""
Signal Manager — Chinese Bot Pro AI Signal Engine
===================================================
Fetches 100% pure, accurate signals directly from Chinese Bot (https://chinese-bot.com/).
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
    Chinese Bot Pro AI Direct Signal Engine.
    Uses 100% pure Chinese Bot AI signals for maximum accuracy.
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
        Generate a signal using 100% pure Chinese Bot AI live market reading.
        """
        # ── 1. Try Chinese Bot Pro AI Live Signal Engine ───────────────────────
        if self.settings.chinese_bot_enabled:
            try:
                cb_data = await chinese_bot_service.fetch_signal(request.pair, request.duration.value)
                if cb_data and "direction" in cb_data:
                    raw_dir = cb_data["direction"]
                    if raw_dir == "UP":
                        sig_action = SignalAction.buy
                    elif raw_dir == "DOWN":
                        sig_action = SignalAction.sell
                    else:
                        sig_action = SignalAction.wait

                    strength = cb_data.get("confidence", 70)
                    confidence = strength if sig_action != SignalAction.wait else 0

                    clean_pair = cb_data.get("clean_pair", request.pair)
                    tf_code = cb_data.get("tf", "5M")
                    htf = cb_data.get("htf_trend", "SIDEWAYS")
                    confirmations = cb_data.get("confirmations", [])

                    conf_str = ", ".join(confirmations) if confirmations else "Market Momentum & Consistency Aligned"

                    analysis = [
                        f"Chinese Bot Pro AI Signal: {raw_dir} ({strength}% Strength Score)",
                        f"Timeframe: {tf_code} | Pair: {clean_pair}",
                        f"Higher Timeframe Trend: {htf}",
                        f"AI Confirmations: {conf_str}",
                        "Engine: 100% Pure Chinese Bot Pro AI (chinese-bot.com)"
                    ]

                    # Use Chinese Bot Entry Price if available, otherwise fetch live snapshot price
                    price = cb_data.get("entry_price", 0.0)
                    snapshot = None
                    if price <= 0.0:
                        try:
                            snapshot = await self.data_engine.snapshot(request)
                            price = round(snapshot.latest_price, 5)
                        except Exception:
                            price = 1.0000

                    response = SignalResponse(
                        mode=request.mode,
                        pair=request.pair,
                        current_price=price,
                        signal=sig_action,
                        confidence=confidence,
                        duration=request.duration,
                        market_trend=htf,
                        status="OK",
                        analysis=analysis,
                        data_source="Chinese Bot Pro AI Engine (chinese-bot.com)",
                        last_market_update=snapshot.latest_update if snapshot else None,
                        data_warning=snapshot.data_warning if snapshot else None
                    )

                    logger.info(
                        "[Signal/ChineseBot] %s — %s | %s | conf=%s%% (Price: %s)",
                        response.signal.value, request.pair, request.duration.value, response.confidence, price
                    )
                    return response
            except Exception as e:
                logger.warning("[Signal/ChineseBot] Exception fetching Chinese Bot signal, using backup engine: %s", e)

        # ── 2. Backup Fallback for Non-Forex Assets (Crypto / Metals) ──────────
        snapshot = await self.data_engine.snapshot(request)
        response = self.signal_engine.analyze(request, snapshot.candles)

        try:
            response.current_price      = round(snapshot.latest_price, 5)
            response.data_source        = snapshot.data_source
            response.last_market_update = snapshot.latest_update
            response.data_warning       = snapshot.data_warning
        except Exception:
            pass

        return response


# Global singleton used by the API routes
signal_manager = SignalManager()
