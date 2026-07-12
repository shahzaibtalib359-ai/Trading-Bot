# AI Trading Signal Application

Professional multi-client trading signal application for Forex and Quotex-style pairs.

Important: this application provides probability-based estimates only. It never guarantees profits, winning trades, or trading outcomes.

## Project Structure

```text
backend/
  api/          FastAPI routes
  indicators/   RSI, EMA, MACD, Bollinger Bands, support/resistance, momentum, candles
  strategy/     Confidence scoring and signal generation
  database/     SQLite repository, history, watchlist, statistics, CSV export
  services/     Market data provider abstraction
desktop/        PyQt6 Windows desktop client
mobile/         Flutter Android client source
assets/         Shared assets
logs/           Runtime logs and CSV exports
```

## Windows Setup

Run this once from the project root:

```bat
cd C:\Users\PMLS\Documents\Trading-Bot
setup_windows.bat
```

The setup script creates `.venv`, installs backend and desktop dependencies, and verifies these imports:

```text
fastapi, uvicorn, pydantic, PyQt6, requests
```

## Backend

Start the API server:

```bat
run_backend.bat
```

Open API docs:

```text
http://127.0.0.1:8012/docs
```

By default the backend uses the pluggable `auto` provider router:

- `Quotex` mode uses an API-Quotex compatible live OTC bridge.
- `Forex` mode uses an XM/MT5 compatible live bridge.
- `Crypto` mode uses Binance public live candles.

Yahoo Finance is not used. If no live Quotex OTC bridge is connected, the app returns `No live Quotex OTC data source connected` and keeps the signal on `WAIT`.

For API-Quotex OTC, set:

```text
TRADING_MARKET_PROVIDER=auto
TRADING_QUOTEX_API_URL=http://127.0.0.1:9001/candles
TRADING_QUOTEX_API_KEY=optional-key
TRADING_QUOTEX_SSID=your-api-quotex-ssid
```

For XM/MT5 Forex, set:

```text
TRADING_MARKET_PROVIDER=auto
TRADING_XM_API_URL=http://127.0.0.1:9002/candles
TRADING_XM_API_KEY=optional-key
```

For Binance crypto candles, no key is required by default:

```text
TRADING_MARKET_PROVIDER=auto
TRADING_BINANCE_API_URL=https://api.binance.com
```

You can still connect a generic candle API by setting:

```text
TRADING_MARKET_PROVIDER=external
TRADING_EXTERNAL_MARKET_API_URL=https://your-provider.example/candles
TRADING_EXTERNAL_MARKET_API_KEY=your-key
```

Expected external response shape:

```json
{
  "candles": [
    {"timestamp": "2026-06-18T12:00:00Z", "open": 1.08, "high": 1.09, "low": 1.07, "close": 1.085, "volume": 1200}
  ]
}
```

## Desktop

Start the backend first, then open a second CMD window and run:

```bat
run_desktop.bat
```

Or start backend and desktop together:

```bat
run_all.bat
```

The Windows desktop client includes:

- Trading mode selection for Forex, Quotex, and Crypto
- Pair and duration selection
- Manual market data refresh
- Multi-pair scanner
- Dark dashboard
- Signal history and statistics
- Sound alert for strong signals

## Mobile

Start the backend first, then:

```bash
cd mobile
flutter pub get
flutter run
```

The Android emulator uses:

```text
http://10.0.2.2:8000/api
```

For a physical Android device, change `baseUrl` in `mobile/lib/services/api_service.dart` to your computer LAN IP.

## Confidence Rules

- `0-59%`: NO TRADE
- `60-74%`: Weak Signal
- `75-89%`: Strong Signal
- `90%+`: Very Strong Signal

## API Highlights

- `GET /api/config`
- `POST /api/signals/generate`
- `POST /api/signals/scan`
- `GET /api/history`
- `PATCH /api/history/{signal_id}/outcome`
- `GET /api/statistics`
- `GET /api/history/export`
