"""Hang Seng Index universe loader (HK market).

Fetches HSI + HSCEI components from Wikipedia and yields yfinance-compatible
tickers (e.g. "0700.HK" for Tencent). Covers the most liquid ~80 names on HKEX.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Optional

import httpx
import pandas as pd

from canslim.universe.base import Universe

log = logging.getLogger(__name__)

HSI_URL = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
UA = "Mozilla/5.0 (canslim-scanner)"


class HKHangSengUniverse(Universe):
    """Hang Seng Index (~82 components, HK mega-caps)."""

    name = "hk_hsi"

    def __init__(self, url: Optional[str] = None, timeout: float = 20.0) -> None:
        self.url = url or HSI_URL
        self.timeout = timeout

    def load(self) -> list[str]:
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
            resp = c.get(self.url)
            resp.raise_for_status()
            html = resp.text
        tables = pd.read_html(io.StringIO(html))
        # Find the components table — it has a column matching "Ticker" or "Code" or "Stock code"
        for df in tables:
            code_col = None
            for c in df.columns:
                if re.search(r"(ticker|stock code|code)", str(c).lower()):
                    code_col = c
                    break
            if code_col is None:
                continue
            raw = df[code_col].astype(str)
            # HSI codes may appear as "SEHK: 700" or "700" or "0700". Normalize to "NNNN.HK".
            tickers: list[str] = []
            for v in raw:
                m = re.search(r"(\d{1,5})", v.replace(",", ""))
                if not m:
                    continue
                code = m.group(1).zfill(4)
                tickers.append(f"{code}.HK")
            if tickers:
                return sorted(set(tickers))
        raise ValueError(f"Could not find HSI components table on {self.url}")
