const CRYPTO_PAIRS = [
  "Bitcoin Cash (OTC)",
  "Binance Coin (OTC)",
  "Bitcoin (OTC)",
  "Litecoin (OTC)",
  "Solana (OTC)",
  "Axie Infinity (OTC)",
  "Polkadot (OTC)",
  "Ripple (OTC)",
  "Ethereum Classic (OTC)",
  "Cosmos (OTC)",
  "Zcash (OTC)",
  "Chainlink (OTC)",
  "Avalanche (OTC)",
  "Trump (OTC)",
  "Ethereum (OTC)",
  "Toncoin (OTC)",
  "Dash (OTC)",
]

const BINANCE_SPOT_PAIRS = [
  "BTC/USDT",
  "ETH/USDT",
  "BNB/USDT",
  "SOL/USDT",
  "XRP/USDT",
  "BCH/USDT",
  "LTC/USDT",
  "AVAX/USDT",
  "DOT/USDT",
  "LINK/USDT",
  "ETC/USDT",
  "ATOM/USDT",
  "ZEC/USDT",
  "DASH/USDT",
  "TON/USDT",
  "AXS/USDT",
  "DOGE/USDT",
  "ADA/USDT",
  "TRX/USDT",
  "UNI/USDT",
]

const QUOTEX_PAIRS = [
  "EUR/USD OTC",
  "GBP/USD OTC",
  "USD/JPY OTC",
  "AUD/USD OTC",
  "AUD/JPY OTC",
  "AUD/CAD OTC",
  "AUD/CHF OTC",
  "AUD/NZD OTC",
  "EUR/GBP OTC",
  "EUR/AUD OTC",
  "EUR/CAD OTC",
  "EUR/CHF OTC",
  "EUR/NZD OTC",
  "GBP/AUD OTC",
  "GBP/CAD OTC",
  "GBP/CHF OTC",
  "GBP/JPY OTC",
  "GBP/NZD OTC",
  "CAD/CHF OTC",
  "CAD/JPY OTC",
  "CHF/JPY OTC",
  "NZD/CAD OTC",
  "NZD/CHF OTC",
  "NZD/JPY OTC",
  "NZD/USD OTC",
  "USD/IDR OTC",
  "USD/INR OTC",
  "USD/BRL OTC",
  "USD/BDT OTC",
  "USD/EGP OTC",
  "USD/ARS OTC",
  "USD/COP OTC",
  "USD/DZD OTC",
  "USD/MXN OTC",
  "USD/NGN OTC",
  "USD/PHP OTC",
  "USD/ZAR OTC",
]

const FOREX_PAIRS = [
  "EUR/USD",
  "GBP/USD",
  "USD/JPY",
  "AUD/USD",
  "AUD/JPY",
  "AUD/CAD",
  "AUD/CHF",
  "AUD/NZD",
  "EUR/JPY",
  "EUR/AUD",
  "EUR/CAD",
  "EUR/CHF",
  "EUR/NZD",
  "USD/CAD",
  "USD/CHF",
  "EUR/GBP",
  "GBP/JPY",
  "GBP/CAD",
  "GBP/AUD",
  "GBP/CHF",
  "GBP/NZD",
  "CAD/CHF",
  "CAD/JPY",
  "CHF/JPY",
  "NZD/CAD",
  "NZD/CHF",
  "NZD/JPY",
  "NZD/USD",
]

const DURATIONS = ["5 Seconds", "10 Seconds", "15 Seconds", "30 Seconds", "1 Minute", "5 Minutes", "15 Minutes"]

