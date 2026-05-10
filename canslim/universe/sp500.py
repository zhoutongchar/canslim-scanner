from __future__ import annotations

import io
import logging
from typing import Optional

import httpx
import pandas as pd

from canslim.universe.base import Universe

log = logging.getLogger(__name__)

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = "Mozilla/5.0 (canslim-scanner)"


class SP500Universe(Universe):
    name = "sp500"

    def __init__(self, url: Optional[str] = None, timeout: float = 20.0) -> None:
        self.url = url or WIKI_URL
        self.timeout = timeout

    def load(self) -> list[str]:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
                resp = c.get(self.url)
                resp.raise_for_status()
                html = resp.text
            tables = pd.read_html(io.StringIO(html))
        except Exception as e:
            log.error("Failed to load S&P 500 list from %s: %s", self.url, e)
            raise
        df = tables[0]
        sym_col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        tickers = df[sym_col].astype(str).str.strip().str.replace(".", "-", regex=False).tolist()
        return sorted({t for t in tickers if t and t != "nan"})
