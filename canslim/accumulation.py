"""Accumulation/Distribution rating — IBD-style A-E grade.

Measures whether a stock is being *accumulated* (bought on strength) or
*distributed* (sold on strength) over the past ~50 sessions. Classic O'Neil
signal: even if the base looks good and earnings are strong, distribution
in the chart is a warning the breakout may fail.

Algorithm:
  * Look at last `sessions` daily bars.
  * For each bar, compute dollar-volume = close * volume.
  * Up-day = close > prior close. Down-day = close < prior close.
  * Emphasize big-range conviction moves: weight each day's dollar volume by
    abs(close-change / prior-close) so a +5% on heavy volume counts much more
    than a +0.1% flat close.
  * ad_ratio = up_flow / (up_flow + down_flow)
  * Map to A/B/C/D/E letter grade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

DEFAULT_SESSIONS = 50


@dataclass(frozen=True)
class ADRating:
    grade: str  # "A" | "B" | "C" | "D" | "E"
    ratio: float  # up_flow / (up_flow + down_flow), 0..1
    up_flow: float
    down_flow: float
    sessions: int


def compute_ad_rating(df: pd.DataFrame, sessions: int = DEFAULT_SESSIONS) -> Optional[ADRating]:
    if df is None or df.empty or len(df) < max(sessions, 10):
        return None
    window = df.tail(sessions + 1).copy()  # +1 so diff covers `sessions` days
    close = window["close"].astype(float)
    vol = window["volume"].astype(float)
    delta = close.diff()
    pct = delta / close.shift(1)
    # Skip the first row (NaN diff)
    pct = pct.iloc[1:]
    close_t = close.iloc[1:]
    vol_t = vol.iloc[1:]

    # Conviction-weighted dollar flow
    dollar_flow = (close_t * vol_t * pct.abs()).astype(float)
    up_mask = pct > 0
    down_mask = pct < 0
    up_flow = float(dollar_flow[up_mask].sum())
    down_flow = float(dollar_flow[down_mask].sum())

    total = up_flow + down_flow
    if total == 0:
        ratio = 0.5
    else:
        ratio = up_flow / total

    if ratio >= 0.62:
        grade = "A"
    elif ratio >= 0.55:
        grade = "B"
    elif ratio >= 0.45:
        grade = "C"
    elif ratio >= 0.38:
        grade = "D"
    else:
        grade = "E"

    return ADRating(
        grade=grade,
        ratio=round(ratio, 4),
        up_flow=round(up_flow, 2),
        down_flow=round(down_flow, 2),
        sessions=int(up_mask.sum() + down_mask.sum()),
    )
