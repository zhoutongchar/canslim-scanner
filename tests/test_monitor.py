from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from canslim.monitor import _evaluate_position, evaluate_market_regime
from canslim.positions import Position

# The synthetic frames end at this fixed date so days_held math is deterministic
FRAME_END = date(2026, 4, 20)


def _frame(
    closes: list[float],
    volumes: list[int] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    # Build a business-day index that ends at FRAME_END
    idx = pd.bdate_range(end=pd.Timestamp(FRAME_END), periods=n)
    closes_arr = np.array(closes, dtype=float)
    vol = volumes if volumes is not None else [1_000_000] * n
    highs_arr = np.array(highs, dtype=float) if highs is not None else closes_arr * 1.01
    lows_arr = np.array(lows, dtype=float) if lows is not None else closes_arr * 0.99
    return pd.DataFrame(
        {
            "open": closes_arr,
            "high": highs_arr,
            "low": lows_arr,
            "close": closes_arr,
            "adj_close": closes_arr,
            "volume": vol,
        },
        index=idx,
    )


def _make_pos(entry: float = 100.0, stop: float = 92.5, days_held: int = 10) -> Position:
    return Position(
        ticker="T",
        entry_price=entry,
        entry_date=FRAME_END - timedelta(days=days_held),
        shares=100,
        stop_loss=stop,
    )


class TestHardStop:
    def test_fires_when_close_at_or_below_stop(self):
        pos = _make_pos(entry=100.0, stop=92.5)
        # 60 sessions to compute SMAs, last bar at $91 triggers stop
        closes = [100.0] * 59 + [91.0]
        df = _frame(closes)
        ev = _evaluate_position(pos, df)
        alerts = {a.signal for a in ev.alerts}
        assert "hard_stop" in alerts

    def test_silent_above_stop(self):
        pos = _make_pos(entry=100.0, stop=92.5)
        closes = [100.0] * 59 + [95.0]
        df = _frame(closes)
        ev = _evaluate_position(pos, df)
        alerts = {a.signal for a in ev.alerts}
        assert "hard_stop" not in alerts


class TestBreakevenUpgrade:
    def test_fires_when_up_15pct(self):
        pos = _make_pos(entry=100.0, stop=92.5)
        closes = [100.0] * 59 + [116.0]  # +16%
        df = _frame(closes)
        ev = _evaluate_position(pos, df)
        alerts = {a.signal for a in ev.alerts}
        assert "breakeven_upgrade" in alerts

    def test_silent_below_15pct(self):
        pos = _make_pos(entry=100.0, stop=92.5)
        closes = [100.0] * 59 + [108.0]  # +8%
        df = _frame(closes)
        ev = _evaluate_position(pos, df)
        alerts = {a.signal for a in ev.alerts}
        assert "breakeven_upgrade" not in alerts


class TestFastWinner:
    def test_fires_for_big_gain_in_short_time(self):
        pos = _make_pos(entry=100.0, stop=92.5, days_held=10)
        closes = [100.0] * 59 + [125.0]  # +25% in 10 days
        df = _frame(closes)
        ev = _evaluate_position(pos, df)
        signals = {a.signal for a in ev.alerts}
        assert "fast_winner" in signals
        # Fast winner explicitly does NOT trigger scale_out
        assert "scale_out" not in signals


class TestScaleOut:
    def test_fires_after_4_weeks_and_22pct(self):
        pos = _make_pos(entry=100.0, stop=92.5, days_held=35)
        closes = [100.0] * 59 + [125.0]  # +25% after 5 weeks
        df = _frame(closes)
        ev = _evaluate_position(pos, df)
        signals = {a.signal for a in ev.alerts}
        assert "scale_out" in signals


class TestMarketRegime:
    def test_distribution_cluster_fires_on_4_days(self):
        # 60 sessions; the last 15 include 4 distribution days (heavy-vol, down, close in lower half).
        # We must explicitly craft high/low so close sits below the midpoint on dist days.
        closes: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        vols: list[int] = []
        price = 100.0
        # Baseline 45 sessions drifting slightly higher on normal volume
        for i in range(45):
            price = 100.0 + i * 0.1
            closes.append(price)
            highs.append(price * 1.005)
            lows.append(price * 0.995)
            vols.append(1_000_000)
        # Last 15 sessions — every 4th is a distribution day
        for i in range(15):
            if i % 4 == 0:
                # Down 1.5%, wide intraday range, close at the LOW end (below mid)
                prev = closes[-1]
                close_today = prev * 0.985
                closes.append(close_today)
                highs.append(prev * 1.005)           # high near previous close
                lows.append(close_today * 0.995)     # low just below today's close
                vols.append(3_000_000)               # heavy
            else:
                price = closes[-1] * 1.001
                closes.append(price)
                highs.append(price * 1.005)
                lows.append(price * 0.995)
                vols.append(1_000_000)
        df = _frame(closes, vols, highs=highs, lows=lows)
        alerts = evaluate_market_regime(df)
        signals = {a.signal for a in alerts}
        assert "distribution_cluster" in signals, f"got signals: {signals}"
