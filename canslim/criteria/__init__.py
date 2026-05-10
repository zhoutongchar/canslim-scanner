from __future__ import annotations

import logging
from importlib.metadata import entry_points

from canslim.criteria.base import Criterion, CriterionContext

log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[Criterion]] = {}


def register(letter: str, cls: type[Criterion]) -> None:
    _REGISTRY[letter.lower()] = cls


def discover() -> dict[str, Criterion]:
    """Instantiate criteria registered via entry points. Returns {letter: criterion}."""
    if not _REGISTRY:
        try:
            eps = entry_points(group="canslim.criteria")
        except TypeError:  # pragma: no cover
            eps = entry_points().get("canslim.criteria", [])  # type: ignore[attr-defined]
        for ep in eps:
            try:
                cls = ep.load()
            except Exception as e:
                log.warning("Failed to load criterion %s: %s", ep.name, e)
                continue
            if not isinstance(cls, type) or not issubclass(cls, Criterion):
                log.warning("Entry point %s is not a Criterion subclass", ep.name)
                continue
            _REGISTRY[ep.name.lower()] = cls
        # Fallback: import-register directly if entry points aren't set up yet (e.g. editable install before metadata regen)
        if not _REGISTRY:
            _direct_register()
    return {letter: cls() for letter, cls in _REGISTRY.items()}


def _direct_register() -> None:
    from canslim.criteria.a_annual import AnnualEarnings
    from canslim.criteria.c_current import CurrentEarnings
    from canslim.criteria.i_institutional import Institutional
    from canslim.criteria.l_leader import Leader
    from canslim.criteria.m_market import MarketDirection
    from canslim.criteria.n_new_high import NewHigh
    from canslim.criteria.s_supply_demand import SupplyDemand

    register("c", CurrentEarnings)
    register("a", AnnualEarnings)
    register("n", NewHigh)
    register("s", SupplyDemand)
    register("l", Leader)
    register("i", Institutional)
    register("m", MarketDirection)


__all__ = ["Criterion", "CriterionContext", "discover", "register"]
