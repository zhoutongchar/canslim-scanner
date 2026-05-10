from __future__ import annotations

from canslim.criteria.base import Criterion, CriterionContext
from canslim.models import CriterionResult


class SupplyDemand(Criterion):
    """S: demand proxy = ADV10 / ADV50 ≥ threshold; supply proxy = float ≤ max."""

    letter = "S"
    name = "Supply & Demand"
    is_gate = True

    def evaluate(self, ctx: CriterionContext) -> CriterionResult:
        pf = ctx.price_features
        th = ctx.thresholds
        if pf is None or pf.adv50 <= 0:
            return CriterionResult(
                letter=self.letter, passed=False, is_gate=True,
                reason="no volume data", threshold=th.s_min_adv10_over_adv50,
            )

        ratio = pf.adv10 / pf.adv50
        demand_ok = ratio >= th.s_min_adv10_over_adv50
        float_ok = ctx.float_shares is None or ctx.float_shares <= th.s_max_float_shares

        # Pattern-aware override: drying-up volume in a cup-with-handle, high-tight-flag,
        # three-weeks-tight, or flat-base is constructive (no distribution while the base
        # forms). When such a pattern is detected with high confidence, treat it as the
        # demand-side signal in place of the volume-uptick gate. Float check still applies.
        constructive_pattern = None
        if th.s_pattern_override_enabled and not demand_ok:
            allowed = set(th.s_pattern_override_patterns)
            for p in (ctx.patterns or []):
                if (
                    p.name in allowed
                    and (p.confidence or 0.0) >= th.s_pattern_override_min_conf
                ):
                    constructive_pattern = p
                    break

        demand_ok_with_override = demand_ok or constructive_pattern is not None
        passed = demand_ok_with_override and float_ok
        score = min(1.0, max(0.0, (ratio - 1.0) / max(th.s_min_adv10_over_adv50 - 1.0, 1e-6)))
        if constructive_pattern is not None and score < 0.8:
            score = 0.8  # pattern-confirmed dry-up is a strong signal even if ratio is low

        reasons = []
        if not demand_ok and constructive_pattern is None:
            reasons.append(f"ADV10/ADV50 {ratio:.2f} < {th.s_min_adv10_over_adv50}")
        if not float_ok:
            reasons.append(f"float {ctx.float_shares:,.0f} > {th.s_max_float_shares:,.0f}")
        if constructive_pattern is not None:
            reasons.append(
                f"pattern override: {constructive_pattern.name} conf {constructive_pattern.confidence:.2f} (dry-up is constructive)"
            )

        return CriterionResult(
            letter=self.letter,
            passed=passed,
            is_gate=True,
            score=score,
            value=ratio,
            threshold=th.s_min_adv10_over_adv50,
            evidence={
                "adv10": pf.adv10,
                "adv50": pf.adv50,
                "ratio": ratio,
                "float_shares": ctx.float_shares,
                "pattern_override": constructive_pattern.name if constructive_pattern else None,
            },
            reason="; ".join(reasons) or "demand uptick with manageable supply",
        )
