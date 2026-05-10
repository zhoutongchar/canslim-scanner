"""Three-Weeks-Tight (3WT) detector.

O'Neil's add-on entry pattern: three consecutive weekly closes within a tight
range (typically ≤1.5% of each other). Signals controlled supply after a prior
advance. Pivot = highest weekly close + $0.10.
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
class ThreeWeeksTightParams:
    weeks: int = 3
    max_range_pct: float = 0.02  # ≤2% across the 3 weekly closes (slightly relaxed)


class ThreeWeeksTight(ChartPattern):
    name = "three_weeks_tight"

    def __init__(self, params: Optional[ThreeWeeksTightParams] = None) -> None:
        self.params = params or ThreeWeeksTightParams()

    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        p = self.params
        if df is None or df.empty or len(df) < p.weeks * 5:
            return None

        # Resample to weekly (Friday close)
        weekly = df["close"].astype(float).resample("W-FRI").last().dropna()
        if len(weekly) < p.weeks + 1:
            return None

        last_weeks = weekly.tail(p.weeks).values
        if np.any(last_weeks <= 0):
            return None
        hi = float(np.max(last_weeks))
        lo = float(np.min(last_weeks))
        rng = (hi - lo) / hi
        if rng > p.max_range_pct:
            return None

        # Require a prior advance so this isn't just sideways sludge
        prior = weekly.iloc[-(p.weeks + 8) : -p.weeks]
        if len(prior) < 4:
            return None
        prior_low = float(prior.min())
        if prior_low <= 0:
            return None
        prior_advance = (lo - prior_low) / prior_low
        if prior_advance < 0.08:  # 8% advance minimum in the 8 weeks before the tight window
            return None

        pivot = hi + 0.10
        last_daily_close = float(df["close"].iloc[-1])
        dist_to_pivot = (pivot - last_daily_close) / pivot if pivot > 0 else None
        confidence = float(0.6 * (1.0 - rng / p.max_range_pct) + 0.4 * min(1.0, prior_advance / 0.20))

        return PatternMatch(
            name=self.name,
            detected=True,
            pivot=round(pivot, 2),
            confidence=round(confidence, 3),
            started_on=_as_date(weekly.index[-p.weeks]),
            completed_on=_as_date(weekly.index[-1]),
            evidence={
                "weekly_closes": [round(v, 2) for v in last_weeks.tolist()],
                "range_pct": round(rng, 4),
                "prior_8w_advance_pct": round(prior_advance, 4),
                "current_close": round(last_daily_close, 2),
                "dist_to_pivot_pct": round(dist_to_pivot, 4) if dist_to_pivot is not None else None,
            },
        )


def _as_date(idx_value) -> Optional[date]:
    try:
        return idx_value.date() if hasattr(idx_value, "date") else None
    except Exception:
        return None
