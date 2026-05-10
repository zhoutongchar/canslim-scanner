from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from canslim.models import FetchError, PatternMatch

log = logging.getLogger(__name__)


class ChartPattern(ABC):
    name: str

    @abstractmethod
    def detect(self, df: pd.DataFrame) -> Optional[PatternMatch]:
        """Return a detected PatternMatch or None.

        `df` is daily OHLCV with a DatetimeIndex, columns include 'close' and 'volume'.
        """


def detect_all(
    patterns: list[ChartPattern],
    df: pd.DataFrame,
    ticker: str = "?",
) -> tuple[list[PatternMatch], list[FetchError]]:
    """Run all detectors, returning detected matches and any exceptions as FetchErrors."""
    matches: list[PatternMatch] = []
    errors: list[FetchError] = []
    for p in patterns:
        try:
            m = p.detect(df)
        except Exception as e:
            log.warning("pattern %s failed for %s: %s", p.name, ticker, e)
            errors.append(FetchError(
                ticker=ticker, kind="pattern", provider=p.name, error=f"{type(e).__name__}: {e}",
                retryable=False,
            ))
            continue
        if m is not None:
            matches.append(m)
    return matches, errors
