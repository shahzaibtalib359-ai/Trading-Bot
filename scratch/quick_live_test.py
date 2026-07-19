"""Quick 3-trade live test - forces signals even in low volume by using 
any non-WAIT signal OR picks the highest confidence pair and trades it."""
import asyncio, sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from backend.models import Candle, SignalRequest, TradingMode
from backend.strategy.signal_engine import SignalEngine
from backend.services.market_data import BinanceMarketDataProvider
from backend.constants import CRYPTO_PAIRS
from backend.services.market_data import binance_symbol

BINANCE_BASE = "https://api.binance.com"

async def get_price(symbol):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{BINANCE_BASE}/api/v3/ticker/price", params={"symbol": symbol})
        r.raise_for_status()
        return float(r.json()["price"])

PAIRS = [
    ("Ethereum (OTC)",     "ETHUSDT"),
    ("Solana (OTC)",       "SOLUSDT"),
    ("Bitcoin (OTC)",      "BTCUSDT"),
    ("Binance Coin (OTC)", "BNBUSDT"),
    ("Ripple (OTC)",       "XRPUSDT"),
    ("Avalanche (OTC)",    "AVAXUSDT"),
    ("Litecoin (OTC)",     "LTCUSDT"),
    ("Polkadot (OTC)",     "DOTUSDT"),
    ("Chainlink (OTC)",    "LINKUSDT"),
    ("Dash (OTC)",         "DASHUSDT"),
]

async def main():
    engine   = SignalEngine()
    provider = BinanceMarketDataProvider()
    
    print("=" * 65)
    print("  QUOTEX LIVE 3-TRADE TEST")
    print("=" * 65)
    now = datetime.now(timezone.utc)
    print(f"  Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()
    
    results = []
    
    for trade_round in range(1, 4):  # 3 trades
        print(f"  --- TRADE #{trade_round} ---")
        
        # Scan all pairs, pick highest confidence non-WAIT signal
        best_conf = -1
        best_resp = None
        best_pair = None
        best_sym  = None
        best_candles = None
        
        print("  Scanning pairs for best signal...")
        for pair_name, sym in PAIRS:
            try:
                candles = await provider.get_candles(TradingMode.quotex, pair_name, limit=160)
                req     = SignalRequest(mode=TradingMode.quotex, pair=pair_name, duration="1 Minute")
                resp    = engine.analyze(req, candles)
                
                print(f"    {pair_name:<28} | {resp.signal.value:<4} | conf={resp.confidence}%")
                
                if resp.signal.value != "WAIT" and resp.confidence > best_conf:
                    best_conf    = resp.confidence
                    best_resp    = resp
                    best_pair    = pair_name
                    best_sym     = sym
                    best_candles = candles
            except Exception as e:
                print(f"    {pair_name:<28} | ERR: {e}")
        
        # If no directional signal, use HIGHEST confidence pair regardless of WAIT
        if best_resp is None:
            print("\n  No directional signals - picking highest confidence pair...")
            for pair_name, sym in PAIRS:
                try:
                    candles = await provider.get_candles(TradingMode.quotex, pair_name, limit=160)
                    req     = SignalRequest(mode=TradingMode.quotex, pair=pair_name, duration="1 Minute")
                    resp    = engine.analyze(req, candles)
                    
                    # Override WAIT based on bull/bear points (pick direction manually)
                    from backend.indicators import closes, ema, rsi, macd, momentum
                    prices = closes(candles)
                    e9     = ema(prices, 9)
                    e21    = ema(prices, 21)
                    mom    = momentum(prices, 10)
                    _, _, mh = macd(prices)
                    
                    # Create a forced signal based on dominant indicators
                    if e9 > e21 and mh > 0 and mom > 0:
                        from backend.models import SignalAction
                        resp.signal = SignalAction.buy
                        resp.confidence = max(resp.confidence, 55)
                    elif e9 < e21 and mh < 0 and mom < 0:
                        from backend.models import SignalAction
                        resp.signal = SignalAction.sell
                        resp.confidence = max(resp.confidence, 55)
                    else:
                        continue
                    
                    if resp.signal.value != "WAIT" and resp.confidence > best_conf:
                        best_conf    = resp.confidence
                        best_resp    = resp
                        best_pair    = pair_name
                        best_sym     = sym
                        best_candles = candles
                except:
                    continue
        
        if best_resp is None or best_pair is None:
            print("  No suitable signal found for this round. Market is very quiet.")
            continue
        
        # Execute the trade
        entry = best_resp.current_price
        sig   = best_resp.signal.value
        conf  = best_resp.confidence
        
        print(f"\n  TRADE: {best_pair}")
        print(f"  Signal: {sig} | Confidence: {conf}%")
        print(f"  Entry Price: {entry:.5f}")
        print(f"  Waiting 62 seconds...")
        
        await asyncio.sleep(62)
        
        # Result
        try:
            exit_price = await get_price(best_sym)
        except Exception as e:
            print(f"  Exit price fetch failed: {e}")
            continue
        
        change_pct = abs(exit_price - entry) / entry * 100
        won = (sig == "UP" and exit_price > entry) or (sig == "DOWN" and exit_price < entry)
        icon = "WIN " if won else "LOSS"
        
        results.append({"pair": best_pair, "sig": sig, "conf": conf, 
                        "entry": entry, "exit": exit_price, "won": won})
        
        wins_now = sum(1 for r in results if r["won"])
        print(f"  Exit:  {exit_price:.5f} | Change: {change_pct:.4f}%")
        print(f"  Result: [{icon}] | Score: {wins_now}/{trade_round}")
        print()
        
        await asyncio.sleep(3)
    
    # Summary
    print("=" * 65)
    print("  3-TRADE TEST SUMMARY")
    print("=" * 65)
    if results:
        wins = sum(1 for r in results if r["won"])
        rate = wins / len(results) * 100
        print(f"  Wins: {wins}/{len(results)} = {rate:.0f}%")
        print()
        for i, r in enumerate(results, 1):
            icon = "WIN " if r["won"] else "LOSS"
            print(f"  {i}. {r['pair']:<25} {r['sig']:<4} conf={r['conf']}% -> [{icon}]")
        print()
        verdict = "GOOD" if rate >= 66 else "NEEDS IMPROVEMENT"
        print(f"  VERDICT: {verdict}")
    else:
        print("  Market too quiet for signals (Sunday low-volume)")
        print("  Try again Monday 09:00+ UTC for active market")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
