"""
Signal Manager — Double-Pass Confirmation System
=================================================
For maximum accuracy (10/10 win rate target):

1. FIRST PASS  — fetch fresh market data → analyze
2. If signal is UP/DOWN → wait briefly → SECOND PASS (re-fetch fresh data → re-analyze)
3. Only issue the signal if BOTH passes agree on the SAME direction
4. If passes disagree → return WAIT (market is not clear enough)

This double-confirmation eliminates false signals caused by:
  - Momentary price spikes
  - Data latency artifacts
  - Short-lived noise patterns
"""
from __future__ import annotations

import asyncio
import logging

from backend.data_engine import LiveMarketDataEngine
from backend.models import SignalAction, SignalRequest, SignalResponse, TradingMode
from backend.strategy.signal_engine import SignalEngine

logger = logging.getLogger(__name__)


class SignalManager:
    """
    Coordinates fresh market snapshots with double-pass confirmation.

    Flow:
      Pass 1 → if WAIT → return WAIT immediately (no second call needed)
      Pass 1 → if UP/DOWN → short pause → Pass 2
        Both agree  → return confirmed signal (averaged confidence)
        Disagree    → return WAIT (signal was not stable enough)
    """

    # Seconds to wait between the two analysis passes.
    # 3 seconds = fresh candle data with minimal market shift = better confirmation.
    CONFIRMATION_DELAY_SECONDS: float = 3.0

    def __init__(
        self,
        data_engine: LiveMarketDataEngine | None = None,
        signal_engine: SignalEngine | None = None,
    ) -> None:
        self.data_engine   = data_engine   or LiveMarketDataEngine()
        self.signal_engine = signal_engine or SignalEngine()

    async def generate(self, request: SignalRequest) -> SignalResponse:
        """
        Generate a high-accuracy signal using double-pass market analysis.

        Pass 1: Fetch candles → run analysis
        If actionable:
            Pass 2: Re-fetch candles → run analysis again
            Confirm only if both passes agree
        """
        # ── PASS 1 ───────────────────────────────────────────────────────
        snapshot1 = await self.data_engine.snapshot(request)
        response1 = self.signal_engine.analyze(request, snapshot1.candles)

        _enrich(response1, snapshot1)

        # If first pass says WAIT, no need to do a second pass
        if response1.signal == SignalAction.wait:
            logger.info(
                "[Pass1] WAIT — %s | %s | conf=%s%%",
                request.pair, request.mode.value, response1.confidence,
            )
            return response1

        logger.info(
            "[Pass1] %s — %s | %s | conf=%s%% — running confirmation pass …",
            response1.signal.value, request.pair, request.mode.value, response1.confidence,
        )

        # ── SHORT PAUSE before second fetch ──────────────────────────────
        await asyncio.sleep(self.CONFIRMATION_DELAY_SECONDS)

        # ── PASS 2 (Confirmation) ─────────────────────────────────────────
        try:
            snapshot2 = await self.data_engine.snapshot(request)
            response2 = self.signal_engine.analyze(request, snapshot2.candles)
            _enrich(response2, snapshot2)
        except Exception as exc:
            # If second pass fails, fall back to WAIT (safety first)
            logger.warning(
                "[Pass2] Failed for %s (%s) — defaulting to WAIT. Error: %s",
                request.pair, request.mode.value, exc,
            )
            return _make_wait(response1, "Confirmation pass failed — market data unstable")

        # ── AGREEMENT CHECK ────────────────────────────────────────────────
        if response1.signal == response2.signal:
            # Both passes agree → confirmed signal
            # Use the LOWER confidence of the two (conservative estimate)
            confirmed_confidence = min(response1.confidence, response2.confidence)

            # Build enriched analysis showing both passes agreed
            combined_analysis = [
                f"✅ DOUBLE-CONFIRMED: Both passes agree — {response2.signal.value}",
                f"   Pass1 conf={response1.confidence}% | Pass2 conf={response2.confidence}% → final={confirmed_confidence}%",
            ] + response2.analysis

            logger.info(
                "[CONFIRMED] %s — %s | conf=%s%% (pass1=%s%% pass2=%s%%)",
                response2.signal.value, request.pair,
                confirmed_confidence, response1.confidence, response2.confidence,
            )

            # Return the second-pass response with combined confidence
            return SignalResponse(
                mode=response2.mode,
                pair=response2.pair,
                current_price=response2.current_price,
                signal=response2.signal,
                confidence=confirmed_confidence,
                duration=response2.duration,
                market_trend=response2.market_trend,
                status=response2.status,
                analysis=combined_analysis[:14],
                data_source=response2.data_source,
                data_warning=response2.data_warning,
                last_market_update=response2.last_market_update,
            )


        else:
            # Passes disagree (opposite directions) → market shifted → WAIT
            logger.info(
                "[DISAGREEMENT] Pass1=%s vs Pass2=%s for %s — issuing WAIT",
                response1.signal.value, response2.signal.value, request.pair,
            )
            return _make_wait(
                response2,
                f"Market direction changed between passes "
                f"(Pass1={response1.signal.value} vs Pass2={response2.signal.value}) — "
                f"signal not stable enough to trade",
            )


def _enrich(response: SignalResponse, snapshot) -> None:
    """Fill live market fields onto a SignalResponse in-place."""
    object.__setattr__(response, "current_price",    round(snapshot.latest_price, 5)) \
        if hasattr(response, "__dataclass_fields__") else None
    # Pydantic models are mutable — set fields directly
    try:
        response.current_price    = round(snapshot.latest_price, 5)
        response.data_source      = snapshot.data_source
        response.last_market_update = snapshot.latest_update
        response.data_warning     = snapshot.data_warning
    except Exception:
        pass


def _make_wait(base: SignalResponse, reason: str) -> SignalResponse:
    """Return a WAIT signal response derived from an existing response."""
    return SignalResponse(
        mode=base.mode,
        pair=base.pair,
        current_price=base.current_price,
        signal=SignalAction.wait,
        confidence=0,
        duration=base.duration,
        market_trend="Sideways",
        status="WAIT",
        analysis=[f"⛔ WAIT — {reason}"] + base.analysis[:8],
        data_source=base.data_source,
        data_warning=base.data_warning,
        last_market_update=base.last_market_update,
    )


# Global singleton used by the API routes
signal_manager = SignalManager()