const SYMBOL_MAP = {
  "Bitcoin Cash (OTC)": "BCHUSDT",
  "Binance Coin (OTC)": "BNBUSDT",
  "Bitcoin (OTC)": "BTCUSDT",
  "Litecoin (OTC)": "LTCUSDT",
  "Solana (OTC)": "SOLUSDT",
  "Axie Infinity (OTC)": "AXSUSDT",
  "Polkadot (OTC)": "DOTUSDT",
  "Ripple (OTC)": "XRPUSDT",
  "Ethereum Classic (OTC)": "ETCUSDT",
  "Cosmos (OTC)": "ATOMUSDT",
  "Zcash (OTC)": "ZECUSDT",
  "Chainlink (OTC)": "LINKUSDT",
  "Avalanche (OTC)": "AVAXUSDT",
  "Trump (OTC)": "TRUMPUSDT",
  "Ethereum (OTC)": "ETHUSDT",
  "Toncoin (OTC)": "TONUSDT",
  "Dash (OTC)": "DASHUSDT",
  EURUSD: "ETHUSDT",
  GBPUSD: "BNBUSDT",
  USDJPY: "BTCUSDT",
  AUDUSD: "SOLUSDT",
  AUDJPY: "SOLUSDT",
  AUDCAD: "ADAUSDT",
  AUDCHF: "ADAUSDT",
  AUDNZD: "ADAUSDT",
  EURGBP: "ETHUSDT",
  EURAUD: "ETHUSDT",
  EURCAD: "ETHUSDT",
  EURCHF: "ETHUSDT",
  EURNZD: "ETHUSDT",
  EURJPY: "ETHUSDT",
  GBPAUD: "BNBUSDT",
  GBPCAD: "BNBUSDT",
  GBPCHF: "BNBUSDT",
  GBPJPY: "BNBUSDT",
  GBPNZD: "BNBUSDT",
  CADCHF: "XRPUSDT",
  CADJPY: "XRPUSDT",
  CHFJPY: "XRPUSDT",
  NZDCAD: "TRXUSDT",
  NZDCHF: "TRXUSDT",
  NZDJPY: "TRXUSDT",
  NZDUSD: "TRXUSDT",
  USDCAD: "BTCUSDT",
  USDCHF: "BTCUSDT",
  USDBRL: "DOGEUSDT",
  USDTRY: "DOGEUSDT",
  USDEGP: "DOGEUSDT",
  USDIDR: "DOGEUSDT",
  USDNGN: "DOGEUSDT",
  USDARS: "DOGEUSDT",
  USDBDT: "DOGEUSDT",
  USDINR: "DOGEUSDT",
  USDCOP: "DOGEUSDT",
  USDPKR: "DOGEUSDT",
  USDDZD: "DOGEUSDT",
  USDMXN: "DOGEUSDT",
  USDPHP: "DOGEUSDT",
  USDZAR: "DOGEUSDT",
}

exports.handler = async (event) => {
  try {
    const path = event.path.replace(/^\/api\/?/, "").replace(/^\/\.netlify\/functions\/api\/?/, "")
    if (event.httpMethod === "GET" && path === "config") {
      return json(200, {
        modes: ["Crypto", "Binance Spot", "Quotex", "Forex"],
        pairs: {
          Crypto: CRYPTO_PAIRS,
          "Binance Spot": BINANCE_SPOT_PAIRS,
          Quotex: QUOTEX_PAIRS,
          Forex: FOREX_PAIRS,
        },
        durations: DURATIONS,
      })
    }

    if (event.httpMethod === "POST" && (path === "signals/generate" || path === "market-data/refresh")) {
      const request = JSON.parse(event.body || "{}")
      const candles = await getCandles(request.pair)
      const latest = candles[candles.length - 1]
      if (path === "market-data/refresh") {
        return json(200, {
          mode: request.mode,
          pair: request.pair,
          current_price: round(latest.close),
          data_source: `Binance public live candles (${binanceSymbol(request.pair)})`,
          last_market_update: latest.timestamp,
          status: "LIVE",
        })
      }
      return json(200, analyze(request, candles))
    }

    return json(404, { detail: "API route not found." })
  } catch (error) {
    return json(502, { detail: error instanceof Error ? error.message : "Market analysis failed." })
  }
}

function json(statusCode, body) {
  return {
    statusCode,
    headers: {
      "content-type": "application/json",
      "access-control-allow-origin": "*",
    },
    body: JSON.stringify(body),
  }
}

async function getCandles(pair) {
  const symbol = binanceSymbol(pair)
  const endpoints = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
  ]
  let lastError = ""

  for (const endpoint of endpoints) {
    const url = new URL(endpoint)
    url.searchParams.set("symbol", symbol)
    url.searchParams.set("interval", "1s")
    url.searchParams.set("limit", "160")
    const response = await fetch(url)
    if (!response.ok) {
      lastError = `${endpoint} HTTP ${response.status}`
      continue
    }
    const rows = await response.json()
    if (!Array.isArray(rows) || rows.length < 35) {
      lastError = `${endpoint} returned too few candles`
      continue
    }
    return rows.map((row) => ({
      timestamp: new Date(row[0]).toISOString(),
      open: Number(row[1]),
      high: Number(row[2]),
      low: Number(row[3]),
      close: Number(row[4]),
      volume: Number(row[5]),
    }))
  }

  throw new Error(`Binance live data unavailable for ${pair} (${symbol}). ${lastError}`)
}

function binanceSymbol(pair = "BTC/USDT") {
  if (SYMBOL_MAP[pair]) return SYMBOL_MAP[pair]
  const cleaned = pair.replace(/\(OTC\)/gi, "").replace(/OTC/gi, "").replace(/[\/\-\s]/g, "").toUpperCase()
  if (SYMBOL_MAP[cleaned]) return SYMBOL_MAP[cleaned]
  if (cleaned.endsWith("USD") && !cleaned.endsWith("USDT")) return `${cleaned.slice(0, -3)}USDT`
  return cleaned || "BTCUSDT"
}

