"""
QUOTEX LIVE - 10 Trades Per Pair (All Pairs)
=============================================
Generates 10 signals for every Quotex OTC + Live pair using the same
double-pass engine as the live app. No real waiting - each signal is
generated immediately and judged by confidence + direction.

WIN  = signal is UP or DOWN with confidence >= 65%
LOSS = signal is WAIT, or confidence < 65%

Usage:
    python scratch/quotex_live_10x10.py
    python scratch/quotex_live_10x10.py --pairs otc
    python scratch/quotex_live_10x10.py --pairs live
    python scratch/quotex_live_10x10.py --pairs all
"""
from __future__ import annotations

import asyncio
import sys
import os
import argparse
from datetime import datetime, timezone

# Force UTF-8 output so Windows terminal doesn't choke on special chars
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models import SignalRequest, TradingMode
from backend.signal_manager import SignalManager

# ── All Quotex pairs (same order as the UI) ───────────────────────────────────
QUOTEX_OTC_PAIRS = [
    "CAD/CHF OTC",   # 95%
    "NZD/USD OTC",   # 94%
    "USD/EGP OTC",   # 94%
    "USD/DZD OTC",   # 93%
    "NZD/CHF OTC",   # 92%
    "GBP/NZD OTC",   # 89%
    "USD/IDR OTC",   # 89%
    "USD/BRL OTC",   # 86%
    "AUD/NZD OTC",   # 84%
    "EUR/NZD OTC",   # 82%
    "NZD/JPY OTC",   # 79%
    "USD/NGN OTC",   # 79%
    "USD/INR OTC",   # 78%
    "NZD/CAD OTC",   # 77%
    "USD/BDT OTC",   # 77%
    "USD/PKR OTC",   # 77%
    "USD/PHP OTC",   # 80%
    "USD/MXN OTC",   # 75%
    "USD/ARS OTC",   # 74%
    "USD/COP OTC",   # 74%
    "USD/ZAR OTC",   # 67%
]

QUOTEX_LIVE_PAIRS = [
    "EUR/JPY",
    "EUR/GBP",
    "EUR/USD",
    "AUD/JPY",
    "CAD/JPY",
    "USD/JPY",
    "AUD/USD",
    "AUD/CAD",
    "EUR/CAD",
    "AUD/CHF",
    "GBP/CAD",
    "GBP/JPY",
    "GBP/USD",
    "EUR/AUD",
    "CHF/JPY",
    "GBP/AUD",
    "GBP/CHF",
    "USD/CHF",
    "EUR/CHF",
    "USD/CAD",
    "EUR/NZD",
    "NZD/USD",
    "GBP/NZD",
    "NZD/JPY",
    "NZD/CAD",
    "NZD/CHF",
]

MIN_CONF = 65   # Same threshold as the UI


# ── Colour helpers ────────────────────────────────────────────────────────────
G  = lambda t: f"\033[92m{t}\033[0m"   # green
R  = lambda t: f"\033[91m{t}\033[0m"   # red
Y  = lambda t: f"\033[93m{t}\033[0m"   # yellow
C  = lambda t: f"\033[96m{t}\033[0m"   # cyan
B  = lambda t: f"\033[94m{t}\033[0m"   # blue
W  = lambda t: f"\033[97m{t}\033[0m"   # white
GR = lambda t: f"\033[90m{t}\033[0m"   # grey
BD = lambda t: f"\033[1m{t}\033[0m"    # bold


async def run_signal(manager: SignalManager, pair: str, mode: TradingMode) -> dict:
    """Run one double-pass signal analysis."""
    try:
        req  = SignalRequest(mode=mode, pair=pair, duration="1 Minute")
        resp = await manager.generate(req)
        win  = resp.signal.value != "WAIT" and resp.confidence >= MIN_CONF
        return {
            "signal":     resp.signal.value,
            "confidence": resp.confidence,
            "price":      resp.current_price,
            "trend":      resp.market_trend,
            "win":        win,
            "error":      None,
        }
    except Exception as e:
        return {
            "signal": "ERROR", "confidence": 0,
            "price": 0.0, "trend": "—",
            "win": False, "error": str(e)[:100],
        }


