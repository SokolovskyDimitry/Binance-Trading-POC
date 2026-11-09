"""
Interactive Command-Line Tool for Binance Market Data
Provides real-time tickers, 24h stats, order book depth, top movers, and candlestick visualizer.
"""

import argparse
import csv
import sys
from datetime import datetime
from typing import List, Dict, Any

# Ensure stdout handles UTF-8 on Windows command prompts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from binance_client import BinancePublicClient, BinanceAPIError


def format_currency(value: float) -> str:
    """Format numbers into readable currency strings."""
    if value >= 1000:
        return f"${value:,.2f}"
    elif value >= 1:
        return f"${value:,.4f}"
    else:
        return f"${value:,.8f}"


def format_percent(value: float) -> str:
    """Format percentage with sign."""
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.2f}%"


def render_ascii_chart(klines: List[Dict[str, Any]], height: int = 10) -> str:
    """Render a clean ASCII line/candle preview chart in terminal."""
    if not klines:
        return "No candlestick data to plot."

    closes = [k["close"] for k in klines]
    min_val = min(closes)
    max_val = max(closes)
    val_range = max_val - min_val if max_val != min_val else 1.0

    lines = []
    lines.append(f"Price Chart ({klines[0]['open_datetime'][:10]} -> {klines[-1]['close_datetime'][:10]})")
    lines.append(f"Max: {format_currency(max_val)}")

    # Map prices to grid
    for h in range(height - 1, -1, -1):
        threshold = min_val + (val_range * (h / (height - 1)))
        row = []
        for i, k in enumerate(klines):
            prev_c = klines[i - 1]["close"] if i > 0 else k["open"]
            char = "#" if k["close"] >= prev_c else "."
            if abs(k["close"] - threshold) <= (val_range / (2 * height)):
                row.append(char)
            elif k["close"] > threshold:
                row.append("|")
            else:
                row.append(" ")
        lines.append("".join(row))

    lines.append(f"Min: {format_currency(min_val)}")
    return "\n".join(lines)


def print_24hr_stats(stats: Dict[str, Any]):
    print("\n" + "=" * 60)
    print(f" [STATS] 24-HOUR STATISTICS: {stats['symbol']}")
    print("=" * 60)
    print(f"  Last Price:        {format_currency(stats['lastPrice'])}")
    print(f"  24h Price Change:  {format_currency(stats['priceChange'])} ({format_percent(stats['priceChangePercent'])})")
    print(f"  24h High:          {format_currency(stats['highPrice'])}")
    print(f"  24h Low:           {format_currency(stats['lowPrice'])}")
    print(f"  24h Weighted Avg:  {format_currency(stats['weightedAvgPrice'])}")
    print(f"  24h Volume (Base): {stats['volume']:,.2f}")
    print(f"  24h Volume (Quote):${stats['quoteVolume']:,.2f}")
    print(f"  Bid Price / Qty:   {format_currency(stats['bidPrice'])} ({stats['bidQty']:.4f})")
    print(f"  Ask Price / Qty:   {format_currency(stats['askPrice'])} ({stats['askQty']:.4f})")
    print(f"  24h Trade Count:   {stats['count']:,}")
    print("=" * 60 + "\n")


def print_top_movers(client: BinancePublicClient, limit: int = 10, quote: str = "USDT"):
    print(f"\nFetching Top Market Movers (Quote Asset: {quote})...\n")
    movers = client.get_top_movers(limit=limit, quote_asset=quote)

    print("TOP GAINERS (24h)")
    print("-" * 55)
    print(f"{'Symbol':<12} {'Last Price':<15} {'24h Change':<12} {'24h Volume ($)':<15}")
    print("-" * 55)
    for s in movers["gainers"]:
        print(f"{s['symbol']:<12} {format_currency(s['lastPrice']):<15} {format_percent(s['priceChangePercent']):<12} ${s['quoteVolume']:,.0f}")

    print("\nTOP LOSERS (24h)")
    print("-" * 55)
    print(f"{'Symbol':<12} {'Last Price':<15} {'24h Change':<12} {'24h Volume ($)':<15}")
    print("-" * 55)
    for s in movers["losers"]:
        print(f"{s['symbol']:<12} {format_currency(s['lastPrice']):<15} {format_percent(s['priceChangePercent']):<12} ${s['quoteVolume']:,.0f}")

    print("\nHIGHEST VOLUME TRADING PAIRS")
    print("-" * 55)
    print(f"{'Symbol':<12} {'Last Price':<15} {'24h Change':<12} {'24h Volume ($)':<15}")
    print("-" * 55)
    for s in movers["volume"]:
        print(f"{s['symbol']:<12} {format_currency(s['lastPrice']):<15} {format_percent(s['priceChangePercent']):<12} ${s['quoteVolume']:,.0f}")
    print()


