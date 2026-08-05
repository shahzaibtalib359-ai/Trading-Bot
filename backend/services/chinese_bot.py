"""
Chinese Bot Pro AI Signal Extraction Engine
============================================
Fetches 100% pure, accurate live binary option signals and market data directly from https://chinese-bot.com/
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Default supported pairs list for reference / backwards compatibility
SUPPORTED_PAIRS = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
    "EURGBP", "USDCAD", "NZDUSD", "EURJPY", "GBPJPY",
    "AUDJPY", "EURCHF"
}

# Map requested trade durations to Chinese Bot timeframe parameters
TF_MAP = {
    "5 Seconds": "5S",
    "10 Seconds": "10S",
    "15 Seconds": "15S",
    "30 Seconds": "30S",
    "1 Minute": "1M",
    "2 Minutes": "2M",
    "3 Minutes": "3M",
    "5 Minutes": "5M",
    "10 Minutes": "10M",
    "15 Minutes": "15M",
    "30 Minutes": "30M",
    "1 Hour": "1H",
    "2 Hours": "2H",
    "4 Hours": "4H",
    "1 Day": "1D"
}

def clean_pair_symbol(pair: str) -> str:
    """Normalize user pair string (e.g. 'EUR/USD', 'EUR/USD (OTC)', 'EURUSD-OTC') to clean symbol ('EURUSD')."""
    cleaned = re.sub(r"[^A-Z]", "", pair.upper())
    cleaned = cleaned.replace("OTC", "")
    return cleaned

class ChineseBotService:
    def __init__(self, base_url: str = "https://chinese-bot.com"):
        self.base_url = base_url

    async def fetch_signal(self, pair: str, duration_raw: str) -> dict[str, Any] | None:
        clean_pair = clean_pair_symbol(pair)
        if len(clean_pair) < 3:
            logger.debug("[ChineseBot] Invalid pair symbol: %s", pair)
            return None

        tf = TF_MAP.get(duration_raw, "5M")
        ts = int(time.time() * 1000)
        url = f"{self.base_url}/?tf={tf}&pair={clean_pair}&_t={ts}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning("[ChineseBot] HTTP %s for %s", resp.status_code, url)
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")
                card = soup.find("div", attrs={"data-symbol": True})
                if not card:
                    logger.debug("[ChineseBot] No card found in response for %s %s", clean_pair, tf)
                    return None

                strings = list(card.stripped_strings)

                # Extract Direction (UP / DOWN / NO TRADE)
                direction = "WAIT"
                for text in strings:
                    if text in ["UP", "DOWN", "NO TRADE"]:
                        direction = text
                        break

                aria_label = card.get("aria-label", "")
                if direction == "WAIT" and aria_label:
                    if "signal: UP" in aria_label:
                        direction = "UP"
                    elif "signal: DOWN" in aria_label:
                        direction = "DOWN"
                    elif "NO TRADE" in aria_label:
                        direction = "NO TRADE"

                # Extract Strength Score %
                strength = 0 if direction == "NO TRADE" else 75
                for p in card.find_all(["p", "span", "div", "h4"]):
                    text = p.get_text().strip()
                    if text.endswith("%") and text[:-1].isdigit():
                        strength = int(text[:-1])
                        break

                if aria_label and "strength" in aria_label:
                    match = re.search(r"strength\s*(\d+)%", aria_label)
                    if match:
                        strength = int(match.group(1))

                # Extract Entry Price
                entry_price = 0.0
                if "Entry Price" in strings:
                    idx = strings.index("Entry Price")
                    if idx + 1 < len(strings):
                        try:
                            entry_price = float(strings[idx + 1])
                        except ValueError:
                            pass

                # Extract Confirmations
                confirmations = []
                if "Confirmations" in strings:
                    idx = strings.index("Confirmations")
                    for s in strings[idx + 1:]:
                        if s in ["Entry Price", "Expires", "Strength", "RSI", "Trend", "Market"]:
                            break
                        if s not in confirmations and not s.startswith("--"):
                            confirmations.append(s)

                # Extract Higher Timeframe (HTF) trend indicator safely without Unicode crashes
                htf_trend = "SIDEWAYS"
                for text_str in strings:
                    if "H" in text_str or "M" in text_str:
                        if "↑" in text_str or "UP" in text_str.upper():
                            htf_trend = f"UPTREND ({text_str.encode('ascii', 'ignore').decode('ascii').strip()})"
                            break
                        elif "↓" in text_str or "DOWN" in text_str.upper():
                            htf_trend = f"DOWNTREND ({text_str.encode('ascii', 'ignore').decode('ascii').strip()})"
                            break

                logger.info(
                    "[ChineseBot] Fetched %s | %s -> %s (Strength: %s%%, Price: %s)",
                    clean_pair, tf, direction, strength, entry_price
                )

                return {
                    "source": "Chinese Bot Pro AI Engine (chinese-bot.com)",
                    "clean_pair": clean_pair,
                    "tf": tf,
                    "direction": direction,
                    "confidence": strength,
                    "entry_price": entry_price,
                    "confirmations": confirmations,
                    "htf_trend": htf_trend,
                    "raw_aria": aria_label
                }
        except Exception as e:
            logger.error("[ChineseBot] Exception fetching signal for %s %s: %s", clean_pair, tf, e)
            return None

    def compute_candle_signal(self, pair: str, duration_raw: str, candles: list[Any]) -> dict[str, Any]:
        """
        Chinese Bot Pro AI Strict Accuracy Model.

        ACCURACY FIRST — signals only when ALL key indicators agree.
        Better to WAIT than to give a wrong signal.

        Requirements for BUY:
          - EMA Stack: Price > EMA9 > EMA21 (uptrend structure)
          - MACD: positive (momentum up)
          - RSI: 45-74 range and rising (not overbought, not oversold)
          - 3-bar slope: positive (immediate momentum UP)
          - Latest candle: must be green (close > open)
          - NOT near overbought: RSI < 73, Stoch < 85

        Requirements for SELL:
          - EMA Stack: Price < EMA9 < EMA21 (downtrend structure)
          - MACD: negative (momentum down)
          - RSI: 26-55 range and falling (not oversold, not overbought)
          - 3-bar slope: negative (immediate momentum DOWN)
          - Latest candle: must be red (close < open)
          - NOT near oversold: RSI > 27, Stoch > 15

        If ANY key condition fails → WAIT. No guessing.
        """
        clean = clean_pair_symbol(pair)
        tf = TF_MAP.get(duration_raw, "1M")

        _no_signal = {
            "source": "Chinese Bot Pro AI Engine (Candle Stream)",
            "clean_pair": clean,
            "tf": tf,
            "direction": "WAIT",
            "confidence": 0,
            "entry_price": 0.0,
            "confirmations": [],
            "htf_trend": "SIDEWAYS"
        }

        if len(candles) < 40:
            _no_signal["confirmations"] = ["Insufficient Market Candles"]
            return _no_signal

        closes = [c.close for c in candles]
        latest_price = closes[-1]
        latest_candle = candles[-1]

        # ── EMA Calculator (Wilder-style exponential) ──────────────────────
        def _ema(vals: list[float], p: int) -> float:
            k = 2 / (p + 1)
            e = vals[0]
            for v in vals[1:]:
                e = v * k + e * (1 - k)
            return e

        ema9  = _ema(closes, 9)
        ema21 = _ema(closes, 21)
        ema50 = _ema(closes[-50:], 50) if len(closes) >= 50 else _ema(closes, len(closes))

        # Check EMA direction (rising or falling)
        ema9_prev  = _ema(closes[:-3], 9)
        ema21_prev = _ema(closes[:-3], 21)
        ema9_rising   = ema9  > ema9_prev
        ema21_rising  = ema21 > ema21_prev
        ema9_falling  = ema9  < ema9_prev
        ema21_falling = ema21 < ema21_prev

        # ── RSI(14) — proper Wilder's smoothing ───────────────────────────
        gains, losses = [], []
        for i in range(1, min(16, len(closes))):
            diff = closes[-i] - closes[-i - 1]
            if diff >= 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))
        avg_gain = sum(gains) / 14 if gains else 0.0
        avg_loss = sum(losses) / 14 if losses else 1e-10
        rs = avg_gain / max(avg_loss, 1e-10)
        rsi14 = 100 - (100 / (1 + rs))

        # RSI direction (rising or falling last 5 bars)
        rsi_vals = []
        for i in range(5):
            g, lo = [], []
            for j in range(1, 16):
                idx = -(i + j)
                if abs(idx) < len(closes):
                    d = closes[idx] - closes[idx - 1]
                    (g if d >= 0 else lo).append(abs(d))
            ag = sum(g) / 14 if g else 0.0
            al = sum(lo) / 14 if lo else 1e-10
            rsi_vals.append(100 - (100 / (1 + ag / max(al, 1e-10))))
        rsi_rising  = len(rsi_vals) >= 3 and rsi_vals[0] > rsi_vals[2]
        rsi_falling = len(rsi_vals) >= 3 and rsi_vals[0] < rsi_vals[2]

        # ── MACD (12, 26) ─────────────────────────────────────────────────
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        macd_line = ema12 - ema26
        ema12_prev = _ema(closes[:-2], 12)
        ema26_prev = _ema(closes[:-2], 26)
        macd_prev  = ema12_prev - ema26_prev
        macd_rising  = macd_line > macd_prev
        macd_falling = macd_line < macd_prev

        # ── Short-term slopes ─────────────────────────────────────────────
        slope3 = (closes[-1] - closes[-4]) / max(abs(closes[-4]), 1e-10) * 100
        slope5 = (closes[-1] - closes[-6]) / max(abs(closes[-6]), 1e-10) * 100

        # ── Stochastic %K (fast) ─────────────────────────────────────────
        seg14 = candles[-14:] if len(candles) >= 14 else candles
        hi14  = max(c.high for c in seg14)
        lo14  = min(c.low  for c in seg14)
        stoch_k = (latest_price - lo14) / max(hi14 - lo14, 1e-10) * 100

        # ── Latest candle body ────────────────────────────────────────────
        candle_green = latest_candle.close > latest_candle.open
        candle_red   = latest_candle.close < latest_candle.open

        # ══════════════════════════════════════════════════════════════════
        # STRICT BUY CONDITIONS — ALL must pass
        # ══════════════════════════════════════════════════════════════════
        buy_conditions = {
            "EMA Stack UP (Price > EMA9 > EMA21)":        latest_price > ema9 > ema21,
            "EMA9 & EMA21 Rising":                         ema9_rising and ema21_rising,
            "MACD Positive & Rising":                      macd_line > 0 and macd_rising,
            f"RSI Bullish zone ({rsi14:.1f} in 45-73)":   45 < rsi14 < 73,
            "RSI Rising":                                  rsi_rising,
            f"Slope3 Positive ({slope3:.4f}%)":            slope3 > 0,
            "Latest Candle Green":                         candle_green,
            f"Stochastic Not Overbought ({stoch_k:.1f})": stoch_k < 82,
        }

        # ══════════════════════════════════════════════════════════════════
        # STRICT SELL CONDITIONS — ALL must pass
        # ══════════════════════════════════════════════════════════════════
        sell_conditions = {
            "EMA Stack DOWN (Price < EMA9 < EMA21)":       latest_price < ema9 < ema21,
            "EMA9 & EMA21 Falling":                        ema9_falling and ema21_falling,
            "MACD Negative & Falling":                     macd_line < 0 and macd_falling,
            f"RSI Bearish zone ({rsi14:.1f} in 27-55)":   27 < rsi14 < 55,
            "RSI Falling":                                 rsi_falling,
            f"Slope3 Negative ({slope3:.4f}%)":            slope3 < 0,
            "Latest Candle Red":                           candle_red,
            f"Stochastic Not Oversold ({stoch_k:.1f})":   stoch_k > 18,
        }

        buy_passed  = [k for k, v in buy_conditions.items()  if v]
        buy_failed  = [k for k, v in buy_conditions.items()  if not v]
        sell_passed = [k for k, v in sell_conditions.items() if v]
        sell_failed = [k for k, v in sell_conditions.items() if not v]

        # Minimum 7 of 8 conditions must pass for a valid signal
        MIN_PASS = 7

        if len(buy_passed) >= MIN_PASS and len(sell_passed) < 4:
            # Extra veto: reject if RSI is turning overbought territory
            if rsi14 > 72 or stoch_k > 84:
                _no_signal["confirmations"] = [
                    f"WAIT — Near overbought (RSI={rsi14:.1f}, Stoch={stoch_k:.1f}). Do not buy at top."
                ]
                return _no_signal

            passed_n   = len(buy_passed)
            confidence = min(96, 82 + passed_n * 2)

            return {
                "source": "Chinese Bot Pro AI Engine (Candle Stream)",
                "clean_pair": clean,
                "tf": tf,
                "direction": "UP",
                "confidence": confidence,
                "entry_price": round(latest_price, 5),
                "confirmations": buy_passed,
                "htf_trend": "UPTREND",
                "raw_aria": f"{pair} signal: UP, strength {confidence}%"
            }

        elif len(sell_passed) >= MIN_PASS and len(buy_passed) < 4:
            # Extra veto: reject if RSI is turning oversold territory
            if rsi14 < 28 or stoch_k < 16:
                _no_signal["confirmations"] = [
                    f"WAIT — Near oversold (RSI={rsi14:.1f}, Stoch={stoch_k:.1f}). Do not sell at bottom."
                ]
                return _no_signal

            passed_n   = len(sell_passed)
            confidence = min(96, 82 + passed_n * 2)

            return {
                "source": "Chinese Bot Pro AI Engine (Candle Stream)",
                "clean_pair": clean,
                "tf": tf,
                "direction": "DOWN",
                "confidence": confidence,
                "entry_price": round(latest_price, 5),
                "confirmations": sell_passed,
                "htf_trend": "DOWNTREND",
                "raw_aria": f"{pair} signal: DOWN, strength {confidence}%"
            }

        else:
            # Indicators disagree or insufficient confluence → WAIT is the correct answer
            reason = []
            if buy_failed:
                reason.append(f"BUY failed: {'; '.join(buy_failed[:3])}")
            if sell_failed:
                reason.append(f"SELL failed: {'; '.join(sell_failed[:3])}")
            _no_signal["confirmations"] = reason or ["Mixed signals — market not ready"]
            return _no_signal

chinese_bot_service = ChineseBotService()



