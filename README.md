# Binance Public REST API Client & Market Suite

A Python client library, command-line interface (CLI) tool, unit test suite, and web dashboard built on Binance's public REST endpoints (`https://api.binance.com/api/v3/...`).

**No API keys or authentication required!**

---

## 🚀 Features

- **Zero Credentials Needed**: Connects directly to Binance public REST v3 API endpoints.
- **`binance_client.py`**: Clean, lightweight Python client supporting:
  - System Ping & Server Time (`/ping`, `/time`)
  - Exchange Information & Trading Rules (`/exchangeInfo`)
  - Real-Time Symbol Prices & Best Book Tickers (`/ticker/price`, `/ticker/bookTicker`)
  - 24-Hour Price Change Statistics (`/ticker/24hr`)
  - Historical Candlestick (OHLCV) Klines (`/klines`)
  - Order Book Depth & Recent Market Trades (`/depth`, `/trades`)
  - Top Gainers, Losers, and Volume Leaders Calculation
- **`indicators.py`**: Technical Indicator computation powered by NumPy:
  - **Donchian Channels**: N-period Highest High and Lowest Low channel calculation.
  - **Bollinger Bands & Squeeze**: Moving Average, Upper/Lower bands, bandwidth %, and squeeze detection.
  - **Volume Expansion**: Ratio of recent volume vs rolling volume moving average.
  - **Breakout Detection**: Combines price breaching resistance/channel bounds with volume surge confirmation.
- **`cli.py`**: Command-line tool featuring:
  - Symbol market summary & 24h stats
  - ASCII terminal candlestick price chart visualizer
  - Top movers table (gainers, losers, volume leaders)
  - CSV exporter for OHLCV historical candle data
- **`app.py`**: Web Dashboard Server:
  - Serves a single-page Web UI with Chart.js price history
  - Live 24h market stats & order book depth visualization
  - Quick symbol selector & search bar
- **`test_binance_client.py`**: Automated unittest suite verifying all public REST endpoints.

---

## 🛠️ Usage

### 1. Python API Client (`binance_client.py`)

```python
from binance_client import BinancePublicClient

client = BinancePublicClient()

# Test API connectivity
print("Ping:", client.ping())

# Get real-time price
btc_price = client.get_ticker_price("BTCUSDT")
print(f"BTC Price: ${btc_price['price']:,.2f}")

# Get 24h Statistics
stats = client.get_24hr_stats("BTCUSDT")
print(f"24h Change: {stats['priceChangePercent']}% | High: ${stats['highPrice']}")

# Fetch Candlesticks (OHLCV)
klines = client.get_klines("BTCUSDT", interval="1h", limit=10)
for k in klines:
    print(f"{k['open_datetime']} | Open: {k['open']} | Close: {k['close']} | Volume: {k['volume']}")

# Fetch Top Gainers & Losers
movers = client.get_top_movers(limit=5, quote_asset="USDT")
print("Top Gainer:", movers['gainers'][0]['symbol'], movers['gainers'][0]['priceChangePercent'], "%")
```

---

### 2. Command-Line Interface (`cli.py`)

#### View 24-Hour Statistics for BTCUSDT:
```bash
python cli.py -s BTCUSDT -a stats
```

#### Display OHLCV Candlestick History & ASCII Chart:
```bash
python cli.py -s BTCUSDT -a klines -i 1d -l 10
```

#### Export Candlestick Data to CSV:
```bash
python cli.py -s ETHUSDT -a klines -i 1h -l 100 --export
```

#### View Order Book Depth (Top Bids/Asks):
```bash
python cli.py -s SOLUSDT -a depth -l 10
```

#### View Technical Indicators & Breakout Signals:
```bash
python cli.py -s BTCUSDT -a indicators -i 1h
```

#### View Top Gainers, Losers, and Volume Leaders:
```bash
python cli.py -a movers
```

---

### 3. Web Dashboard (`app.py`)

Launch the dashboard server locally:
```bash
python app.py 5000
```
Open **[http://localhost:5000](http://localhost:5000)** in your browser to view the interactive real-time dashboard.

---

### 4. Running Tests (`test_binance_client.py`)

Run the automated test suite against Binance public REST endpoints:
```bash
python -m unittest test_binance_client.py
```
