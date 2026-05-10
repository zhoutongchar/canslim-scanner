from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from canslim.models import EarningsBundle, InstitutionalSnapshot


@dataclass(frozen=True)
class PriceBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int


@dataclass(frozen=True)
class EarningsReport:
    period: str  # e.g. "2026-Q1" or "2025"
    period_end: date
    eps_diluted: Optional[float]
    revenue: Optional[float]
    roe: Optional[float]
    kind: str  # "quarterly" | "annual"


class ProviderError(Exception):
    pass


class RateLimited(ProviderError):
    pass


class BudgetExhausted(ProviderError):
    pass


class DataProvider(ABC):
    """Abstract data provider. One instance per provider per run."""

    name: str

    @abstractmethod
    async def health_check(self) -> dict[str, str]:
        """Return a dict of diagnostic info or raise ProviderError."""

    async def get_prices(
        self,
        tickers: list[str],
        start: Optional[date] = None,
        end: Optional[date] = None,
        force_refresh: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Return {ticker: DataFrame} with columns [open, high, low, close, adj_close, volume], date index."""
        raise NotImplementedError(f"{self.name} does not implement get_prices")

    async def get_fundamentals(self, ticker: str) -> EarningsBundle:
        raise NotImplementedError(f"{self.name} does not implement get_fundamentals")

    async def get_institutional(self, ticker: str) -> Optional[InstitutionalSnapshot]:
        raise NotImplementedError(f"{self.name} does not implement get_institutional")

    async def get_shares_float(self, ticker: str) -> Optional[float]:
        raise NotImplementedError(f"{self.name} does not implement get_shares_float")

    async def close(self) -> None:
        """Override to release connections."""
