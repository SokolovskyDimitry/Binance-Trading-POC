"""
Multi-Timeframe Crypto Breakout Strategy
Combines Higher Timeframe (HTF) trend filtering with Lower Timeframe (LTF) volatility squeeze,
Donchian channel breakout, volume surge confirmation, and ATR dynamic risk management.
Signals are enriched by the BreakthroughReasoningEngine with a conviction score (0-100).
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from indicators import (
    donchian_channels,
    bollinger_bands,
    volume_expansion,
    _to_numpy_array,
)
from reasoning import BreakthroughReasoningEngine


def ema(data: Union[List[float], np.ndarray], period: int) -> np.ndarray:
    """Compute Exponential Moving Average (EMA) using NumPy."""
    arr = _to_numpy_array(data)
    n = len(arr)
    result = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return result

    # Initial SMA seed
    sma = np.mean(arr[:period])
    result[period - 1] = sma
    multiplier = 2.0 / (period + 1.0)

    for i in range(period, n):
        result[i] = (arr[i] - result[i - 1]) * multiplier + result[i - 1]

    return result


def atr(
    high: Union[List[float], np.ndarray],
    low: Union[List[float], np.ndarray],
    close: Union[List[float], np.ndarray],
    period: int = 14
) -> np.ndarray:
    """Compute Average True Range (ATR)."""
    high_arr = _to_numpy_array(high)
    low_arr = _to_numpy_array(low)
    close_arr = _to_numpy_array(close)

    n = len(close_arr)
    tr = np.zeros(n, dtype=np.float64)

    tr[0] = high_arr[0] - low_arr[0]
    for i in range(1, n):
        hl = high_arr[i] - low_arr[i]
        hc = abs(high_arr[i] - close_arr[i - 1])
        lc = abs(low_arr[i] - close_arr[i - 1])
        tr[i] = max(hl, hc, lc)

    atr_arr = np.full(n, np.nan, dtype=np.float64)
    if n >= period:
        atr_arr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr_arr[i] = (atr_arr[i - 1] * (period - 1) + tr[i]) / float(period)

    return atr_arr


class MultiTimeframeBreakoutStrategy:
    """
    Multi-Timeframe Breakout Trading Strategy.
    HTF: 4-hour (4h) Trend Filter (EMA 50 > EMA 200 for Longs; EMA 50 < EMA 200 for Shorts)
    LTF: 1-hour (1h) Entry Trigger:
       - Donchian Channel 20 Breach (Breakout)
       - Bollinger Band Squeeze (Volatility Contraction prior to move)
       - Volume Expansion >= 1.5x (Volume Surge Confirmation)
    Risk Management:
       - Dynamic Stop Loss = 1.5 * ATR(14)
       - Take Profit Target = 3.0 * ATR(14) (Risk/Reward 1:2)
    Reasoning:
       - Each signal is scored 0-100 by BreakthroughReasoningEngine.
       - Signals below `min_conviction` are downgraded to HOLD.
    """

    def __init__(
        self,
        htf_ema_fast: int = 50,
        htf_ema_slow: int = 200,
        ltf_donchian_period: int = 20,
        ltf_bollinger_period: int = 20,
        ltf_volume_period: int = 20,
        volume_threshold: float = 1.5,
        atr_period: int = 14,
        stop_loss_atr_mult: float = 1.5,
        take_profit_atr_mult: float = 3.0,
        min_conviction: float = 60.0,
    ):
        self.htf_ema_fast = htf_ema_fast
        self.htf_ema_slow = htf_ema_slow
        self.ltf_donchian_period = ltf_donchian_period
        self.ltf_bollinger_period = ltf_bollinger_period
        self.ltf_volume_period = ltf_volume_period
        self.volume_threshold = volume_threshold
        self.atr_period = atr_period
        self.stop_loss_atr_mult = stop_loss_atr_mult
        self.take_profit_atr_mult = take_profit_atr_mult
        self.min_conviction = min_conviction

        # Reasoning engine (shares same period settings as the strategy)
        self._reasoning = BreakthroughReasoningEngine(
            donchian_period=ltf_donchian_period,
            bollinger_period=ltf_bollinger_period,
            volume_period=ltf_volume_period,
            volume_threshold=volume_threshold,
            min_score=min_conviction,
        )


    def analyze_htf_trend(self, htf_klines: List[Dict[str, Any]]) -> Dict[str, np.ndarray]:
        """Compute Higher Timeframe Trend Bias."""
        closes = np.array([k["close"] for k in htf_klines], dtype=np.float64)
        ema_fast = ema(closes, self.htf_ema_fast)
        ema_slow = ema(closes, self.htf_ema_slow)

        bullish_bias = (ema_fast > ema_slow) & ~np.isnan(ema_slow)
        bearish_bias = (ema_fast < ema_slow) & ~np.isnan(ema_slow)

        return {
            "timestamps": np.array([k["open_time"] for k in htf_klines]),
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "bullish_bias": bullish_bias,
            "bearish_bias": bearish_bias
        }

    def generate_signals(
        self,
        ltf_klines: List[Dict[str, Any]],
        htf_klines: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate time-aligned entry signals and risk targets over LTF klines.

        Each signal is enriched with:
          - conviction_score (0-100): composite multi-factor reasoning score
          - grade: STRONG / MODERATE / WEAK / NONE
          - reasons: list of human-readable factor explanations
          - factor_scores: per-factor breakdown dict

        Signals below `min_conviction` are downgraded to HOLD even if the
        technical pattern fires, ensuring only high-quality setups are traded.
        """
        n_ltf = len(ltf_klines)
        if n_ltf < max(self.ltf_donchian_period, self.atr_period) + 1:
            return []

        # HTF Trend
        htf_trend = self.analyze_htf_trend(htf_klines)
        htf_times = htf_trend["timestamps"]
        htf_bullish = htf_trend["bullish_bias"]
        htf_bearish = htf_trend["bearish_bias"]

        # Map each LTF candle to the latest available HTF candle bias
        ltf_bullish_htf = np.full(n_ltf, False, dtype=bool)
        ltf_bearish_htf = np.full(n_ltf, False, dtype=bool)

        htf_idx = 0
        for i in range(n_ltf):
            ltf_time = ltf_klines[i]["open_time"]
            while htf_idx + 1 < len(htf_times) and htf_times[htf_idx + 1] <= ltf_time:
                htf_idx += 1
            ltf_bullish_htf[i] = htf_bullish[htf_idx]
            ltf_bearish_htf[i] = htf_bearish[htf_idx]

        # LTF Indicators
        highs = np.array([k["high"] for k in ltf_klines], dtype=np.float64)
        lows = np.array([k["low"] for k in ltf_klines], dtype=np.float64)
        closes = np.array([k["close"] for k in ltf_klines], dtype=np.float64)
        volumes = np.array([k["volume"] for k in ltf_klines], dtype=np.float64)

        dc = donchian_channels(highs, lows, period=self.ltf_donchian_period)
        ve = volume_expansion(volumes, period=self.ltf_volume_period, expansion_threshold=self.volume_threshold)
        bb = bollinger_bands(closes, period=self.ltf_bollinger_period)
        atr_vals = atr(highs, lows, closes, period=self.atr_period)

        # Pre-compute per-bar reasoning scores (returns list with skeleton for warm-up bars)
        try:
            reasoning_bars = self._reasoning.analyze(ltf_klines)
            reasoning_map = {r["index"]: r for r in reasoning_bars}
        except ValueError:
            reasoning_map = {}

        signals = []

        start_idx = max(self.ltf_donchian_period, self.atr_period)
        for i in range(start_idx, n_ltf):
            k = ltf_klines[i]
            prev_upper = dc["upper"][i - 1]
            prev_lower = dc["lower"][i - 1]
            curr_close = closes[i]
            curr_vol_expansion = ve["is_expansion"][i]
            curr_atr = atr_vals[i]

            # Pull reasoning for this bar (defaults to empty if not available)
            reasoning = reasoning_map.get(i, {})
            conviction = reasoning.get("conviction_score", 0.0)
            grade = reasoning.get("grade", "NONE")
            reasons = reasoning.get("reasons", [])
            factor_scores = reasoning.get("factor_scores", {})

            signal_type = "HOLD"
            stop_loss = 0.0
            take_profit = 0.0

            # Long Entry: HTF Bullish + LTF Close > Prev Donchian Upper + Volume Expansion
            # Additionally gated by minimum conviction score
            if (ltf_bullish_htf[i] and curr_close > prev_upper
                    and curr_vol_expansion and conviction >= self.min_conviction):
                signal_type = "BUY"
                stop_loss = curr_close - (self.stop_loss_atr_mult * curr_atr)
                take_profit = curr_close + (self.take_profit_atr_mult * curr_atr)

            # Short Entry: HTF Bearish + LTF Close < Prev Donchian Lower + Volume Expansion
            elif (ltf_bearish_htf[i] and curr_close < prev_lower
                  and curr_vol_expansion and conviction >= self.min_conviction):
                signal_type = "SELL"
                stop_loss = curr_close + (self.stop_loss_atr_mult * curr_atr)
                take_profit = curr_close - (self.take_profit_atr_mult * curr_atr)

            signals.append({
                "index": i,
                "timestamp": k["open_time"],
                "datetime": k["open_datetime"],
                "close": curr_close,
                "high": k["high"],
                "low": k["low"],
                "signal": signal_type,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "atr": curr_atr,
                "volume_ratio": ve["volume_ratio"][i],
                "is_squeeze": bb["is_squeeze"][i],
                "htf_bias": "BULLISH" if ltf_bullish_htf[i] else ("BEARISH" if ltf_bearish_htf[i] else "NEUTRAL"),
                # Reasoning enrichment
                "conviction_score": conviction,
                "grade": grade,
                "reasons": reasons,
                "factor_scores": factor_scores,
            })

        return signals

