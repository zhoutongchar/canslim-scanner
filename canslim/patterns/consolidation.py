"""Consolidation (Square Box) detector.

Rectangle consolidation with a flat ceiling and a nearly flat floor — tighter than
a flat base on both ends. Often forms after a strong advance; breakout above the
upper rail can precede another leg higher.

Rules:
  * Duration 15-40 sessions
  * Upper rail variation ≤ 3%
  * Lower rail variation ≤ 3%
  * Box range (high-low) 5-15%
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
class ConsolidationParams:
    min_sessions: int = 15
    max_sessions: int = 40
    max_rail_variation: float = 0.03
    min_box_range: float = 0.05
    max_box_range: float = 0.15


class Consolidation(ChartPattern):
    name = "consolidation"

    def __init__(self, params: Optional[ConsolidationParams] = None) -> None:
        self.params = params or ConsolidationParams()

    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        p = self.params
        if df is None or df.empty or len(df) < p.min_sessions:
            return None

        for size in range(min(p.max_sessions, len(df)), p.min_sessions - 1, -1):
            window = df.tail(size)
            highs = window["high"].astype(float).values
            lows = window["low"].astype(float).values
            if not highs.size or np.min(highs) <= 0:
                continue

            upper_var = (np.max(highs) - np.quantile(highs, 0.85)) / np.max(highs)
            lower_var = (np.quantile(lows, 0.15) - np.min(lows)) / np.min(lows) if np.min(lows) > 0 else 1.0
            if upper_var > p.max_rail_variation or lower_var > p.max_rail_variation:
                continue

            box_hi = float(np.max(highs))
            box_lo = float(np.min(lows))
            box_range = (box_hi - box_lo) / box_hi if box_hi > 0 else 0.0
            if not (p.min_box_range <= box_range <= p.max_box_range):
                continue

            pivot = box_hi + 0.10
            last_close = float(window["close"].iloc[-1])
            # Reject "stale" consolidation: price >20% past pivot — entry is gone.
            if pivot > 0 and last_close > pivot * 1.20:
                continue
            dist_to_pivot = (pivot - last_close) / pivot if pivot > 0 else None
            tight_score = 1.0 - min(1.0, (upper_var + lower_var) / (2 * p.max_rail_variation))
            confidence = float(0.7 * tight_score + 0.3 * min(1.0, size / p.max_sessions))

            return PatternMatch(
                name=self.name,
                detected=True,
                pivot=round(pivot, 2),
                confidence=round(confidence, 3),
                started_on=_as_date(window.index[0]),
                completed_on=_as_date(window.index[-1]),
                evidence={
                    "sessions": int(size),
                    "box_high": round(box_hi, 2),
                    "box_low": round(box_lo, 2),
                    "box_range_pct": round(box_range, 4),
                    "upper_rail_variation_pct": round(upper_var, 4),
                    "lower_rail_variation_pct": round(lower_var, 4),
                    "current_close": round(last_close, 2),
                    "dist_to_pivot_pct": round(dist_to_pivot, 4) if dist_to_pivot is not None else None,
                },
            )
        return None


def _as_date(idx_value) -> Optional[date]:
    try:
        return idx_value.date() if hasattr(idx_value, "date") else None
    except Exception:
        return None
