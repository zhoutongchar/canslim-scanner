"""Sell-signal monitor — evaluates held positions against O'Neil's sell rules.

Inputs:
  * positions YAML file
  * fresh daily price bars (reuses scanner's yfinance cache)

For each position, emits alerts in severity order:

  CRITICAL — act now
    * hard_stop: close at or below stop_loss
    * 50dma_break: close below 50-DMA on heavy volume

  WARNING — consider action
    * climax_run: 3+ accelerating up-days + exhaustion bar
    * scale_out: +22% gain and > 4 weeks held (normal winner — take 1/3)
    * distribution_cluster: 3+ distribution days in SPY over last 15 sessions

  INFO — management
    * breakeven_upgrade: up ≥15% — move stop to breakeven
    * fast_winner: up ≥20% in ≤15 sessions — HOLD, trail stop at 10% below
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from canslim.config import Settings
from canslim.positions import Position, PositionEvaluation, PositionsFile, SellAlert
from canslim.providers.cache import CacheStore
from canslim.providers.yfinance_provider import YFinanceProvider

log = logging.getLogger(__name__)

MARKET_BENCHMARK = "SPY"


async def evaluate_positions(
    positions: list[Position],
    settings: Settings,
    force_refresh: bool = False,
) -> tuple[list[PositionEvaluation], list[SellAlert]]:
    """Fetch fresh prices for each position + SPY, evaluate all sell rules, return per-position
    evaluations and a list of market-level alerts."""
    cache = CacheStore(settings.cache.root)
    yf = YFinanceProvider(settings.providers.get("yfinance") or _default_yf(), settings.cache, cache)

    tickers = sorted({p.ticker for p in positions} | {MARKET_BENCHMARK})
    try:
        price_frames = await yf.get_prices(tickers, force_refresh=force_refresh)
    finally:
        await yf.close()

    market_df = price_frames.pop(MARKET_BENCHMARK, None)
    market_alerts = evaluate_market_regime(market_df)

    evaluations: list[PositionEvaluation] = []
    for pos in positions:
        df = price_frames.get(pos.ticker)
        evaluation = _evaluate_position(pos, df)
        evaluations.append(evaluation)

    return evaluations, market_alerts


def _default_yf():
    from canslim.config import ProviderConfig
    return ProviderConfig(enabled=True, concurrency=4)


def _evaluate_position(pos: Position, df: Optional[pd.DataFrame]) -> PositionEvaluation:
    if df is None or df.empty:
        return PositionEvaluation(
            ticker=pos.ticker, entry_price=pos.entry_price, entry_date=pos.entry_date,
            shares=pos.shares, stop_loss=pos.stop_loss,
            alerts=[SellAlert(
                ticker=pos.ticker, severity="warning", signal="no_price_data",
                message="No price data available — check yfinance status or retry with --force-refresh",
                action="VERIFY",
            )],
        )

    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    last = float(close.iloc[-1])
    last_date = df.index[-1].date() if hasattr(df.index[-1], "date") else pos.entry_date
    days_held = max(0, (last_date - pos.entry_date).days)

    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    avg_vol_50 = float(vol.rolling(50).mean().iloc[-1]) if len(vol) >= 50 else None
    today_vol = float(vol.iloc[-1])

    unrealized_pct = (last - pos.entry_price) / pos.entry_price
    unrealized_usd = (last - pos.entry_price) * pos.shares

    evaluation = PositionEvaluation(
        ticker=pos.ticker,
        entry_price=pos.entry_price,
        entry_date=pos.entry_date,
        shares=pos.shares,
        stop_loss=pos.stop_loss,
        current_price=round(last, 2),
        unrealized_pct=round(unrealized_pct, 4),
        unrealized_usd=round(unrealized_usd, 2),
        sma50=round(sma50, 2) if sma50 else None,
        sma200=round(sma200, 2) if sma200 else None,
        days_held=days_held,
    )

    alerts: list[SellAlert] = []

    # --- CRITICAL ---------------------------------------------------------

    # 1. Hard stop
    if last <= pos.stop_loss:
        alerts.append(SellAlert(
            ticker=pos.ticker, severity="critical", signal="hard_stop",
            message=f"Close ${last:.2f} ≤ stop-loss ${pos.stop_loss:.2f} — thesis invalidated.",
            action="SELL ALL (market order next session)",
            current_price=last, unrealized_pct=unrealized_pct,
        ))

    # 2. 50-DMA break on heavy volume
    if sma50 is not None and avg_vol_50 is not None and last < sma50 and today_vol > avg_vol_50:
        alerts.append(SellAlert(
            ticker=pos.ticker, severity="critical", signal="50dma_break",
            message=(
                f"Close ${last:.2f} below 50-DMA ${sma50:.2f} on volume "
                f"{today_vol/avg_vol_50:.2f}× average — institutions are distributing."
            ),
            action="SELL ALL or at minimum SELL HALF; re-enter only on a new base",
            current_price=last, unrealized_pct=unrealized_pct,
        ))

    # --- WARNING ----------------------------------------------------------

    # 3. Climax run: 3 accelerating up days + exhaustion bar (wide range at the top)
    climax = _detect_climax_run(df)
    if climax:
        alerts.append(SellAlert(
            ticker=pos.ticker, severity="warning", signal="climax_run",
            message=climax,
            action="SELL HALF into strength; trail the other half tighter",
            current_price=last, unrealized_pct=unrealized_pct,
        ))

    # 4. Scale-out on normal winner (not a fast runner)
    if unrealized_pct >= 0.22 and days_held >= 28 and pos.scaled_out_pct < 0.33:
        alerts.append(SellAlert(
            ticker=pos.ticker, severity="warning", signal="scale_out",
            message=f"+{unrealized_pct:.1%} over {days_held} days — normal-pace winner, not a fast runner.",
            action="SCALE OUT 1/3 — take some chips off the table, let the rest run",
            current_price=last, unrealized_pct=unrealized_pct,
        ))

    # --- INFO -------------------------------------------------------------

    # 5. Breakeven-stop upgrade
    if unrealized_pct >= 0.15 and pos.stop_loss < pos.entry_price:
        alerts.append(SellAlert(
            ticker=pos.ticker, severity="info", signal="breakeven_upgrade",
            message=f"+{unrealized_pct:.1%} gain — consider moving stop from ${pos.stop_loss:.2f} to ${pos.entry_price:.2f} (breakeven).",
            action="RAISE STOP to entry price; converts winner to a free trade",
            current_price=last, unrealized_pct=unrealized_pct,
        ))

    # 6. Fast winner — explicitly DO NOT SELL
    if unrealized_pct >= 0.20 and days_held <= 15:
        alerts.append(SellAlert(
            ticker=pos.ticker, severity="info", signal="fast_winner",
            message=(
                f"+{unrealized_pct:.1%} in {days_held} days — O'Neil's 'fast runner' rule: "
                "don't cut these; they're often the biggest winners."
            ),
            action="HOLD; trail a 10% stop from the high rather than scaling out",
            current_price=last, unrealized_pct=unrealized_pct,
        ))

    evaluation.alerts = alerts
    return evaluation


def _detect_climax_run(df: pd.DataFrame) -> Optional[str]:
    """Return a description string if a climax run is present, else None."""
    if df is None or len(df) < 10:
        return None
    close = df["close"].astype(float).values
    high = df["high"].astype(float).values if "high" in df.columns else close
    low = df["low"].astype(float).values if "low" in df.columns else close
    vol = df["volume"].astype(float).values
    n = len(close)

    # Last 3 sessions all up with accelerating magnitude
    if n < 4:
        return None
    deltas = [(close[n - i] - close[n - i - 1]) / close[n - i - 1] for i in (1, 2, 3)]
    if not all(d > 0 for d in deltas):
        return None
    # Accelerating: today's gain > yesterday's gain > the day before's
    if not (deltas[0] > deltas[1] > deltas[2]):
        return None
    # Today's range substantially wider than the 10-session average (exhaustion bar)
    ranges = high[-10:] - low[-10:]
    avg_range = float(ranges[:-1].mean()) if len(ranges) > 1 else 0.0
    today_range = float(ranges[-1])
    if avg_range > 0 and today_range >= 1.8 * avg_range:
        return (
            f"Climax-like action: 3 accelerating up-days ({deltas[2]:+.1%} → {deltas[1]:+.1%} → {deltas[0]:+.1%}), "
            f"today's range {today_range/avg_range:.1f}× 10-day avg — possible exhaustion."
        )
    return None


def evaluate_market_regime(spy_df: Optional[pd.DataFrame]) -> list[SellAlert]:
    """Market-level alerts that apply across the portfolio."""
    alerts: list[SellAlert] = []
    if spy_df is None or spy_df.empty or len(spy_df) < 25:
        return alerts

    close = spy_df["close"].astype(float)
    vol = spy_df["volume"].astype(float)
    high = spy_df["high"].astype(float) if "high" in spy_df.columns else close
    low = spy_df["low"].astype(float) if "low" in spy_df.columns else close

    last = float(close.iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    # Distribution day: heavy-volume down day that closes in lower half of range
    window = 25
    avg_vol = vol.rolling(50).mean()
    dist_days = 0
    dist_dates: list[str] = []
    for i in range(-window, 0):
        if i + len(close) < 1:
            continue
        c_today = float(close.iloc[i])
        c_prev = float(close.iloc[i - 1]) if i - 1 >= -len(close) else None
        v_today = float(vol.iloc[i])
        v_avg = float(avg_vol.iloc[i]) if not pd.isna(avg_vol.iloc[i]) else None
        if c_prev is None or v_avg is None or v_avg <= 0:
            continue
        is_down = c_today < c_prev
        heavy = v_today > v_avg
        hi_today = float(high.iloc[i])
        lo_today = float(low.iloc[i])
        if hi_today <= lo_today:
            continue
        mid_range = (hi_today + lo_today) / 2
        closes_lower_half = c_today < mid_range
        if is_down and heavy and closes_lower_half:
            dist_days += 1
            idx_date = spy_df.index[i]
            dist_dates.append(idx_date.strftime("%Y-%m-%d") if hasattr(idx_date, "strftime") else str(idx_date))

    if dist_days >= 4:
        alerts.append(SellAlert(
            ticker="SPY", severity="critical", signal="distribution_cluster",
            message=f"{dist_days} distribution days in last {window} sessions: {', '.join(dist_dates)}",
            action="TIGHTEN ALL STOPS; pause new long entries; raise cash to 40-50%",
        ))
    elif dist_days == 3:
        alerts.append(SellAlert(
            ticker="SPY", severity="warning", signal="distribution_cluster",
            message=f"3 distribution days in last {window} sessions: {', '.join(dist_dates)}",
            action="TIGHTEN ALL STOPS; pause new entries; watch for 4th day",
        ))

    # SPY below 50-DMA on heavy volume
    if sma50 is not None and last < sma50:
        today_vol = float(vol.iloc[-1])
        avg_vol_50 = float(vol.rolling(50).mean().iloc[-1])
        if today_vol > avg_vol_50:
            alerts.append(SellAlert(
                ticker="SPY", severity="critical", signal="spy_below_50dma",
                message=f"SPY close ${last:.2f} below 50-DMA ${sma50:.2f} on heavy volume.",
                action="REDUCE GROSS EXPOSURE; stop opening new positions.",
            ))

    # 50-DMA below 200-DMA
    if sma50 is not None and sma200 is not None and sma50 < sma200:
        alerts.append(SellAlert(
            ticker="SPY", severity="critical", signal="death_cross",
            message=f"SPY 50-DMA ${sma50:.2f} has crossed below 200-DMA ${sma200:.2f}.",
            action="RAISE CASH to majority per strict CANSLIM M-gate; only hold positions in clear uptrends.",
        ))

    return alerts


def render_monitor_report(
    evaluations: list[PositionEvaluation],
    market_alerts: list[SellAlert],
) -> str:
    lines: list[str] = []
    lines.append(f"# Position monitor — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # Headline counts
    crit = sum(1 for ev in evaluations for a in ev.alerts if a.severity == "critical") + sum(
        1 for a in market_alerts if a.severity == "critical"
    )
    warn = sum(1 for ev in evaluations for a in ev.alerts if a.severity == "warning") + sum(
        1 for a in market_alerts if a.severity == "warning"
    )
    info = sum(1 for ev in evaluations for a in ev.alerts if a.severity == "info") + sum(
        1 for a in market_alerts if a.severity == "info"
    )
    lines.append(f"- Positions tracked: **{len(evaluations)}**")
    lines.append(f"- Alerts: **{crit} critical**, {warn} warning, {info} info")
    lines.append("")

    # Market regime
    lines.append("## Market regime (SPY)")
    lines.append("")
    if not market_alerts:
        lines.append("_No market-level sell signals today. M-gate remains green._")
    else:
        for a in sorted(market_alerts, key=lambda x: {"critical":0,"warning":1,"info":2}[x.severity]):
            lines.append(f"- **[{a.severity.upper()}]** `{a.signal}` — {a.message}")
            lines.append(f"  - **Action:** {a.action}")
    lines.append("")

    # Per-position
    lines.append("## Positions")
    lines.append("")
    lines.append("| Ticker | Entry | Current | Unreal % | Unreal $ | Stop | 50-DMA | Alerts |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for ev in sorted(evaluations, key=lambda e: -(e.unrealized_pct or 0)):
        price = f"${ev.current_price:.2f}" if ev.current_price else "n/a"
        pct = f"{ev.unrealized_pct:+.1%}" if ev.unrealized_pct is not None else "—"
        usd = f"${ev.unrealized_usd:+,.0f}" if ev.unrealized_usd is not None else "—"
        sma50 = f"${ev.sma50:.2f}" if ev.sma50 else "—"
        alert_count = len(ev.alerts)
        crit_count = sum(1 for a in ev.alerts if a.severity == "critical")
        alerts_cell = f"**{crit_count} critical** / {alert_count} total" if crit_count else f"{alert_count}"
        lines.append(
            f"| {ev.ticker} | ${ev.entry_price:.2f} | {price} | {pct} | {usd} | ${ev.stop_loss:.2f} | {sma50} | {alerts_cell} |"
        )
    lines.append("")

    # Detailed alerts per position
    alerting = [ev for ev in evaluations if ev.alerts]
    if alerting:
        lines.append("## Per-position alerts")
        lines.append("")
        for ev in sorted(alerting, key=lambda e: (
            -max((1 if a.severity == "critical" else 0 for a in e.alerts), default=0),
            e.ticker,
        )):
            lines.append(f"### {ev.ticker}  ·  ${ev.current_price:.2f}  ·  {ev.unrealized_pct:+.1%}  ·  held {ev.days_held} days")
            lines.append("")
            for a in sorted(ev.alerts, key=lambda x: {"critical":0,"warning":1,"info":2}[x.severity]):
                lines.append(f"- **[{a.severity.upper()}]** `{a.signal}` — {a.message}")
                lines.append(f"  - **Action:** {a.action}")
            lines.append("")

    lines.append("---")
    lines.append("_Stop-losses are non-negotiable. If a critical alert fires, the disciplined action is to act on the next session's open, not to override the signal with a story about why this time is different._")
    return "\n".join(lines)


def snapshot_dict(
    evaluations: list[PositionEvaluation],
    market_alerts: list[SellAlert],
) -> dict:
    """Structured JSON-ready snapshot of a monitor run — feeds the dashboard."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "positions": [ev.model_dump(mode="json") for ev in evaluations],
        "market_alerts": [a.model_dump(mode="json") for a in market_alerts],
    }


def write_snapshot(snapshot: dict, archive_dir: Path) -> tuple[Path, Path]:
    """Write timestamped .md and .json snapshots for the dashboard + cron history."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    json_path = archive_dir / f"{ts}.json"
    json_path.write_text(json.dumps(snapshot, indent=2, default=str))
    return json_path, archive_dir / f"{ts}.md"
