"""
Unit Tests for Multi-Timeframe Strategy & Backtester
"""

import unittest
import numpy as np
from strategy import ema, atr, MultiTimeframeBreakoutStrategy
from backtest import Backtester


class TestStrategyAndBacktest(unittest.TestCase):

    def setUp(self):
        # Generate 60 synthetic klines for LTF (1h) and 20 for HTF (4h)
        self.ltf_klines = []
        self.htf_klines = []

        base_time = 1700000000000
        for i in range(100):
            price = 100.0 + (i * 0.5) + (5.0 if i > 70 else 0.0)
            vol = 100.0 if i != 75 else 500.0  # Spike volume at index 75
            high_p = price + 2.0
            low_p = price - 2.0

            self.ltf_klines.append({
                "open_time": base_time + (i * 3600 * 1000),
                "open_datetime": f"2026-01-01T{i%24:02d}:00:00Z",
                "open": price - 0.2,
                "high": high_p,
                "low": low_p,
                "close": price,
                "volume": vol,
                "close_time": base_time + ((i + 1) * 3600 * 1000) - 1
            })

            if i % 4 == 0:
                self.htf_klines.append({
                    "open_time": base_time + (i * 3600 * 1000),
                    "open_datetime": f"2026-01-01T{i%24:02d}:00:00Z",
                    "open": price - 0.5,
                    "high": high_p + 1.0,
                    "low": low_p - 1.0,
                    "close": price,
                    "volume": vol * 4.0,
                    "close_time": base_time + ((i + 4) * 3600 * 1000) - 1
                })

    def test_ema(self):
        data = [10.0] * 50
        res = ema(data, 10)
        self.assertTrue(np.isnan(res[8]))
        self.assertAlmostEqual(res[9], 10.0)
        self.assertAlmostEqual(res[49], 10.0)

    def test_atr(self):
        highs = [12.0] * 30
        lows = [10.0] * 30
        closes = [11.0] * 30
        res = atr(highs, lows, closes, period=14)
        self.assertTrue(np.isnan(res[12]))
        self.assertAlmostEqual(res[13], 2.0)
        self.assertAlmostEqual(res[29], 2.0)

    def test_strategy_signal_generation(self):
        strat = MultiTimeframeBreakoutStrategy(
            htf_ema_fast=5,
            htf_ema_slow=10,
            ltf_donchian_period=10,
            ltf_bollinger_period=10,
            ltf_volume_period=10,
            volume_threshold=1.5
        )
        signals = strat.generate_signals(self.ltf_klines, self.htf_klines)
        self.assertIsInstance(signals, list)
        self.assertGreater(len(signals), 0)

        # Ensure signal contains stop loss and take profit targets
        sample = signals[-1]
        self.assertIn("signal", sample)
        self.assertIn("stop_loss", sample)
        self.assertIn("take_profit", sample)

    def test_backtester_execution(self):
        strat = MultiTimeframeBreakoutStrategy(
            htf_ema_fast=5,
            htf_ema_slow=10,
            ltf_donchian_period=10,
            ltf_bollinger_period=10,
            ltf_volume_period=10,
            volume_threshold=1.2
        )
        bt = Backtester(initial_capital=10000.0)
        results = bt.run(self.ltf_klines, self.htf_klines, strat)

        self.assertIn("final_capital", results)
        self.assertIn("total_trades", results)
        self.assertIn("win_rate", results)
        self.assertIn("max_drawdown", results)
        self.assertIn("trade_log", results)


if __name__ == "__main__":
    unittest.main()
