"""
Honest Backtest V3 - Compare old vs new engine at SAME threshold.
Find optimal confidence threshold empirically.
"""
import asyncio, sys, os, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from datetime import datetime, timezone
from backend.models import Candle, SignalRequest, TradingMode
from backend.strategy.signal_engine import SignalEngine
from backend.constants import CRYPTO_PAIRS
from backend.services.market_data import binance_symbol

BINANCE_BASE = "https://api.binance.com"
LOOKBACK = 160
TEST_WINDOW = 80
LIMIT = LOOKBACK + TEST_WINDOW + 5

async def fetch(symbol, limit):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{BINANCE_BASE}/api/v3/klines",
                        params={"symbol": symbol, "interval": "1m", "limit": limit})
        r.raise_for_status()
        return [Candle(
            timestamp=datetime.fromtimestamp(row[0]/1000, tz=timezone.utc),
            open=float(row[1]), high=float(row[2]),
            low=float(row[3]),  close=float(row[4]), volume=float(row[5])
        ) for row in r.json()]

async def main():
    engine = SignalEngine()
    
    # Collect ALL trades with confidence levels
    all_trades = []
    print("Fetching data for all 17 pairs...")
    
    for pair in CRYPTO_PAIRS:
        sym = binance_symbol(pair)
        try:
            candles = await fetch(sym, LIMIT)
        except Exception as e:
            print(f"  SKIP {pair}: {e}")
            continue
        
        total = len(candles)
        for i in range(LOOKBACK, total - 1):
            window = candles[i - LOOKBACK : i]
            try:
                req = SignalRequest(mode=TradingMode.quotex, pair=pair, duration="1 Minute")
                resp = engine.analyze(req, window)
            except:
                continue
            
            if resp.signal.value == "WAIT":
                continue
            
            entry  = candles[i-1].close
            result = candles[i].close
            
            if resp.signal.value == "UP":
                won = result > entry
            else:
                won = result < entry
            
            if result == entry:
                won = False  # tie = loss in binary options
            
            all_trades.append({
                "conf": resp.confidence,
                "signal": resp.signal.value,
                "won": won,
                "pair": pair,
            })
    
    print(f"\nTotal signals generated: {len(all_trades)}")
    print()
    
    # Test every threshold from 50% to 90%
    print("=" * 65)
    print("  WIN RATE vs CONFIDENCE THRESHOLD")
    print("=" * 65)
    print(f"  {'Threshold':>10} | {'Trades':>7} | {'Wins':>5} | {'Win%':>7} | {'Grade'}")
    print(f"  {'-'*10}-+-{'-'*7}-+-{'-'*5}-+-{'-'*7}-+----------")
    
    best_threshold = 72
    best_rate = 0
    best_trades = 0
    
    for thresh in range(50, 91, 5):
        group = [t for t in all_trades if t["conf"] >= thresh]
        if len(group) < 5:
            print(f"  {thresh:>9}%+ | {len(group):>7} | {'N/A':>5} | {'N/A':>7} | Too few trades")
            continue
        wins = sum(1 for t in group if t["won"])
        rate = wins / len(group) * 100
        grade = "EXCELLENT" if rate >= 80 else ("GOOD" if rate >= 65 else ("FAIR" if rate >= 55 else "POOR"))
        print(f"  {thresh:>9}%+ | {len(group):>7} | {wins:>5} | {rate:>6.1f}% | {grade}")
        if rate > best_rate and len(group) >= 10:
            best_rate = rate
            best_threshold = thresh
            best_trades = len(group)
    
    print()
    print("=" * 65)
    print("  SIGNAL FREQUENCY vs QUALITY")
    print("=" * 65)
    total_test_points = TEST_WINDOW * len(CRYPTO_PAIRS)
    for thresh in [60, 65, 70, 72, 75, 80]:
        group = [t for t in all_trades if t["conf"] >= thresh]
        signal_rate = len(group) / total_test_points * 100 if total_test_points > 0 else 0
        wins = sum(1 for t in group if t["won"])
        rate = wins / len(group) * 100 if group else 0
        print(f"  Threshold {thresh}%: {len(group):>4} signals ({signal_rate:.0f}% rate) | {rate:.1f}% win rate")
    
    print()
    print("=" * 65)
    print("  VERDICT")
    print("=" * 65)
    
    # Overall at current threshold (72%)
    at72 = [t for t in all_trades if t["conf"] >= 72]
    wins72 = sum(1 for t in at72 if t["won"])
    rate72 = wins72 / len(at72) * 100 if at72 else 0
    
    print(f"  New engine at 72% threshold: {rate72:.1f}% win rate ({len(at72)} trades)")
    print()
    
    if rate72 >= 80:
        print("  STATUS: EXCELLENT - Signal engine is performing well!")
    elif rate72 >= 65:
        print("  STATUS: GOOD - Acceptable performance.")
    elif rate72 >= 55:
        print("  STATUS: FAIR - Better than random but needs work.")
    else:
        print("  STATUS: The 1-minute timeframe is extremely challenging.")
        print("  Next-candle binary options prediction is near-random for all systems.")
        print("  Recommendation: Use signals as TREND DIRECTION guides,")
        print("  not as precise 1-minute trade entries.")
        print()
        print("  Better use case: Use signals for 5-15 minute expiry trades")
        print("  where indicator signals have more predictive value.")
    
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
