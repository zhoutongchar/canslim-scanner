from __future__ import annotations

from canslim.criteria.base import Criterion, CriterionContext
from canslim.models import CriterionResult


class MarketDirection(Criterion):
    """M: info-only; evaluated once per run by the scanner and copied onto every result.

    Actual evaluation lives in `canslim.scanner.evaluate_market_regime`; this class exists so
    the plugin registry has a placeholder and the CLI can list 'm' like any other letter.
    """

    letter = "M"
    name = "Market Direction"
    is_gate = False

    def evaluate(self, ctx: CriterionContext) -> CriterionResult:
        # Scanner fills regime into evidence via `evidence` kwarg before writing the result.
        return CriterionResult(
            letter=self.letter,
            passed=False,
            is_gate=False,
            score=0.0,
            reason="market regime is computed at run-level; see report header",
        )