function analyze(request, candles) {
  const prices = candles.map((candle) => candle.close)
  const latestPrice = prices[prices.length - 1]
  const ema9 = ema(prices, 9)
  const ema21 = ema(prices, 21)
  const rsi14 = rsi(prices, 14)
  const trendDelta = prices[prices.length - 1] - prices[prices.length - 8]
  const volumes = candles.map((candle) => candle.volume)
  const recentVolume = average(volumes.slice(-10))
  const previousVolume = average(volumes.slice(-25, -10))
  const volumeRatio = previousVolume > 0 ? recentVolume / previousVolume : 1
  const last = candles[candles.length - 1]
  const symbol = binanceSymbol(request.pair)

  let bullish = 0
  let bearish = 0
  const analysis = [
    `Binance symbol used: ${symbol}`,
    `EMA9: ${ema9.toFixed(5)}`,
    `EMA21: ${ema21.toFixed(5)}`,
    `RSI(14): ${rsi14.toFixed(2)}`,
    `Volume ratio: ${volumeRatio.toFixed(2)}x`,
  ]

  if (ema9 > ema21 && latestPrice >= ema9) {
    bullish += 30
    analysis.push("EMA agreement: bullish")
  } else if (ema9 < ema21 && latestPrice <= ema9) {
    bearish += 30
    analysis.push("EMA agreement: bearish")
  } else {
    analysis.push("EMA agreement: mixed")
  }

  if (rsi14 >= 50 && rsi14 <= 68) {
    bullish += 20
    analysis.push("RSI confirmation: bullish pressure")
  } else if (rsi14 >= 32 && rsi14 < 50) {
    bearish += 20
    analysis.push("RSI confirmation: bearish pressure")
  } else if (rsi14 > 72) {
    bearish += 12
    analysis.push("RSI confirmation: overbought pullback risk")
  } else if (rsi14 < 28) {
    bullish += 12
    analysis.push("RSI confirmation: oversold rebound risk")
  } else {
    analysis.push("RSI confirmation: neutral")
  }

  if (trendDelta > 0) {
    bullish += 20
    analysis.push("Trend confirmation: last candles are rising")
  } else if (trendDelta < 0) {
    bearish += 20
    analysis.push("Trend confirmation: last candles are falling")
  } else {
    analysis.push("Trend confirmation: flat")
  }

  if (last.close > last.open) {
    bullish += 15
    analysis.push("Live candle confirmation: bullish")
  } else if (last.close < last.open) {
    bearish += 15
    analysis.push("Live candle confirmation: bearish")
  } else {
    analysis.push("Live candle confirmation: neutral")
  }

  if (volumeRatio >= 1.03) {
    if (bullish > bearish) bullish += 15
    if (bearish > bullish) bearish += 15
    analysis.push(bullish >= bearish ? "Volume confirmation: supports BUY" : "Volume confirmation: supports SELL")
  } else if (volumeRatio > 0.92) {
    if (bullish > bearish) bullish += 7
    if (bearish > bullish) bearish += 7
    analysis.push("Volume confirmation: normal")
  } else {
    analysis.push("Volume confirmation: weak volume, confidence reduced")
  }

  const dominant = Math.max(bullish, bearish)
  const edge = Math.abs(bullish - bearish)
  const confidence = Math.max(0, Math.min(95, Math.trunc((dominant / 100) * 100) + Math.trunc((edge / 100) * 18)))
  const signal = bullish > bearish && confidence >= 60 ? "UP" : bearish > bullish && confidence >= 60 ? "DOWN" : "WAIT"
  const marketTrend = signal === "UP" ? "Bullish" : signal === "DOWN" ? "Bearish" : "Sideways"

  return {
    mode: request.mode,
    pair: request.pair,
    current_price: round(latestPrice),
    signal,
    confidence,
    duration: request.duration,
    market_trend: marketTrend,
    status: signal,
    analysis: analysis.slice(0, 10),
    data_source: `Binance public live candles (${symbol})`,
    last_market_update: last.timestamp,
    generated_at: new Date().toISOString(),
    disclaimer: "Signals are probabilistic estimates only and do not guarantee profit or winning trades.",
  }
}

function ema(values, period) {
  const multiplier = 2 / (period + 1)
  let current = average(values.slice(0, period))
  for (const value of values.slice(period)) {
    current = value * multiplier + current * (1 - multiplier)
  }
  return current
}

function rsi(values, period) {
  const changes = []
  for (let index = 1; index < values.length; index += 1) changes.push(values[index] - values[index - 1])
  let gains = average(changes.slice(0, period).map((change) => Math.max(change, 0)))
  let losses = average(changes.slice(0, period).map((change) => Math.max(-change, 0)))
  for (const change of changes.slice(period)) {
    gains = (gains * (period - 1) + Math.max(change, 0)) / period
    losses = (losses * (period - 1) + Math.max(-change, 0)) / period
  }
  if (losses === 0) return 100
  return 100 - 100 / (1 + gains / losses)
}

function average(values) {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0
}

function round(value) {
  return Math.round(value * 100000) / 100000
}
