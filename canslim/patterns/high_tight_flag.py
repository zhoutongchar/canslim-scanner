"""High-Tight-Flag detector.

O'Neil's most explosive pattern — rare but powerful:
  * Prior rally of 100-120%+ in 4-8 weeks (the "flagpole")
  * Followed by a tight 3-5 week consolidation that gives back 10-25%
  * Consolidation must stay in a tight range (the "flag")
  * Pivot = flag's highest close + $0.10
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
class HighTightFlagParams:
    flagpole_min_sessions: int = 20   # 4 weeks
    flagpole_max_sessions: int = 50   # 10 weeks (loosen slightly)
    flagpole_min_advance: float = 0.80  # 80%+ rally (relaxed from 100%)
    flag_min_sessions: int = 12       # 2.5 weeks
    flag_max_sessions: int = 30       # 6 weeks
    flag_min_pullback: float = 0.05
    flag_max_pullback: float = 0.28


class HighTightFlag(ChartPattern):
    name = "high_tight_flag"

    def __init__(self, params: Optional[HighTightFlagParams] = None) -> None:
        self.params = params or HighTightFlagParams()

    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        p = self.params
        needed = p.flagpole_max_sessions + p.flag_max_sessions
        if df is None or df.empty or len(df) < needed:
            return None

        # Flag: the trailing consolidation window
        for flag_size in range(p.flag_max_sessions, p.flag_min_sessions - 1, -1):
            flag = df.tail(flag_size)
            flag_high = float(flag["high"].max())
            flag_low = float(flag["low"].min())
            if flag_high <= 0:
                continue
            pullback = (flag_high - flag_low) / flag_high
            if not (p.flag_min_pullback <= pullback <= p.flag_max_pullback):
                continue

            # Flagpole: window before the flag
            pre_flag = df.iloc[: len(df) - flag_size]
            for pole_size in range(p.flagpole_max_sessions, p.flagpole_min_sessions - 1, -1):
                if len(pre_flag) < pole_size:
                    continue
                pole = pre_flag.tail(pole_size)
                pole_low = float(pole["low"].min())
                pole_high = float(pole["high"].max())
                if pole_low <= 0:
                    continue
                advance = (pole_high - pole_low) / pole_low
                if advance < p.flagpole_min_advance:
                    continue
                # The high must come near the end of the flagpole (it's the pole top)
                pole_high_idx_rel = int(np.argmax(pole["high"].values))
                if pole_high_idx_rel < pole_size * 0.5:
                    continue

                pivot = flag_high + 0.10
                last_close = float(flag["close"].iloc[-1])
                # Reject "stale" flag: price >20% past pivot — flag already resolved upward.
                if pivot > 0 and last_close > pivot * 1.20:
                    continue
                dist_to_pivot = (pivot - last_close) / pivot if pivot > 0 else None
                confidence = float(
                    min(1.0, 0.5 * min(1.0, advance / 1.0) + 0.3 * (1.0 - pullback / p.flag_max_pullback) + 0.2)
                )
                return PatternMatch(
                    name=self.name,
                    detected=True,
                    pivot=round(pivot, 2),
                    confidence=round(confidence, 3),
                    started_on=_as_date(pole.index[0]),
                    completed_on=_as_date(flag.index[-1]),
                    evidence={
                        "flagpole_sessions": int(pole_size),
                        "flagpole_advance_pct": round(advance, 4),
                        "flag_sessions": int(flag_size),
                        "flag_pullback_pct": round(pullback, 4),
                        "flag_high": round(flag_high, 2),
                        "flag_low": round(flag_low, 2),
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
