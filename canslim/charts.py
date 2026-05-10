"""Per-ticker price + volume chart with CANSLIM pattern overlays.

Renders a two-panel PNG (price on top, volume on bottom) with:
  * 50-day and 200-day SMAs
  * 52-week high dashed line
  * Pivot line from the top-confidence detected pattern
  * Pattern-specific shading (cup region, handle box, W-lows, etc.)

Headless-safe: forces the matplotlib 'Agg' backend.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from canslim.models import PatternMatch, ScanResult  # noqa: E402

log = logging.getLogger(__name__)

# Limit the x-axis span so the chart stays readable
_VISIBLE_SESSIONS = 200


def render_chart(
    ticker: str,
    df: pd.DataFrame,
    result: ScanResult,
    out_dir: Path,
) -> Optional[Path]:
    if df is None or df.empty:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{ticker}.png"

    window = df.tail(_VISIBLE_SESSIONS).copy()
    if len(window) < 2:
        return None

    close = window["close"].astype(float)
    high = window.get("high", window["close"]).astype(float)
    volume = window["volume"].astype(float)
    dates = window.index

    # SMAs computed over the full cached series so they're accurate at the left edge of the window
    full_close = df["close"].astype(float)
    sma50 = full_close.rolling(50).mean().loc[window.index]
    sma200 = full_close.rolling(200).mean().loc[window.index]

    last_close = float(close.iloc[-1])
    high_52w = float(full_close.tail(252).max()) if len(full_close) >= 20 else float(high.max())

    fig = plt.figure(figsize=(10, 6), dpi=110)
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.05)
    ax_price = fig.add_subplot(gs[0, 0])
    ax_vol = fig.add_subplot(gs[1, 0], sharex=ax_price)

    # Price
    ax_price.plot(dates, close, color="#111", linewidth=1.2, label="close")
    ax_price.plot(dates, sma50, color="#2676d3", linewidth=0.9, alpha=0.8, label="50d SMA")
    ax_price.plot(dates, sma200, color="#c0392b", linewidth=0.9, alpha=0.8, label="200d SMA")
    ax_price.axhline(y=high_52w, color="#7f8c8d", linestyle="--", linewidth=0.7, alpha=0.7, label=f"52w hi {high_52w:.2f}")

    # Pattern overlays — draw annotations for each detected pattern
    top_pattern = max(result.patterns, key=lambda p: p.confidence) if result.patterns else None
    _apply_pattern_overlays(ax_price, window, result.patterns)

    # Pivot line from top pattern
    if top_pattern and top_pattern.pivot:
        ax_price.axhline(
            y=top_pattern.pivot,
            color="#27ae60",
            linestyle="-.",
            linewidth=1.2,
            alpha=0.9,
            label=f"pivot {top_pattern.pivot:.2f} ({top_pattern.name})",
        )

    # Title + header metadata
    status = "MATCH" if result.passed else ("near-miss" if result.status == "scanned" else result.status)
    gate_flags = _gate_flags(result)
    title = f"{ticker}  ·  close {last_close:.2f}  ·  score {result.composite_score:.2f}  ·  {gate_flags}  ·  {status}"
    ax_price.set_title(title, fontsize=11, loc="left")
    ax_price.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax_price.legend(loc="upper left", fontsize=7, ncol=2, framealpha=0.85)
    ax_price.tick_params(labelbottom=False)

    # Volume
    colors = np.where(close.diff().fillna(0.0) >= 0, "#27ae60", "#c0392b")
    ax_vol.bar(dates, volume, color=colors, width=1.0, alpha=0.7)
    vol_avg50 = volume.rolling(50).mean()
    ax_vol.plot(dates, vol_avg50, color="#2c3e50", linewidth=0.8, alpha=0.8, label="50d avg vol")
    ax_vol.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax_vol.set_ylabel("volume", fontsize=8)
    ax_vol.legend(loc="upper left", fontsize=7, framealpha=0.85)

    # Date formatting
    ax_price.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    for label in ax_vol.get_xticklabels():
        label.set_rotation(0)
        label.set_fontsize(8)

    try:
        fig.savefig(png_path, bbox_inches="tight")
    except Exception as e:
        log.warning("chart render failed for %s: %s", ticker, e)
        plt.close(fig)
        return None
    plt.close(fig)
    return png_path


def _gate_flags(r: ScanResult) -> str:
    letters = ["C", "A", "N", "S", "L", "I", "M"]
    out = []
    for letter in letters:
        cr = r.criteria.get(letter)
        if cr is None:
            out.append("·")
        elif cr.passed:
            out.append(letter)
        else:
            out.append(letter.lower())
    return "".join(out)


def _apply_pattern_overlays(ax, window: pd.DataFrame, patterns: list[PatternMatch]) -> None:
    if not patterns:
        return
    idx = window.index
    first_date, last_date = idx[0], idx[-1]

    for p in sorted(patterns, key=lambda x: -x.confidence):
        e = p.evidence
        if p.name == "cup_with_handle":
            left = e.get("left_peak")
            right = e.get("right_peak")
            bottom = e.get("cup_bottom")
            if left and right and bottom:
                # Cup span: highlight the region between left peak and right peak
                ax.axhspan(bottom, max(left, right), facecolor="#3498db", alpha=0.05)
                # Handle box: last handle_duration sessions
                hdur = int(e.get("handle_duration_sessions", 0) or 0)
                if hdur > 1 and len(idx) > hdur:
                    handle_start = idx[-hdur]
                    ax.axvspan(handle_start, last_date, facecolor="#f39c12", alpha=0.12,
                               label=f"handle ({hdur}d)")
        elif p.name == "double_bottom":
            first_low = e.get("first_low")
            second_low = e.get("second_low")
            middle_peak = e.get("middle_peak")
            if first_low and second_low and middle_peak:
                ax.axhline(first_low, color="#8e44ad", linestyle=":", linewidth=0.8, alpha=0.8)
                ax.axhline(middle_peak, color="#8e44ad", linestyle=":", linewidth=0.8, alpha=0.8)
                ax.annotate("W-bot", xy=(last_date, first_low), xytext=(-30, -10),
                            textcoords="offset points", fontsize=7, color="#8e44ad")
        elif p.name == "saucer":
            bottom = e.get("saucer_bottom")
            left = e.get("left_peak")
            right = e.get("right_peak")
            if bottom and left and right:
                ax.axhspan(bottom, max(left, right), facecolor="#9b59b6", alpha=0.04)
        elif p.name == "high_tight_flag":
            flag_hi = e.get("flag_high")
            flag_lo = e.get("flag_low")
            flag_sessions = int(e.get("flag_sessions", 0) or 0)
            if flag_hi and flag_lo and flag_sessions > 0 and len(idx) > flag_sessions:
                flag_start = idx[-flag_sessions]
                ax.axhspan(flag_lo, flag_hi, xmin=_xfrac(flag_start, first_date, last_date),
                           facecolor="#e67e22", alpha=0.10)
        elif p.name == "ascending_triangle":
            top_max = e.get("top_max")
            if top_max:
                ax.axhline(top_max, color="#16a085", linestyle=":", linewidth=0.8, alpha=0.8,
                           label="triangle top")
        elif p.name == "flat_base":
            hi = e.get("base_high")
            lo = e.get("base_low")
            sessions = int(e.get("sessions", 0) or 0)
            if hi and lo and sessions > 0 and len(idx) > sessions:
                base_start = idx[-sessions]
                ax.axhspan(lo, hi, xmin=_xfrac(base_start, first_date, last_date),
                           facecolor="#95a5a6", alpha=0.08)
        elif p.name == "consolidation":
            hi = e.get("box_high")
            lo = e.get("box_low")
            sessions = int(e.get("sessions", 0) or 0)
            if hi and lo and sessions > 0 and len(idx) > sessions:
                box_start = idx[-sessions]
                ax.axhspan(lo, hi, xmin=_xfrac(box_start, first_date, last_date),
                           facecolor="#34495e", alpha=0.07)
        elif p.name == "three_weeks_tight":
            closes = e.get("weekly_closes")
            if isinstance(closes, list) and closes:
                ax.axhline(max(closes), color="#2980b9", linestyle=":", linewidth=0.7, alpha=0.6,
                           label="3WT pivot")


def _xfrac(target_date, first, last) -> float:
    try:
        total = (last - first).days or 1
        offset = (target_date - first).days
        return max(0.0, min(1.0, offset / total))
    except Exception:
        return 0.0
