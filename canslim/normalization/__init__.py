"""Pluggable EPS normalization — strip one-time items from reported earnings.

Register a new rule:

    from canslim.normalization.base import NormalizationRule, register_rule

    class MyRule(NormalizationRule):
        name = "my_rule"
        description = "..."
        direction = "subtract"          # or "add_back"
        concepts = ("GainLossOn...", )
        pre_tax = True                  # False if concept is already net-of-tax

    register_rule(MyRule)

Or via `pyproject.toml` entry-points group `canslim.normalization_rules`.
"""

from canslim.normalization.base import (
    NormalizationRule,
    apply_rules,
    default_rules,
    register_rule,
)

__all__ = ["NormalizationRule", "apply_rules", "default_rules", "register_rule"]
