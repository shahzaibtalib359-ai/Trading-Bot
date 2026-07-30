import asyncio
import logging
from backend.models import SignalRequest, TradingMode
from backend.strategy.signal_engine import SignalEngine
from backend.services.market_data import generate_synthetic_candles, BinanceMarketDataProvider, YahooFinanceForexProvider

logging.basicConfig(level=logging.WARNING)

async def test_batch():
    engine = SignalEngine()
    binance = BinanceMarketDataProvider()
    yahoo = YahooFinanceForexProvider()

    pairs_to_test = [
        "EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/USD OTC",
        "USD/CAD OTC", "EUR/GBP OTC", "USD/BRL OTC", "USD/INR OTC",
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"
    ]

    print(f"{'PAIR':<15} | {'MODE':<8} | {'SIGNAL':<6} | {'CONF':<4} | {'BULL':<4} | {'BEAR':<4} | {'EDGE':<4}")
    print("-" * 65)

    for p in pairs_to_test:
        mode = TradingMode.crypto if "USDT" in p else TradingMode.quotex
        req = SignalRequest(mode=mode, pair=p, duration="1 Minute")
        try:
            if mode == TradingMode.crypto:
                candles = await binance.get_candles(mode, p, limit=150)
            else:
                candles = generate_synthetic_candles(p, 150)
            
            res = engine.analyze(req, candles)
            bull = 0
            bear = 0
            for line in res.analysis:
                if 'Votes:' in line:
                    parts = line.split('Bull=')[1].split('pt')
                    bull = int(parts[0])
                    bear = int(parts[1].split('Bear=')[1])
            edge = abs(bull - bear)
            
            print(f"{p:<15} | {mode.value:<8} | {res.signal.value:<6} | {res.confidence:>3}% | {bull:>4} | {bear:>4} | {edge:>4}")
        except Exception as e:
            print(f"{p:<15} | ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_batch())
