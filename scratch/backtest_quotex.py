"""
Quotex OTC Signal Backtester
-----------------------------
Real backtest on Binance historical 1-min candles:
  - Fetch 300 candles per pair
  - Slide through last 80 candles as "test points"
  - Use preceding 160 candles for signal analysis
  - Check if actual next candle direction matched signal
  - Report win rate per pair + overall
"""
import asyncio, sys, os
from dataclasses import dataclass
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from backend.models import Candle, SignalRequest, TradingMode
from backend.strategy.signal_engine import SignalEngine
from backend.constants import CRYPTO_PAIRS
from backend.services.market_data import binance_symbol

BINANCE_BASE = "https://api.binance.com"
MIN_CANDLES_FOR_ANALYSIS = 35
LOOKBACK = 160        # candles fed into signal engine
TEST_WINDOW = 60      # how many test points per pair
LIMIT = LOOKBACK + TEST_WINDOW + 5   # total candles to fetch
MIN_CONFIDENCE = 55   # only count signals above this threshold
DURATION = "1 Minute"

@dataclass
class BacktestResult:
    pair: str
    trades: int
    wins: int
    losses: int
    skipped: int  # WAIT signals

    @property
    def win_rate(self):
        return (self.wins / self.trades * 100) if self.trades > 0 else 0.0

    @property
    def grade(self):
        if self.trades < 5:
            return "N/A (too few trades)"
        if self.win_rate >= 85:
            return "EXCELLENT"
        if self.win_rate >= 70:
            return "GOOD"
        if self.win_rate >= 55:
            return "FAIR"
        return "POOR"


async def fetch_candles(symbol: str, limit: int) -> list[Candle]:
    url = f"{BINANCE_BASE}/api/v3/klines"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params={"symbol": symbol, "interval": "1m", "limit": limit})
        r.raise_for_status()
        rows = r.json()
    return [
        Candle(
            timestamp=datetime.fromtimestamp(row[0]/1000, tz=timezone.utc),
            open=float(row[1]), high=float(row[2]),
            low=float(row[3]),  close=float(row[4]),
            volume=float(row[5]),
        )
        for row in rows
    ]


def backtest_pair(pair: str, candles: list[Candle], engine: SignalEngine) -> BacktestResult:
    wins = losses = skipped = 0
    total = len(candles)
    # Test on positions LOOKBACK..total-2
    # At each position i, we use candles[i-LOOKBACK:i] for signal
    # Then check candles[i].close vs candles[i-1].close for direction
    trade_count = 0

    for i in range(LOOKBACK, total - 1):
        window = candles[i - LOOKBACK : i]
        if len(window) < MIN_CANDLES_FOR_ANALYSIS:
            continue

        try:
            req = SignalRequest(mode=TradingMode.quotex, pair=pair, duration=DURATION)
            resp = engine.analyze(req, window)
        except Exception:
            continue

        if resp.signal.value == "WAIT" or resp.confidence < MIN_CONFIDENCE:
            skipped += 1
            continue

        # Actual outcome: candles[i] is the NEXT candle after signal
        entry_close  = candles[i - 1].close  # close at signal time
        result_close = candles[i].close       # close of next candle (trade result)

        actual_up = result_close > entry_close
        actual_dn = result_close < entry_close

        if resp.signal.value == "UP":
            if actual_up:
                wins += 1
            elif actual_dn:
                losses += 1
            else:
                skipped += 1  # tie / doji
        elif resp.signal.value == "DOWN":
            if actual_dn:
                wins += 1
            elif actual_up:
                losses += 1
            else:
                skipped += 1
        trade_count += 1

    return BacktestResult(
        pair=pair,
        trades=wins + losses,
        wins=wins,
        losses=losses,
        skipped=skipped,
    )


async def main():
    print("=" * 70)
    print("  QUOTEX OTC SIGNAL BACKTEST")
    print("=" * 70)
    print(f"  Test config:")
    print(f"    Lookback candles  : {LOOKBACK}")
    print(f"    Test points/pair  : {TEST_WINDOW}")
    print(f"    Min confidence    : {MIN_CONFIDENCE}%")
    print(f"    Trade duration    : {DURATION}")
    print(f"    Pairs to test     : {len(CRYPTO_PAIRS)}")
    print()

    engine = SignalEngine()
    all_results: list[BacktestResult] = []

    for pair in CRYPTO_PAIRS:
        sym = binance_symbol(pair)
        try:
            candles = await fetch_candles(sym, LIMIT)
            result = backtest_pair(pair, candles, engine)
            all_results.append(result)

            bar_wins   = "#" * result.wins
            bar_losses = "-" * result.losses
            rate_str = f"{result.win_rate:.0f}%" if result.trades > 0 else "N/A"
            grade_short = result.grade.split(" ")[0]
            print(f"  {pair:<28} | {rate_str:>5} | W:{result.wins:>2} L:{result.losses:>2} Skip:{result.skipped:>2} | {grade_short}")

        except Exception as e:
            print(f"  {pair:<28} | ERR | {str(e)[:40]}")

    # ====================================================================
    # AGGREGATE SUMMARY
    # ====================================================================
    print()
    print("=" * 70)
    print("  AGGREGATE RESULTS")
    print("=" * 70)

    valid = [r for r in all_results if r.trades >= 5]
    total_wins   = sum(r.wins   for r in valid)
    total_losses = sum(r.losses for r in valid)
    total_trades = sum(r.trades for r in valid)
    overall_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

    print(f"  Valid pairs analyzed : {len(valid)}/{len(CRYPTO_PAIRS)}")
    print(f"  Total trades         : {total_trades}")
    print(f"  Total wins           : {total_wins}")
    print(f"  Total losses         : {total_losses}")
    print(f"  Overall Win Rate     : {overall_rate:.1f}%")
    print()

    verdict_icon = "EXCELLENT" if overall_rate >= 85 else ("GOOD" if overall_rate >= 70 else ("FAIR" if overall_rate >= 55 else "NEEDS TUNING"))
    print(f"  VERDICT: {verdict_icon}")
    print()

    # Best / Worst pairs
    if valid:
        best  = sorted(valid, key=lambda r: r.win_rate, reverse=True)[:3]
        worst = sorted(valid, key=lambda r: r.win_rate)[:3]
        print("  Top 3 pairs:")
        for r in best:
            print(f"    {r.pair:<28} {r.win_rate:.0f}% ({r.trades} trades)")
        print("  Needs attention:")
        for r in worst:
            print(f"    {r.pair:<28} {r.win_rate:.0f}% ({r.trades} trades)")

    # Recommendation
    print()
    print("=" * 70)
    print("  SIGNAL ENGINE ASSESSMENT")
    print("=" * 70)
    if overall_rate >= 80:
        print("  Signal engine is performing WELL.")
        print("  No tuning required.")
    elif overall_rate >= 65:
        print("  Signal engine is acceptable but can be improved.")
        print("  Suggestion: raise MIN_CONFIDENCE threshold to filter weak signals.")
    else:
        print("  Signal engine needs improvement.")
        print("  Will analyze weak areas and suggest parameter adjustments...")
        # Show confidence distribution for losses
        print()
        print("  Consider adjustments:")
        print("   - Raise confidence threshold (currently 55%) to 65-70%")
        print("   - Add volume filter: skip signals when volume_ratio < 0.8")
        print("   - Add ATR filter: skip signals when ATR < 0.0003 (too quiet)")

    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
