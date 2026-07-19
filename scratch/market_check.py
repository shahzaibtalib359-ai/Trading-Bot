"""
Market Open Check + 10 Trade Win Rate Test (FIXED)
------------------------------------------------------
FIX 1: Removed Unicode emoji (UnicodeEncodeError on Windows cp1252)
FIX 2: Uses historical candle backtest instead of 5-second real-time check
        (5s check was broken: price doesn't move in 5s -> always 0.00% change)
FIX 3: Proper binary options simulation: signal on candle[i], outcome = candle[i+1]
"""
from __future__ import annotations
import asyncio
import sys
import os
from datetime import datetime, timezone

# Force UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from backend.models import Candle, SignalRequest, TradingMode
from backend.strategy.signal_engine import SignalEngine

BINANCE_BASE  = "https://api.binance.com"
LOOKBACK      = 100   # candles for signal analysis
TEST_WINDOW   = 30    # how many candles to test as "outcomes"
TOTAL_FETCH   = LOOKBACK + TEST_WINDOW + 5
MIN_CONF      = 65    # minimum confidence to count as a trade
WIN_TARGET    = 9     # target: 9 out of 10

TEST_PAIRS = [
    ("Ethereum (OTC)",     "ETHUSDT"),
    ("Bitcoin (OTC)",      "BTCUSDT"),
    ("Solana (OTC)",       "SOLUSDT"),
    ("Binance Coin (OTC)", "BNBUSDT"),
    ("Ripple (OTC)",       "XRPUSDT"),
    ("Avalanche (OTC)",    "AVAXUSDT"),
    ("Litecoin (OTC)",     "LTCUSDT"),
    ("Polkadot (OTC)",     "DOTUSDT"),
]


async def fetch_candles(symbol: str, limit: int) -> list[Candle]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": "1m", "limit": limit}
        )
        r.raise_for_status()
        return [
            Candle(
                timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                open=float(row[1]), high=float(row[2]),
                low=float(row[3]),  close=float(row[4]), volume=float(row[5])
            )
            for row in r.json()
        ]


# ============================================================
# STEP 1: Market open check
# ============================================================
async def check_market_open() -> bool:
    print("=" * 65)
    print("  STEP 1: MARKET OPEN CHECK")
    print("=" * 65)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{BINANCE_BASE}/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"})
            r.raise_for_status()
            d = r.json()

        btc_price  = float(d["lastPrice"])
        volume_24h = float(d["volume"])
        change_pct = float(d["priceChangePercent"])
        now        = datetime.now(timezone.utc)
        hour       = now.hour

        if   8 <= hour < 16: session = "LONDON/NEW YORK  (HIGH VOLUME)"
        elif 4 <= hour <  8: session = "ASIAN/LONDON     (MODERATE)"
        elif 16 <= hour < 20: session = "NEW YORK PM      (MODERATE)"
        else:                 session = "QUIET HOURS      (LOW VOLUME)"

        print(f"  [OK] Binance API  : ONLINE")
        print(f"  [OK] UTC Time     : {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  [OK] BTC Price    : ${btc_price:,.2f}")
        print(f"  [OK] 24h Volume   : {volume_24h:,.0f} BTC")
        print(f"  [OK] 24h Change   : {change_pct:+.2f}%")
        print(f"  [OK] Session      : {session}")
        print(f"  [OK] Crypto Market: 24/7 ALWAYS OPEN")
        print()
        print("  Market status: GOOD - proceeding to trade test")
        return True

    except Exception as e:
        print(f"  [FAIL] Cannot reach Binance API: {e}")
        print(f"  Check your internet connection.")
        return False


