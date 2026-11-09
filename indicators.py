"""
Technical Indicator Computation using NumPy
Provides Donchian Channels, Bollinger Bands & Squeeze detection, Volume Expansion, Breakout Signal Detection,
Rate-of-Change (momentum), and Candle Body Ratio (wick-strength analysis).
"""

from typing import Any, Dict, List, Union
import numpy as np


def _to_numpy_array(data: Union[List[float], np.ndarray]) -> np.ndarray:
    """Ensure input data is a 1D float64 NumPy array."""
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("Input data array must be 1-dimensional.")
    return arr


def donchian_channels(
    high: Union[List[float], np.ndarray],
    low: Union[List[float], np.ndarray],
    period: int = 20
) -> Dict[str, np.ndarray]:
    """
    Compute Donchian Channels over an N-period window.
    Upper Channel: N-period Highest High
    Lower Channel: N-period Lowest Low
    Middle Channel: Average of Upper and Lower Channels
    """
    high_arr = _to_numpy_array(high)
    low_arr = _to_numpy_array(low)

    if len(high_arr) != len(low_arr):
        raise ValueError("High and Low arrays must be of equal length.")

    n = len(high_arr)
    upper = np.full(n, np.nan, dtype=np.float64)
    lower = np.full(n, np.nan, dtype=np.float64)

    for i in range(period - 1, n):
        upper[i] = np.max(high_arr[i - period + 1 : i + 1])
        lower[i] = np.min(low_arr[i - period + 1 : i + 1])

    middle = (upper + lower) / 2.0

    return {
        "upper": upper,
        "lower": lower,
        "middle": middle
    }


def bollinger_bands(
    close: Union[List[float], np.ndarray],
    period: int = 20,
    num_std: float = 2.0,
    squeeze_quantile: float = 0.20
) -> Dict[str, np.ndarray]:
    """
    Compute Bollinger Bands, Bandwidth %, and Squeeze Detection.
    - Middle Band: N-period SMA
    - Upper Band: SMA + (num_std * std)
    - Lower Band: SMA - (num_std * std)
    - Bandwidth: (Upper - Lower) / Middle
    - Squeeze: Bandwidth is below the historical quantile threshold
    """
    close_arr = _to_numpy_array(close)
    n = len(close_arr)

    sma = np.full(n, np.nan, dtype=np.float64)
    std = np.full(n, np.nan, dtype=np.float64)

    for i in range(period - 1, n):
        window = close_arr[i - period + 1 : i + 1]
        sma[i] = np.mean(window)
        std[i] = np.std(window, ddof=0)

    upper = sma + (num_std * std)
    lower = sma - (num_std * std)

    bandwidth = np.full(n, np.nan, dtype=np.float64)
    valid_mask = ~np.isnan(sma) & (sma > 0)
    bandwidth[valid_mask] = (upper[valid_mask] - lower[valid_mask]) / sma[valid_mask]

    # Calculate squeeze: bandwidth below quantile threshold of non-NaN values
    valid_bw = bandwidth[valid_mask]
    squeeze_threshold = np.quantile(valid_bw, squeeze_quantile) if len(valid_bw) > 0 else np.nan
    is_squeeze = np.full(n, False, dtype=bool)
    if not np.isnan(squeeze_threshold):
        is_squeeze[valid_mask] = bandwidth[valid_mask] <= squeeze_threshold

    return {
        "sma": sma,
        "upper": upper,
        "lower": lower,
        "bandwidth": bandwidth,
        "is_squeeze": is_squeeze,
        "squeeze_threshold": squeeze_threshold
    }


def volume_expansion(
    volume: Union[List[float], np.ndarray],
    period: int = 20,
    expansion_threshold: float = 1.5
) -> Dict[str, np.ndarray]:
    """
    Compute Volume Expansion ratio vs rolling N-period volume moving average.
    - volume_sma: N-period SMA of volume
    - volume_ratio: Recent volume / volume_sma
    - is_expansion: True if volume_ratio >= expansion_threshold
    """
    vol_arr = _to_numpy_array(volume)
    n = len(vol_arr)

    vol_sma = np.full(n, np.nan, dtype=np.float64)
    for i in range(period - 1, n):
        vol_sma[i] = np.mean(vol_arr[i - period + 1 : i + 1])

    vol_ratio = np.full(n, np.nan, dtype=np.float64)
    valid_mask = ~np.isnan(vol_sma) & (vol_sma > 0)
    vol_ratio[valid_mask] = vol_arr[valid_mask] / vol_sma[valid_mask]

    is_expansion = np.full(n, False, dtype=bool)
    is_expansion[valid_mask] = vol_ratio[valid_mask] >= expansion_threshold

    return {
        "volume_sma": vol_sma,
        "volume_ratio": vol_ratio,
        "is_expansion": is_expansion
    }


