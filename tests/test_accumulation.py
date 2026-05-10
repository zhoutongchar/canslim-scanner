from __future__ import annotations

import numpy as np
import pandas as pd

from canslim.accumulation import compute_ad_rating


def _frame(closes: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="B")
    closes_arr = np.array(closes, dtype=float)
    vol = volumes if volumes is not None else [1_000_000] * len(closes)
    return pd.DataFrame(
        {
            "open": closes_arr,
            "high": closes_arr * 1.005,
            "low": closes_arr * 0.995,
            "close": closes_arr,
            "adj_close": closes_arr,
            "volume": vol,
        },
        index=idx,
    )


def test_accumulation_grade_A_on_heavy_up_volume():
    # Up days on heavy volume, down days on light volume — classic accumulation
    closes = []
    vols = []
    for i in range(60):
        if i % 2 == 0:
            closes.append(100 + i * 0.5)  # up day
            vols.append(3_000_000)  # heavy
        else:
            closes.append(100 + i * 0.5 - 0.2)  # tiny pullback
            vols.append(500_000)  # light
    df = _frame(closes, vols)
    rating = compute_ad_rating(df)
    assert rating is not None
    assert rating.grade in ("A", "B")  # allow B for borderline construction
    assert rating.ratio > 0.55


def test_distribution_grade_E_on_heavy_down_volume():
    # Up days light, down days heavy — classic distribution
    closes = []
    vols = []
    for i in range(60):
        if i % 2 == 0:
            closes.append(100 - i * 0.3)  # down day
            vols.append(3_000_000)  # heavy
        else:
            closes.append(100 - i * 0.3 + 0.1)  # tiny uptick
            vols.append(500_000)  # light
    df = _frame(closes, vols)
    rating = compute_ad_rating(df)
    assert rating is not None
    assert rating.grade in ("D", "E")
    assert rating.ratio < 0.45


def test_returns_none_for_short_history():
    df = _frame([100.0] * 5)
    assert compute_ad_rating(df, sessions=50) is None