# ============================================================
# STEP 2: Historical candle backtest (proper binary options sim)
# ============================================================
def backtest_pair(pair_name: str, candles: list[Candle], engine: SignalEngine) -> list[dict]:
    """
    Proper binary options backtest:
      - At position i, use candles[i-LOOKBACK : i] for signal
      - Entry price = candles[i-1].close  (last candle at signal time)
      - Exit  price = candles[i].close    (next candle close = trade result)
    """
    trades = []
    total  = len(candles)

    for i in range(LOOKBACK, total - 1):
        window = candles[i - LOOKBACK : i]
        try:
            req  = SignalRequest(mode=TradingMode.quotex, pair=pair_name, duration="1 Minute")
            resp = engine.analyze(req, window)
        except Exception:
            continue

        if resp.signal.value == "WAIT" or resp.confidence < MIN_CONF:
            continue

        entry_price  = candles[i - 1].close
        exit_price   = candles[i].close
        change       = exit_price - entry_price
        change_pct   = abs(change) / entry_price * 100 if entry_price > 0 else 0

        won = (
            (resp.signal.value == "UP"   and exit_price > entry_price) or
            (resp.signal.value == "DOWN" and exit_price < entry_price)
        )

        trades.append({
            "pair":       pair_name,
            "signal":     resp.signal.value,
            "conf":       resp.confidence,
            "entry":      entry_price,
            "exit":       exit_price,
            "change_pct": change_pct,
            "won":        won,
            "ts":         candles[i].timestamp.strftime("%H:%M"),
        })

        # Stop after collecting 2 trades per pair (for speed)
        if len(trades) >= 2:
            break

    return trades


async def run_backtest_10_trades() -> list[dict]:
    print()
    print("=" * 65)
    print("  STEP 2: 10-TRADE HISTORICAL BACKTEST")
    print("=" * 65)
    print(f"  Method   : Historical candle simulation (1-minute candles)")
    print(f"  Min conf : {MIN_CONF}%")
    print(f"  Logic    : Signal on candle[N], outcome = candle[N+1] close")
    print()

    engine     = SignalEngine(volume_threshold=1.05)
    all_trades: list[dict] = []

    for pair_name, symbol in TEST_PAIRS:
        try:
            candles = await fetch_candles(symbol, TOTAL_FETCH)
        except Exception as e:
            print(f"  [SKIP] {pair_name}: fetch error - {e}")
            continue

        trades = backtest_pair(pair_name, candles, engine)

        if trades:
            for t in trades:
                icon = "WIN " if t["won"] else "LOSS"
                print(f"  [{t['ts']}] {t['pair']:<22} {t['signal']:<4} conf={t['conf']:>3}%  "
                      f"entry={t['entry']:.4f}  exit={t['exit']:.4f}  "
                      f"chg={t['change_pct']:.4f}%  [{icon}]")
            all_trades.extend(trades)
        else:
            print(f"  [----] {pair_name:<22} -- No signal above {MIN_CONF}% in test window")

        # Stop at 10 trades
        if len(all_trades) >= 10:
            all_trades = all_trades[:10]
            break

    return all_trades


# ============================================================
# STEP 3: Diagnose issues if win rate < 90%
# ============================================================
def diagnose_issues(trades: list[dict]) -> list[dict]:
    issues = []

    if not trades:
        issues.append({
            "type": "NO_SIGNALS_AT_ALL",
            "desc": "Engine ne koi bhi signal generate nahi kiya (sab WAIT)",
            "fix":  "signal_engine.py me SIGNAL_THRESHOLD 65% -> 55% karo, "
                    "ya MIN_CONF is script me 65 -> 50 karo",
        })
        return issues

    wins     = sum(1 for t in trades if t["won"])
    win_rate = wins / len(trades) * 100

    if win_rate < 90:
        # 1. Zero-change trades
        zero_chg = [t for t in trades if t["change_pct"] == 0.0]
        if zero_chg:
            issues.append({
                "type": "ZERO_PRICE_CHANGE",
                "desc": f"{len(zero_chg)} trade(s) me entry == exit (price move = 0)",
                "fix":  "Ye sideways/flat candle tha. ATR filter: skip if atr_pct < 0.0003",
            })

        # 2. Losses at borderline confidence
        low_conf_losses = [t for t in trades if not t["won"] and t["conf"] < 72]
        if low_conf_losses:
            issues.append({
                "type": "LOW_CONFIDENCE_LOSSES",
                "desc": f"{len(low_conf_losses)} loss(es) at confidence 65-71% (borderline)",
                "fix":  "SIGNAL_THRESHOLD 65% -> 70% karo signal_engine.py line 279 me",
            })

        # 3. Wrong direction
        wrong_dir = [t for t in trades if not t["won"] and t["change_pct"] > 0.05]
        if wrong_dir:
            issues.append({
                "type": "WRONG_DIRECTION_SIGNALS",
                "desc": f"{len(wrong_dir)} trade(s) me signal direction galat tha (price moved opposite)",
                "fix":  "MACD building check strengthen karo: require macd_hist > 0.0001 (not just > 0)",
            })

        # 4. Overall low rate
        if win_rate < 60:
            issues.append({
                "type": "CHOPPY_MARKET_CONDITIONS",
                "desc": f"Win rate {win_rate:.0f}% - market abhi choppy/sideways hai",
                "fix":  "Best trading hours: 08:00-16:00 UTC (London/NY session). "
                        "Abhi NY afternoon me volatility kam hai.",
            })

    return issues


