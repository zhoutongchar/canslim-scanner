from __future__ import annotations

from canslim.normalization import apply_rules, default_rules
from canslim.providers.sec_provider import _bundle_from_facts


def test_discontinued_ops_gain_is_subtracted():
    """ESE-like case: big divestiture gain inflates reported EPS.

    Scenario: FY2025 reports $11.55 EPS, but $182.9M of that is discontinued-ops gain.
    Normalized EPS should drop to ~$4.50.
    """
    facts = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {"fp": "FY", "fy": 2025, "end": "2025-09-30", "val": 11.55},
                            {"fp": "FY", "fy": 2024, "end": "2024-09-30", "val": 3.94},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"fp": "FY", "fy": 2025, "end": "2025-09-30", "val": 299_223_000},
                            {"fp": "FY", "fy": 2024, "end": "2024-09-30", "val": 101_881_000},
                        ]
                    }
                },
                "IncomeLossFromDiscontinuedOperationsNetOfTax": {
                    "units": {
                        "USD": [
                            {"fp": "FY", "fy": 2025, "end": "2025-09-30", "val": 182_924_000},
                            {"fp": "FY", "fy": 2024, "end": "2024-09-30", "val": -747_000},
                        ]
                    }
                },
            }
        }
    }
    eb = _bundle_from_facts("ESE", facts)

    # Reported should still show $11.55
    assert eb.reported_annual_eps[0] == 11.55
    # Normalized should be much lower — about $4.50 (12B net of 11.55 EPS => ~26M shares
    # minus $182.9M / 26M = $7.04 per share, so 11.55 - 7.04 = ~4.51)
    assert 4.0 < eb.annual_eps[0] < 5.0, f"expected ~$4.50 normalized, got ${eb.annual_eps[0]:.2f}"
    # 2024 had a tiny loss in disc ops — should be *added back* (slight positive adjustment),
    # so normalized 2024 ≥ reported 2024
    assert eb.annual_eps[1] >= eb.reported_annual_eps[1] - 0.01

    # Adjustments list should include at least one discontinued_operations entry
    rule_names = {a.rule_name for a in eb.normalization_adjustments}
    assert "discontinued_operations" in rule_names


def test_goodwill_impairment_is_added_back():
    """Impairment charge depresses reported EPS; normalization adds it back (with tax haircut)."""
    facts = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {"fp": "FY", "fy": 2024, "end": "2024-12-31", "val": 1.00},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [{"fp": "FY", "fy": 2024, "end": "2024-12-31", "val": 100_000_000}],
                    }
                },
                "GoodwillImpairmentLoss": {
                    "units": {
                        "USD": [{"fp": "FY", "fy": 2024, "end": "2024-12-31", "val": 50_000_000}],
                    }
                },
            }
        }
    }
    eb = _bundle_from_facts("T", facts)
    # Reported: $1.00
    # Shares = NI/EPS = 100M shares
    # Impairment after 21% tax = $50M × 0.79 = $39.5M → $0.395 per share added back
    # Normalized ≈ $1.395
    assert eb.reported_annual_eps[0] == 1.00
    assert 1.30 < eb.annual_eps[0] < 1.50, f"expected ~$1.40, got ${eb.annual_eps[0]:.3f}"
    rule_names = {a.rule_name for a in eb.normalization_adjustments}
    assert "goodwill_impairment" in rule_names


def test_no_adjustments_keeps_eps_unchanged():
    """Clean filing with no one-time items: normalized EPS == reported EPS."""
    facts = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {"USD/shares": [{"fp": "FY", "fy": 2024, "end": "2024-12-31", "val": 3.25}]}
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"fp": "FY", "fy": 2024, "end": "2024-12-31", "val": 325_000_000}]}
                },
            }
        }
    }
    eb = _bundle_from_facts("T", facts)
    assert eb.annual_eps[0] == 3.25
    assert eb.reported_annual_eps[0] == 3.25
    assert eb.normalization_adjustments == []


def test_concept_alias_is_deduped():
    """If a value is reported under two concept-name aliases within one rule, apply only once.

    SEC emits IncomeLossFromDiscontinuedOperationsNetOfTax AND the ...AttributableToReportingEntity
    concept with the same dollar value. Without dedup we'd subtract it twice.
    """
    facts = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {"USD/shares": [{"fp": "FY", "fy": 2025, "end": "2025-09-30", "val": 10.00}]}
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"fp": "FY", "fy": 2025, "end": "2025-09-30", "val": 260_000_000}]}
                },
                "IncomeLossFromDiscontinuedOperationsNetOfTax": {
                    "units": {"USD": [{"fp": "FY", "fy": 2025, "end": "2025-09-30", "val": 130_000_000}]}
                },
                "IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity": {
                    "units": {"USD": [{"fp": "FY", "fy": 2025, "end": "2025-09-30", "val": 130_000_000}]}
                },
            }
        }
    }
    eb = _bundle_from_facts("T", facts)
    # Implied shares = 260M / 10 = 26M. Per-share impact = 130M/26M = $5.
    # Correct normalized = 10 - 5 = 5.  BROKEN-dedup would yield 10 - 10 = 0.
    assert abs(eb.annual_eps[0] - 5.0) < 0.05, f"dedup broken: got ${eb.annual_eps[0]:.2f}"
    # Exactly ONE adjustment emitted for this rule × period, not two
    disc_adjs = [a for a in eb.normalization_adjustments if a.rule_name == "discontinued_operations"]
    assert len(disc_adjs) == 1, f"expected 1 adj, got {len(disc_adjs)}"


def test_default_rules_are_registered():
    """Importing the rules module auto-registers the default rule set."""
    rules = default_rules()
    names = {r.name for r in rules}
    # Check a sample of rules we expect
    expected = {
        "discontinued_operations",
        "goodwill_impairment",
        "restructuring_charges",
        "gain_on_sale_of_business",
        "asset_impairment",
    }
    assert expected.issubset(names), f"missing rules: {expected - names}"