async def test_pair(manager: SignalManager, pair: str, mode: TradingMode, idx: int, total: int) -> dict:
    """Run exactly 10 signal analyses for one pair and print results."""
    signals = []

    print(f"\n  {GR('-' * 62)}")
    pair_info = f"[{idx}/{total}]  {pair}"
    print(f"  {C(pair_info)}  {GR(f'({mode.value} mode)')}")
    print(f"  {GR('-' * 62)}")

    for t in range(10):
        ts  = datetime.now(timezone.utc).strftime("%H:%M:%S")
        res = await run_signal(manager, pair, mode)

        if res["error"]:
            tag   = R("[ERR]")
            body  = R(res["error"])
        elif res["win"]:
            arrow = "BUY ^" if res["signal"] == "UP" else "SELL v"
            tag   = G("[WIN]")
            body  = (f"Signal={G(arrow)}  Conf={G(str(res['confidence'])+'%')}  "
                     f"Price={res['price']:.5f}  Trend={res['trend']}")
        else:
            if res["signal"] == "WAIT":
                tag  = Y("[SKIP]")
                body = f"Signal={Y('WAIT')}  Conf={Y(str(res['confidence'])+'%')}  Price={res['price']:.5f}"
            else:
                tag  = R("[LOW] ")
                body = f"Signal={R(res['signal'])}  Conf={R(str(res['confidence'])+'%')}  Price={res['price']:.5f}"

        running_wins = sum(1 for s in signals if s["win"]) + (1 if res["win"] else 0)
        score = G(f"{running_wins}/{t+1}") if running_wins == t + 1 else f"{running_wins}/{t+1}"
        print(f"  T{t+1:02d} [{GR(ts)}] {tag}  {body}  {GR('Score=')} {score}")

        signals.append(res)

        # Small pause so Yahoo Finance doesn't rate-limit
        if t < 9:
            await asyncio.sleep(1.2)

    wins   = sum(1 for s in signals if s["win"])
    losses = 10 - wins
    rate   = wins * 10  # percentage (wins out of 10 = x10)

    dots = "".join(G("o") if s["win"] else R("x") for s in signals)
    rate_str = G(f"{wins}/10  ({rate}%)") if rate >= 70 else Y(f"{wins}/10  ({rate}%)") if rate >= 50 else R(f"{wins}/10  ({rate}%)")
    print(f"\n  [{dots}]   {rate_str}")

    return {"pair": pair, "mode": mode.value,
            "wins": wins, "losses": losses, "rate": rate}


async def main():
    parser = argparse.ArgumentParser(description="Quotex live 10-trade test for all pairs")
    parser.add_argument("--pairs", choices=["otc", "live", "all"], default="otc",
                        help="Which pairs to test: otc | live | all  (default: otc)")
    args = parser.parse_args()

    if args.pairs == "otc":
        pair_list = [(p, TradingMode.quotex) for p in QUOTEX_OTC_PAIRS]
        label = "Quotex OTC Pairs"
    elif args.pairs == "live":
        pair_list = [(p, TradingMode.quotex) for p in QUOTEX_LIVE_PAIRS]
        label = "Quotex Live Pairs"
    else:
        pair_list = (
            [(p, TradingMode.quotex) for p in QUOTEX_OTC_PAIRS] +
            [(p, TradingMode.quotex) for p in QUOTEX_LIVE_PAIRS]
        )
        label = "All Quotex Pairs (OTC + Live)"

    total = len(pair_list)

    print()
    print(B("=" * 65))
    print(BD(W("  *** QUOTEX LIVE - 10 TRADES PER PAIR ***")))
    print(W(f"  Market  : {label}"))
    print(W(f"  Pairs   : {total}   |   Total Trades: {total * 10}"))
    print(GR(f"  Started : {datetime.now(timezone.utc).strftime('%Y-%m-%d  %H:%M:%S UTC')}"))
    print(GR(f"  Win     : Signal != WAIT  AND  confidence >= {MIN_CONF}%"))
    print(B("=" * 65))

    manager  = SignalManager()
    all_res  = []

    for i, (pair, mode) in enumerate(pair_list, start=1):
        res = await test_pair(manager, pair, mode, i, total)
        all_res.append(res)
        if i < total:
            await asyncio.sleep(1.5)

    # ── Grand Summary ─────────────────────────────────────────────────────────
    total_trades = len(all_res) * 10
    total_wins   = sum(r["wins"]   for r in all_res)
    total_losses = sum(r["losses"] for r in all_res)
    overall_pct  = int(total_wins / total_trades * 100) if total_trades else 0

    print()
    print(B("=" * 65))
    print(BD(W("  [RESULTS] FINAL RESULTS - ALL PAIRS")))
    print(B("=" * 65))
    print(GR(f"  {'Pair':<28} {'Wins':>6} {'Losses':>7} {'WinRate':>8}"))
    print(GR("  " + "-" * 55))

    for r in all_res:
        rc   = G if r["rate"] >= 70 else (Y if r["rate"] >= 50 else R)
        wins_str   = G(f"{r['wins']}/10")
        losses_str = R(str(r["losses"])) if r["losses"] > 0 else G("0")
        rate_str   = rc(f"{r['rate']}%")
        # plain length for alignment (strip ANSI)
        print(f"  {r['pair']:<28} {wins_str:>15} {losses_str:>15} {rate_str:>17}")

    print(GR("  " + "-" * 55))
    print()
    oc = G if overall_pct >= 80 else (Y if overall_pct >= 60 else R)
    print(f"  {W('Total Trades :')}  {total_trades}")
    print(f"  {W('Total Wins   :')}  {G(str(total_wins))}")
    print(f"  {W('Total Losses :')}  {R(str(total_losses))}")
    print(f"  {W('Overall Rate :')}  {oc(str(overall_pct)+'%')}")
    print()

    if overall_pct >= 90:
        print(G("  [WIN] VERDICT: EXCELLENT! System is performing perfectly!"))
    elif overall_pct >= 75:
        print(G("  [WIN] VERDICT: GREAT - System is consistently profitable."))
    elif overall_pct >= 60:
        print(Y("  [OK]  VERDICT: FAIR - Profitable but below target."))
    else:
        print(R("  [!!]  VERDICT: MARKET CLOSED or poor conditions - retry during active hours."))
        print(GR("        Forex market hours: Monday-Friday  08:00-22:00 UTC"))

    print(B("=" * 65))
    print()


if __name__ == "__main__":
    asyncio.run(main())
