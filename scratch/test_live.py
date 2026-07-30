import asyncio
from backend.models import SignalRequest, TradingMode
from backend.strategy.signal_engine import SignalEngine
from backend.services.market_data import BinanceMarketDataProvider, YahooFinanceForexProvider

async def test_live():
    engine = SignalEngine()
    binance = BinanceMarketDataProvider()
    yahoo = YahooFinanceForexProvider()

    crypto_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT"]
    print("--- LIVE BINANCE CRYPTO SIGNALS ---")
    for p in crypto_pairs:
        req = SignalRequest(mode=TradingMode.crypto, pair=p, duration="1 Minute")
        try:
            candles = await binance.get_candles(TradingMode.crypto, p, limit=150)
            res = engine.analyze(req, candles)
            clean_analysis = res.analysis[0].encode('ascii', 'ignore').decode('ascii')
            print(f"{p:<10} | {res.signal.value:<6} | Conf: {res.confidence:>3}% | Price: {res.current_price:<10} | {clean_analysis}")
        except Exception as e:
            print(f"{p:<10} | ERROR: {e}")

    forex_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    print("\n--- LIVE YAHOO FOREX SIGNALS ---")
    for p in forex_pairs:
        req = SignalRequest(mode=TradingMode.forex, pair=p, duration="1 Minute")
        try:
            candles = await yahoo.get_candles(TradingMode.forex, p, limit=150)
            res = engine.analyze(req, candles)
            clean_analysis = res.analysis[0].encode('ascii', 'ignore').decode('ascii')
            print(f"{p:<10} | {res.signal.value:<6} | Conf: {res.confidence:>3}% | Price: {res.current_price:<10} | {clean_analysis}")
        except Exception as e:
            print(f"{p:<10} | ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_live())
