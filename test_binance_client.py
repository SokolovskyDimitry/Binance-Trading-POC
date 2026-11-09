"""
Unit and Integration Tests for BinancePublicClient
"""

import unittest
from binance_client import BinancePublicClient, BinanceAPIError


class TestBinancePublicClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = BinancePublicClient()

    def test_ping(self):
        result = self.client.ping()
        self.assertTrue(result, "Ping to Binance REST API failed")

    def test_get_server_time(self):
        res = self.client.get_server_time()
        self.assertIn("serverTime", res)
        self.assertIn("iso", res)
        self.assertGreater(res["serverTime"], 0)

    def test_get_ticker_price(self):
        btc_price = self.client.get_ticker_price("BTCUSDT")
        self.assertIsInstance(btc_price, dict)
        self.assertEqual(btc_price["symbol"], "BTCUSDT")
        self.assertGreater(btc_price["price"], 0)

    def test_get_24hr_stats(self):
        stats = self.client.get_24hr_stats("BTCUSDT")
        self.assertIsInstance(stats, dict)
        self.assertEqual(stats["symbol"], "BTCUSDT")
        self.assertIn("lastPrice", stats)
        self.assertIn("highPrice", stats)
        self.assertIn("lowPrice", stats)
        self.assertIn("priceChangePercent", stats)

    def test_get_klines(self):
        klines = self.client.get_klines("BTCUSDT", interval="1h", limit=10)
        self.assertIsInstance(klines, list)
        self.assertEqual(len(klines), 10)
        first_candle = klines[0]
        self.assertIn("open", first_candle)
        self.assertIn("high", first_candle)
        self.assertIn("low", first_candle)
        self.assertIn("close", first_candle)
        self.assertIn("volume", first_candle)

    def test_get_order_book(self):
        depth = self.client.get_order_book("BTCUSDT", limit=5)
        self.assertIn("bids", depth)
        self.assertIn("asks", depth)
        self.assertEqual(len(depth["bids"]), 5)
        self.assertEqual(len(depth["asks"]), 5)

    def test_get_recent_trades(self):
        trades = self.client.get_recent_trades("BTCUSDT", limit=5)
        self.assertIsInstance(trades, list)
        self.assertEqual(len(trades), 5)
        self.assertIn("price", trades[0])
        self.assertIn("qty", trades[0])

    def test_get_top_movers(self):
        movers = self.client.get_top_movers(limit=5, quote_asset="USDT")
        self.assertIn("gainers", movers)
        self.assertIn("losers", movers)
        self.assertIn("volume", movers)
        self.assertLessEqual(len(movers["gainers"]), 5)

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            self.client.get_klines("BTCUSDT", interval="invalid_interval")

    def test_invalid_depth_limit(self):
        with self.assertRaises(ValueError):
            self.client.get_order_book("BTCUSDT", limit=123)

    def test_invalid_symbol(self):
        with self.assertRaises(BinanceAPIError):
            self.client.get_ticker_price("NONEXISTENT_SYMBOL_XYZ")


if __name__ == "__main__":
    unittest.main()
