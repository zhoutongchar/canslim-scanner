from __future__ import annotations

from canslim.criteria.base import Criterion, CriterionContext
from canslim.models import CriterionResult


class Leader(Criterion):
    """L: cross-sectional 12-month RS percentile (weighted 40/20/20/20 by quarter) ≥ threshold.

    The actual RS computation + ranking happens in the scanner; this criterion just gates on
    `ctx.rs_percentile`.
    """

    letter = "L"
    name = "Leader"
    is_gate = True

    def evaluate(self, ctx: CriterionContext) -> CriterionResult:
        th = ctx.thresholds
        pct = ctx.rs_percentile
        if pct is None:
            return CriterionResult(
                letter=self.letter, passed=False, is_gate=True,
                reason="RS percentile unavailable", threshold=th.l_min_rs_percentile,
            )
        passed = pct >= th.l_min_rs_percentile
        score = min(1.0, max(0.0, pct))
        return CriterionResult(
            letter=self.letter,
            passed=passed,
            is_gate=True,
            score=score,
            value=pct,
            threshold=th.l_min_rs_percentile,
            evidence={
                "rs_percentile": pct,
                "rs_return_12m_weighted": ctx.price_features.rs_return_12m_weighted if ctx.price_features else None,
            },
            reason=f"RS percentile {pct:.2f} vs threshold {th.l_min_rs_percentile:.2f}",
        )
