"""Default set of EPS normalization rules.

To add a new rule: declare a subclass of `NormalizationRule` and decorate with
`@register_rule`. Declarative-only — no evaluate method needed unless behavior
diverges from the concept-list pattern.

Direction convention:
  * "subtract" — the filing value is a GAIN that inflates reported EPS; we strip it.
  * "add_back" — the filing value is a CHARGE that depresses reported EPS; we restore it.
"""

from __future__ import annotations

from canslim.normalization.base import NormalizationRule, register_rule


# ============================================================
# ONE-TIME GAINS — subtract from reported EPS
# ============================================================

@register_rule
class DiscontinuedOperations(NormalizationRule):
    name = "discontinued_operations"
    description = "Gain/loss from discontinued operations (divestiture of a business unit)"
    # Value is already net-of-tax on the income statement.
    concepts = (
        "IncomeLossFromDiscontinuedOperationsNetOfTax",
        "IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity",
    )
    direction = "subtract"
    pre_tax = False
    # Handle both signs: positive = gain to subtract, negative = loss to add-back.
    # We emit separately from the loss branch below.
    sign_filter = "positive_only"
    periodicity = "both"


@register_rule
class DiscontinuedOperationsLoss(NormalizationRule):
    name = "discontinued_operations_loss"
    description = "Loss from discontinued operations (divestiture write-down or underperforming unit)"
    concepts = (
        "IncomeLossFromDiscontinuedOperationsNetOfTax",
        "IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity",
    )
    direction = "add_back"
    pre_tax = False
    sign_filter = "negative_only"
    periodicity = "both"


@register_rule
class GainOnSaleOfBusiness(NormalizationRule):
    name = "gain_on_sale_of_business"
    description = "Gain on sale of a business or subsidiary"
    concepts = (
        "GainLossOnSaleOfBusiness",
        "GainLossOnDispositionOfAssets1",
        "GainLossOnSalesOfBusinessAffiliatesAndSubsidiariesNetOfTax",
    )
    direction = "subtract"
    pre_tax = True
    sign_filter = "positive_only"
    periodicity = "both"


@register_rule
class GainOnDebtExtinguishment(NormalizationRule):
    name = "gain_on_debt_extinguishment"
    description = "Gain from extinguishing debt at less than par (rare but inflates EPS)"
    concepts = ("GainsLossesOnExtinguishmentOfDebt",)
    direction = "subtract"
    pre_tax = True
    sign_filter = "positive_only"
    periodicity = "both"


@register_rule
class BargainPurchaseGain(NormalizationRule):
    name = "bargain_purchase_gain"
    description = "Bargain-purchase gain from acquiring a business for less than book value"
    concepts = ("BusinessCombinationBargainPurchaseGainRecognizedAmount",)
    direction = "subtract"
    pre_tax = True
    sign_filter = "positive_only"
    periodicity = "both"


@register_rule
class InsuranceRecoveries(NormalizationRule):
    name = "insurance_recoveries"
    description = "Insurance proceeds received (non-recurring)"
    concepts = (
        "InsuranceRecoveries",
        "ProceedsFromInsuranceSettlementOperatingActivities",
    )
    direction = "subtract"
    pre_tax = True
    sign_filter = "positive_only"
    periodicity = "both"


@register_rule
class UnrealizedInvestmentGains(NormalizationRule):
    name = "unrealized_investment_gains"
    description = "Mark-to-market investment gains (non-operating)"
    concepts = (
        "UnrealizedGainLossOnInvestments",
        "MarketableSecuritiesUnrealizedGainLoss",
    )
    direction = "subtract"
    pre_tax = True
    sign_filter = "positive_only"
    periodicity = "both"


# ============================================================
# ONE-TIME LOSSES / CHARGES — add back to reported EPS
# ============================================================

@register_rule
class GoodwillImpairment(NormalizationRule):
    name = "goodwill_impairment"
    description = "Goodwill write-down (non-cash, signals overpaid acquisition)"
    concepts = ("GoodwillImpairmentLoss",)
    direction = "add_back"
    pre_tax = True
    periodicity = "both"


@register_rule
class IntangibleImpairment(NormalizationRule):
    name = "intangible_impairment"
    description = "Impairment of finite-lived or indefinite-lived intangibles"
    concepts = (
        "ImpairmentOfIntangibleAssetsExcludingGoodwill",
        "ImpairmentOfIntangibleAssetsFinitelived",
        "ImpairmentOfIntangibleAssetsIndefinitelivedExcludingGoodwill",
    )
    direction = "add_back"
    pre_tax = True
    periodicity = "both"


@register_rule
class AssetImpairment(NormalizationRule):
    name = "asset_impairment"
    description = "Generic asset impairment charges (facility closures, write-downs)"
    concepts = (
        "AssetImpairmentCharges",
        "ImpairmentOfLongLivedAssetsToBeDisposedOf",
        "ImpairmentOfLongLivedAssetsHeldForUse",
    )
    direction = "add_back"
    pre_tax = True
    periodicity = "both"


@register_rule
class RestructuringCharges(NormalizationRule):
    name = "restructuring_charges"
    description = "Restructuring costs (layoffs, facility consolidation, one-time)"
    concepts = (
        "RestructuringCharges",
        "RestructuringSettlementAndImpairmentProvisions",
    )
    direction = "add_back"
    pre_tax = True
    periodicity = "both"


@register_rule
class LitigationCharges(NormalizationRule):
    name = "litigation_charges"
    description = "Litigation / regulatory settlement charges (one-time)"
    concepts = (
        "LossContingencyAccrualAtCarryingValue",
        "LitigationSettlementExpense",
        "LossContingencyAccrualPeriodIncreaseDecrease",
    )
    direction = "add_back"
    pre_tax = True
    sign_filter = "positive_only"  # these are expenses recorded as positives
    periodicity = "both"


@register_rule
class LossOnDebtExtinguishment(NormalizationRule):
    name = "loss_on_debt_extinguishment"
    description = "Loss from early debt retirement or refinancing"
    concepts = ("GainsLossesOnExtinguishmentOfDebt",)
    direction = "add_back"
    pre_tax = True
    sign_filter = "negative_only"
    periodicity = "both"


@register_rule
class InventoryWriteDown(NormalizationRule):
    name = "inventory_write_down"
    description = "Non-recurring inventory obsolescence / write-down"
    concepts = (
        "InventoryWriteDown",
        "InventoryLIFOReservePeriodCharge",
    )
    direction = "add_back"
    pre_tax = True
    sign_filter = "positive_only"
    periodicity = "both"


@register_rule
class TaxCutsAndJobsAct(NormalizationRule):
    name = "tcja_tax_reform"
    description = "One-time tax impact from 2017 TCJA (mostly 2017-2018 filings)"
    concepts = ("TaxCutsAndJobsActOf2017IncomeTaxExpenseBenefit",)
    # Sign convention: a negative value is a benefit (reduces tax, raises NI) — subtract.
    # Positive value is a deferred-tax hit — add back.
    # For simplicity we emit for both; downstream report shows the sign.
    direction = "subtract"
    pre_tax = False
    periodicity = "both"