def print_order_book(client: BinancePublicClient, symbol: str, limit: int = 10):
    depth = client.get_order_book(symbol, limit=limit)
    print(f"\n[DEPTH] ORDER BOOK DEPTH for {symbol.upper()} (Top {limit})")
    print("=" * 55)
    print(f"{'ASKS (Sell)':^26} | {'BIDS (Buy)':^26}")
    print(f"{'Price':<14} {'Qty':<11} | {'Price':<14} {'Qty':<11}")
    print("-" * 55)

    asks = list(reversed(depth["asks"][:limit]))
    bids = depth["bids"][:limit]

    for i in range(max(len(asks), len(bids))):
        ask_str = f"{format_currency(asks[i][0]):<14} {asks[i][1]:<11.4f}" if i < len(asks) else ""
        bid_str = f"{format_currency(bids[i][0]):<14} {bids[i][1]:<11.4f}" if i < len(bids) else ""
        print(f"{ask_str} | {bid_str}")
    print("=" * 55 + "\n")


def print_klines(client: BinancePublicClient, symbol: str, interval: str, limit: int, export_csv: bool = False):
    klines = client.get_klines(symbol, interval=interval, limit=limit)
    print(f"\n[CANDLES] CANDLESTICK HISTORY for {symbol.upper()} ({interval} candles, count={len(klines)})")
    print("-" * 80)
    print(f"{'Open Time':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12} {'Volume':<10}")
    print("-" * 80)

    for k in klines[-15:]:  # Print last 15 in detail
        dt_str = k['open_datetime'].replace('T', ' ')[:19]
        print(f"{dt_str:<20} {k['open']:<12.4f} {k['high']:<12.4f} {k['low']:<12.4f} {k['close']:<12.4f} {k['volume']:<10.2f}")

    print("-" * 80)
    print(render_ascii_chart(klines))

    if export_csv:
        filename = f"{symbol.upper()}_{interval}_klines.csv"
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=klines[0].keys())
            writer.writeheader()
            writer.writerows(klines)
        print(f"\n[OK] Exported OHLCV data to '{filename}' successfully!")


from indicators import detect_breakouts


def print_indicators(client: BinancePublicClient, symbol: str, interval: str, limit: int = 50):
    klines = client.get_klines(symbol, interval=interval, limit=limit)
    res = detect_breakouts(klines, donchian_period=20, volume_period=20)
    latest = res["latest"]

    print("\n" + "=" * 60)
    print(f" [INDICATORS] TECHNICAL ANALYSIS & BREAKOUT SIGNAL: {symbol}")
    print("=" * 60)
    print(f"  Candle Time:       {latest['datetime']}")
    print(f"  Current Price:     {format_currency(latest['close'])}")
    print(f"  Donchian Upper (20):{format_currency(latest['upper_channel'])}")
    print(f"  Donchian Lower (20):{format_currency(latest['lower_channel'])}")
    print(f"  Volume Ratio (20): {latest['volume_ratio']:.2f}x (Expansion: {'YES' if latest['is_volume_expansion'] else 'NO'})")
    print(f"  Bollinger Squeeze: {'ACTIVE' if latest['is_squeeze'] else 'NONE'}")
    
    breakout_str = "NONE"
    if latest['bullish_breakout']:
        breakout_str = "🟢 BULLISH BREAKOUT CONFIRMED!"
    elif latest['bearish_breakout']:
        breakout_str = "🔴 BEARISH BREAKOUT CONFIRMED!"
    
    print(f"  Breakout Status:   {breakout_str}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Binance Public Market Data CLI Tool")
    parser.add_argument("-s", "--symbol", type=str, default="BTCUSDT", help="Trading pair symbol (e.g. BTCUSDT, ETHUSDT)")
    parser.add_argument("-a", "--action", type=str, choices=["stats", "price", "klines", "movers", "depth", "indicators", "all"], default="all", help="Action to perform")
    parser.add_argument("-i", "--interval", type=str, default="1h", help="Candlestick interval (1m, 5m, 15m, 1h, 4h, 1d, etc.)")
    parser.add_argument("-l", "--limit", type=int, default=20, help="Number of records to fetch")
    parser.add_argument("--export", action="store_true", help="Export candlestick data to CSV")

    args = parser.parse_args()
    client = BinancePublicClient()

    symbol = args.symbol.upper()

    try:
        if args.action == "stats":
            stats = client.get_24hr_stats(symbol)
            print_24hr_stats(stats)
        elif args.action == "price":
            price_data = client.get_ticker_price(symbol)
            print(f"\n[PRICE] Current Price for {symbol}: {format_currency(price_data['price'])}\n")
        elif args.action == "klines":
            print_klines(client, symbol, args.interval, args.limit, args.export)
        elif args.action == "movers":
            print_top_movers(client, limit=args.limit)
        elif args.action == "depth":
            print_order_book(client, symbol, limit=args.limit)
        elif args.action == "indicators":
            print_indicators(client, symbol, args.interval, limit=max(args.limit, 50))
        elif args.action == "all":
            print(f"\n[SUMMARY] RUNNING FULL MARKET SUMMARY FOR {symbol}")
            price_data = client.get_ticker_price(symbol)
            print(f"Current Price: {format_currency(price_data['price'])}")
            stats = client.get_24hr_stats(symbol)
            print_24hr_stats(stats)
            print_order_book(client, symbol, limit=10)
            print_indicators(client, symbol, args.interval, limit=50)
            print_klines(client, symbol, args.interval, limit=args.limit, export_csv=args.export)
    except BinanceAPIError as e:
        print(f"\n[ERROR] Binance API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
