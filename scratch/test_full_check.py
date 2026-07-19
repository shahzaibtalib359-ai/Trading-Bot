"""Comprehensive test: Gold, Forex market hours, and Quotex deep analysis."""
import asyncio
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.market_data import (
    is_forex_market_open, _COMMODITY_PAIRS,
    YahooFinanceForexProvider, XmMarketDataProvider,
)
from backend.models import TradingMode, SignalRequest
from backend.signal_manager import SignalManager


async def main():
    now = datetime.now(timezone.utc)
    print("=" * 65)
    print("  FULL SYSTEM CHECK")
    print("=" * 65)
    print(f"  Current UTC: {now.strftime('%A %Y-%m-%d %H:%M UTC')}")
    market_open = is_forex_market_open()
    status_str = "OPEN" if market_open else "CLOSED (weekend/after-hours)"
    print(f"  Forex Market: {status_str}")

    # 1. Gold / Silver
    print()
    print("-- Gold & Silver Test --")
    for pair, label in [("XAU/USD", "Gold"), ("XAG/USD", "Silver")]:
        try:
            p = YahooFinanceForexProvider()
            candles = await p.get_candles(TradingMode.forex, pair, limit=50)
            unique = len(set(round(c.close, 4) for c in candles[-20:]))
            live = "LIVE" if unique > 1 else "STALE"
            print(f"  [{label}] {pair}: price={candles[-1].close:.4f} | candles={len(candles)} | {live}")
        except Exception as e:
            print(f"  [{label}] {pair}: FAILED -- {e}")

    # 2. Forex market-closed guard
    print()
    print("-- Forex Market Guard Test --")
    for pair in ["EUR/USD", "GBP/USD", "USD/JPY"]:
        try:
            p = XmMarketDataProvider()
            candles = await p.get_candles(TradingMode.forex, pair, limit=50)
            print(f"  [OK]     {pair}: price={candles[-1].close:.5f} | candles={len(candles)}")
        except RuntimeError as e:
            msg = str(e)
            if "CLOSED" in msg:
                print(f"  [CLOSED] {pair}: Market correctly blocked")
            else:
                print(f"  [ERR]    {pair}: {msg[:80]}")

    # 3. Quotex OTC deep analysis
    print()
    print("-- Quotex OTC Deep Analysis --")
    manager = SignalManager()
    quotex_pairs = [
        ("EUR/USD OTC", "1 Minute"),
        ("GBP/USD OTC", "1 Minute"),
        ("Bitcoin (OTC)", "1 Minute"),
        ("Ethereum (OTC)", "1 Minute"),
        ("Solana (OTC)", "1 Minute"),
    ]
    issues = []
    for pair, dur in quotex_pairs:
        try:
            req = SignalRequest(mode=TradingMode.quotex, pair=pair, duration=dur)
            resp = await manager.generate(req)
            probs = []
            if resp.confidence == 0:
                probs.append("confidence=0")
            if resp.current_price == 0:
                probs.append("price=0")
            if len(resp.analysis) < 4:
                probs.append(f"only {len(resp.analysis)} analysis lines")
            icon = "OK  " if not probs else "WARN"
            print(f"  [{icon}] {pair}: signal={resp.signal.value} conf={resp.confidence}% price={resp.current_price:.4f}")
            if resp.data_warning:
                print(f"        WARNING: {resp.data_warning[:70]}")
            if probs:
                issues.append(f"{pair}: {', '.join(probs)}")
        except RuntimeError as e:
            msg = str(e)
            tag = "CLOSED" if "CLOSED" in msg else "ERR   "
            print(f"  [{tag}] {pair}: {msg[:80]}")
            issues.append(f"{pair}: {msg[:60]}")

    # Summary
    print()
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    print(f"  Forex market: {status_str}")
    if issues:
        print(f"  Issues found ({len(issues)}):")
        for i in issues:
            print(f"    - {i}")
    else:
        print("  All checks PASSED -- no issues found.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
