from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from canslim.config import Settings


class Universe(ABC):
    name: str

    @abstractmethod
    def load(self) -> list[str]:
        """Return a list of tickers."""


def load_universe(name: str, settings: Optional[Settings] = None) -> list[str]:
    """Resolve a universe by name. Thin factory."""
    from canslim.universe.custom import CustomUniverse
    from canslim.universe.hk_hscei import HKHSCEIUniverse
    from canslim.universe.hk_hsi import HKHangSengUniverse
    from canslim.universe.sp500 import SP500Universe
    from canslim.universe.us_all import USAllUniverse

    if name == "sp500":
        return SP500Universe().load()
    if name == "us_all":
        return USAllUniverse().load()
    if name == "hk_hsi":
        return HKHangSengUniverse().load()
    if name == "hk_hscei":
        return HKHSCEIUniverse().load()
    if name == "custom":
        path = settings.scanner.universe_file if settings else None
        if not path:
            raise ValueError("custom universe requires scanner.universe_file in config")
        return CustomUniverse(path).load()
    raise ValueError(f"Unknown universe: {name}")