# ============================================================
# MAIN
# ============================================================
async def main():
    print()
    print("=" * 65)
    print("  QUOTEX MARKET CHECK + 10-TRADE WIN RATE VERIFIER")
    print("=" * 65)
    print()

    # Step 1
    market_ok = await check_market_open()
    if not market_ok:
        print("\n[STOP] Market unreachable - test aborted.")
        return

    # Step 2
    trades = await run_backtest_10_trades()

    # Step 3: Report
    print()
    print("=" * 65)
    print("  FINAL REPORT")
    print("=" * 65)

    if not trades:
        print()
        print("  No trades found - all pairs returned WAIT signal.")
        print(f"  Reason: Market conditions don't meet {MIN_CONF}%+ confidence.")
        print()
    else:
        wins     = sum(1 for t in trades if t["won"])
        losses   = len(trades) - wins
        win_rate = wins / len(trades) * 100

        print()
        print(f"  Total Trades : {len(trades)}")
        print(f"  Wins         : {wins}")
        print(f"  Losses       : {losses}")
        print(f"  Win Rate     : {win_rate:.1f}%")
        print()

        # Table
        print(f"  {'#':>2} | {'Pair':<22} | {'Dir':<4} | {'C%':>3} | Result | Chg%")
        print(f"  {'-'*2}-+-{'-'*22}-+-{'-'*4}-+-{'-'*3}-+--------+----------")
        for n, t in enumerate(trades, 1):
            icon = "WIN " if t["won"] else "LOSS"
            print(f"  {n:>2} | {t['pair']:<22} | {t['signal']:<4} | {t['conf']:>3} | {icon}   | {t['change_pct']:.4f}%")

        print()
        if win_rate >= 90:
            print(f"  [PASS] EXCELLENT! {wins}/10 wins ({win_rate:.0f}%) - System READY!")
            print(f"         Quotex me trade laga sakte hain!")
        elif win_rate >= 70:
            print(f"  [GOOD] {wins}/10 wins ({win_rate:.0f}%) - Profitable but needs minor tuning.")
        elif win_rate >= 55:
            print(f"  [FAIR] {wins}/10 wins ({win_rate:.0f}%) - Break-even zone. Needs improvement.")
        else:
            print(f"  [FAIL] {wins}/10 wins ({win_rate:.0f}%) - Not ready. See fixes below.")

    # Step 4: Diagnose
    issues = diagnose_issues(trades)
    if issues:
        print()
        print("=" * 65)
        print("  ERRORS FOUND + FIX GUIDE")
        print("=" * 65)
        for i, issue in enumerate(issues, 1):
            print()
            print(f"  [{i}] Problem : {issue['type']}")
            print(f"       Details : {issue['desc']}")
            print(f"       Fix     : {issue['fix']}")
    else:
        print()
        print("  [OK] Koi critical errors nahi mile!")
        print("  [OK] System theek chal raha hai.")

    print()
    print("=" * 65)
    print("  TEST COMPLETE")
    print("=" * 65)
    print()


if __name__ == "__main__":
    asyncio.run(main())
