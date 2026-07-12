from __future__ import annotations

from statistics import mean, pstdev

from backend.models import Candle


def closes(candles: list[Candle]) -> list[float]:
    return [c.close for c in candles]


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    multiplier = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = (value - current) * multiplier + current
    return current


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-period - 1 : -1], values[-period:]):
        change = current - previous
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = mean(gains) if gains else 0.0
    avg_loss = mean(losses) if losses else 0.0
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: list[float]) -> tuple[float, float, float]:
    if len(values) < 26:
        return 0.0, 0.0, 0.0
    macd_line = ema(values, 12) - ema(values, 26)
    macd_series: list[float] = []
    for index in range(26, len(values) + 1):
        window = values[:index]
        macd_series.append(ema(window, 12) - ema(window, 26))
    signal_line = ema(macd_series, 9)
    return macd_line, signal_line, macd_line - signal_line


def bollinger_bands(values: list[float], period: int = 20, width: float = 2.0) -> tuple[float, float, float]:
    if len(values) < period:
        last = values[-1] if values else 0.0
        return last, last, last
    window = values[-period:]
    middle = mean(window)
    deviation = pstdev(window) if len(window) > 1 else 0.0
    return middle - width * deviation, middle, middle + width * deviation


def support_resistance(candles: list[Candle], period: int = 20) -> tuple[float, float]:
    window = candles[-period:] if len(candles) >= period else candles
    if not window:
        return 0.0, 0.0
    return min(c.low for c in window), max(c.high for c in window)


def atr(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    ranges: list[float] = []
    window = candles[-(period + 1) :]
    for previous, current in zip(window, window[1:]):
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return mean(ranges) if ranges else 0.0


def momentum(values: list[float], lookback: int = 10) -> float:
    if len(values) <= lookback:
        return 0.0
    return values[-1] - values[-lookback]


def stochastic(candles: list[Candle], k_period: int = 14, d_period: int = 3) -> tuple[float, float]:
    """Stochastic Oscillator — returns (%K, %D).
    %K < 20 = oversold (bullish reversal), %K > 80 = overbought (bearish reversal).
    """
    if len(candles) < k_period:
        return 50.0, 50.0
    window = candles[-k_period:]
    lowest_low  = min(c.low  for c in window)
    highest_high = max(c.high for c in window)
    current_close = candles[-1].close
    if highest_high == lowest_low:
        k = 50.0
    else:
        k = (current_close - lowest_low) / (highest_high - lowest_low) * 100

    # Build a small %K series for %D (SMA of last d_period %K values)
    k_series: list[float] = []
    for i in range(max(0, len(candles) - k_period - d_period + 1), len(candles) - k_period + 1):
        seg = candles[i: i + k_period]
        lo = min(c.low  for c in seg)
        hi = max(c.high for c in seg)
        cl = candles[i + k_period - 1].close
        k_series.append(50.0 if hi == lo else (cl - lo) / (hi - lo) * 100)

    d = mean(k_series[-d_period:]) if len(k_series) >= d_period else k
    return k, d


def williams_r(candles: list[Candle], period: int = 14) -> float:
    """Williams %R — range -100 to 0.
    Above -20 = overbought (bearish), below -80 = oversold (bullish).
    """
    if len(candles) < period:
        return -50.0
    window = candles[-period:]
    highest_high = max(c.high  for c in window)
    lowest_low   = min(c.low   for c in window)
    current_close = candles[-1].close
    if highest_high == lowest_low:
        return -50.0
    return (highest_high - current_close) / (highest_high - lowest_low) * -100


def cci(candles: list[Candle], period: int = 20) -> float:
    """Commodity Channel Index.
    CCI > +100 = overbought, CCI < -100 = oversold.
    """
    if len(candles) < period:
        return 0.0
    window = candles[-period:]
    typical_prices = [(c.high + c.low + c.close) / 3 for c in window]
    tp_mean = mean(typical_prices)
    mean_deviation = mean(abs(tp - tp_mean) for tp in typical_prices)
    if mean_deviation == 0:
        return 0.0
    return (typical_prices[-1] - tp_mean) / (0.015 * mean_deviation)


def detect_candlestick(candles: list[Candle]) -> str:
    if len(candles) < 3:
        return "Neutral"
    prev2, previous, current = candles[-3], candles[-2], candles[-1]
    current_body = abs(current.close - current.open)
    candle_range = max(current.high - current.low, 0.00001)
    upper_wick = current.high - max(current.open, current.close)
    lower_wick = min(current.open, current.close) - current.low

    # Bullish Engulfing
    if current.close > current.open and previous.close < previous.open:
        if current.close >= previous.open and current.open <= previous.close:
            return "Bullish Engulfing"

    # Bearish Engulfing
    if current.close < current.open and previous.close > previous.open:
        if current.open >= previous.close and current.close <= previous.open:
            return "Bearish Engulfing"

    # Morning Star (3-candle bullish reversal)
    if (prev2.close < prev2.open and                    # first: big bearish
        abs(previous.close - previous.open) < abs(prev2.close - prev2.open) * 0.4 and  # second: small body
        current.close > current.open and                # third: bullish
        current.close > (prev2.open + prev2.close) / 2):
        return "Morning Star"

    # Evening Star (3-candle bearish reversal)
    if (prev2.close > prev2.open and
        abs(previous.close - previous.open) < abs(prev2.close - prev2.open) * 0.4 and
        current.close < current.open and
        current.close < (prev2.open + prev2.close) / 2):
        return "Evening Star"

    # Hammer (bullish — at bottom of downtrend)
    if lower_wick > current_body * 2 and upper_wick < candle_range * 0.25:
        return "Hammer"

    # Hanging Man (bearish — at top of uptrend)
    if lower_wick > current_body * 2 and upper_wick < candle_range * 0.25 and current.close < current.open:
        return "Hanging Man"

    # Shooting Star (bearish)
    if upper_wick > current_body * 2 and lower_wick < candle_range * 0.25:
        return "Shooting Star"

    # Doji (indecision)
    if current_body <= candle_range * 0.1:
        return "Doji"

    return "Neutral"
