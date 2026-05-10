from __future__ import annotations

import numpy as np
import pandas as pd

from canslim.patterns.cup_handle import CupWithHandle
from canslim.patterns.double_bottom import DoubleBottom
from canslim.patterns.flat_base import FlatBase


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


class TestCupWithHandle:
    def test_detects_classic_cup(self):
        # Build a synthetic cup + handle:
        # rally up, round down 20%, recover, then small 8% handle over ~10 days
        rally = np.linspace(80, 100, 30)
        cup = 100 - 20 * np.sin(np.linspace(0, np.pi, 60))  # rounded U from 100 -> 80 -> 100
        recovery = np.linspace(100, 100, 5)  # hover at top
        handle = 100 * np.array([1.0, 0.985, 0.975, 0.965, 0.96, 0.955, 0.96, 0.965, 0.97, 0.975, 0.98])
        closes = np.concatenate([rally, cup, recovery, handle]).tolist()
        # Light handle volume: cup rise is 2M, handle is 800k
        volumes = [1_500_000] * 30 + [2_000_000] * 60 + [2_000_000] * 5 + [800_000] * len(handle)
        df = _frame(closes, volumes)
        match = CupWithHandle().detect(df)
        assert match is not None
        assert match.name == "cup_with_handle"
        assert match.pivot is not None and match.pivot > 99
        assert 0.15 <= match.evidence["cup_depth_pct"] <= 0.25
        assert match.evidence["light_handle_volume"] is True

    def test_rejects_v_shape(self):
        # Sharp V, no rounded bottom
        closes = np.concatenate([
            np.linspace(80, 100, 30),
            np.linspace(100, 75, 3),   # V crash
            np.linspace(75, 100, 3),   # V rebound
            np.linspace(100, 98, 20),
        ]).tolist()
        df = _frame(closes)
        assert CupWithHandle().detect(df) is None

    def test_rejects_too_deep(self):
        # Cup depth > 35% should fail
        closes = np.concatenate([
            np.linspace(80, 100, 20),
            100 - 50 * np.sin(np.linspace(0, np.pi, 60)),  # 50% drop
            np.linspace(100, 95, 10),
        ]).tolist()
        df = _frame(closes)
        assert CupWithHandle().detect(df) is None

    def test_accepts_small_overshoot(self):
        # Cup recovers normally to prior peak (~100), then handle high reaches
        # ~106 (6% above left peak — within 10% overshoot allowance).
        rally = np.linspace(80, 100, 30)
        cup = 100 - 20 * np.sin(np.linspace(0, np.pi, 60))  # rounded U 100→80→100
        small_overshoot = np.array([102, 106, 103, 104, 103, 104, 105])
        closes = np.concatenate([rally, cup, small_overshoot]).tolist()
        volumes = [1_500_000] * 30 + [2_000_000] * 60 + [3_000_000] + [1_000_000] * 6
        df = _frame(closes, volumes)
        match = CupWithHandle().detect(df)
        assert match is not None, "small overshoot (<10%) should pass"
        assert match.pivot is not None and match.pivot > 100.0

    def test_rejects_excessive_overshoot(self):
        # Right side >20% past left peak — too far for cup-with-handle.
        # These should be classified as post-earnings continuation, not cup-with-handle.
        rally = np.linspace(80, 100, 30)
        cup = 100 - 20 * np.sin(np.linspace(0, np.pi, 60))
        excessive = np.array([102, 130, 125, 128, 124, 127, 130])  # 30% past peak
        closes = np.concatenate([rally, cup, excessive]).tolist()
        df = _frame(closes)
        assert CupWithHandle().detect(df) is None

    def test_rejects_amd_style_uptrend_phase(self):
        # AMD-shape: cup down 30%, then a sustained markup that pushed 35%+ past
        # the left peak. Stock is in a markup phase, NOT a cup-with-handle base.
        rally = np.linspace(80, 267, 40)        # rally to 267 (left peak)
        cup_down = np.linspace(267, 188, 70)    # decline to 188 (29% drop)
        markup = np.linspace(188, 363, 100)     # sustained rally to 363 (36% past peak)
        handle = np.array([360, 357, 355, 358, 360, 362])  # tight near top
        closes = np.concatenate([rally, cup_down, markup, handle]).tolist()
        df = _frame(closes)
        assert CupWithHandle().detect(df) is None, (
            "AMD-style sustained markup past prior peak should not qualify as cup-with-handle"
        )


class TestDoubleBottom:
    def test_detects_w_shape(self):
        # Long pre-roll to satisfy the 120-session lookback window, then W.
        closes = np.concatenate([
            np.linspace(95, 100, 30),   # calm pre-roll
            np.linspace(100, 80, 25),   # decline to first low
            np.linspace(80, 90, 25),    # rally to middle peak
            np.linspace(90, 79, 25),    # decline to second low (undercut)
            np.linspace(79, 88, 15),    # recovery toward pivot
            [88, 89, 87, 88, 89, 88, 87, 88, 89, 88],  # ride near pivot
        ]).tolist()
        df = _frame(closes)
        match = DoubleBottom().detect(df)
        assert match is not None
        assert match.evidence["second_undercuts_first"] is True
        assert 0.05 <= match.evidence["middle_peak_rise_pct"] <= 0.20

    def test_rejects_mismatched_lows(self):
        # Lows too far apart in price
        closes = np.concatenate([
            np.linspace(100, 80, 20),
            np.linspace(80, 90, 20),
            np.linspace(90, 60, 20),   # second low much lower
            np.linspace(60, 85, 30),
        ]).tolist()
        df = _frame(closes)
        assert DoubleBottom().detect(df) is None


class TestFlatBase:
    def test_detects_tight_range(self):
        # 30 sessions in 8% range
        closes = np.concatenate([
            np.linspace(70, 100, 30),      # rally
            100 + np.random.RandomState(0).normal(0, 1.5, 30),  # flat with tight noise
        ]).tolist()
        df = _frame(closes)
        match = FlatBase().detect(df)
        assert match is not None
        assert match.evidence["range_pct"] < 0.15

    def test_rejects_wide_range(self):
        closes = np.concatenate([
            np.linspace(70, 100, 30),
            np.linspace(100, 70, 30),  # 30% range
        ]).tolist()
        df = _frame(closes)
        assert FlatBase().detect(df) is None
