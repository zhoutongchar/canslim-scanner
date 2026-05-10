"""Double-Bottom ("W") detector.

Rules (O'Neil):
  * Two distinct lows separated by ~7 weeks minimum (35 sessions).
  * Middle peak rises 5-15% from the lows.
  * Second low is at or below first low (undercut is ideal).
  * Pattern forms after a prior decline of 8%+ (or near a 52-week high recovery).
  * Pivot = middle peak high + $0.10.
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
class DoubleBottomParams:
    lookback_sessions: int = 120
    min_separation_sessions: int = 30  # ~6 weeks
    max_low_mismatch_pct: float = 0.05  # second low within 5% of first
    min_middle_peak_rise: float = 0.05
    max_middle_peak_rise: float = 0.20
    require_second_undercut: bool = False  # strict O'Neil prefers this; off by default for more hits


class DoubleBottom(ChartPattern):
    name = "double_bottom"

    def __init__(self, params: Optional[DoubleBottomParams] = None) -> None:
        self.params = params or DoubleBottomParams()

    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        p = self.params
        if df is None or df.empty or len(df) < p.lookback_sessions:
            return None

        window = df.tail(p.lookback_sessions).copy()
        if len(window) < p.min_separation_sessions + 10:
            return None

        low = window.get("low", window["close"]).astype(float).values
        high = window.get("high", window["close"]).astype(float).values
        close = window["close"].astype(float).values
        index = window.index

        # First low = min in first half
        first_half_end = len(window) // 2
        if first_half_end < 5:
            return None
        first_low_idx = int(np.argmin(low[:first_half_end]))
        first_low = float(low[first_low_idx])

        # Second low = min in a window after enough separation
        second_search_start = first_low_idx + p.min_separation_sessions
        if second_search_start >= len(window) - 5:
            return None
        second_low_rel = int(np.argmin(low[second_search_start:]))
        second_low_idx = second_search_start + second_low_rel
        second_low = float(low[second_low_idx])

        # Lows must be comparable
        low_ref = min(first_low, second_low)
        if low_ref <= 0:
            return None
        mismatch = abs(first_low - second_low) / first_low
        if mismatch > p.max_low_mismatch_pct:
            return None

        if p.require_second_undercut and second_low > first_low:
            return None

        # Middle peak between the two lows
        if second_low_idx - first_low_idx < 5:
            return None
        middle_region = high[first_low_idx:second_low_idx]
        if middle_region.size == 0:
            return None
        middle_peak_rel = int(np.argmax(middle_region))
        middle_peak = float(middle_region[middle_peak_rel])

        rise_from_first = (middle_peak - first_low) / first_low if first_low > 0 else 0.0
        if not (p.min_middle_peak_rise <= rise_from_first <= p.max_middle_peak_rise):
            return None

        # Pivot = middle peak high + small buffer
        pivot = middle_peak + 0.10
        last_close = float(close[-1])
        dist_to_pivot = (pivot - last_close) / pivot if pivot > 0 else None

        # Confidence: balance mismatch quality + peak rise centered on ~10%
        mismatch_score = 1.0 - min(1.0, mismatch / p.max_low_mismatch_pct)
        rise_score = 1.0 - min(1.0, abs(rise_from_first - 0.10) / 0.10)
        undercut_bonus = 0.15 if second_low <= first_low else 0.0
        confidence = float(min(1.0, 0.5 * mismatch_score + 0.35 * rise_score + undercut_bonus))

        return PatternMatch(
            name=self.name,
            detected=True,
            pivot=round(pivot, 2),
            confidence=round(confidence, 3),
            started_on=_as_date(index[first_low_idx]),
            completed_on=_as_date(index[-1]),
            evidence={
                "first_low": round(first_low, 2),
                "second_low": round(second_low, 2),
                "low_mismatch_pct": round(mismatch, 4),
                "middle_peak": round(middle_peak, 2),
                "middle_peak_rise_pct": round(rise_from_first, 4),
                "separation_sessions": int(second_low_idx - first_low_idx),
                "second_undercuts_first": bool(second_low <= first_low),
                "current_close": round(last_close, 2),
                "dist_to_pivot_pct": round(dist_to_pivot, 4) if dist_to_pivot is not None else None,
            },
        )


def _as_date(idx_value) -> Optional[date]:
    try:
        return idx_value.date() if hasattr(idx_value, "date") else None
    except Exception:
        return None
