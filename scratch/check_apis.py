"""
API Key & Data Source Health Check
====================================
Yeh script check karta hai:
1. Binance API connected hai ya nahi
2. Yahoo Finance forex data aa raha hai ya nahi
3. Konse pairs pe actual live data milta hai
4. Signal engine kaam kar rahi hai ya nahi

Run karo: python -m scratch.check_apis
"""
import asyncio
import httpx
import sys
import os
from datetime import datetime, timezone

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✅ {msg}{RESET}")
def fail(msg):  print(f"  {RED}❌ {msg}{RESET}")
def warn(msg):  print(f"  {YELLOW}⚠️  {msg}{RESET}")
def info(msg):  print(f"  {CYAN}ℹ️  {msg}{RESET}")

async def check_binance():
    print(f"\n{BOLD}━━━ 1. BINANCE API CHECK ━━━{RESET}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Ping
            r = await client.get("https://api.binance.com/api/v3/ping")
            if r.status_code == 200:
                ok("Binance API reachable ✓")
            else:
                fail(f"Binance ping failed: HTTP {r.status_code}")
                return False

            # Server time
            r2 = await client.get("https://api.binance.com/api/v3/time")
            server_time = r2.json().get("serverTime", 0)
            local_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            diff_ms = abs(server_time - local_time)
            if diff_ms < 5000:
                ok(f"Binance server time synced (diff={diff_ms}ms)")
            else:
                warn(f"Time diff large: {diff_ms}ms — may cause issues")

            # EUR/USD OTC data test (EURUSDT)
            r3 = await client.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": "EURUSDT", "interval": "1m", "limit": 5}
            )
            if r3.status_code == 200:
                candles = r3.json()
                latest_price = float(candles[-1][4])
                ok(f"EURUSDT live data: price={latest_price:.5f} ({len(candles)} candles)")
            else:
                fail(f"EURUSDT data fetch failed: {r3.status_code}")

            # BTC/USDT
            r4 = await client.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": "BTCUSDT", "interval": "1m", "limit": 3}
            )
            if r4.status_code == 200:
                btc_price = float(r4.json()[-1][4])
                ok(f"BTCUSDT live data: price={btc_price:.2f}")
            
            return True

    except Exception as e:
        fail(f"Binance unreachable: {e}")
        return False


async def check_yahoo_forex():
    print(f"\n{BOLD}━━━ 2. YAHOO FINANCE FOREX CHECK ━━━{RESET}")
    pairs = {
        "EUR/USD": "EURUSD=X",
        "USD/JPY": "USDJPY=X",
        "GBP/USD": "GBPUSD=X",
        "AUD/USD": "AUDUSD=X",
    }
    all_ok = True
    import time
    for pair, symbol in pairs.items():
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                r = await client.get(url, params={
                    "interval": "1m", "range": "1d",
                    "_": str(int(time.time())),
                }, headers={
                    "User-Agent": "Mozilla/5.0",
                    "Cache-Control": "no-cache",
                })
                if r.status_code == 200:
                    data = r.json()
                    result = (data.get("chart", {}).get("result") or [{}])[0]
                    timestamps = result.get("timestamp") or []
                    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
                    closes = quotes.get("close") or []
                    valid = [c for c in closes if c is not None]
                    
                    if len(valid) >= 10:
                        unique = len(set(round(v, 6) for v in valid[-10:]))
                        latest = valid[-1]
                        if unique > 2:
                            ok(f"{pair} ({symbol}): price={latest:.5f}, {len(valid)} candles, {unique} unique — LIVE ✓")
                        else:
                            warn(f"{pair}: data may be STALE ({unique} unique closes) — market may be closed")
                    else:
                        warn(f"{pair}: only {len(valid)} candles returned — insufficient data")
                else:
                    fail(f"{pair}: Yahoo Finance HTTP {r.status_code}")
                    all_ok = False
        except Exception as e:
            fail(f"{pair}: {e}")
            all_ok = False
    return all_ok