def detect_breakouts(
    klines: List[Dict[str, Any]],
    donchian_period: int = 20,
    volume_period: int = 20,
    volume_threshold: float = 1.5
) -> Dict[str, Any]:
    """
    Detect price breakouts confirmed by volume expansion.
    - Bullish Breakout: Close > Upper Donchian Channel of PREVIOUS candle AND Volume Ratio >= Volume Threshold.
    - Bearish Breakout: Close < Lower Donchian Channel of PREVIOUS candle AND Volume Ratio >= Volume Threshold.
    """
    if len(klines) < max(donchian_period, volume_period) + 1:
        raise ValueError(f"Need at least {max(donchian_period, volume_period) + 1} klines to compute breakouts.")

    highs = np.array([k["high"] for k in klines], dtype=np.float64)
    lows = np.array([k["low"] for k in klines], dtype=np.float64)
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    volumes = np.array([k["volume"] for k in klines], dtype=np.float64)

    dc = donchian_channels(highs, lows, period=donchian_period)
    ve = volume_expansion(volumes, period=volume_period, expansion_threshold=volume_threshold)
    bb = bollinger_bands(closes, period=20)

    n = len(klines)
    bullish = np.full(n, False, dtype=bool)
    bearish = np.full(n, False, dtype=bool)

    for i in range(max(donchian_period, volume_period), n):
        prev_upper = dc["upper"][i - 1]
        prev_lower = dc["lower"][i - 1]

        vol_expanded = ve["is_expansion"][i]

        if vol_expanded and closes[i] > prev_upper:
            bullish[i] = True
        elif vol_expanded and closes[i] < prev_lower:
            bearish[i] = True

    # Latest bar status summary
    last_idx = n - 1
    latest_status = {
        "symbol": klines[last_idx].get("symbol", "N/A"),
        "datetime": klines[last_idx].get("close_datetime", ""),
        "close": closes[last_idx],
        "upper_channel": dc["upper"][last_idx - 1] if last_idx > 0 else np.nan,
        "lower_channel": dc["lower"][last_idx - 1] if last_idx > 0 else np.nan,
        "volume_ratio": ve["volume_ratio"][last_idx],
        "is_volume_expansion": bool(ve["is_expansion"][last_idx]),
        "is_squeeze": bool(bb["is_squeeze"][last_idx]),
        "bullish_breakout": bool(bullish[last_idx]),
        "bearish_breakout": bool(bearish[last_idx]),
    }

    return {
        "donchian": dc,
        "bollinger": bb,
        "volume_expansion": ve,
        "bullish_breakout": bullish,
        "bearish_breakout": bearish,
        "latest": latest_status
    }


def rate_of_change(
    close: Union[List[float], np.ndarray],
    period: int = 5
) -> np.ndarray:
    """
    Compute the Rate of Change (ROC) momentum indicator.

    ROC[i] = ((close[i] - close[i - period]) / close[i - period]) * 100

    Returns an array of percentage change values.  Values for indices
    where a prior bar is unavailable are set to NaN.
    """
    close_arr = _to_numpy_array(close)
    n = len(close_arr)
    roc = np.full(n, np.nan, dtype=np.float64)

    for i in range(period, n):
        prev = close_arr[i - period]
        if prev != 0:
            roc[i] = ((close_arr[i] - prev) / prev) * 100.0

    return roc


def candle_body_ratio(
    open_: Union[List[float], np.ndarray],
    high: Union[List[float], np.ndarray],
    low: Union[List[float], np.ndarray],
    close: Union[List[float], np.ndarray],
) -> np.ndarray:
    """
    Compute the Candle Body Ratio — the fraction of the full candle range
    that is occupied by the real body (open-to-close).

    ratio = |close - open| / (high - low)

    Returns values in [0, 1].  A ratio near 1 indicates a strong candle with
    little upper/lower wick; a ratio near 0 indicates an indecision doji.
    Candles where high == low (zero-range) are assigned a ratio of 0.
    """
    open_arr = _to_numpy_array(open_)
    high_arr = _to_numpy_array(high)
    low_arr = _to_numpy_array(low)
    close_arr = _to_numpy_array(close)

    n = len(close_arr)
    ratio = np.zeros(n, dtype=np.float64)

    full_range = high_arr - low_arr
    body = np.abs(close_arr - open_arr)

    nonzero = full_range > 0
    ratio[nonzero] = body[nonzero] / full_range[nonzero]

    return ratio

