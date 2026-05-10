"""Per-ticker deep-dive markdown reports.

For every full match and every candidate in the "buyable zone", emit a standalone
`.md` file under `out/runs/<ts>/deepdive/<TICKER>.md` that contains:

  * Verdict + trading plan (pivot, buy zone, stop-loss)
  * Embedded chart (base64 or file ref)
  * CANSLIM 7-letter breakdown with RAW numbers and citations
  * Full quarterly + annual EPS tables (from SEC when available)
  * Every detected chart pattern with full evidence dict
  * A/D rating with up/down flow breakdown
  * Data-integrity notes (what was cached, what source returned empty)
  * Primary-source links (SEC EDGAR, yfinance)

Principle: every claim carries a citation — no number without its source.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from canslim.models import PatternMatch, RunManifest, ScanResult

LETTERS = ["C", "A", "N", "S", "L", "I", "M"]


def emit_deepdives(
    results: list[ScanResult],
    manifest: RunManifest,
    run_dir: Path,
    price_frames: Optional[dict[str, pd.DataFrame]] = None,
    chart_paths: Optional[dict[str, Path]] = None,
    embed_base64: bool = True,
    tickers: Optional[set[str]] = None,
) -> list[Path]:
    """Write one deepdive md per target ticker. Returns list of written paths."""
    out_dir = run_dir / "deepdive"
    out_dir.mkdir(parents=True, exist_ok=True)

    if tickers is None:
        tickers = _select_deepdive_tickers(results)

    written: list[Path] = []
    for r in results:
        if r.ticker not in tickers:
            continue
        df = price_frames.get(r.ticker) if price_frames else None
        chart_path = chart_paths.get(r.ticker) if chart_paths else None
        md = _render_deepdive(r, df, manifest, chart_path, embed_base64)
        p = out_dir / f"{r.ticker}.md"
        p.write_text(md)
        written.append(p)
    return written


def _select_deepdive_tickers(results: list[ScanResult]) -> set[str]:
    """Only the genuine top candidates warrant a deep-dive file.

    Inclusion rules (any one qualifies):
      1. Full CANSLIM match (all gate criteria pass).
      2. Pass 4/5 gates — the "one step away" tier.
      3. Buyable zone: top-confidence pattern within ±5% of pivot AND confidence ≥ 0.55
         AND composite_score ≥ 0.75 AND at least 3 of 5 gates pass.

    Rule 3 cuts "stock passes pre-filter and happened to have a flat_base nearby"
    noise. Without it we'd emit ~1,000+ deep-dives and drown the user in files.
    """
    out: set[str] = set()
    for r in results:
        if r.status != "scanned":
            continue
        if r.passed:
            out.add(r.ticker)
            continue
        # pass 4/5 gates
        gate_results = [cr for cr in r.criteria.values() if cr.is_gate]
        gate_passes = sum(1 for cr in gate_results if cr.passed)
        if gate_results and gate_passes >= len(gate_results) - 1:
            out.add(r.ticker)
            continue
        # buyable zone — tightened
        if r.composite_score < 0.75 or gate_passes < 3:
            continue
        for p in r.patterns:
            if p.confidence < 0.55:
                continue
            dist = p.evidence.get("dist_to_pivot_pct")
            if isinstance(dist, (int, float)) and -0.05 <= dist <= 0.05:
                out.add(r.ticker)
                break
    return out


def _render_deepdive(
    r: ScanResult,
    price_df: Optional[pd.DataFrame],
    manifest: RunManifest,
    chart_path: Optional[Path],
    embed_base64: bool,
) -> str:
    lines: list[str] = []
    verdict, trade_plan = _compute_verdict_and_plan(r)

    # Header
    lines.append(f"# {r.ticker} — deep-dive analysis")
    lines.append("")
    lines.append(f"_Run `{manifest.run_id}` · universe `{manifest.universe_name}` · scanned {r.as_of.isoformat()}_")
    lines.append("")
    lines.append(f"> **Verdict:** {verdict}")
    lines.append("")

    # Trading plan
    if trade_plan:
        lines.append("## Trading plan")
        lines.append("")
        for k, v in trade_plan.items():
            lines.append(f"- **{k}:** {v}")
        lines.append("")
        lines.append(
            "> *These levels are derived from the detected pattern's pivot per O'Neil's rules. "
            "Do your own verification; this is not advice.*"
        )
        lines.append("")

    # Chart
    chart_ref = _chart_ref(chart_path, embed_base64)
    if chart_ref:
        lines.append("## Chart")
        lines.append("")
        lines.append(f"![{r.ticker} chart]({chart_ref})")
        lines.append("")
        lines.append("_200 daily sessions, 50/200-DMA overlay, 52-week-high reference, pivot line from top-confidence pattern._")
        lines.append("")

    # Price summary
    if price_df is not None and not price_df.empty:
        lines.append("## Price summary")
        lines.append("")
        close = price_df["close"].astype(float)
        vol = price_df["volume"].astype(float)
        last = float(close.iloc[-1])
        last_date = price_df.index[-1].strftime("%Y-%m-%d") if hasattr(price_df.index[-1], "strftime") else str(price_df.index[-1])
        sma10 = float(close.rolling(10).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        high52 = float(close.tail(252).max())
        low52 = float(close.tail(252).min())
        adv50 = float((close.tail(50) * vol.tail(50)).mean())
        adv10 = float((close.tail(10) * vol.tail(10)).mean())

        lines.append("| Metric | Value | Source |")
        lines.append("|---|---|---|")
        lines.append(f"| Last close | ${last:,.2f} ({last_date}) | yfinance daily bar |")
        lines.append(f"| 10-day SMA | ${sma10:,.2f} | computed from cache |")
        lines.append(f"| 50-day SMA | ${sma50:,.2f} | computed from cache |")
        lines.append(f"| 200-day SMA | ${sma200:,.2f} | computed from cache |")
        lines.append(f"| 52-week high | ${high52:,.2f} | 252 trailing sessions |")
        lines.append(f"| 52-week low | ${low52:,.2f} | 252 trailing sessions |")
        lines.append(f"| Distance to 52w high | {(high52-last)/high52:.1%} | |")
        lines.append(f"| Position vs 50-DMA | {(last/sma50 - 1):+.1%} | |")
        lines.append(f"| ADV50 (dollar volume) | ${adv50:,.0f} | close × volume, trailing 50 |")
        lines.append(f"| ADV10 / ADV50 | {adv10/adv50:.2f} | recent volume pressure |")
        lines.append("")

    # CANSLIM 7-letter breakdown
    lines.append("## CANSLIM evaluation")
    lines.append("")
    lines.append("Every criterion below cites the raw evidence used. Zero trust without evidence.")
    lines.append("")
    for letter in LETTERS:
        cr = r.criteria.get(letter)
        if cr is None:
            continue
        gate = "GATE" if cr.is_gate else "info"
        check = "✅ PASS" if cr.passed else "❌ FAIL"
        lines.append(f"### {letter} — {_letter_name(letter)} ({gate})  ·  {check}")
        lines.append("")
        lines.append(f"- **Reason:** {cr.reason or '(no reason)'}")
        if cr.value is not None:
            lines.append(f"- **Value:** `{cr.value}`")
        if cr.threshold is not None:
            lines.append(f"- **Threshold:** `{cr.threshold}`")
        lines.append(f"- **Normalized score:** {cr.score:.3f}")
        if cr.evidence:
            lines.append("- **Evidence:**")
            lines.append("")
            lines.append("  ```json")
            lines.append(f"  {json.dumps(cr.evidence, indent=2, default=str)}")
            lines.append("  ```")
        lines.append("")

    # Accumulation/Distribution
    if r.ad_grade is not None:
        descr = {
            "A": "heavy accumulation — institutions buying on strength",
            "B": "moderate accumulation",
            "C": "neutral — balanced supply and demand",
            "D": "moderate distribution — institutions selling on strength",
            "E": "heavy distribution",
        }.get(r.ad_grade, "?")
        lines.append("## Accumulation / Distribution")
        lines.append("")
        lines.append(f"- **Grade:** `{r.ad_grade}` — {descr}")
        if r.ad_ratio is not None:
            lines.append(f"- **Up-flow ratio:** {r.ad_ratio:.3f} (up-day dollar-flow / total dollar-flow over trailing 50 sessions)")
        lines.append(f"- **Method:** conviction-weighted — each day's dollar volume weighted by abs(daily return) to emphasize big-range moves")
        lines.append("")

    # Fundamentals — raw SEC history
    lines.extend(_render_fundamentals_from_cache(r.ticker))

    # Patterns
    if r.patterns:
        lines.append("## Detected chart patterns")
        lines.append("")
        lines.append("All detected patterns, ordered by confidence:")
        lines.append("")
        for p in sorted(r.patterns, key=lambda x: -x.confidence):
            _emit_pattern(lines, p)
    else:
        lines.append("## Chart patterns")
        lines.append("")
        lines.append("_No chart pattern detected above confidence threshold._")
        lines.append("")

    # Recent management changes (SEC 8-K Item 5.02) — the automatable slice of O'Neil's "N"
    if r.management_events_90d:
        lines.append("## Recent management changes (SEC 8-K Item 5.02, trailing 90 days)")
        lines.append("")
        lines.append("_This is the automatable half of O'Neil's N gate beyond the 52-week-high test:_")
        lines.append("_officer/director departures or appointments filed with the SEC._")
        lines.append("")
        lines.append("| Filed | Item codes | Filing |")
        lines.append("|---|---|---|")
        for e in sorted(r.management_events_90d, key=lambda x: x.filed, reverse=True):
            link = f"[{e.accession or 'view'}]({e.url})" if e.url else (e.accession or "n/a")
            lines.append(f"| {e.filed.isoformat()} | {e.items} | {link} |")
        lines.append("")
        lines.append("_New management within the trailing 90 days is a qualitative strengthener of the N signal._")
        lines.append("_Read the primary filing to classify: CEO/CFO change, director refresh, or routine board rotation._")
        lines.append("")

    # Fetch errors / data gaps
    if r.errors:
        lines.append("## Data integrity warnings")
        lines.append("")
        lines.append("| Kind | Provider | Error |")
        lines.append("|---|---|---|")
        for e in r.errors:
            err_short = (e.error[:120] + "…") if len(e.error) > 120 else e.error
            lines.append(f"| {e.kind} | {e.provider} | {err_short} |")
        lines.append("")
        lines.append("_If a critical field (fundamentals, institutional) was missing, the relevant gate may be an artifact. Check manually._")
        lines.append("")

    # Primary sources
    lines.append("## Primary sources (verify directly)")
    lines.append("")
    lines.append(f"- SEC EDGAR full-text search: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={r.ticker}&type=10-K&dateb=&owner=include&count=40")
    lines.append(f"- yfinance summary: https://finance.yahoo.com/quote/{r.ticker}")
    lines.append(f"- Company press releases: search `{r.ticker} investor relations`")
    lines.append("")
    lines.append("_Every number above is derived from the cached SEC XBRL and yfinance daily bars as of the scan date. Before acting, reconcile against the primary filings._")
    lines.append("")

    # Generated footer
    lines.append("---")
    lines.append(f"_Generated by canslim scanner · {datetime.utcnow().isoformat()}Z · schema v{r.schema_version}_")
    return "\n".join(lines)


def _emit_pattern(lines: list[str], p: PatternMatch) -> None:
    lines.append(f"### {p.name} — confidence {p.confidence:.2f}")
    lines.append("")
    if p.pivot is not None:
        lines.append(f"- **Pivot:** ${p.pivot:.2f}")
    dist = p.evidence.get("dist_to_pivot_pct")
    if isinstance(dist, (int, float)):
        state = "in buy zone" if -0.05 <= dist <= 0.05 else ("approaching" if dist > 0.05 else "extended past pivot")
        lines.append(f"- **Distance to pivot:** {dist:+.1%} ({state})")
    if p.started_on:
        lines.append(f"- **Pattern started:** {p.started_on}")
    if p.completed_on:
        lines.append(f"- **Completed / as-of:** {p.completed_on}")
    lines.append("- **Full evidence:**")
    lines.append("")
    lines.append("  ```json")
    lines.append(f"  {json.dumps(p.evidence, indent=2, default=str)}")
    lines.append("  ```")
    lines.append("")


def _render_fundamentals_from_cache(ticker: str) -> list[str]:
    """Render the raw SEC fundamentals bundle if cached. Cites the cache path for verifiability."""
    cache_paths = [
        Path(f"cache/fundamentals/sec/{ticker}.json"),
        Path(f"cache/fundamentals/fmp/{ticker}.json"),
    ]
    lines: list[str] = []
    for p in cache_paths:
        if not p.exists():
            continue
        try:
            blob = json.loads(p.read_text())
        except Exception:
            continue
        source = p.parts[-2]
        lines.append(f"## Earnings history ({source.upper()})")
        lines.append("")
        lines.append(f"_Source: `{p}` (raw SEC XBRL `companyfacts` payload parsed at scan time)._")
        lines.append("_EPS shown is **normalized** — one-time items (divestiture gains, impairments, etc.) are stripped per the rules in `canslim/normalization/rules.py`. Reported GAAP EPS is shown alongside for comparison._")
        lines.append("")

        # Annual — show normalized vs reported side-by-side
        aperiods = blob.get("annual_periods", [])
        aeps = blob.get("annual_eps", [])
        reported_a = blob.get("reported_annual_eps", []) or aeps
        aroe = blob.get("annual_roe_pct", [])
        if aperiods:
            lines.append("### Annual EPS")
            lines.append("")
            lines.append("| Period | Reported EPS | Normalized EPS | Δ per share | ROE |")
            lines.append("|---|---|---|---|---|")
            for i, per in enumerate(aperiods):
                rep = reported_a[i] if i < len(reported_a) else None
                norm = aeps[i] if i < len(aeps) else None
                roe = aroe[i] if i < len(aroe) else None
                rep_s = f"${rep:.2f}" if isinstance(rep, (int, float)) else "n/a"
                norm_s = f"${norm:.2f}" if isinstance(norm, (int, float)) else "n/a"
                delta = (norm - rep) if (isinstance(norm, (int, float)) and isinstance(rep, (int, float))) else None
                delta_s = f"{delta:+.2f}" if delta is not None else "—"
                roe_s = f"{roe*100:.1f}%" if isinstance(roe, (int, float)) else "n/a"
                lines.append(f"| {per} | {rep_s} | **{norm_s}** | {delta_s} | {roe_s} |")
            lines.append("")

        # Quarterly
        qperiods = blob.get("quarterly_periods", [])
        qeps = blob.get("quarterly_eps", [])
        reported_q = blob.get("reported_quarterly_eps", []) or qeps
        if qperiods:
            lines.append("### Quarterly EPS (newest first)")
            lines.append("")
            lines.append("| Period | Reported EPS | Normalized EPS |")
            lines.append("|---|---|---|")
            for i, per in enumerate(qperiods[:12]):
                rep = reported_q[i] if i < len(reported_q) else None
                norm = qeps[i] if i < len(qeps) else None
                rep_s = f"${rep:.3f}" if isinstance(rep, (int, float)) else "n/a"
                norm_s = f"${norm:.3f}" if isinstance(norm, (int, float)) else "n/a"
                lines.append(f"| {per} | {rep_s} | **{norm_s}** |")
            lines.append("")

        # Normalization adjustments
        adjustments = blob.get("normalization_adjustments", []) or []
        if adjustments:
            lines.append("### Normalization adjustments applied")
            lines.append("")
            lines.append("_Each row shows an item that was stripped from (or added back to) reported EPS._")
            lines.append("_Direction:  `subtract` = one-time GAIN removed; `add_back` = one-time LOSS restored._")
            lines.append("")
            lines.append("| Period | Rule | Direction | Δ EPS | $ amount | Concept | Net-of-tax |")
            lines.append("|---|---|---|---|---|---|---|")
            for adj in sorted(adjustments, key=lambda a: (a.get("period", ""), a.get("rule_name", "")), reverse=True):
                direction = adj.get("direction", "")
                per_share = adj.get("per_share_impact", 0)
                sign = "-" if direction == "subtract" else "+"
                lines.append(
                    f"| {adj.get('period', '')} | {adj.get('rule_name', '')} | {direction} | "
                    f"{sign}${per_share:.3f} | ${adj.get('dollar_amount', 0):,.0f} | "
                    f"`{adj.get('concept', '')}` | {'yes' if adj.get('after_tax') else 'no (21% haircut applied)'} |"
                )
            lines.append("")
            lines.append("_See `canslim/normalization/rules.py` for the rule definitions. To add a new rule (e.g. a specific client-settlement concept), subclass `NormalizationRule` and register it._")
            lines.append("")

        return lines
    return lines


def _compute_verdict_and_plan(r: ScanResult) -> tuple[str, dict[str, str]]:
    """Derive a one-line verdict and concrete trading plan from pattern + gates."""
    if r.patterns:
        top = max(r.patterns, key=lambda p: p.confidence)
        dist = top.evidence.get("dist_to_pivot_pct")
        pivot = top.pivot
    else:
        top = None
        dist = None
        pivot = None

    gates_passing = sum(1 for cr in r.criteria.values() if cr.is_gate and cr.passed)
    gates_total = sum(1 for cr in r.criteria.values() if cr.is_gate)

    plan: dict[str, str] = {}

    if r.passed:
        verdict = f"**FULL CANSLIM MATCH** — passes all {gates_total} gates. Composite score {r.composite_score:.2f}. AD grade `{r.ad_grade or 'n/a'}`."
    elif top and isinstance(dist, (int, float)):
        if -0.05 <= dist <= 0.05:
            verdict = (
                f"**Buyable zone** — passes {gates_passing}/{gates_total} gates, "
                f"`{top.name}` pivot at ${pivot:.2f} ({dist:+.1%} from current), confidence {top.confidence:.2f}."
            )
        elif dist > 0.05:
            verdict = (
                f"**Watchlist (approaching)** — pivot at ${pivot:.2f} is {dist:+.1%} above current; "
                f"passes {gates_passing}/{gates_total} gates."
            )
        else:
            verdict = (
                f"**Watchlist (extended)** — already {abs(dist):.1%} past pivot, likely too late to chase; "
                f"passes {gates_passing}/{gates_total} gates."
            )
    else:
        verdict = f"**Basing / no pivot** — {gates_passing}/{gates_total} gates pass; no chart trigger yet."

    if pivot is not None:
        buy_upper = pivot * 1.05
        stop = pivot * 0.925  # 7.5% below pivot — O'Neil's typical stop zone
        plan["Pivot (buy trigger)"] = f"${pivot:.2f}"
        plan["Buy zone"] = f"${pivot:.2f} – ${buy_upper:.2f} (within 5% past pivot)"
        plan["Volume confirmation"] = "close ≥ 1.4× 50-day average daily volume"
        plan["Stop-loss"] = f"${stop:.2f} (7.5% below pivot)"
        plan["Target R/R"] = "first scale-out +20% (reward), stop -7.5% (risk), ratio ~2.7:1"
    return verdict, plan


def _chart_ref(chart_path: Optional[Path], embed_base64: bool) -> Optional[str]:
    if chart_path is None or not chart_path.exists():
        return None
    if embed_base64:
        try:
            data = chart_path.read_bytes()
            return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"
        except Exception:
            return f"../charts/{chart_path.name}"
    return f"../charts/{chart_path.name}"


def _letter_name(letter: str) -> str:
    return {
        "C": "Current quarterly earnings",
        "A": "Annual earnings growth",
        "N": "New highs / products",
        "S": "Supply & demand",
        "L": "Leader (relative strength)",
        "I": "Institutional sponsorship",
        "M": "Market direction",
    }.get(letter, letter)
