"""
Breakthrough Reasoning Engine
Scores and explains price breakthrough signals using a multi-factor weighted model.

Factors and Weights
-------------------
  Channel Breach      30 pts  -- How far price pierced the Donchian boundary
  Volume Surge        25 pts  -- Volume relative to its 20-period rolling average
  Squeeze Release     20 pts  -- Bollinger bandwidth expanding out of a squeeze
  Momentum (ROC-5)    15 pts  -- 5-bar rate-of-change in breakout direction
  Candle Body Ratio   10 pts  -- Body-to-range proportion on the breakout candle

Total conviction score: 0-100.
A score >= min_score (default 60) marks the signal as is_confirmed = True.
"""

from typing import Any, Dict, List, Union
import numpy as np

from indicators import (
    donchian_channels,
    bollinger_bands,
    volume_expansion,
    rate_of_change,
    candle_body_ratio,
    _to_numpy_array,
)

# ---------------------------------------------------------------------------
# Weight constants (must sum to 100)
# ---------------------------------------------------------------------------
W_CHANNEL  = 30
W_VOLUME   = 25
W_SQUEEZE  = 20
W_MOMENTUM = 15
W_BODY     = 10

# Default parameters
DEFAULT_DONCHIAN_PERIOD  = 20
DEFAULT_BOLLINGER_PERIOD = 20
DEFAULT_VOLUME_PERIOD    = 20
DEFAULT_ROC_PERIOD       = 5
DEFAULT_MIN_SCORE        = 60

# Volume ratio is capped at this multiple before scoring (prevents outliers)
VOLUME_RATIO_CAP = 3.0

# Grade thresholds
GRADE_STRONG   = 75
GRADE_MODERATE = 50
GRADE_WEAK     = 25


def _grade(score: float) -> str:
    """Convert a numeric conviction score to a qualitative grade string."""
    if score >= GRADE_STRONG:
        return "STRONG"
    if score >= GRADE_MODERATE:
        return "MODERATE"
    if score >= GRADE_WEAK:
        return "WEAK"
    return "NONE"


