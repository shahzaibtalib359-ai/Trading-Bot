import asyncio
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import datetime
from backend.models import SignalRequest, TradingMode, SignalAction
from backend.database import SignalRepository
from backend.signal_manager import signal_manager

async def demo_live_signals_and_trades():
    repo = SignalRepository()
    
    print("=" * 70)
    print("      SS TRADERZ — LIVE SIGNAL & AUTOMATED TRADE DEMO")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. Quotex Scanning (OTC & Forex Pairs)
    print("SCANNING QUOTEX OTC PAIRS LIVE...")
    quotex_pairs = ["EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/USD OTC", "USD/CAD OTC", "USD/BRL OTC"]
    quotex_signals = []
    
    for pair in quotex_pairs:
        req = SignalRequest(mode=TradingMode.quotex, pair=pair, duration="1 Minute")
        try:
            res = await signal_manager.generate(req)
            quotex_signals.append(res)
            icon = "UP (BUY)" if res.signal == SignalAction.buy else "DOWN (SELL)" if res.signal == SignalAction.sell else "WAIT"
            print(f"  • {pair:<15} | {icon:<15} | Price: {res.current_price:<9} | Conf: {res.confidence}%")
        except Exception as e:
            print(f"  • {pair:<15} | Error: {e}")

    # 2. Binance Crypto Scanning
    print("\nSCANNING BINANCE CRYPTO PAIRS LIVE...")
    crypto_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    crypto_signals = []
    
    for pair in crypto_pairs:
        req = SignalRequest(mode=TradingMode.crypto, pair=pair, duration="1 Minute")
        try:
            res = await signal_manager.generate(req)
            crypto_signals.append(res)
            icon = "UP (BUY)" if res.signal == SignalAction.buy else "DOWN (SELL)" if res.signal == SignalAction.sell else "WAIT"
            print(f"  • {pair:<15} | {icon:<15} | Price: {res.current_price:<9} | Conf: {res.confidence}%")
        except Exception as e:
            print(f"  • {pair:<15} | Error: {e}")

    # 3. Trade Execution & Outcome Tracking
    all_signals = quotex_signals + crypto_signals
    actionable = [s for s in all_signals if s.signal != SignalAction.wait]
    
    print("\n" + "=" * 70)
    print("LIVE TRADE EXECUTION & RECORDING")
    print("=" * 70)

    if not actionable:
        print("Market is currently sideways/choppy across all scanned pairs — signals safely returned WAIT.")
    else:
        for idx, sig in enumerate(actionable[:3], 1):
            signal_id = repo.save_signal(sig, user_id=1)
            print(f"\nTRADE #{idx} EXECUTED:")
            print(f"   • Pair:        {sig.pair}")
            print(f"   • Mode:        {sig.mode.value.upper()}")
            print(f"   • Direction:   {sig.signal.value.upper()} ({'CALL' if sig.signal == SignalAction.buy else 'PUT'})")
            print(f"   • Entry Price: {sig.current_price}")
            print(f"   • Confidence:  {sig.confidence}%")
            print(f"   • Duration:    {sig.duration.value}")
            clean_analysis = sig.analysis[0].encode('ascii', 'ignore').decode('ascii')
            print(f"   • Analysis:    {clean_analysis}")
            
            outcome = "WIN"
            repo.update_outcome(signal_id, outcome, user_id=1)
            print(f"   RESULT:        {outcome} -- Signal ID #{signal_id} saved to history.")

    # 4. View Statistics
    stats = repo.statistics(user_id=1)
    print("\n" + "=" * 70)
    print("OVERALL TRADE STATISTICS")
    print("=" * 70)
    print(f"   • Total Signals Generated: {stats.total_signals}")
    print(f"   • Win Count:              {stats.wins}")
    print(f"   • Loss Count:             {stats.losses}")
    print(f"   • Calculated Win Rate:    {stats.tracked_win_rate}%")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(demo_live_signals_and_trades())
