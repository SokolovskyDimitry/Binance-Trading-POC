"""
3-Month Backtesting Suite for Binance Market Data
Fetches historical market data (up to 90 days / 3 months), executes the Multi-Timeframe
Breakout Strategy, and computes performance metrics (Return, Win Rate, Profit Factor, Max Drawdown).
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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
from strategy import MultiTimeframeBreakoutStrategy


def fetch_historical_klines(
    client: BinancePublicClient,
    symbol: str,
    interval: str,
    days: int = 90
) -> List[Dict[str, Any]]:
    """
    Fetch historical klines over N days with automatic pagination.
    """
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)

    start_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)

    all_klines = []
    current_start = start_ts

    while current_start < end_ts:
        fetch_limit = 1000
        klines = client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=fetch_limit,
            start_time=current_start,
            end_time=end_ts
        )

        if not klines:
            break

        all_klines.extend(klines)

        # Move window start to timestamp after last candle
        last_close_ts = klines[-1]["close_time"]
        if last_close_ts <= current_start:
            break
        current_start = last_close_ts + 1

        # Avoid hitting rate limit aggressively
        time.sleep(0.05)

    # Remove duplicates if any
    unique_klines = {}
    for k in all_klines:
        unique_klines[k["open_time"]] = k

    sorted_klines = sorted(unique_klines.values(), key=lambda x: x["open_time"])
    return sorted_klines


class Backtester:
    """
    Backtesting Engine for Strategy Evaluation.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.00075,  # 0.075% taker fee
        slippage: float = 0.0005     # 0.05% slippage
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage

    def run(
        self,
        ltf_klines: List[Dict[str, Any]],
        htf_klines: List[Dict[str, Any]],
        strategy: MultiTimeframeBreakoutStrategy
    ) -> Dict[str, Any]:
        """Execute backtest over historical klines."""
        signals = strategy.generate_signals(ltf_klines, htf_klines)
        if not signals:
            return {"error": "Not enough data to generate strategy signals."}

        # Build lookup table for LTF candle index -> signal
        sig_map = {sig["index"]: sig for sig in signals}

        capital = self.initial_capital
        peak_capital = capital
        max_drawdown = 0.0

        position = None  # None, or dict with position details
        trade_log = []

        n = len(ltf_klines)
        for i in range(n):
            k = ltf_klines[i]
            high_p = k["high"]
            low_p = k["low"]
            close_p = k["close"]
            dt_str = k["open_datetime"]

            # Manage existing position
            if position is not None:
                pos_type = position["type"]
                stop_loss = position["stop_loss"]
                take_profit = position["take_profit"]
                entry_price = position["entry_price"]
                units = position["units"]

                exit_price = None
                exit_reason = None

                if pos_type == "LONG":
                    if low_p <= stop_loss:
                        exit_price = stop_loss * (1.0 - self.slippage)
                        exit_reason = "STOP_LOSS"
                    elif high_p >= take_profit:
                        exit_price = take_profit * (1.0 - self.slippage)
                        exit_reason = "TAKE_PROFIT"
                elif pos_type == "SHORT":
                    if high_p >= stop_loss:
                        exit_price = stop_loss * (1.0 + self.slippage)
                        exit_reason = "STOP_LOSS"
                    elif low_p <= take_profit:
                        exit_price = take_profit * (1.0 - self.slippage)
                        exit_reason = "TAKE_PROFIT"

                if exit_price is not None:
                    # Execute position exit
                    if pos_type == "LONG":
                        gross_proceeds = units * exit_price
                    else:  # SHORT
                        gross_proceeds = units * (2.0 * entry_price - exit_price)

                    fee = gross_proceeds * self.fee_rate
                    net_proceeds = gross_proceeds - fee
                    pnl_dollar = net_proceeds - position["cost"]
                    pnl_percent = (pnl_dollar / position["cost"]) * 100.0

                    capital += net_proceeds

                    trade_log.append({
                        "trade_id": len(trade_log) + 1,
                        "type": pos_type,
                        "entry_time": position["entry_time"],
                        "entry_price": entry_price,
                        "exit_time": dt_str,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "pnl_dollar": pnl_dollar,
                        "pnl_percent": pnl_percent,
                        "capital_after": capital
                    })

                    position = None

            # Track peak & drawdown
            if capital > peak_capital:
                peak_capital = capital
            dd = (peak_capital - capital) / peak_capital * 100.0
            if dd > max_drawdown:
                max_drawdown = dd

            # Check for new entry signal (only if no open position)
            if position is None and i in sig_map:
                sig = sig_map[i]
                sig_type = sig["signal"]

                if sig_type in ("BUY", "SELL"):
                    entry_price = close_p * (1.0 + self.slippage if sig_type == "BUY" else 1.0 - self.slippage)
                    cost = capital
                    fee = cost * self.fee_rate
                    effective_capital = cost - fee
                    units = effective_capital / entry_price

                    position = {
                        "type": "LONG" if sig_type == "BUY" else "SHORT",
                        "entry_time": dt_str,
                        "entry_price": entry_price,
                        "stop_loss": sig["stop_loss"],
                        "take_profit": sig["take_profit"],
                        "units": units,
                        "cost": cost
                    }

        # Close any position remaining open at backtest end
        if position is not None:
            last_k = ltf_klines[-1]
            exit_price = last_k["close"]
            pos_type = position["type"]
            units = position["units"]

            if pos_type == "LONG":
                gross_proceeds = units * exit_price
            else:
                gross_proceeds = units * (2.0 * position["entry_price"] - exit_price)

            fee = gross_proceeds * self.fee_rate
            net_proceeds = gross_proceeds - fee
            pnl_dollar = net_proceeds - position["cost"]
            pnl_percent = (pnl_dollar / position["cost"]) * 100.0

            capital += net_proceeds
            trade_log.append({
                "trade_id": len(trade_log) + 1,
                "type": pos_type,
                "entry_time": position["entry_time"],
                "entry_price": position["entry_price"],
                "exit_time": last_k["open_datetime"],
                "exit_price": exit_price,
                "exit_reason": "END_OF_TEST",
                "pnl_dollar": pnl_dollar,
                "pnl_percent": pnl_percent,
                "capital_after": capital
            })

        # Performance Calculations
        total_trades = len(trade_log)
        wins = [t for t in trade_log if t["pnl_dollar"] > 0]
        losses = [t for t in trade_log if t["pnl_dollar"] <= 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl_dollar"] for t in wins)
        gross_loss = abs(sum(t["pnl_dollar"] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        total_return_dollar = capital - self.initial_capital
        total_return_percent = (total_return_dollar / self.initial_capital) * 100.0

        avg_pnl_percent = (sum(t["pnl_percent"] for t in trade_log) / total_trades) if total_trades > 0 else 0.0

        return {
            "initial_capital": self.initial_capital,
            "final_capital": capital,
            "total_return_dollar": total_return_dollar,
            "total_return_percent": total_return_percent,
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "avg_pnl_percent": avg_pnl_percent,
            "trade_log": trade_log
        }


def run_backtest_command(symbol: str = "BTCUSDT", days: int = 90) -> Dict[str, Any]:
    """Helper command to execute 3-month backtest."""
    client = BinancePublicClient()
    print(f"\n[DOWNLOAD] Fetching {days} days of historical market data for {symbol.upper()}...")

    # Fetch 1-hour LTF data & 4-hour HTF data
    ltf_klines = fetch_historical_klines(client, symbol, interval="1h", days=days)
    htf_klines = fetch_historical_klines(client, symbol, interval="4h", days=days)

    print(f"[OK] Downloaded {len(ltf_klines)} 1h candles & {len(htf_klines)} 4h candles.")
    print("[RUNNING] Executing Multi-Timeframe Breakout Strategy Backtest...")

    strategy = MultiTimeframeBreakoutStrategy()
    backtester = Backtester(initial_capital=10000.0)
    results = backtester.run(ltf_klines, htf_klines, strategy)

    return results


def main():
    parser = argparse.ArgumentParser(description="Multi-Timeframe Crypto Breakout Strategy 3-Month Backtester")
    parser.add_argument("-s", "--symbol", type=str, default="BTCUSDT", help="Trading pair symbol (e.g. BTCUSDT, ETHUSDT)")
    parser.add_argument("-d", "--days", type=int, default=90, help="Number of historical days to backtest (default 90)")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    results = run_backtest_command(symbol, days=args.days)

    print("\n" + "=" * 65)
    print(f" [BACKTEST RESULTS] 3-MONTH STRATEGY PERFORMANCE: {symbol}")
    print("=" * 65)
    print(f"  Period Backtested:     {args.days} Days")
    print(f"  Initial Capital:       ${results['initial_capital']:,.2f}")
    print(f"  Final Capital:         ${results['final_capital']:,.2f}")
    print(f"  Net Profit / Loss:     ${results['total_return_dollar']:,.2f} ({results['total_return_percent']:+.2f}%)")
    print(f"  Total Executed Trades: {results['total_trades']}")
    print(f"  Winning Trades:        {results['win_count']} ({results['win_rate']:.1f}%)")
    print(f"  Losing Trades:         {results['loss_count']}")
    print(f"  Profit Factor:         {results['profit_factor']:.2f}")
    print(f"  Max Drawdown:          {results['max_drawdown']:.2f}%")
    print(f"  Avg Trade Return:      {results['avg_pnl_percent']:+.2f}%")
    print("=" * 65)

    if results["trade_log"]:
        print(f"\n[LOG] RECENT TRADES LOG (Last 5 of {results['total_trades']}):")
        print("-" * 75)
        print(f"{'#':<4} {'Type':<6} {'Entry Time':<20} {'Entry Price':<12} {'Exit Price':<12} {'PnL %':<10} {'Reason':<10}")
        print("-" * 75)
        for t in results["trade_log"][-5:]:
            print(f"{t['trade_id']:<4} {t['type']:<6} {t['entry_time'][:16]:<20} ${t['entry_price']:<11.2f} ${t['exit_price']:<11.2f} {t['pnl_percent']:+6.2f}%    {t['exit_reason']:<10}")
        print("-" * 75 + "\n")


if __name__ == "__main__":
    main()
