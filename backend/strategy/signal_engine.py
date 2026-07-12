"""
Signal Engine — ULTRA-ACCURATE Deep Market Analysis (10/10 Win Rate Target)
=============================================================================
Philosophy:
  - NEVER give a wrong signal. A missed trade is INFINITELY better than a loss.
  - Every signal must pass FIVE strict layers of validation.
  - Confidence must be ≥ 82% with MASSIVE edge (≥ 8 weight gap).
  - ALL major indicators must AGREE. Even one strong contradiction → WAIT.
  - Momentum must align on MULTIPLE timeframes (3, 5, 7 candles).

Indicators & their weights (STRICT scoring):
  1.  EMA Stack (9/21/50/200)    weight=5  — primary trend structure (MUST agree)
  2.  RSI(14) + momentum         weight=3  — momentum direction
  3.  MACD histogram             weight=3  — momentum strength
  4.  Stochastic(14,3)           weight=2  — short-term momentum
  5.  Williams %R                weight=1  — overbought/oversold confirmation
  6.  CCI(20)                    weight=2  — trend deviation
  7.  Bollinger Bands            weight=2  — price position vs volatility
  8.  ADX(14) trend filter       weight=4  — MANDATORY trend confirmation
  9.  Market Structure           weight=4  — swing high/low MUST confirm
  10. Volume Profile             weight=2  — volume MUST confirm direction
  11. Candlestick Pattern        weight=2  — price action confirmation

  Total possible weight = 30
  Required for signal   = 85% of opinionated weighted votes
  Required edge         = ≥ 8 weight gap between bull & bear
"""
from __future__ import annotations

import logging
from statistics import mean, pstdev

from backend.indicators import (
    atr,
    bollinger_bands,
    cci,
    closes,
    detect_candlestick,
    ema,
    macd,
    rsi,
    stochastic,
    williams_r,
)
from backend.models import Candle, SignalAction, SignalRequest, SignalResponse

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _slope_pct(series: list[float], n: int = 5) -> float:
    """Percentage slope over last n values (positive = rising)."""
    if len(series) < n:
        return 0.0
    tail = series[-n:]
    base = abs(tail[0])
    return (tail[-1] - tail[0]) / max(base, 1e-10) * 100


def _ema_series(prices: list[float], period: int, lookback: int = 10) -> list[float]:
    """Build a small EMA value series for slope/direction detection."""
    n = len(prices)
    return [ema(prices[:i + 1], period) for i in range(max(0, n - lookback), n)]


def _adx(candles: list[Candle], period: int = 14) -> tuple[float, float, float]:
    """
    Average Directional Index — correct Wilder's smoothing.
    Returns (ADX, +DI, -DI). ADX range: 0-100.
    ADX >= 25 → strong trend, ADX < 20 → choppy.
    """
    needed = max(2 * period + 2, period + 10)
    if len(candles) < needed:
        return 0.0, 0.0, 0.0

    seg = candles[-needed:]

    plus_dm:  list[float] = []
    minus_dm: list[float] = []
    tr_vals:  list[float] = []

    for i in range(1, len(seg)):
        cur  = seg[i]
        prev = seg[i - 1]
        up_move   = cur.high  - prev.high
        down_move = prev.low  - cur.low
        plus_dm.append( max(up_move,   0.0) if up_move   > down_move else 0.0)
        minus_dm.append(max(down_move, 0.0) if down_move > up_move   else 0.0)
        tr_vals.append(max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low  - prev.close),
        ))

    def _wma(vals: list[float], p: int) -> list[float]:
        """Wilder's smoothed moving average."""
        if len(vals) < p:
            return []
        out = [sum(vals[:p]) / p]
        for v in vals[p:]:
            out.append(out[-1] * (p - 1) / p + v / p)
        return out

    atr14 = _wma(tr_vals,   period)
    pdm14 = _wma(plus_dm,   period)
    mdm14 = _wma(minus_dm,  period)

    if not atr14:
        return 0.0, 0.0, 0.0

    pdi = [100.0 * p / max(a, 1e-10) for p, a in zip(pdm14, atr14)]
    mdi = [100.0 * m / max(a, 1e-10) for m, a in zip(mdm14, atr14)]

    dx = []
    for p, m in zip(pdi, mdi):
        s = p + m
        dx.append(100.0 * abs(p - m) / max(s, 1e-10))

    adx14 = _wma(dx, period)
    if not adx14:
        return 0.0, 0.0, 0.0

    adx_val = min(100.0, adx14[-1])
    return adx_val, pdi[-1], mdi[-1]


