"""
Unit Tests for Technical Indicator Computations in indicators.py
"""

import unittest
import numpy as np
from binance_client import BinancePublicClient
from indicators import (
    donchian_channels,
    bollinger_bands,
    volume_expansion,
    detect_breakouts
)


class TestIndicators(unittest.TestCase):

    def setUp(self):
        # Create synthetic deterministic dataset
        self.highs = np.array([10, 12, 11, 13, 15, 14, 16, 18, 17, 20, 22, 21, 23, 25, 24, 26, 28, 27, 30, 32, 40], dtype=np.float64)
        self.lows = np.array([8,  9,  9,  10, 12, 11, 13, 14, 14, 16, 18, 17, 19, 20, 20, 22, 23, 22, 25, 26, 31], dtype=np.float64)
        self.closes = np.array([9, 11, 10, 12, 14, 13, 15, 17, 16, 19, 20, 19, 21, 23, 22, 25, 26, 25, 28, 30, 39], dtype=np.float64)
        self.volumes = np.array([100, 110, 95, 105, 115, 100, 120, 130, 105, 110, 100, 95, 105, 110, 100, 115, 120, 110, 105, 100, 500], dtype=np.float64)

    def test_donchian_channels(self):
        dc = donchian_channels(self.highs, self.lows, period=5)
        self.assertTrue(np.isnan(dc["upper"][0]))
        self.assertTrue(np.isnan(dc["upper"][3]))
        # At index 4 (5th element): max(highs[0:5]) = 15, min(lows[0:5]) = 8
        self.assertEqual(dc["upper"][4], 15.0)
        self.assertEqual(dc["lower"][4], 8.0)
        self.assertEqual(dc["middle"][4], 11.5)

    def test_bollinger_bands(self):
        bb = bollinger_bands(self.closes, period=5, num_std=2.0)
        self.assertTrue(np.isnan(bb["sma"][0]))
        self.assertFalse(np.isnan(bb["sma"][4]))
        
        # Check upper > sma > lower
        self.assertGreater(bb["upper"][4], bb["sma"][4])
        self.assertLess(bb["lower"][4], bb["sma"][4])
        
        # Check bandwidth % calculation
        expected_bw = (bb["upper"][4] - bb["lower"][4]) / bb["sma"][4]
        self.assertAlmostEqual(bb["bandwidth"][4], expected_bw)

    def test_volume_expansion(self):
        ve = volume_expansion(self.volumes, period=5, expansion_threshold=1.5)
        self.assertTrue(np.isnan(ve["volume_sma"][0]))
        self.assertFalse(np.isnan(ve["volume_sma"][4]))
        
        # On the last bar (500 volume vs average ~110), volume expansion must be True
        self.assertTrue(ve["is_expansion"][-1])
        self.assertGreater(ve["volume_ratio"][-1], 2.0)

    def test_detect_breakouts_synthetic(self):
        klines = []
        for i in range(len(self.closes)):
            klines.append({
                "high": float(self.highs[i]),
                "low": float(self.lows[i]),
                "close": float(self.closes[i]),
                "volume": float(self.volumes[i]),
                "close_datetime": f"2026-09-01T{i:02d}:00:00Z"
            })

        breakouts = detect_breakouts(klines, donchian_period=5, volume_period=5, volume_threshold=1.5)
        self.assertIn("latest", breakouts)
        # The last candle spiked from 30 to 39 with 500 volume -> should trigger a bullish breakout!
        self.assertTrue(breakouts["latest"]["bullish_breakout"])
        self.assertFalse(breakouts["latest"]["bearish_breakout"])

    def test_detect_breakouts_live_binance(self):
        client = BinancePublicClient()
        klines = client.get_klines("BTCUSDT", interval="1h", limit=50)
        breakouts = detect_breakouts(klines, donchian_period=20, volume_period=20)
        
        self.assertIn("latest", breakouts)
        self.assertIn("volume_ratio", breakouts["latest"])
        self.assertIn("is_squeeze", breakouts["latest"])
        self.assertIn("bullish_breakout", breakouts["latest"])


if __name__ == "__main__":
    unittest.main()
