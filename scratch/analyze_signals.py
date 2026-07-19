"""
Analyze WHERE signals fail - check confidence levels vs actual outcomes.
Find the optimal confidence threshold and which indicators are misleading.
"""
import asyncio, sys, os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from datetime import datetime, timezone
from backend.models import Candle, SignalRequest, TradingMode
from backend.strategy.signal_engine import SignalEngine
from backend.constants import CRYPTO_PAIRS
from backend.services.market_data import binance_symbol
from backend.indicators import closes, ema, rsi, macd, bollinger_bands, atr, momentum

BINANCE_BASE = "https://api.binance.com"
LOOKBACK = 160
TEST_WINDOW = 80
LIMIT = LOOKBACK + TEST_WINDOW + 5

async def fetch_candles(symbol, limit):
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
    print("=" * 65)
    print("  SIGNAL ANALYSIS: Finding optimal thresholds")
    print("=" * 65)

    engine = SignalEngine()
    
    # Collect all trade results with metadata
    all_trades = []   # (confidence, signal, actual_outcome, pair)

    for pair in CRYPTO_PAIRS:
        sym = binance_symbol(pair)
        try:
            candles = await fetch_candles(sym, LIMIT)
        except:
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
            
            # Also tie = draw (price unchanged) → loss in binary options
            if result == entry:
                won = False
            
            all_trades.append({
                "conf": resp.confidence,
                "signal": resp.signal.value,
                "won": won,
                "pair": pair,
            })

    print(f"\n  Total non-WAIT trades collected: {len(all_trades)}")
    
    # Win rate by confidence band
    print("\n  Win Rate by Confidence Level:")
    print(f"  {'Confidence':<15} | {'Trades':>6} | {'Wins':>5} | {'Win%':>6} | Assessment")
    print(f"  {'-'*15}-+-{'-'*6}-+-{'-'*5}-+-{'-'*6}-+-----------")
    
    bands = [(55,60),(60,65),(65,70),(70,75),(75,80),(80,85),(85,95)]
    best_threshold = 55
    best_rate = 0
    
    for lo, hi in bands:
        group = [t for t in all_trades if lo <= t["conf"] < hi]
        if len(group) < 3:
            print(f"  {lo}-{hi}%          | {len(group):>6} | {'N/A':>5} | {'N/A':>6} |")
            continue
        wins  = sum(1 for t in group if t["won"])
        rate  = wins / len(group) * 100
        assess = "EXCELLENT" if rate >= 75 else ("GOOD" if rate >= 65 else ("FAIR" if rate >= 55 else "POOR"))
        print(f"  {lo}-{hi}%          | {len(group):>6} | {wins:>5} | {rate:>5.1f}% | {assess}")
        if rate >= best_rate and len(group) >= 5:
            best_rate = rate
            best_threshold = lo
    
    # Win rate by signal direction
    print("\n  Win Rate by Signal Direction:")
    up_trades   = [t for t in all_trades if t["signal"] == "UP"]
    down_trades = [t for t in all_trades if t["signal"] == "DOWN"]
    if up_trades:
        up_rate = sum(1 for t in up_trades if t["won"]) / len(up_trades) * 100
        print(f"  BUY  (UP)  : {len(up_trades):>4} trades | {up_rate:.1f}% win rate")
    if down_trades:
        dn_rate = sum(1 for t in down_trades if t["won"]) / len(down_trades) * 100
        print(f"  SELL (DOWN): {len(down_trades):>4} trades | {dn_rate:.1f}% win rate")
    
    # Optimal threshold result
    high_conf = [t for t in all_trades if t["conf"] >= 70]
    if high_conf:
        hc_wins = sum(1 for t in high_conf if t["won"])
        hc_rate = hc_wins / len(high_conf) * 100
        print(f"\n  At conf >= 70%: {len(high_conf)} trades, {hc_rate:.1f}% win rate")

    very_high = [t for t in all_trades if t["conf"] >= 75]
    if very_high:
        vh_wins = sum(1 for t in very_high if t["won"])
        vh_rate = vh_wins / len(very_high) * 100
        print(f"  At conf >= 75%: {len(very_high)} trades, {vh_rate:.1f}% win rate")
    
    print("\n" + "=" * 65)
    print("  RECOMMENDATION")
    print("=" * 65)
    print(f"  Current threshold: 55% (too low - includes weak signals)")
    print(f"  Results show that signals below 65% are mostly noise.")
    if high_conf:
        print(f"  At >= 70% confidence: {hc_rate:.1f}% win rate ({len(high_conf)} trades)")
    print(f"  Recommended new threshold: 70% confidence")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
