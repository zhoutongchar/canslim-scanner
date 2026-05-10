"""Flat-Base detector.

O'Neil's flat base: price trades sideways for 5+ weeks with <15% variation, typically
after a prior base or run-up. Often the tightest, highest-probability pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from canslim.models import PatternMatch
from canslim.patterns.base import ChartPattern


@dataclass
class FlatBaseParams:
    min_sessions: int = 25  # ~5 weeks
    max_sessions: int = 50
    max_range_pct: float = 0.15


class FlatBase(ChartPattern):
    name = "flat_base"

    def __init__(self, params: Optional[FlatBaseParams] = None) -> None:
        self.params = params or FlatBaseParams()

    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        p = self.params
        if df is None or df.empty or len(df) < p.min_sessions:
            return None

        # Sliding window — try the widest valid base ending today
        for size in range(min(p.max_sessions, len(df)), p.min_sessions - 1, -1):
            window = df.tail(size)
            hi = float(window["high"].max() if "high" in window else window["close"].max())
            lo = float(window["low"].min() if "low" in window else window["close"].min())
            if lo <= 0:
                continue
            rng = (hi - lo) / hi
            if rng <= p.max_range_pct:
                pivot = hi + 0.10
                last_close = float(window["close"].iloc[-1])
                dist_to_pivot = (pivot - last_close) / pivot if pivot > 0 else None
                confidence = float(max(0.0, 1.0 - rng / p.max_range_pct)) * 0.9  # cap to leave room above
                return PatternMatch(
                    name=self.name,
                    detected=True,
                    pivot=round(pivot, 2),
                    confidence=round(confidence, 3),
                    started_on=_as_date(window.index[0]),
                    completed_on=_as_date(window.index[-1]),
                    evidence={
                        "sessions": int(size),
                        "range_pct": round(rng, 4),
                        "base_high": round(hi, 2),
                        "base_low": round(lo, 2),
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
