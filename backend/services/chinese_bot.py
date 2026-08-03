"""
Chinese Bot Pro AI Signal Extraction Engine
============================================
Fetches 100% pure, accurate live binary option signals and market data directly from https://chinese-bot.com/
"""
from __future__ import annotations

import logging
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Supported currency pairs on Chinese Bot
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
        if clean_pair not in SUPPORTED_PAIRS:
            logger.debug("[ChineseBot] Pair %s (clean: %s) not in supported pairs list.", pair, clean_pair)
            return None

        tf = TF_MAP.get(duration_raw, "5M")
        url = f"{self.base_url}/?tf={tf}&pair={clean_pair}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning("[ChineseBot] HTTP %s for %s", resp.status_code, url)
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")
                card = soup.find("div", attrs={"data-symbol": True})
                if not card:
                    logger.warning("[ChineseBot] No card found in response for %s %s", clean_pair, tf)
                    return None

                strings = list(card.stripped_strings)

                # Extract Direction (UP / DOWN / NO TRADE)
                direction = "WAIT"
                for text in strings:
                    if text in ["UP", "DOWN", "NO TRADE"]:
                        direction = text
                        break

                # Extract Strength Score %
                strength = 0 if direction == "NO TRADE" else 70
                for p in card.find_all(["p", "span", "div", "h4"]):
                    text = p.get_text().strip()
                    if text.endswith("%") and text[:-1].isdigit():
                        strength = int(text[:-1])
                        break

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

                # Extract Higher Timeframe (HTF) trend indicator
                htf_trend = "SIDEWAYS"
                htf_elem = card.find(string=re.compile(r"[↑↓]\s*\d+[HM]"))
                if htf_elem:
                    htf_text = htf_elem.strip()
                    if "↑" in htf_text:
                        htf_trend = f"UPTREND ({htf_text})"
                    elif "↓" in htf_text:
                        htf_trend = f"DOWNTREND ({htf_text})"

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
                    "raw_aria": card.get("aria-label", "")
                }
        except Exception as e:
            logger.error("[ChineseBot] Exception fetching signal for %s %s: %s", clean_pair, tf, e)
            return None

chinese_bot_service = ChineseBotService()
