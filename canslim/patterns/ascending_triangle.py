"""Ascending Triangle detector.

Bullish continuation pattern: flat upper resistance with rising lower support,
forming a triangle that converges toward an upside breakout.

Rules:
  * At least 2 swing highs near the same level (<3% variation — "flat top")
  * At least 2 swing lows with a positive slope (rising support)
  * Duration typically 4-12 weeks
  * Pivot = flat top + $0.10
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from canslim.models import PatternMatch
from canslim.patterns.base import ChartPattern


@dataclass
class AscendingTriangleParams:
    min_sessions: int = 20   # ~4 weeks
    max_sessions: int = 60   # ~12 weeks
    max_top_variation: float = 0.04    # flat resistance: ≤4% variation across highs
    min_lows_slope_pct: float = 0.02   # rising support: last swing low ≥2% above first
    peak_prominence: float = 0.02      # swing must be 2%+ above neighbors


class AscendingTriangle(ChartPattern):
    name = "ascending_triangle"

    def __init__(self, params: Optional[AscendingTriangleParams] = None) -> None:
        self.params = params or AscendingTriangleParams()

    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        p = self.params
        if df is None or df.empty or len(df) < p.min_sessions:
            return None

        for size in range(min(p.max_sessions, len(df)), p.min_sessions - 1, -1):
            window = df.tail(size)
            highs = window["high"].astype(float).values
            lows = window["low"].astype(float).values
            closes = window["close"].astype(float).values

            top_level, top_indices = _top_swings(highs, p.peak_prominence)
            if top_level is None or len(top_indices) < 2:
                continue
            top_max = float(np.max(highs[top_indices]))
            top_min = float(np.min(highs[top_indices]))
            if top_max <= 0:
                continue
            variation = (top_max - top_min) / top_max
            if variation > p.max_top_variation:
                continue

            bot_indices = _bottom_swings(lows, p.peak_prominence)
            if len(bot_indices) < 2:
                continue
            first_low = float(lows[bot_indices[0]])
            last_low = float(lows[bot_indices[-1]])
            if first_low <= 0:
                continue
            slope_pct = (last_low - first_low) / first_low
            if slope_pct < p.min_lows_slope_pct:
                continue

            pivot = top_max + 0.10
            last_close = float(closes[-1])
            # Reject "stale" triangle: price >20% past pivot — already broken out and run.
            if pivot > 0 and last_close > pivot * 1.20:
                continue
            dist_to_pivot = (pivot - last_close) / pivot if pivot > 0 else None
            # Confidence: tight top + strong rising support + enough swings
            tight_score = 1.0 - min(1.0, variation / p.max_top_variation)
            slope_score = min(1.0, slope_pct / 0.10)
            swings_score = min(1.0, (len(top_indices) + len(bot_indices)) / 6.0)
            confidence = float(0.45 * tight_score + 0.35 * slope_score + 0.2 * swings_score)

            return PatternMatch(
                name=self.name,
                detected=True,
                pivot=round(pivot, 2),
                confidence=round(confidence, 3),
                started_on=_as_date(window.index[0]),
                completed_on=_as_date(window.index[-1]),
                evidence={
                    "sessions": int(size),
                    "top_max": round(top_max, 2),
                    "top_variation_pct": round(variation, 4),
                    "rising_support_pct": round(slope_pct, 4),
                    "top_touches": int(len(top_indices)),
                    "bottom_touches": int(len(bot_indices)),
                    "current_close": round(last_close, 2),
                    "dist_to_pivot_pct": round(dist_to_pivot, 4) if dist_to_pivot is not None else None,
                },
            )
        return None


def _top_swings(highs: np.ndarray, prominence: float) -> tuple[Optional[float], list[int]]:
    """Find local maxima that rise `prominence` above neighbors."""
    n = len(highs)
    out: list[int] = []
    for i in range(2, n - 2):
        if highs[i] <= 0:
            continue
        left = max(highs[i - 2], highs[i - 1])
        right = max(highs[i + 1], highs[i + 2])
        if highs[i] > left * (1 + prominence * 0.5) and highs[i] > right * (1 + prominence * 0.5):
            out.append(i)
    return (max(highs[out]) if out else None), out


def _bottom_swings(lows: np.ndarray, prominence: float) -> list[int]:
    n = len(lows)
    out: list[int] = []
    for i in range(2, n - 2):
        if lows[i] <= 0:
            continue
        left = min(lows[i - 2], lows[i - 1])
        right = min(lows[i + 1], lows[i + 2])
        if lows[i] < left * (1 - prominence * 0.5) and lows[i] < right * (1 - prominence * 0.5):
            out.append(i)
    return out


def _as_date(idx_value) -> Optional[date]:
    try:
        return idx_value.date() if hasattr(idx_value, "date") else None
    except Exception:
        return None
