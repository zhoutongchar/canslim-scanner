"""Core normalization-rule machinery.

A rule declares:
  * `concepts` — SEC us-gaap concept names to look for
  * `direction` — "subtract" (gain we remove) or "add_back" (loss we restore)
  * `pre_tax` — True if the filing value is pre-tax and we should apply a tax haircut

The `apply_rules` entry point walks the `facts` dict once and returns a list of
`NormalizationAdjustment` objects, one per (rule, period) hit.
"""

from __future__ import annotations

import logging
from abc import ABC
from importlib.metadata import entry_points
from typing import Iterable, Optional

from canslim.models import NormalizationAdjustment

log = logging.getLogger(__name__)

DEFAULT_TAX_RATE = 0.21  # US federal corporate rate; fallback when effective rate can't be computed


class NormalizationRule(ABC):
    """Declarative rule. Subclass with class-level attributes, no code usually needed."""

    name: str = "unnamed"
    description: str = ""
    direction: str = "subtract"          # "subtract" (gains) or "add_back" (losses)
    concepts: tuple[str, ...] = ()        # us-gaap concept names
    pre_tax: bool = True                  # apply tax haircut if True
    sign_filter: Optional[str] = None     # "positive_only", "negative_only", or None for both
    periodicity: str = "annual"           # "annual" only by default; "both" for quarterly + annual


_REGISTRY: list[type[NormalizationRule]] = []


def register_rule(cls: type[NormalizationRule]) -> type[NormalizationRule]:
    """Class decorator / function to register a normalization rule."""
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
    return cls


def default_rules() -> list[NormalizationRule]:
    """Rules shipped by default (see rules.py). Also honors entry-point plugins."""
    # Importing rules.py populates the registry via its @register_rule decorators.
    from canslim.normalization import rules  # noqa: F401
    # Discover third-party rules via entry points
    try:
        eps_ = entry_points(group="canslim.normalization_rules")
    except TypeError:  # pragma: no cover
        eps_ = entry_points().get("canslim.normalization_rules", [])  # type: ignore[attr-defined]
    for ep in eps_:
        try:
            cls = ep.load()
        except Exception as e:
            log.warning("Failed to load normalization rule %s: %s", ep.name, e)
            continue
        if isinstance(cls, type) and issubclass(cls, NormalizationRule):
            register_rule(cls)
    return [cls() for cls in _REGISTRY]


def apply_rules(
    rules: Iterable[NormalizationRule],
    usgaap_root: dict,
    period_shares: dict[str, float],
    period_tax_rates: Optional[dict[str, float]] = None,
    periodicity_filter: str = "annual",
) -> list[NormalizationAdjustment]:
    """Walk `usgaap_root` for each rule's concepts and emit adjustments.

    * `period_shares[period]` — diluted shares outstanding for that period.
    * `period_tax_rates[period]` — optional per-period effective tax rate.
    * `periodicity_filter` — "annual" means only examine FY entries; "quarterly" means Q1/Q2/Q3/Q4.
    """
    period_tax_rates = period_tax_rates or {}
    out: list[NormalizationAdjustment] = []

    for rule in rules:
        # Skip rules not applicable to the requested periodicity
        if rule.periodicity != "both" and rule.periodicity != periodicity_filter:
            continue

        # Dedup within a rule: SEC often emits the same value under multiple concept aliases
        # (e.g. IncomeLossFromDiscontinuedOperationsNetOfTax AND
        # ...AttributableToReportingEntity). Without this, the same $182.9M divestiture gets
        # subtracted twice and annual EPS swings wildly.
        best_per_period: dict[str, NormalizationAdjustment] = {}

        for concept in rule.concepts:
            node = usgaap_root.get(concept)
            if not node:
                continue
            units = node.get("units", {})
            entries = units.get("USD") or (next(iter(units.values())) if units else [])
            for e in entries:
                fp = e.get("fp")
                val = e.get("val")
                end = e.get("end")
                if val in (None, 0) or end is None:
                    continue
                if periodicity_filter == "annual" and fp != "FY":
                    continue
                if periodicity_filter == "quarterly" and fp not in ("Q1", "Q2", "Q3", "Q4"):
                    continue
                if rule.sign_filter == "positive_only" and val <= 0:
                    continue
                if rule.sign_filter == "negative_only" and val >= 0:
                    continue

                period_key = end[:4] if periodicity_filter == "annual" else f"{end[:4]}-{fp}"
                shares = period_shares.get(period_key)
                if not shares or shares <= 0:
                    continue

                if rule.pre_tax:
                    tax_rate = period_tax_rates.get(period_key, DEFAULT_TAX_RATE)
                    after_tax_amount = float(val) * (1.0 - tax_rate)
                else:
                    tax_rate = None
                    after_tax_amount = float(val)

                per_share = after_tax_amount / shares
                if rule.direction == "add_back":
                    per_share = abs(per_share)

                adj = NormalizationAdjustment(
                    rule_name=rule.name,
                    description=rule.description,
                    period=period_key,
                    concept=concept,
                    dollar_amount=float(val),
                    per_share_impact=round(per_share, 4),
                    direction=rule.direction,
                    after_tax=not rule.pre_tax,
                    tax_rate_assumed=tax_rate,
                )
                # Keep the entry with the largest absolute dollar amount — handles alias cases
                # where one concept name reports the unattributed value and the alias reports
                # only the parent-attributable portion.
                existing = best_per_period.get(period_key)
                if existing is None or abs(adj.dollar_amount) > abs(existing.dollar_amount):
                    best_per_period[period_key] = adj

        out.extend(best_per_period.values())
    return out