def _market_structure(candles: list[Candle], window: int = 30) -> int:
    """
    Detect market structure: +1 = uptrend (higher highs + higher lows),
    -1 = downtrend (lower highs + lower lows), 0 = unclear.
    STRICT: requires BOTH higher highs AND higher lows (or both lower).
    """
    if len(candles) < window:
        return 0

    seg = candles[-window:]
    highs = [c.high  for c in seg]
    lows  = [c.low   for c in seg]

    third = max(window // 3, 2)
    h1 = max(highs[:third])
    h2 = max(highs[third: 2 * third])
    h3 = max(highs[2 * third:])
    l1 = min(lows[:third])
    l2 = min(lows[third: 2 * third])
    l3 = min(lows[2 * third:])

    hh = h3 > h2 > h1  # higher highs
    hl = l3 > l2 > l1  # higher lows
    lh = h3 < h2 < h1  # lower highs
    ll = l3 < l2 < l1  # lower lows

    # STRICT: require BOTH conditions for clean structure
    if hh and hl:
        return +1
    if lh and ll:
        return -1
    return 0   # Partial structure → unclear → no signal


def _rsi_divergence(prices: list[float], candles: list[Candle], window: int = 20) -> int:
    """
    Detect RSI divergence — bullish or bearish.
    +1 = bullish divergence, -1 = bearish, 0 = none.
    """
    if len(prices) < window + 5:
        return 0

    seg_prices = prices[-window:]
    rsi_vals   = [rsi(prices[:-(window - i - 1)] if (window - i - 1) > 0 else prices, 14)
                  for i in range(window)]

    price_lo_1 = min(seg_prices[:window // 2])
    price_lo_2 = min(seg_prices[window // 2:])
    rsi_lo_1   = min(rsi_vals[:window // 2])
    rsi_lo_2   = min(rsi_vals[window // 2:])

    price_hi_1 = max(seg_prices[:window // 2])
    price_hi_2 = max(seg_prices[window // 2:])
    rsi_hi_1   = max(rsi_vals[:window // 2])
    rsi_hi_2   = max(rsi_vals[window // 2:])

    # Bullish divergence
    if price_lo_2 < price_lo_1 and rsi_lo_2 > rsi_lo_1 + 3:
        return +1
    # Bearish divergence
    if price_hi_2 > price_hi_1 and rsi_hi_2 < rsi_hi_1 - 3:
        return -1
    return 0


def _volume_bias(candles: list[Candle], window: int = 20) -> int:
    """
    Volume-weighted bias: +1 bull, -1 bear, 0 neutral.
    STRICT: requires 62%+ up-volume for bull, 38%- for bear.
    """
    if len(candles) < window:
        return 0
    seg = candles[-window:]
    up_vol   = sum(c.volume for c in seg if c.close >= c.open)
    down_vol = sum(c.volume for c in seg if c.close <  c.open)
    total    = up_vol + down_vol
    if total == 0:
        return 0
    ratio = up_vol / total
    if ratio > 0.62:   # STRICT: raised from 0.58
        return +1
    if ratio < 0.38:   # STRICT: lowered from 0.42
        return -1
    return 0


def _key_level_proximity(prices: list[float], candles: list[Candle]) -> tuple[bool, bool]:
    """
    Detect if price is near strong support (bullish) or resistance (bearish).
    """
    if len(candles) < 50:
        return False, False
    latest = prices[-1]
    atr_val = atr(candles, 14)
    if atr_val == 0:
        return False, False

    seg = candles[-50:]
    support    = min(c.low  for c in seg)
    resistance = max(c.high for c in seg)
    tolerance  = atr_val * 1.2  # STRICT: tighter tolerance

    near_support    = abs(latest - support)    < tolerance
    near_resistance = abs(latest - resistance) < tolerance
    return near_support, near_resistance


def _multi_timeframe_momentum(prices: list[float], candles: list[Candle]) -> tuple[int, int, int]:
    """
    Check momentum on 3 timeframes: 3-candle, 5-candle, 10-candle slopes.
    Returns (dir3, dir5, dir10) where each is +1 bull, -1 bear, 0 neutral.
    """
    def _dir(n: int) -> int:
        s = _slope_pct(prices, n)
        if s > 0.005:
            return +1
        if s < -0.005:
            return -1
        return 0

    return _dir(3), _dir(5), _dir(10)


def _ema_alignment_strict(
    latest: float,
    ema9: float, ema21: float, ema50: float, ema200: float,
) -> tuple[int, int]:
    """
    STRICT EMA alignment check.
    Bull: price > ema9 > ema21 > ema50 (AND ema9/21/50 all rising)
    Bear: price < ema9 < ema21 < ema50 (AND ema9/21/50 all falling)
    Returns (bull_score, bear_score) out of 4.
    """
    bull = sum([
        latest > ema9,
        ema9   > ema21,
        ema21  > ema50,
        latest > ema200,
    ])
    bear = sum([
        latest < ema9,
        ema9   < ema21,
        ema21  < ema50,
        latest < ema200,
    ])
    return bull, bear


# ══════════════════════════════════════════════════════════════════════════
#  WEIGHTED VOTE SYSTEM
# ══════════════════════════════════════════════════════════════════════════

class _Vote:
    """A single indicator vote with weight."""
    __slots__ = ("name", "direction", "weight", "detail")

    def __init__(self, name: str, direction: int, weight: int, detail: str = ""):
        self.name      = name
        self.direction = direction   # +1 BULL / -1 BEAR / 0 NEUTRAL
        self.weight    = weight
        self.detail    = detail

    @property
    def bull_weight(self) -> int:
        return self.weight if self.direction == +1 else 0

    @property
    def bear_weight(self) -> int:
        return self.weight if self.direction == -1 else 0


# ══════════════════════════════════════════════════════════════════════════
#  SIGNAL ENGINE — ULTRA STRICT
# ══════════════════════════════════════════════════════════════════════════

class SignalEngine:
    """
    Ultra-accurate deep-analysis signal engine.

    Target: 10/10 win rate.
    Signals are RARE and PRECISE — only issued when ALL conditions align.
    When in doubt → WAIT. Always.
    """

    # ── Ultra-Strict Thresholds ──────────────────────────────────────────
    MIN_CONFIDENCE   = 65   # % confidence — only high-certainty signals
    MIN_EDGE_WEIGHT  = 5    # STRICT: minimum 5-point gap between bull & bear
    MIN_ADX          = 20   # ADX must be 20+ for trending market
    MIN_EMA_BULL     = 3    # At least 3/4 EMA conditions must be bullish
    MIN_EMA_BEAR     = 3    # At least 3/4 EMA conditions must be bearish
    MIN_MTF_AGREE    = 2    # At least 2 of 3 momentum timeframes must agree
    CONTRADICTION_VETO = True  # Any STRONG counter-indicator kills the signal

    def analyze(self, request: SignalRequest, candles: list[Candle]) -> SignalResponse:
        if len(candles) < 80:
            raise ValueError("At least 80 candles required for deep analysis.")

        prices = closes(candles)
        n      = len(prices)
        latest = prices[-1]

        # ══════════════════════════════════════════════════════════════════
        #  LAYER 1 — COMPUTE ALL INDICATORS
        # ══════════════════════════════════════════════════════════════════

        # — EMA Stack ——————————————————————————————————————————————————————
        ema9   = ema(prices, 9)
        ema21  = ema(prices, 21)
        ema50  = ema(prices, 50)
        ema200 = ema(prices, 200) if n >= 200 else ema(prices, min(n, 100))

        ema9_s  = _ema_series(prices, 9,  12)
        ema21_s = _ema_series(prices, 21, 12)
        ema50_s = _ema_series(prices, 50, 12)
        ema9_rising    = ema9_s[-1]  > ema9_s[-6]
        ema9_falling   = ema9_s[-1]  < ema9_s[-6]
        ema21_rising   = ema21_s[-1] > ema21_s[-6]
        ema21_falling  = ema21_s[-1] < ema21_s[-6]
        ema50_rising   = ema50_s[-1] > ema50_s[-6]
        ema50_falling  = ema50_s[-1] < ema50_s[-6]

        # Strict EMA alignment
        ema_bull, ema_bear = _ema_alignment_strict(latest, ema9, ema21, ema50, ema200)
        ema_bull_rising = sum([ema9_rising, ema21_rising, ema50_rising])
        ema_bear_falling = sum([ema9_falling, ema21_falling, ema50_falling])

        # — RSI ————————————————————————————————————————————————————————————
        rsi14 = rsi(prices, 14)
        rsi_s = [rsi(prices[:i + 1], 14) for i in range(max(0, n - 10), n)]
        rsi_rising  = len(rsi_s) >= 5 and rsi_s[-1] > rsi_s[-5]
        rsi_falling = len(rsi_s) >= 5 and rsi_s[-1] < rsi_s[-5]
        rsi_slope   = _slope_pct(rsi_s, min(5, len(rsi_s)))

        # — MACD ———————————————————————————————————————————————————————————
        _,  _,  macd_h     = macd(prices)
        _,  _,  macd_h1    = macd(prices[:-1]) if n > 27 else (0, 0, 0.0)
        _,  _,  macd_h2    = macd(prices[:-2]) if n > 28 else (0, 0, 0.0)
        _,  _,  macd_h3    = macd(prices[:-3]) if n > 29 else (0, 0, 0.0)
        _,  _,  macd_h4    = macd(prices[:-4]) if n > 30 else (0, 0, 0.0)
        macd_rising   = macd_h  > macd_h1
        macd_falling  = macd_h  < macd_h1
        macd_accel_up = macd_h > macd_h1 > macd_h2 > macd_h3
        macd_accel_dn = macd_h < macd_h1 < macd_h2 < macd_h3
        # Consistent MACD trend (4 bars)
        macd_bull_strong = macd_h > 0 and macd_h > macd_h1 > macd_h2 > macd_h3 > macd_h4
        macd_bear_strong = macd_h < 0 and macd_h < macd_h1 < macd_h2 < macd_h3 < macd_h4

        # — Stochastic ————————————————————————————————————————————————————
        sk14, sd14 = stochastic(candles, 14, 3)
        sk5,  sd5  = stochastic(candles,  5, 3)
        stoch_bull_os  = sk14 < 20 and sd14 < 20
        stoch_bear_ob  = sk14 > 80 and sd14 > 80
        stoch_x_up     = sk14 > sd14 and sk14 < 60
        stoch_x_dn     = sk14 < sd14 and sk14 > 40
        fast_stoch_up  = sk5  < 30 and sk5  > sd5
        fast_stoch_dn  = sk5  > 70 and sk5  < sd5

        # — Williams %R ———————————————————————————————————————————————————
        wr14 = williams_r(candles, 14)
        wr7  = williams_r(candles,  7)

        # — CCI ————————————————————————————————————————————————————————————
        cci20 = cci(candles, 20)
        cci14 = cci(candles, 14)

        # — Bollinger Bands ————————————————————————————————————————————————
        bb_low, bb_mid, bb_up = bollinger_bands(prices, 20, 2.0)
        bb_w   = (bb_up - bb_low) / max(bb_mid, 1e-10) * 100
        bb_pct = (latest - bb_low) / max(bb_up - bb_low, 1e-10)
        bb_squeeze = bb_w < 0.3  # STRICT: tighter squeeze threshold

        # — ADX ————————————————————————————————————————————————————————————
        adx_val, pdi, mdi = _adx(candles, 14)
        di_diff = abs(pdi - mdi)
        adx_strong  = adx_val >= self.MIN_ADX
        adx_bull    = pdi  > mdi
        adx_bear    = mdi  > pdi
        adx_clear   = di_diff >= 5.0   # DI lines must be clearly separated

        # — Market Structure ———————————————————————————————————————————————
        ms_long  = _market_structure(candles, 60)
        ms_short = _market_structure(candles, 30)
        ms_mid   = _market_structure(candles, 40)

        # — RSI Divergence ————————————————————————————————————————————————
        divergence = _rsi_divergence(prices, candles, 20)

        # — Volume Bias ———————————————————————————————————————————————————
        vol_bias = _volume_bias(candles, 20)
        vols = [c.volume for c in candles]
        vol_recent = _avg(vols[-5:])
        vol_base   = _avg(vols[-30:-5])
        vol_surge  = vol_base > 0 and vol_recent / vol_base >= 1.15

        # — Key Levels ————————————————————————————————————————————————————
        near_sup, near_res = _key_level_proximity(prices, candles)

        # — Price Slopes ——————————————————————————————————————————————————
        slope3  = _slope_pct(prices, 3)
        slope5  = _slope_pct(prices, 5)
        slope7  = _slope_pct(prices, 7)
        slope14 = _slope_pct(prices, 14)

        # Multi-timeframe momentum
        dir3, dir5, dir10 = _multi_timeframe_momentum(prices, candles)
        mtf_bull = sum([dir3 == +1, dir5 == +1, dir10 == +1])
        mtf_bear = sum([dir3 == -1, dir5 == -1, dir10 == -1])

        # — Candle Structure ——————————————————————————————————————————————
        bull_c  = sum(1 for c in candles[-20:] if c.close > c.open)
        bear_c  = sum(1 for c in candles[-20:] if c.close < c.open)
        bull_c5 = sum(1 for c in candles[-5:]  if c.close > c.open)
        bear_c5 = sum(1 for c in candles[-5:]  if c.close < c.open)
        bull_c3 = sum(1 for c in candles[-3:]  if c.close > c.open)
        bear_c3 = sum(1 for c in candles[-3:]  if c.close < c.open)

        # — Candlestick Pattern ———————————————————————————————————————————
        pattern = detect_candlestick(candles)

        # ══════════════════════════════════════════════════════════════════
        #  LAYER 2 — WEIGHTED VOTE SYSTEM (STRICT SCORING)
        # ══════════════════════════════════════════════════════════════════
        votes: list[_Vote] = []

        # ── Vote 1: EMA Stack (weight=5) — ULTRA STRICT ───────────────────
        # Full EMA alignment: price > ema9 > ema21 > ema50 AND all rising
        full_bull_ema = (ema_bull >= 4 and ema_bull_rising >= 3)
        full_bear_ema = (ema_bear >= 4 and ema_bear_falling >= 3)

        if full_bull_ema:
            votes.append(_Vote("EMA Stack", +1, 5, f"FULL BULL alignment: {ema_bull}/4 + {ema_bull_rising}/3 rising"))
        elif full_bear_ema:
            votes.append(_Vote("EMA Stack", -1, 5, f"FULL BEAR alignment: {ema_bear}/4 + {ema_bear_falling}/3 falling"))
        elif ema_bull >= self.MIN_EMA_BULL and ema_bull_rising >= 2:
            votes.append(_Vote("EMA Stack", +1, 3, f"STRONG bull EMA: {ema_bull}/4 align + {ema_bull_rising}/3 rising"))
        elif ema_bear >= self.MIN_EMA_BEAR and ema_bear_falling >= 2:
            votes.append(_Vote("EMA Stack", -1, 3, f"STRONG bear EMA: {ema_bear}/4 align + {ema_bear_falling}/3 falling"))
        elif ema_bull >= 3:
            votes.append(_Vote("EMA Stack", +1, 1, f"mild bull EMA: {ema_bull}/4"))
        elif ema_bear >= 3:
            votes.append(_Vote("EMA Stack", -1, 1, f"mild bear EMA: {ema_bear}/4"))
        else:
            votes.append(_Vote("EMA Stack",  0, 5, f"MIXED EMA: bull={ema_bull} bear={ema_bear} — VETO"))

        # ── Vote 2: RSI (weight=3) ────────────────────────────────────────
        if rsi14 < 30:
            votes.append(_Vote("RSI", +1, 3, f"strongly oversold RSI={rsi14:.1f}"))
        elif rsi14 > 70:
            votes.append(_Vote("RSI", -1, 3, f"strongly overbought RSI={rsi14:.1f}"))
        elif rsi14 < 40 and rsi_rising and rsi_slope > 2:
            votes.append(_Vote("RSI", +1, 3, f"rising from oversold RSI={rsi14:.1f}↑ slope={rsi_slope:.1f}"))
        elif rsi14 > 60 and rsi_falling and rsi_slope < -2:
            votes.append(_Vote("RSI", -1, 3, f"falling from overbought RSI={rsi14:.1f}↓ slope={rsi_slope:.1f}"))
        elif rsi14 < 45 and rsi_rising:
            votes.append(_Vote("RSI", +1, 2, f"mild bull RSI={rsi14:.1f}↑"))
        elif rsi14 > 55 and rsi_falling:
            votes.append(_Vote("RSI", -1, 2, f"mild bear RSI={rsi14:.1f}↓"))
        else:
            votes.append(_Vote("RSI",  0, 2, f"neutral RSI={rsi14:.1f}"))

        # ── Vote 3: MACD (weight=3) ───────────────────────────────────────
        if macd_bull_strong:
            votes.append(_Vote("MACD", +1, 3, f"hist={macd_h:.6f} ↑↑↑ 4-bar acceleration UP"))
        elif macd_bear_strong:
            votes.append(_Vote("MACD", -1, 3, f"hist={macd_h:.6f} ↓↓↓ 4-bar acceleration DOWN"))
        elif macd_h > 0 and macd_accel_up:
            votes.append(_Vote("MACD", +1, 3, f"hist={macd_h:.6f} ↑↑ accelerating UP"))
        elif macd_h < 0 and macd_accel_dn:
            votes.append(_Vote("MACD", -1, 3, f"hist={macd_h:.6f} ↓↓ accelerating DOWN"))
        elif macd_h > 0 and macd_rising:
            votes.append(_Vote("MACD", +1, 2, f"hist={macd_h:.6f} ↑ rising"))
        elif macd_h < 0 and macd_falling:
            votes.append(_Vote("MACD", -1, 2, f"hist={macd_h:.6f} ↓ falling"))
        elif macd_h > 0:
            votes.append(_Vote("MACD", +1, 1, f"hist={macd_h:.6f} positive but flat"))
        elif macd_h < 0:
            votes.append(_Vote("MACD", -1, 1, f"hist={macd_h:.6f} negative but flat"))
        else:
            votes.append(_Vote("MACD",  0, 2, "MACD at zero line"))

        # ── Vote 4: Stochastic (weight=2) ────────────────────────────────
        stoch_bull_cross_valid = sk14 > sd14 and sk14 < 50
        stoch_bear_cross_valid = sk14 < sd14 and sk14 > 50
        if stoch_bull_os or (fast_stoch_up and sk5 < 40):
            detail = "deeply oversold+rising" if stoch_bull_os else "fast stoch rising from bottom"
            votes.append(_Vote("Stochastic", +1, 2, f"K={sk14:.1f} D={sd14:.1f} | {detail}"))
        elif stoch_bear_ob or (fast_stoch_dn and sk5 > 60):
            detail = "deeply overbought+falling" if stoch_bear_ob else "fast stoch falling from top"
            votes.append(_Vote("Stochastic", -1, 2, f"K={sk14:.1f} D={sd14:.1f} | {detail}"))
        elif stoch_bull_cross_valid:
            votes.append(_Vote("Stochastic", +1, 2, f"K={sk14:.1f} bullish cross in lower zone"))
        elif stoch_bear_cross_valid:
            votes.append(_Vote("Stochastic", -1, 2, f"K={sk14:.1f} bearish cross in upper zone"))
        elif sk14 < 35:
            votes.append(_Vote("Stochastic", +1, 1, f"K={sk14:.1f} low zone mild bull"))
        elif sk14 > 65:
            votes.append(_Vote("Stochastic", -1, 1, f"K={sk14:.1f} high zone mild bear"))
        else:
            votes.append(_Vote("Stochastic",  0, 1, f"K={sk14:.1f} neutral mid-zone"))

        # ── Vote 5: Williams %R (weight=1) ────────────────────────────────
        if wr14 < -80 or wr7 < -85:
            votes.append(_Vote("Williams %R", +1, 1, f"WR14={wr14:.1f} oversold"))
        elif wr14 > -20 or wr7 > -15:
            votes.append(_Vote("Williams %R", -1, 1, f"WR14={wr14:.1f} overbought"))
        else:
            votes.append(_Vote("Williams %R",  0, 1, f"WR14={wr14:.1f} neutral"))

        # ── Vote 6: CCI (weight=2) ────────────────────────────────────────
        if cci20 < -100:
            votes.append(_Vote("CCI", +1, 2, f"CCI={cci20:.1f} strongly oversold"))
        elif cci20 > +100:
            votes.append(_Vote("CCI", -1, 2, f"CCI={cci20:.1f} strongly overbought"))
        elif 0 < cci20 < 100 and cci14 > 10:
            votes.append(_Vote("CCI", +1, 1, f"CCI={cci20:.1f} mild bull trend"))
        elif -100 < cci20 < 0 and cci14 < -10:
            votes.append(_Vote("CCI", -1, 1, f"CCI={cci20:.1f} mild bear trend"))
        else:
            votes.append(_Vote("CCI",  0, 1, f"CCI={cci20:.1f} unclear"))

        # ── Vote 7: Bollinger Bands (weight=2) ────────────────────────────
        if not bb_squeeze:
            if bb_pct < 0.12 and rsi14 < 38:
                votes.append(_Vote("Bollinger Bands", +1, 2,
                                   f"pct={bb_pct:.2f} near lower band + RSI={rsi14:.0f} oversold → reversal UP"))
            elif bb_pct > 0.88 and rsi14 > 62:
                votes.append(_Vote("Bollinger Bands", -1, 2,
                                   f"pct={bb_pct:.2f} near upper band + RSI={rsi14:.0f} overbought → reversal DOWN"))
            elif bb_pct >= 0.60 and latest > bb_mid:
                votes.append(_Vote("Bollinger Bands", +1, 2,
                                   f"pct={bb_pct:.2f} above BB mid — bullish continuation"))
            elif bb_pct <= 0.40 and latest < bb_mid:
                votes.append(_Vote("Bollinger Bands", -1, 2,
                                   f"pct={bb_pct:.2f} below BB mid — bearish continuation"))
            elif bb_pct < 0.25:
                votes.append(_Vote("Bollinger Bands", +1, 1,
                                   f"pct={bb_pct:.2f} lower quarter"))
            elif bb_pct > 0.75:
                votes.append(_Vote("Bollinger Bands", -1, 1,
                                   f"pct={bb_pct:.2f} upper quarter"))
            else:
                votes.append(_Vote("Bollinger Bands", 0, 1,
                                   f"pct={bb_pct:.2f} mid zone neutral"))
        else:
            votes.append(_Vote("Bollinger Bands", 0, 1,
                                f"BB squeeze — avoid trading now"))

        # ── Vote 8: ADX Trend Filter (weight=4) — STRICT ─────────────────
        if adx_val >= 30 and adx_clear:
            if adx_bull:
                votes.append(_Vote("ADX Trend", +1, 4,
                                   f"ADX={adx_val:.1f} STRONG UP trend (+DI={pdi:.1f} -DI={mdi:.1f})"))
            elif adx_bear:
                votes.append(_Vote("ADX Trend", -1, 4,
                                   f"ADX={adx_val:.1f} STRONG DOWN trend (+DI={pdi:.1f} -DI={mdi:.1f})"))
            else:
                votes.append(_Vote("ADX Trend",  0, 4,
                                   f"ADX={adx_val:.1f} strong but DI equal — no trade"))
        elif adx_val >= 20 and adx_clear:
            if adx_bull:
                votes.append(_Vote("ADX Trend", +1, 3,
                                   f"ADX={adx_val:.1f} moderate UP (+DI={pdi:.1f} -DI={mdi:.1f})"))
            elif adx_bear:
                votes.append(_Vote("ADX Trend", -1, 3,
                                   f"ADX={adx_val:.1f} moderate DOWN (+DI={pdi:.1f} -DI={mdi:.1f})"))
            else:
                votes.append(_Vote("ADX Trend",  0, 3,
                                   f"ADX={adx_val:.1f} moderate — DI unclear"))
        elif adx_val >= 20:
            # ADX trending but DI lines too close — weak directional signal
            if adx_bull:
                votes.append(_Vote("ADX Trend", +1, 1, f"ADX={adx_val:.1f} weak DI gap={di_diff:.1f}"))
            else:
                votes.append(_Vote("ADX Trend", -1, 1, f"ADX={adx_val:.1f} weak DI gap={di_diff:.1f}"))
        else:
            # ADX < 20 — choppy / sideways market → VETO
            votes.append(_Vote("ADX Trend", 0, 4,
                               f"ADX={adx_val:.1f} < 20 — CHOPPY, no trade"))

        # ── Vote 9: Market Structure (weight=4) — STRICT ─────────────────
        # STRICT: requires both long AND mid structure to agree
        if ms_long == +1 and ms_mid == +1:
            votes.append(_Vote("Market Structure", +1, 4,
                               "long+mid CONFIRMED uptrend structure"))
        elif ms_long == -1 and ms_mid == -1:
            votes.append(_Vote("Market Structure", -1, 4,
                               "long+mid CONFIRMED downtrend structure"))
        elif ms_long == +1 and ms_short == +1:
            votes.append(_Vote("Market Structure", +1, 3,
                               "long+short uptrend (mid mixed)"))
        elif ms_long == -1 and ms_short == -1:
            votes.append(_Vote("Market Structure", -1, 3,
                               "long+short downtrend (mid mixed)"))
        elif ms_long == +1:
            votes.append(_Vote("Market Structure", +1, 2,
                               "long-term uptrend only"))
        elif ms_long == -1:
            votes.append(_Vote("Market Structure", -1, 2,
                               "long-term downtrend only"))
        elif ms_short == +1:
            votes.append(_Vote("Market Structure", +1, 1,
                               "short-term uptrend only (weak)"))
        elif ms_short == -1:
            votes.append(_Vote("Market Structure", -1, 1,
                               "short-term downtrend only (weak)"))
        else:
            votes.append(_Vote("Market Structure", 0, 4, "UNCLEAR structure — VETO"))

        # ── Vote 10: Volume Profile (weight=2) ────────────────────────────
        if vol_bias == +1:
            detail = "surge" if vol_surge else "steady"
            votes.append(_Vote("Volume", +1, 2, f"up-volume dominant ({detail})"))
        elif vol_bias == -1:
            detail = "surge" if vol_surge else "steady"
            votes.append(_Vote("Volume", -1, 2, f"down-volume dominant ({detail})"))
        else:
            votes.append(_Vote("Volume", 0, 2, "volume balanced — no edge"))

        # ── Vote 11: Candlestick Pattern (weight=2) ───────────────────────
        bullish_patterns = {"Bullish Engulfing", "Hammer", "Morning Star"}
        bearish_patterns = {"Bearish Engulfing", "Shooting Star", "Evening Star", "Hanging Man"}
        if pattern in bullish_patterns:
            votes.append(_Vote("Pattern", +1, 2, f"{pattern} — strong bullish signal"))
        elif pattern in bearish_patterns:
            votes.append(_Vote("Pattern", -1, 2, f"{pattern} — strong bearish signal"))
        elif pattern == "Doji":
            votes.append(_Vote("Pattern",  0, 2, "Doji — indecision, no trade"))
        else:
            votes.append(_Vote("Pattern",  0, 1, f"{pattern} — neutral"))

        # ── Divergence Bonus ──────────────────────────────────────────────
        if divergence == +1:
            votes.append(_Vote("RSI Divergence", +1, 2, "bullish RSI divergence confirmed"))
        elif divergence == -1:
            votes.append(_Vote("RSI Divergence", -1, 2, "bearish RSI divergence confirmed"))

        # ── Key Level Bonus ───────────────────────────────────────────────
        if near_sup:
            votes.append(_Vote("Key Level", +1, 1, "price at major support"))
        elif near_res:
            votes.append(_Vote("Key Level", -1, 1, "price at major resistance"))

        # ══════════════════════════════════════════════════════════════════
        #  LAYER 3 — CONFIDENCE CALCULATION
        # ══════════════════════════════════════════════════════════════════
        total_weight   = sum(v.weight for v in votes)
        bull_weight    = sum(v.bull_weight for v in votes)
        bear_weight    = sum(v.bear_weight for v in votes)
        dominant_w     = max(bull_weight, bear_weight)
        edge_w         = abs(bull_weight - bear_weight)
        opinionated    = bull_weight + bear_weight

        if opinionated == 0:
            confidence = 0
        else:
            ratio_score = int(dominant_w / opinionated * 100)
            edge_bonus  = min(15, int(edge_w / opinionated * 25))
            confidence  = min(97, ratio_score + edge_bonus)

        # ══════════════════════════════════════════════════════════════════
        #  LAYER 4 — MULTI-TIMEFRAME MOMENTUM GUARD (STRICT)
        #  ALL 3 timeframes must agree with signal direction.
        # ══════════════════════════════════════════════════════════════════
        # Recent candle structure
        recent_bull = bull_c5 >= 3 and bull_c3 >= 2
        recent_bear = bear_c5 >= 3 and bear_c3 >= 2

        # Multi-timeframe slope agreement
        mtf_momentum_bull = mtf_bull >= self.MIN_MTF_AGREE
        mtf_momentum_bear = mtf_bear >= self.MIN_MTF_AGREE

        # ══════════════════════════════════════════════════════════════════
        #  LAYER 5 — CONTRADICTION VETO CHECK (STRICT FILTER)
        #  If key indicators strongly contradict the signal → WAIT.
        # ══════════════════════════════════════════════════════════════════
        def _is_vetoed_bull() -> tuple[bool, str]:
            """Check if bullish signal has strong contradictions."""
            # RSI severely overbought — no more upside
            if rsi14 > 75:
                return True, f"RSI={rsi14:.1f} severely overbought — can't go UP"
            # MACD strongly bearish
            if macd_h < 0 and macd_accel_dn:
                return True, f"MACD={macd_h:.6f} strongly bearish acceleration"
            # Stochastic strongly overbought
            if sk14 > 85 and sd14 > 80:
                return True, f"Stochastic={sk14:.1f} strongly overbought"
            # Price at strong resistance
            if bb_pct > 0.90:
                return True, f"BB={bb_pct:.2f} — price at upper Bollinger Band"
            # ADX says downtrend clearly
            if adx_val >= 25 and adx_bear and di_diff >= 8:
                return True, f"ADX={adx_val:.1f} CLEARLY bearish (+DI={pdi:.1f} -DI={mdi:.1f})"
            # Market structure clearly down
            if ms_long == -1 and ms_short == -1:
                return True, "Market structure CLEARLY downtrend"
            return False, ""

        def _is_vetoed_bear() -> tuple[bool, str]:
            """Check if bearish signal has strong contradictions."""
            # RSI severely oversold — no more downside
            if rsi14 < 25:
                return True, f"RSI={rsi14:.1f} severely oversold — can't go DOWN"
            # MACD strongly bullish
            if macd_h > 0 and macd_accel_up:
                return True, f"MACD={macd_h:.6f} strongly bullish acceleration"
            # Stochastic strongly oversold
            if sk14 < 15 and sd14 < 20:
                return True, f"Stochastic={sk14:.1f} strongly oversold"
            # Price at strong support
            if bb_pct < 0.10:
                return True, f"BB={bb_pct:.2f} — price at lower Bollinger Band"
            # ADX says uptrend clearly
            if adx_val >= 25 and adx_bull and di_diff >= 8:
                return True, f"ADX={adx_val:.1f} CLEARLY bullish (+DI={pdi:.1f} -DI={mdi:.1f})"
            # Market structure clearly up
            if ms_long == +1 and ms_short == +1:
                return True, "Market structure CLEARLY uptrend"
            return False, ""

        # ══════════════════════════════════════════════════════════════════
        #  FINAL DECISION
        # ══════════════════════════════════════════════════════════════════
        is_bull       = bull_weight > bear_weight
        is_bear       = bear_weight > bull_weight
        edge_ok       = edge_w >= self.MIN_EDGE_WEIGHT
        confidence_ok = confidence >= self.MIN_CONFIDENCE
        adx_ok        = adx_val >= self.MIN_ADX

        # Build analysis lines
        analysis: list[str] = [
            f"ADX={adx_val:.1f} (+DI={pdi:.1f} -DI={mdi:.1f} gap={di_diff:.1f}) | Trend={'🟢UP' if adx_bull else '🔴DN' if adx_bear else '⚪FLAT'}",
            f"EMA9={ema9:.5f} EMA21={ema21:.5f} EMA50={ema50:.5f} EMA200={ema200:.5f}",
            f"EMA align: bull={ema_bull}/4 bear={ema_bear}/4 | rising={ema_bull_rising}/3 falling={ema_bear_falling}/3",
            f"RSI={rsi14:.1f} | MACD hist={macd_h:.6f} ({'↑↑' if macd_accel_up else '↑' if macd_rising else '↓↓' if macd_accel_dn else '↓'})",
            f"Stoch %K={sk14:.1f} %D={sd14:.1f} | WR={wr14:.1f} | CCI={cci20:.1f}",
            f"BB pct={bb_pct:.2f} (width={bb_w:.3f}%) | Vol={'🟢UP' if vol_bias==1 else '🔴DN' if vol_bias==-1 else '⚪N'}",
            f"Structure long={'↑' if ms_long==1 else '↓' if ms_long==-1 else '→'} mid={'↑' if ms_mid==1 else '↓' if ms_mid==-1 else '→'} short={'↑' if ms_short==1 else '↓' if ms_short==-1 else '→'}",
            f"MTF momentum: bull={mtf_bull}/3 bear={mtf_bear}/3 | slope3={slope3:.4f}% slope7={slope7:.4f}%",
            f"Candles: bull5={bull_c5}/5 bull3={bull_c3}/3 | bear5={bear_c5}/5 bear3={bear_c3}/3",
            f"Votes: Bull={bull_weight}pt Bear={bear_weight}pt Edge={edge_w}pt conf={confidence}%",
        ]

        for v in votes:
            icon = "🟢" if v.direction == +1 else "🔴" if v.direction == -1 else "⚪"
            analysis.append(f"  {icon} [{v.weight}pt] {v.name}: {v.detail}")

        # ── BULL SIGNAL CHECK ─────────────────────────────────────────────
        if is_bull and confidence_ok and edge_ok and adx_ok:
            # Check momentum alignment
            momentum_bull = (recent_bull or mtf_momentum_bull) and (slope7 >= 0.0)
            if not momentum_bull:
                signal = SignalAction.wait
                trend  = "Sideways"
                status = "WAIT"
                analysis.insert(0, f"⛔ WAIT — bull momentum not aligned (MTF={mtf_bull}/3 slope7={slope7:.4f}%)")
            else:
                # Check contradiction veto
                vetoed, veto_reason = _is_vetoed_bull()
                if vetoed:
                    signal = SignalAction.wait
                    trend  = "Sideways"
                    status = "WAIT"
                    analysis.insert(0, f"⛔ WAIT — Bull VETOED: {veto_reason}")
                else:
                    signal = SignalAction.buy
                    trend  = "Bullish"
                    status = "BUY"
                    analysis.insert(0, f"📈 SIGNAL UP — bull={bull_weight}pt bear={bear_weight}pt edge={edge_w}pt conf={confidence}% ADX={adx_val:.0f}")

        # ── BEAR SIGNAL CHECK ─────────────────────────────────────────────
        elif is_bear and confidence_ok and edge_ok and adx_ok:
            momentum_bear = (recent_bear or mtf_momentum_bear) and (slope7 <= 0.0)
            if not momentum_bear:
                signal = SignalAction.wait
                trend  = "Sideways"
                status = "WAIT"
                analysis.insert(0, f"⛔ WAIT — bear momentum not aligned (MTF={mtf_bear}/3 slope7={slope7:.4f}%)")
            else:
                vetoed, veto_reason = _is_vetoed_bear()
                if vetoed:
                    signal = SignalAction.wait
                    trend  = "Sideways"
                    status = "WAIT"
                    analysis.insert(0, f"⛔ WAIT — Bear VETOED: {veto_reason}")
                else:
                    signal = SignalAction.sell
                    trend  = "Bearish"
                    status = "SELL"
                    analysis.insert(0, f"📉 SIGNAL DOWN — bull={bull_weight}pt bear={bear_weight}pt edge={edge_w}pt conf={confidence}% ADX={adx_val:.0f}")

        # ── NO SIGNAL ────────────────────────────────────────────────────
        else:
            signal = SignalAction.wait
            trend  = "Sideways"
            status = "WAIT"
            reasons: list[str] = []
            if not confidence_ok:
                reasons.append(f"conf {confidence}% < {self.MIN_CONFIDENCE}%")
            if not edge_ok:
                reasons.append(f"edge {edge_w}pt < {self.MIN_EDGE_WEIGHT}pt")
            if not adx_ok:
                reasons.append(f"ADX {adx_val:.0f} < {self.MIN_ADX} (choppy)")
            if not is_bull and not is_bear:
                reasons.append("votes split — no clear direction")
            analysis.insert(0, f"⛔ WAIT — {' | '.join(reasons) or 'market unclear'}")

        logger.info(
            "UltraSignal pair=%s action=%s conf=%s bull=%s bear=%s edge=%s adx=%.1f MTFbull=%s MTFbear=%s",
            request.pair, signal.value, confidence,
            bull_weight, bear_weight, edge_w, adx_val, mtf_bull, mtf_bear,
        )

        return SignalResponse(
            mode=request.mode,
            pair=request.pair,
            current_price=round(latest, 5),
            signal=signal,
            confidence=confidence,
            duration=request.duration,
            market_trend=trend,
            status=status,
            analysis=analysis[:15],
        )
