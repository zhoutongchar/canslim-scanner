from __future__ import annotations

from canslim.criteria.base import Criterion, CriterionContext
from canslim.models import CriterionResult


class NewHigh(Criterion):
    """N: info-only. Proximity to 52-week high and breakout detection (price + volume)."""

    letter = "N"
    name = "New High"
    is_gate = False

    def evaluate(self, ctx: CriterionContext) -> CriterionResult:
        pf = ctx.price_features
        th = ctx.thresholds
        if pf is None:
            return CriterionResult(
                letter=self.letter, passed=False, is_gate=False,
                reason="no price data", threshold=th.n_max_dist_to_high_pct,
            )

        within_range = pf.dist_to_52w_high_pct <= th.n_max_dist_to_high_pct
        breakout = (
            pf.dist_to_52w_high_pct <= th.n_breakout_pivot_pct
            and pf.recent_vol_ratio >= th.n_breakout_volume_multiple
        )
        passed = within_range  # info-only "pass" means near highs
        score = max(0.0, 1.0 - pf.dist_to_52w_high_pct / max(th.n_max_dist_to_high_pct, 1e-6))
        score = min(1.0, score + (0.2 if breakout else 0.0))

        return CriterionResult(
            letter=self.letter,
            passed=passed,
            is_gate=False,
            score=score,
            value=pf.dist_to_52w_high_pct,
            threshold=th.n_max_dist_to_high_pct,
            evidence={
                "close": pf.close,
                "high_52w": pf.high_52w,
                "dist_to_52w_high_pct": pf.dist_to_52w_high_pct,
                "recent_vol_ratio": pf.recent_vol_ratio,
                "breakout": breakout,
            },
            reason=("breakout" if breakout else ("near 52w high" if within_range else "far from 52w high")),
        )
