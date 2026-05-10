"""Saucer (Rounding Bottom) detector.

A cup without a handle — gentler, typically longer in duration than a classic cup.
O'Neil considered this a valid base though less common than cup-with-handle.

Rules:
  * Duration 8+ weeks (40+ sessions), up to ~40 weeks
  * Depth 8-30% (shallower than cup; deeper ones are cups)
  * Rounded bottom (no sharp V)
  * Right side recovers within 6% of the left peak
  * No handle required — recent action hugging the right-side peak is fine
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
class SaucerParams:
    min_sessions: int = 40   # 8 weeks
    max_sessions: int = 200  # ~40 weeks
    min_depth: float = 0.08
    max_depth: float = 0.30
    max_right_side_gap: float = 0.06


class Saucer(ChartPattern):
    name = "saucer"

    def __init__(self, params: Optional[SaucerParams] = None) -> None:
        self.params = params or SaucerParams()

    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        p = self.params
        if df is None or df.empty or len(df) < p.min_sessions:
            return None

        window = df.tail(min(p.max_sessions, len(df))).copy()
        if len(window) < p.min_sessions:
            return None

        highs = window["high"].astype(float).values
        lows = window["low"].astype(float).values
        closes = window["close"].astype(float).values

        # Left peak: first-third maximum
        third = max(5, len(window) // 3)
        left_idx = int(np.argmax(highs[:third]))
        left_peak = float(highs[left_idx])

        # Bottom between left peak and the last third
        bottom_search = lows[left_idx : len(window) - third]
        if bottom_search.size < 5:
            return None
        bottom_rel = int(np.argmin(bottom_search))
        bottom_idx = left_idx + bottom_rel
        bottom = float(lows[bottom_idx])

        depth = (left_peak - bottom) / left_peak if left_peak > 0 else 0.0
        if not (p.min_depth <= depth <= p.max_depth):
            return None

        # Rounded bottom check: not a V
        if (bottom_idx - left_idx) < p.min_sessions // 3:
            return None

        # Right side peak in the final third
        right_region = highs[bottom_idx:]
        if right_region.size < 3:
            return None
        right_peak = float(right_region.max())
        recovery_gap = (left_peak - right_peak) / left_peak if left_peak > 0 else 1.0
        # right side must approach the left peak (<= max_right_side_gap below it)
        # and not exceed it by more than 5% (past that, the base has resolved into a breakout)
        if recovery_gap > p.max_right_side_gap or recovery_gap < -0.05:
            return None

        # If the current close sits close to the right-side peak, it's a valid saucer setup
        last_close = float(closes[-1])
        pivot = right_peak + 0.10
        dist_to_pivot = (pivot - last_close) / pivot if pivot > 0 else None

        depth_score = 1.0 - min(1.0, abs(depth - 0.15) / 0.15)
        # Clamp recovery_gap to [0, max] so negative gaps (right exceeded left) score as "great recovery"
        recovery_score = 1.0 - min(1.0, max(0.0, recovery_gap) / p.max_right_side_gap)
        confidence = float(max(0.0, min(1.0, 0.55 * depth_score + 0.45 * recovery_score)))

        return PatternMatch(
            name=self.name,
            detected=True,
            pivot=round(pivot, 2),
            confidence=round(confidence, 3),
            started_on=_as_date(window.index[left_idx]),
            completed_on=_as_date(window.index[-1]),
            evidence={
                "left_peak": round(left_peak, 2),
                "saucer_bottom": round(bottom, 2),
                "right_peak": round(right_peak, 2),
                "depth_pct": round(depth, 4),
                "duration_sessions": int(len(window) - left_idx),
                "current_close": round(last_close, 2),
                "dist_to_pivot_pct": round(dist_to_pivot, 4) if dist_to_pivot is not None else None,
            },
        )


def _as_date(idx_value) -> Optional[date]:
    try:
        return idx_value.date() if hasattr(idx_value, "date") else None
    except Exception:
        return None
