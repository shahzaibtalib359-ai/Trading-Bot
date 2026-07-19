"""Test script: Check Quotex single-pair signal generation locally."""
from __future__ import annotations

import asyncio
import sys
import os

# Force UTF-8 output on Windows to support Unicode characters
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models import SignalRequest, TradingMode, SignalResponse
import argparse
from backend.signal_manager import SignalManager


TEST_PAIRS = [
    "EUR/USD OTC",
    "GBP/USD OTC",
    "USD/JPY OTC",
    "Bitcoin (OTC)",
    "Ethereum (OTC)",
    "Solana (OTC)",
]

TEST_DURATIONS = ["1 Minute", "15 Seconds"]


async def test_single_pair(manager: SignalManager, pair: str, duration: str) -> dict:
    """Test a single pair and return results."""
    try:
        request = SignalRequest(
            mode=TradingMode.quotex,
            pair=pair,
            duration=duration,
        )
        response: SignalResponse = await manager.generate(request)
        return {
            "pair": pair,
            "duration": duration,
            "status": "OK",
            "signal": response.signal.value,
            "confidence": response.confidence,
            "price": response.current_price,
            "trend": response.market_trend,
            "data_source": response.data_source,
            "data_warning": response.data_warning,
            "analysis_count": len(response.analysis),
            "analysis": response.analysis[:5],
        }
    except Exception as exc:
        return {
            "pair": pair,
            "duration": duration,
            "status": "ERROR",
            "error": str(exc),
        }



async def main():
    parser = argparse.ArgumentParser(description="Quotex single‑pair signal test with confidence filter")
    parser.add_argument('--conf-thresh', type=int, default=55,
                        help='Minimum confidence percentage to treat a signal as a trade')
    args = parser.parse_args()

    manager = SignalManager()
    results = []
    for pair in TEST_PAIRS:
        for dur in TEST_DURATIONS:
            print(f"\n>> Testing: {pair} | Duration: {dur}")
            result = await test_single_pair(manager, pair, dur)
            # Filter by confidence if signal OK
            if result["status"] == "OK" and result["confidence"] < args.conf_thresh:
                # Treat as wait/skip
                result["status"] = "SKIP"
                result["error"] = f"Confidence {result['confidence']}% below threshold {args.conf_thresh}%"
            results.append(result)
            if result["status"] == "OK":
                print(f"   Signal: {result['signal']} | Confidence: {result['confidence']}%")
                print(f"   Price: {result['price']} | Trend: {result['trend']}")
                print(f"   Data Source: {result['data_source']}")
                if result["data_warning"]:
                    print(f"   [WARN] Warning: {result['data_warning']}")
                print(f"   Analysis ({result['analysis_count']} items):")
                for line in result["analysis"]:
                    print(f"     - {line}")
            elif result["status"] == "SKIP":
                print(f"   [SKIP] {result['error']}")
            else:
                print(f"   [FAIL] ERROR: {result['error']}")

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    ok = [r for r in results if r["status"] == "OK"]
    skips = [r for r in results if r.get("status") == "SKIP"]
    errors = [r for r in results if r["status"] == "ERROR"]
    print(f"  Total tests: {len(results)}")
    print(f"  [PASS] Passed: {len(ok)}")
    print(f"  [SKIP] Skipped (low confidence): {len(skips)}")
    print(f"  [FAIL] Failed: {len(errors)}")
    if errors:
        print("\n  FAILURES:")
        for e in errors:
            print(f"    - {e['pair']} ({e['duration']}): {e['error']}")
    # Signal quality check
    if ok:
        print("\n  SIGNAL QUALITY CHECK:")
        for r in ok:
            issues = []
            if r["confidence"] == 0:
                issues.append("confidence=0 (might be broken)")
            if r["confidence"] > 95:
                issues.append("confidence>95 (unrealistically high)")
            if r["price"] == 0:
                issues.append("price=0 (no data)")
            if r["analysis_count"] < 4:
                issues.append(f"only {r['analysis_count']} analysis lines (expected 8+)")
            status_icon = "[OK] " if not issues else "[WARN]"
            print(f"    {status_icon}{r['pair']} ({r['duration']}): signal={r['signal']} conf={r['confidence']}% price={r['price']}")
            for issue in issues:
                print(f"      [WARN] {issue}")
    print("\n" + "=" * 70)
    print("  TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
