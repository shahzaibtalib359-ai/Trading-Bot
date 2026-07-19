"""Deep Analysis: Quotex OTC - Crypto pairs + Indicator sanity check."""
import asyncio, sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models import SignalRequest, TradingMode
from backend.signal_manager import SignalManager
from backend.constants import CRYPTO_PAIRS
from backend.services.market_data import is_forex_market_open
from backend.indicators import ema, rsi, macd, bollinger_bands, atr, momentum, closes

# All Quotex crypto OTC pairs  
QUOTEX_CRYPTO = CRYPTO_PAIRS   # These all go via Binance 24/7

QUOTEX_FOREX_SAMPLE = [
    "EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC",
    "AUD/USD OTC", "EUR/JPY", "GBP/JPY OTC",
]

async def analyze_pair(manager, pair, duration="1 Minute"):
    try:
        req = SignalRequest(mode=TradingMode.quotex, pair=pair, duration=duration)
        resp = await manager.generate(req)
        return resp, None
    except RuntimeError as e:
        return None, str(e)

async def main():
    now = datetime.now(timezone.utc)
    market_open = is_forex_market_open()

    print("=" * 70)
    print("  QUOTEX OTC DEEP ANALYSIS")
    print("=" * 70)
    print(f"  Time (UTC)   : {now.strftime('%A %Y-%m-%d %H:%M')}")
    print(f"  Forex Market : {'OPEN' if market_open else 'CLOSED (weekend - normal)'}")
    print(f"  Crypto pairs : {len(QUOTEX_CRYPTO)} (24/7 via Binance)")

    manager = SignalManager()

    # ====================================================================
    # CRYPTO OTC - All 17 pairs
    # ====================================================================
    print("\n" + "=" * 70)
    print("  ALL CRYPTO OTC PAIRS (24/7 Available via Binance)")
    print("=" * 70)
    print(f"  {'Pair':<28} | Signal | Conf | Price")
    print(f"  {'-'*28}-+--------+------+---------")

    crypto_results = []
    for pair in QUOTEX_CRYPTO:
        resp, err = await analyze_pair(manager, pair)
        if resp:
            crypto_results.append(resp)
            warn = " [PROXY WARNING]" if resp.data_warning else ""
            print(f"  {pair:<28} | {resp.signal.value:<6} | {resp.confidence:>3}% | {resp.current_price:>12,.4f}{warn}")
        else:
            print(f"  {pair:<28} | ERROR  |      | {(err or '')[:40]}")

    # ====================================================================
    # Forex OTC - just status check
    # ====================================================================
    print("\n" + "=" * 70)
    print(f"  FOREX OTC SAMPLE CHECK ({'Live' if market_open else 'Closed - weekend'})")
    print("=" * 70)
    for pair in QUOTEX_FOREX_SAMPLE:
        resp, err = await analyze_pair(manager, pair)
        if resp:
            print(f"  [LIVE]   {pair:<28} | {resp.signal.value:<4} | {resp.confidence}% | {resp.current_price:.5f}")
        else:
            if err and "CLOSED" in err:
                print(f"  [CLOSED] {pair:<28} | Market closed - correct behavior")
            else:
                print(f"  [ERR]    {pair:<28} | {(err or '')[:50]}")

    # ====================================================================
    # SIGNAL QUALITY ANALYSIS
    # ====================================================================
    print("\n" + "=" * 70)
    print("  CRYPTO OTC SIGNAL QUALITY REPORT")
    print("=" * 70)
    if crypto_results:
        buy   = [r for r in crypto_results if r.signal.value == "UP"]
        sell  = [r for r in crypto_results if r.signal.value == "DOWN"]
        wait  = [r for r in crypto_results if r.signal.value == "WAIT"]
        confs = [r.confidence for r in crypto_results]
        avg_c = sum(confs)/len(confs)

        print(f"  Pairs analyzed  : {len(crypto_results)}/{len(QUOTEX_CRYPTO)}")
        print(f"  BUY  (UP)       : {len(buy):>2} ({len(buy)/len(crypto_results)*100:.0f}%)")
        print(f"  SELL (DOWN)     : {len(sell):>2} ({len(sell)/len(crypto_results)*100:.0f}%)")
        print(f"  WAIT            : {len(wait):>2} ({len(wait)/len(crypto_results)*100:.0f}%)")
        print(f"  Avg Confidence  : {avg_c:.1f}%")
        print(f"  Min Confidence  : {min(confs)}%")
        print(f"  Max Confidence  : {max(confs)}%")

        issues = []
        for r in crypto_results:
            if r.current_price == 0:
                issues.append(f"  [!] Zero price: {r.pair}")
            if r.confidence == 0:
                issues.append(f"  [!] Zero confidence: {r.pair}")
            if r.confidence >= 95:
                issues.append(f"  [!] Unrealistic confidence: {r.pair} @ {r.confidence}%")
        
        print()
        if issues:
            print("  QUALITY ISSUES:")
            for iss in issues:
                print(iss)
        else:
            print("  No quality issues detected. All signals look realistic.")

        strong = sorted([r for r in crypto_results if r.signal.value != "WAIT" and r.confidence >= 65],
                        key=lambda x: x.confidence, reverse=True)
        if strong:
            print()
            print(f"  Strong signals right now ({len(strong)} pairs, conf >= 65%):")
            for r in strong:
                print(f"    {r.signal.value:>4}  {r.pair:<28}  {r.confidence}%  @ {r.current_price:,.4f}")
        else:
            print()
            print("  No strong signals right now (market may be consolidating).")

    # ====================================================================
    # INDICATOR SANITY CHECK - Bitcoin + Ethereum
    # ====================================================================
    print("\n" + "=" * 70)
    print("  INDICATOR SANITY CHECK")
    print("=" * 70)
    from backend.data_engine import LiveMarketDataEngine

    for check_pair in ["Bitcoin (OTC)", "Ethereum (OTC)", "Solana (OTC)"]:
        try:
            engine = LiveMarketDataEngine()
            req = SignalRequest(mode=TradingMode.quotex, pair=check_pair, duration="1 Minute")
            snap = await engine.snapshot(req)
            prices = closes(snap.candles)
            p = prices[-1]
            e9  = ema(prices, 9)
            e21 = ema(prices, 21)
            r14 = rsi(prices, 14)
            _, _, mh = macd(prices)
            blo, bm, bhi = bollinger_bands(prices, 20, 2.0)
            a14 = atr(snap.candles, 14)
            mom = momentum(prices, 10)

            ema_dir = "Bullish" if e9 > e21 else "Bearish"
            rsi_zone = "Overbought" if r14 > 70 else ("Oversold" if r14 < 30 else "Neutral")
            macd_dir = "Bull" if mh > 0 else "Bear"
            mom_dir  = "Rising" if mom > 0 else "Falling"

            sanity_ok = (blo < bm < bhi) and (0 <= r14 <= 100) and (a14 >= 0) and (p > 0)
            icon = "OK" if sanity_ok else "FAIL"

            print(f"\n  [{icon}] {check_pair}")
            print(f"       Price: {p:,.4f} | EMA: {ema_dir} | RSI: {r14:.1f} ({rsi_zone})")
            print(f"       MACD: {macd_dir} ({mh:+.5f}) | Momentum: {mom_dir} ({mom:+.4f})")
            print(f"       BB: {blo:.4f} -- {bm:.4f} -- {bhi:.4f} | ATR: {a14:.5f}")
            print(f"       Candles: {len(snap.candles)} | Source: {snap.data_source}")
        except Exception as e:
            print(f"\n  [FAIL] {check_pair}: {e}")

    print("\n" + "=" * 70)
    print("  DEEP ANALYSIS COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