class BreakthroughReasoningEngine:
    """
    Multi-factor breakthrough reasoning engine.

    Usage
    -----
    engine = BreakthroughReasoningEngine()
    results = engine.analyze(klines)         # per-bar list of reasoning dicts
    latest  = engine.analyze_latest(klines)  # only the most recent bar
    """

    def __init__(
        self,
        donchian_period: int = DEFAULT_DONCHIAN_PERIOD,
        bollinger_period: int = DEFAULT_BOLLINGER_PERIOD,
        volume_period: int = DEFAULT_VOLUME_PERIOD,
        roc_period: int = DEFAULT_ROC_PERIOD,
        volume_threshold: float = 1.5,
        min_score: float = DEFAULT_MIN_SCORE,
    ):
        self.donchian_period  = donchian_period
        self.bollinger_period = bollinger_period
        self.volume_period    = volume_period
        self.roc_period       = roc_period
        self.volume_threshold = volume_threshold
        self.min_score        = min_score

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Score and explain every bar in klines.

        Parameters
        ----------
        klines : list of dicts as returned by BinancePublicClient.get_klines()

        Returns
        -------
        List of per-bar reasoning dicts (see module docstring for schema).
        Bars without enough history return a skeleton dict with signal=NONE.
        """
        min_bars = (
            max(self.donchian_period, self.bollinger_period, self.volume_period)
            + self.roc_period + 1
        )
        if len(klines) < min_bars:
            raise ValueError(
                "Need at least {} klines to compute breakthrough reasoning "
                "(got {}).".format(min_bars, len(klines))
            )

        opens   = np.array([k["open"]   for k in klines], dtype=np.float64)
        highs   = np.array([k["high"]   for k in klines], dtype=np.float64)
        lows    = np.array([k["low"]    for k in klines], dtype=np.float64)
        closes  = np.array([k["close"]  for k in klines], dtype=np.float64)
        volumes = np.array([k["volume"] for k in klines], dtype=np.float64)

        # Pre-compute all indicators
        dc  = donchian_channels(highs, lows, period=self.donchian_period)
        bb  = bollinger_bands(closes, period=self.bollinger_period)
        ve  = volume_expansion(
            volumes, period=self.volume_period,
            expansion_threshold=self.volume_threshold
        )
        roc = rate_of_change(closes, period=self.roc_period)
        cbr = candle_body_ratio(opens, highs, lows, closes)

        start_idx = (
            max(self.donchian_period, self.bollinger_period, self.volume_period)
            + self.roc_period
        )

        results = []
        for i in range(len(klines)):
            k = klines[i]
            if i < start_idx:
                results.append(self._empty_bar(k, i))
            else:
                results.append(
                    self._score_bar(
                        index=i, k=k, closes=closes,
                        dc=dc, bb=bb, ve=ve, roc=roc, cbr=cbr,
                    )
                )
        return results

    def analyze_latest(self, klines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return reasoning for only the most recent bar."""
        return self.analyze(klines)[-1]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_bar(self, index, k, closes, dc, bb, ve, roc, cbr):
        """Score a single bar and return a reasoning dict."""
        i = index
        curr_close = closes[i]
        prev_upper = dc["upper"][i - 1]
        prev_lower = dc["lower"][i - 1]

        # Determine directional bias using PREVIOUS bar channel (confirm on close)
        bullish_candidate = bool(curr_close > prev_upper and not np.isnan(prev_upper))
        bearish_candidate = bool(curr_close < prev_lower and not np.isnan(prev_lower))

        if not bullish_candidate and not bearish_candidate:
            return self._empty_bar(k, i)

        direction = "BULLISH" if bullish_candidate else "BEARISH"
        side_label = "upper" if bullish_candidate else "lower"
        breach_sign = "+" if bullish_candidate else "-"

        # ── Factor 1: Channel Breach (0-30) ─────────────────────────────────
        channel_ref = prev_upper if bullish_candidate else prev_lower
        if channel_ref != 0:
            breach_pct = abs(curr_close - channel_ref) / channel_ref * 100.0
        else:
            breach_pct = 0.0
        # 0% breach -> 0 pts; >=1% breach -> full 30 pts (linear)
        f_channel = min(W_CHANNEL, (breach_pct / 1.0) * W_CHANNEL)
        r_channel = (
            "Price breached Donchian {} by {}{:.2f}% (score: {:.1f}/{})".format(
                side_label, breach_sign, breach_pct, f_channel, W_CHANNEL
            )
        )

        # ── Factor 2: Volume Surge (0-25) ────────────────────────────────────
        vol_ratio = ve["volume_ratio"][i]
        if np.isnan(vol_ratio):
            vol_ratio = 0.0
        # 1.0x -> 0 pts; >=3.0x -> full 25 pts (linear, capped)
        capped_ratio = min(vol_ratio, VOLUME_RATIO_CAP)
        f_volume = max(0.0, ((capped_ratio - 1.0) / (VOLUME_RATIO_CAP - 1.0)) * W_VOLUME)
        r_volume = "Volume surge {:.2f}x avg (score: {:.1f}/{})".format(
            vol_ratio, f_volume, W_VOLUME
        )

        # ── Factor 3: Volatility Squeeze Release (0-20) ──────────────────────
        prev_squeeze = bool(bb["is_squeeze"][i - 1]) if i > 0 else False
        curr_bw = bb["bandwidth"][i]
        prev_bw = bb["bandwidth"][i - 1] if i > 0 else np.nan
        bw_expanding = (
            not np.isnan(curr_bw) and not np.isnan(prev_bw) and curr_bw > prev_bw
        )
        if prev_squeeze and bw_expanding:
            f_squeeze = float(W_SQUEEZE)
            r_squeeze = (
                "Bollinger squeeze released, bandwidth expanding "
                "({:.4f} > {:.4f}) (score: {:.1f}/{})".format(
                    curr_bw, prev_bw, f_squeeze, W_SQUEEZE
                )
            )
        elif bw_expanding:
            f_squeeze = W_SQUEEZE * 0.5
            r_squeeze = "Bollinger bandwidth expanding (no prior squeeze) (score: {:.1f}/{})".format(
                f_squeeze, W_SQUEEZE
            )
        else:
            f_squeeze = 0.0
            r_squeeze = "No Bollinger bandwidth expansion (score: 0/{})".format(W_SQUEEZE)

        # ── Factor 4: Momentum / ROC (0-15) ──────────────────────────────────
        curr_roc = roc[i] if not np.isnan(roc[i]) else 0.0
        # Directional: positive ROC for bullish, negative ROC for bearish
        directional_roc = curr_roc if bullish_candidate else -curr_roc
        # 0% ROC -> 0 pts; >=2% ROC in right direction -> full 15 pts (linear)
        f_momentum = min(W_MOMENTUM, max(0.0, (directional_roc / 2.0) * W_MOMENTUM))
        alignment_label = "aligned" if directional_roc > 0 else "counter"
        r_momentum = (
            "ROC-{}: {:+.2f}% ({} with breakout direction) (score: {:.1f}/{})".format(
                self.roc_period, curr_roc, alignment_label, f_momentum, W_MOMENTUM
            )
        )

        # ── Factor 5: Candle Body Ratio (0-10) ───────────────────────────────
        body_r = cbr[i]
        candle_bullish = k["close"] >= k["open"]
        body_aligned = (
            (bullish_candidate and candle_bullish)
            or (bearish_candidate and not candle_bullish)
        )
        f_body = (body_r * W_BODY) if body_aligned else 0.0
        body_label = "aligned" if body_aligned else "misaligned"
        r_body = "Candle body ratio {:.2f} ({} with breakout) (score: {:.1f}/{})".format(
            body_r, body_label, f_body, W_BODY
        )

        # ── Composite Score ───────────────────────────────────────────────────
        conviction = round(
            min(100.0, max(0.0, f_channel + f_volume + f_squeeze + f_momentum + f_body)),
            2,
        )

        return {
            "index":            i,
            "timestamp":        k.get("open_time"),
            "datetime":         k.get("open_datetime", ""),
            "close":            float(curr_close),
            "signal":           direction,
            "conviction_score": conviction,
            "grade":            _grade(conviction),
            "is_confirmed":     bool(conviction >= self.min_score),
            "reasons":          [r_channel, r_volume, r_squeeze, r_momentum, r_body],
            "factor_scores": {
                "channel_breach":  round(f_channel,  2),
                "volume_surge":    round(f_volume,   2),
                "squeeze_release": round(f_squeeze,  2),
                "momentum":        round(f_momentum, 2),
                "candle_body":     round(f_body,     2),
            },
            "meta": {
                "prev_donchian_upper": float(prev_upper) if not np.isnan(prev_upper) else None,
                "prev_donchian_lower": float(prev_lower) if not np.isnan(prev_lower) else None,
                "volume_ratio": (
                    round(float(ve["volume_ratio"][i]), 4)
                    if not np.isnan(ve["volume_ratio"][i]) else None
                ),
                "bollinger_bandwidth": (
                    round(float(bb["bandwidth"][i]), 6)
                    if not np.isnan(bb["bandwidth"][i]) else None
                ),
                "roc": (
                    round(float(roc[i]), 4)
                    if not np.isnan(roc[i]) else None
                ),
                "body_ratio":       round(float(cbr[i]), 4),
                "prev_was_squeeze": bool(prev_squeeze),
            },
        }

    @staticmethod
    def _empty_bar(k: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Return a skeleton reasoning dict for bars without enough history."""
        return {
            "index":            index,
            "timestamp":        k.get("open_time"),
            "datetime":         k.get("open_datetime", ""),
            "close":            float(k.get("close", 0.0)),
            "signal":           "NONE",
            "conviction_score": 0.0,
            "grade":            "NONE",
            "is_confirmed":     False,
            "reasons":          ["Insufficient historical data for scoring."],
            "factor_scores": {
                "channel_breach":  0.0,
                "volume_surge":    0.0,
                "squeeze_release": 0.0,
                "momentum":        0.0,
                "candle_body":     0.0,
            },
            "meta": {},
        }