async def check_signal_engine():
    print(f"\n{BOLD}━━━ 3. SIGNAL ENGINE LIVE TEST ━━━{RESET}")
    print("  Testing best OTC pairs with real Binance data...\n")
    
    try:
        from backend.models import SignalRequest, TradingMode
        from backend.strategy.signal_engine import SignalEngine
        from backend.services.market_data import BinanceMarketDataProvider, _fetch_binance_klines
        
        engine = SignalEngine()
        binance = BinanceMarketDataProvider()
        
        # Best pairs — Binance direct data (EUR/USD OTC → EURUSDT)
        # NOTE: NZD/USD OTC removed — NZDUSDT doesn't exist on Binance, uses Yahoo Finance
        test_pairs = [
            ("EUR/USD OTC",   "EURUSDT",  TradingMode.quotex),
            ("GBP/USD OTC",   "GBPUSDT",  TradingMode.quotex),
            ("AUD/USD OTC",   "AUDUSDT",  TradingMode.quotex),
            ("NZD/USD OTC",   None,        TradingMode.quotex),  # Yahoo Finance fallback
            ("Bitcoin (OTC)", None,        TradingMode.quotex),
            ("Ethereum (OTC)",None,        TradingMode.quotex),
            ("BTC/USDT",      None,        TradingMode.crypto),
            ("ETH/USDT",      None,        TradingMode.crypto),
            ("SOL/USDT",      None,        TradingMode.crypto),
        ]

        print(f"  {'PAIR':<20} | {'SIGNAL':<6} | {'CONF':>4} | {'EDGE':>4} | STATUS")
        print(f"  {'-'*70}")

        results = []
        for pair, binance_sym, mode in test_pairs:
            req = SignalRequest(mode=mode, pair=pair, duration="1 Minute")
            try:
                if binance_sym:
                    # Direct Binance fetch (fastest — 0 delay)
                    candles = await _fetch_binance_klines(binance_sym, 160)
                else:
                    # Use full auto router → Yahoo Finance / Binance fallback as needed
                    from backend.services.market_data import AutoMarketDataProviderRouter
                    router = AutoMarketDataProviderRouter()
                    candles = await router.get_candles(mode, pair, limit=160)

                res = engine.analyze(req, candles)

                # Parse edge from analysis
                edge = 0
                for line in res.analysis:
                    if 'Edge=' in line:
                        try:
                            edge = int(line.split('Edge=')[1].split('pt')[0])
                        except Exception:
                            pass
                        break

                sig_color = GREEN if res.signal.value in ("BUY", "SELL") else YELLOW
                results.append((pair, res.signal.value, res.confidence, edge))
                print(f"  {pair:<20} | {sig_color}{res.signal.value:<6}{RESET} | {res.confidence:>3}% | {edge:>4}pt | {'🔥 TRADE!' if res.signal.value != 'WAIT' else 'waiting...'}")

            except Exception as e:
                print(f"  {pair:<20} | {RED}ERROR{RESET}  | --- | ---- | {str(e)[:55]}")


        # Summary
        tradeable = [r for r in results if r[1] != "WAIT"]
        print(f"\n  {BOLD}Summary: {len(tradeable)}/{len(results)} pairs have active signals right now{RESET}")
        if tradeable:
            print(f"\n  {GREEN}🏆 BEST PAIRS TO TRADE RIGHT NOW:{RESET}")
            for pair, sig, conf, edge in sorted(tradeable, key=lambda x: x[2], reverse=True):
                print(f"    → {pair}: {sig} @ {conf}% confidence (edge={edge}pt)")

    except Exception as e:
        fail(f"Signal engine test failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print(f"\n{BOLD}{CYAN}{'='*55}")
    print(f"  TRADING BOT — API & SIGNAL HEALTH CHECK")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}{RESET}")

    binance_ok = await check_binance()
    yahoo_ok   = await check_yahoo_forex()
    await check_signal_engine()

    print(f"\n{BOLD}━━━ RESULT SUMMARY ━━━{RESET}")
    ok("Binance API: WORKING") if binance_ok else fail("Binance API: FAILED")
    ok("Yahoo Finance: WORKING") if yahoo_ok else warn("Yahoo Finance: Limited (weekend/after-hours?)")
    
    print(f"""
{BOLD}{CYAN}━━━ TRADING GUIDE ━━━{RESET}

{BOLD}🏆 BEST PAIRS (in order):{RESET}
  1. EUR/USD OTC  — Binance data (most liquid, 0-delay)
  2. GBP/USD OTC  — Binance data (high volatility, good trends)
  3. Bitcoin (OTC) — Binance BTCUSDT (24/7, strong trends)
  4. Ethereum (OTC)— Binance ETHUSDT (24/7, clear signals)
  5. AUD/USD OTC  — Binance data (good daytime signals)

{BOLD}❌ AVOID THESE PAIRS:{RESET}
  • USD/JPY OTC, EUR/JPY OTC, GBP/JPY OTC — Yahoo Finance only (delayed)
  • USD/CHF OTC, EUR/CHF OTC — Yahoo Finance only
  • Any exotic pair (USD/BRL, USD/TRY etc.) — unreliable data

{BOLD}⏱️ CANDLE TIMING — JAB SIGNAL AAYE TO:{RESET}
  • Signal message mein "TRADE NOW" likha ho → CURRENT candle pe trade karo
  • Signal message mein "WAIT for NEXT candle" likha ho → Abhi DO NOT trade
    Agli candle start hone ka wait karo, phir enter karo
  • KABHI BHI candle ke beech mein mat jaao — sirf candle open par jaao

{BOLD}📊 SIGNAL ACCURACY TIPS:{RESET}
  • Sirf 75%+ confidence signals pe trade karo
  • WAIT signal aaye to bilkul mat trade karo — "jaldi" NAHI karni
  • 9/10 win chahiye to har WAIT signal pe RUKO
  • 1 minute expiry best hai OTC pairs ke liye
""")

if __name__ == "__main__":
    asyncio.run(main())
