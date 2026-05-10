"""Hang Seng China Enterprises Index (HSCEI) — ~50 major H-share names on HKEX."""

from __future__ import annotations

import io
import logging
import re
from typing import Optional

import httpx
import pandas as pd

from canslim.universe.base import Universe

log = logging.getLogger(__name__)

HSCEI_URL = "https://en.wikipedia.org/wiki/Hang_Seng_China_Enterprises_Index"
UA = "Mozilla/5.0 (canslim-scanner)"


class HKHSCEIUniverse(Universe):
    name = "hk_hscei"

    def __init__(self, url: Optional[str] = None, timeout: float = 20.0) -> None:
        self.url = url or HSCEI_URL
        self.timeout = timeout

    def load(self) -> list[str]:
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
            resp = c.get(self.url)
            resp.raise_for_status()
            html = resp.text
        tables = pd.read_html(io.StringIO(html))
        for df in tables:
            code_col = None
            for c in df.columns:
                if re.search(r"(ticker|stock code|code)", str(c).lower()):
                    code_col = c
                    break
            if code_col is None:
                continue
            raw = df[code_col].astype(str)
            tickers: list[str] = []
            for v in raw:
                m = re.search(r"(\d{1,5})", v.replace(",", ""))
                if not m:
                    continue
                tickers.append(f"{m.group(1).zfill(4)}.HK")
            if tickers:
                return sorted(set(tickers))
        raise ValueError(f"Could not find HSCEI components table on {self.url}")
