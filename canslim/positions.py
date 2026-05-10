"""Position tracking + sell-signal evaluation.

A `Position` is a held-long stock with entry price, date, shares, stop-loss, and
optionally the pivot it was bought against. The monitor checks each position
against current market data and emits `SellAlert`s aligned to O'Neil's sell rules.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    ticker: str
    entry_price: float
    entry_date: date
    shares: float
    stop_loss: float                    # hard stop-loss, no-exceptions sell level
    pivot: Optional[float] = None        # original pattern pivot for reference
    pattern: Optional[str] = None        # e.g. "cup_with_handle", "high_tight_flag"
    notes: Optional[str] = None
    scaled_out_pct: float = 0.0          # 0.0 = full position, 0.33 = 1/3 scaled out, etc.


class PositionsFile(BaseModel):
    positions: list[Position] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "PositionsFile":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Positions file not found: {p}")
        raw = yaml.safe_load(p.read_text()) or {}
        return cls.model_validate(raw)


Severity = Literal["critical", "warning", "info"]


class SellAlert(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    severity: Severity
    signal: str              # short code, e.g. "hard_stop", "50dma_break", "scale_out"
    message: str             # human-readable description
    action: str              # "SELL ALL" / "SELL 1/3" / "TIGHTEN STOP" / "HOLD"
    current_price: Optional[float] = None
    unrealized_pct: Optional[float] = None  # (current - entry) / entry, signed


class PositionEvaluation(BaseModel):
    """Per-position snapshot + alerts."""

    ticker: str
    entry_price: float
    entry_date: date
    shares: float
    stop_loss: float
    current_price: Optional[float] = None
    unrealized_pct: Optional[float] = None
    unrealized_usd: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    days_held: int = 0
    alerts: list[SellAlert] = Field(default_factory=list)
