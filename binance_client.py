"""
Binance Public REST API v3 Client
No API keys or authentication required.
Endpoints covered:
  - System Ping & Server Time
  - Exchange Information & Symbol Specifications
  - Real-time Symbol Prices & Book Tickers
  - 24-hour Price Change Statistics
  - Order Book Depth & Recent Trades
  - Historical Candlestick (OHLCV) Klines
  - Top Gainers, Losers, and Volume Leaders
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union


class BinanceAPIError(Exception):
    """Exception raised when Binance REST API returns an error response."""
    def __init__(self, status_code: int, code: int, msg: str):
        self.status_code = status_code
        self.code = code
        self.msg = msg
        super().__init__(f"Binance API Error {code} (HTTP {status_code}): {msg}")


class BinancePublicClient:
    """Public REST API client for Binance Spot Market (v3)."""

    BASE_URL = "https://api.binance.com/api/v3"

    VALID_INTERVALS = {
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "8h", "12h",
        "1d", "3d", "1w", "1M"
    }

    def __init__(self, base_url: Optional[str] = None, timeout: int = 10):
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.timeout = timeout

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Internal helper to send GET requests to Binance public endpoints."""
        url = f"{self.base_url}{endpoint}"
        if params:
            # Filter out None values
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if filtered_params:
                query_string = urllib.parse.urlencode(filtered_params)
                url = f"{url}?{query_string}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BinancePublicClient/1.0 (Python)",
                "Accept": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                err_data = json.loads(error_body)
                raise BinanceAPIError(
                    status_code=e.code,
                    code=err_data.get("code", -1),
                    msg=err_data.get("msg", str(e))
                ) from e
            except json.JSONDecodeError:
                raise BinanceAPIError(status_code=e.code, code=-1, msg=error_body or str(e)) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to connect to Binance API ({url}): {e.reason}") from e

    def ping(self) -> bool:
        """Test connectivity to the Binance REST API."""
        res = self._request("/ping")
        return res == {}

    def get_server_time(self) -> Dict[str, Any]:
        """Fetch current Binance server timestamp."""
        res = self._request("/time")
        server_ms = res.get("serverTime", 0)
        dt = datetime.fromtimestamp(server_ms / 1000.0, tz=timezone.utc)
        return {
            "serverTime": server_ms,
            "iso": dt.isoformat(),
            "datetime": dt
        }

    def get_exchange_info(self, symbol: Optional[str] = None, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fetch current exchange trading rules and symbol information."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        elif symbols:
            params["symbols"] = json.dumps([s.upper() for s in symbols])
        return self._request("/exchangeInfo", params)

    def get_ticker_price(self, symbol: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Fetch latest price for a symbol or all symbols."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        res = self._request("/ticker/price", params)
        if isinstance(res, dict):
            res["price"] = float(res["price"])
        elif isinstance(res, list):
            for item in res:
                item["price"] = float(item["price"])
        return res

    def get_24hr_stats(self, symbol: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Fetch 24-hour rolling window price change statistics."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        res = self._request("/ticker/24hr", params)
        
        def _parse_stats(item: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "symbol": item["symbol"],
                "priceChange": float(item.get("priceChange", 0)),
                "priceChangePercent": float(item.get("priceChangePercent", 0)),
                "weightedAvgPrice": float(item.get("weightedAvgPrice", 0)),
                "prevClosePrice": float(item.get("prevClosePrice", 0)),
                "lastPrice": float(item.get("lastPrice", 0)),
                "lastQty": float(item.get("lastQty", 0)),
                "bidPrice": float(item.get("bidPrice", 0)),
                "bidQty": float(item.get("bidQty", 0)),
                "askPrice": float(item.get("askPrice", 0)),
                "askQty": float(item.get("askQty", 0)),
                "openPrice": float(item.get("openPrice", 0)),
                "highPrice": float(item.get("highPrice", 0)),
                "lowPrice": float(item.get("lowPrice", 0)),
                "volume": float(item.get("volume", 0)),
                "quoteVolume": float(item.get("quoteVolume", 0)),
                "openTime": item.get("openTime"),
                "closeTime": item.get("closeTime"),
                "firstId": item.get("firstId"),
                "lastId": item.get("lastId"),
                "count": item.get("count", 0),
            }

        if isinstance(res, dict):
            return _parse_stats(res)
        elif isinstance(res, list):
            return [_parse_stats(item) for item in res]
        return res

    def get_book_ticker(self, symbol: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Fetch best price/qty on the order book for a symbol or all symbols."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        res = self._request("/ticker/bookTicker", params)
        def _parse_book(item: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "symbol": item["symbol"],
                "bidPrice": float(item.get("bidPrice", 0)),
                "bidQty": float(item.get("bidQty", 0)),
                "askPrice": float(item.get("askPrice", 0)),
                "askQty": float(item.get("askQty", 0))
            }
        if isinstance(res, dict):
            return _parse_book(res)
        elif isinstance(res, list):
            return [_parse_book(i) for i in res]
        return res

    VALID_DEPTH_LIMITS = {5, 10, 20, 50, 100, 500, 1000, 5000}

    def get_order_book(self, symbol: str, limit: int = 100, raw: bool = False) -> Dict[str, Any]:
        """
        Fetch order book bids and asks (depth) from GET /api/v3/depth.
        Valid limits: 5, 10, 20, 50, 100, 500, 1000, 5000.
        """
        if limit not in self.VALID_DEPTH_LIMITS:
            raise ValueError(f"Invalid depth limit '{limit}'. Must be one of: {sorted(self.VALID_DEPTH_LIMITS)}")

        params = {"symbol": symbol.upper(), "limit": limit}
        res = self._request("/depth", params)
        
        if raw:
            return res

        return {
            "lastUpdateId": res.get("lastUpdateId"),
            "bids": [[float(price), float(qty)] for price, qty in res.get("bids", [])],
            "asks": [[float(price), float(qty)] for price, qty in res.get("asks", [])]
        }

    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch recent trades for a symbol."""
        params = {"symbol": symbol.upper(), "limit": limit}
        res = self._request("/trades", params)
        parsed = []
        for trade in res:
            parsed.append({
                "id": trade.get("id"),
                "price": float(trade.get("price", 0)),
                "qty": float(trade.get("qty", 0)),
                "quoteQty": float(trade.get("quoteQty", 0)),
                "time": trade.get("time"),
                "datetime": datetime.fromtimestamp(trade.get("time", 0) / 1000.0, tz=timezone.utc).isoformat(),
                "isBuyerMaker": trade.get("isBuyerMaker"),
                "isBestMatch": trade.get("isBestMatch")
            })
        return parsed

    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch candlestick / OHLCV history.
        Interval options: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M.
        """
        if interval not in self.VALID_INTERVALS:
            raise ValueError(f"Invalid interval '{interval}'. Must be one of: {sorted(self.VALID_INTERVALS)}")

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time
        }
        res = self._request("/klines", params)
        
        parsed_klines = []
        for item in res:
            open_ts = item[0]
            close_ts = item[6]
            parsed_klines.append({
                "open_time": open_ts,
                "open_datetime": datetime.fromtimestamp(open_ts / 1000.0, tz=timezone.utc).isoformat(),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "close_time": close_ts,
                "close_datetime": datetime.fromtimestamp(close_ts / 1000.0, tz=timezone.utc).isoformat(),
                "quote_volume": float(item[7]),
                "trades_count": int(item[8]),
                "taker_buy_base_volume": float(item[9]),
                "taker_buy_quote_volume": float(item[10])
            })
        return parsed_klines

    def get_top_movers(
        self,
        limit: int = 10,
        quote_asset: str = "USDT"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch top gainers, top losers, and highest volume trading pairs."""
        all_stats = self.get_24hr_stats()
        if not isinstance(all_stats, list):
            all_stats = [all_stats]

        # Filter by quote asset (e.g. USDT)
        quote_upper = quote_asset.upper()
        filtered = [
            s for s in all_stats
            if s["symbol"].endswith(quote_upper) and s["quoteVolume"] > 10000.0  # filter low volume noise
        ]

        top_gainers = sorted(filtered, key=lambda x: x["priceChangePercent"], reverse=True)[:limit]
        top_losers = sorted(filtered, key=lambda x: x["priceChangePercent"])[:limit]
        top_volume = sorted(filtered, key=lambda x: x["quoteVolume"], reverse=True)[:limit]

        return {
            "gainers": top_gainers,
            "losers": top_losers,
            "volume": top_volume
        }
