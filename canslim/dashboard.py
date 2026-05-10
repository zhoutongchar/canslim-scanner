"""Dashboard renderer — single self-contained HTML file, no server required.

Reads monitor snapshots (JSON) from a directory, renders a Grafana-style HTML
with:

  * Header: last-updated, market-regime badge, critical-alert count
  * Active alerts panel — color-coded by severity
  * Positions table — current price, P&L %, P&L $, stop distance, per-ticker alerts
  * Time-series charts (Chart.js via CDN):
      - Cumulative P&L per position
      - Alert count by severity over time
      - SPY distribution-day history (from market-alerts)

The resulting file is double-click-openable in any browser. Hosting on a cron
writes snapshot history + overwrites `dashboard.html` each run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


def render_dashboard(history_dir: Path, out_path: Path) -> Path:
    """Read every *.json snapshot in `history_dir`, render `dashboard.html`."""
    history_dir = Path(history_dir)
    out_path = Path(out_path)
    snapshots = _load_snapshots(history_dir)
    html = _render_html(snapshots)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path


def _load_snapshots(history_dir: Path) -> list[dict]:
    snaps: list[dict] = []
    for p in sorted(history_dir.glob("*.json")):
        try:
            snaps.append(json.loads(p.read_text()))
        except Exception:
            continue
    return snaps


def _render_html(snapshots: list[dict]) -> str:
    latest: dict[str, Any] = snapshots[-1] if snapshots else {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "positions": [],
        "market_alerts": [],
    }
    positions = latest.get("positions", [])
    market_alerts = latest.get("market_alerts", [])

    # Build time-series data for charts
    ts_data = _build_timeseries(snapshots)

    # Regime badge
    has_critical_market = any(a.get("severity") == "critical" for a in market_alerts)
    regime_label = "CAUTION" if has_critical_market else ("WARN" if market_alerts else "CLEAR")
    regime_color = "#c0392b" if has_critical_market else ("#e67e22" if market_alerts else "#27ae60")

    total_critical = sum(
        1 for p in positions for a in p.get("alerts", []) if a.get("severity") == "critical"
    ) + sum(1 for a in market_alerts if a.get("severity") == "critical")
    total_warning = sum(
        1 for p in positions for a in p.get("alerts", []) if a.get("severity") == "warning"
    ) + sum(1 for a in market_alerts if a.get("severity") == "warning")
    total_info = sum(
        1 for p in positions for a in p.get("alerts", []) if a.get("severity") == "info"
    ) + sum(1 for a in market_alerts if a.get("severity") == "info")

    total_pnl = sum(p.get("unrealized_usd") or 0 for p in positions)
    total_cost = sum((p.get("entry_price") or 0) * (p.get("shares") or 0) for p in positions)
    portfolio_pct = (total_pnl / total_cost) if total_cost else 0.0

    generated = latest.get("generated_at", "")

    data_json = json.dumps(ts_data, default=str)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>canslim · position dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {{
      --bg: #0f1218;
      --card: #171b24;
      --border: #242a37;
      --text: #e6e9ef;
      --muted: #8891a3;
      --critical: #c0392b;
      --warning: #e67e22;
      --info: #2676d3;
      --ok: #27ae60;
    }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg); color: var(--text); padding: 24px; }}
    h1 {{ font-size: 20px; margin: 0 0 4px; }}
    .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
      padding: 16px; box-sizing: border-box; }}
    .card h2 {{ font-size: 13px; margin: 0 0 10px; color: var(--muted); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.5px; }}
    .kpi {{ font-size: 28px; font-weight: 600; }}
    .kpi-sub {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    .col-3 {{ grid-column: span 3; }}
    .col-4 {{ grid-column: span 4; }}
    .col-6 {{ grid-column: span 6; }}
    .col-8 {{ grid-column: span 8; }}
    .col-12 {{ grid-column: span 12; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
      font-weight: 600; letter-spacing: 0.5px; }}
    .b-critical {{ background: var(--critical); color: #fff; }}
    .b-warning {{ background: var(--warning); color: #fff; }}
    .b-info {{ background: var(--info); color: #fff; }}
    .b-ok {{ background: var(--ok); color: #fff; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ font-size: 11px; color: var(--muted); font-weight: 500;
      text-transform: uppercase; letter-spacing: 0.5px; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tr:last-child td {{ border-bottom: none; }}
    .pos-gain {{ color: var(--ok); }}
    .pos-loss {{ color: var(--critical); }}
    .alert-row {{ padding: 10px 12px; border-left: 3px solid; margin-bottom: 8px;
      border-radius: 0 4px 4px 0; background: rgba(255,255,255,0.02); }}
    .alert-row.critical {{ border-left-color: var(--critical); }}
    .alert-row.warning {{ border-left-color: var(--warning); }}
    .alert-row.info {{ border-left-color: var(--info); }}
    .alert-title {{ font-weight: 600; font-size: 13px; }}
    .alert-msg {{ color: var(--muted); font-size: 12px; margin: 3px 0; }}
    .alert-action {{ font-size: 12px; color: var(--text); }}
    canvas {{ background: transparent; }}
    .footer {{ color: var(--muted); font-size: 11px; margin-top: 24px; text-align: center; }}
  </style>
</head>
<body>
  <h1>CANSLIM · position dashboard</h1>
  <div class="sub">Last updated: {escape(generated)} · {len(snapshots)} snapshots in history</div>

  <div class="grid">
    <div class="card col-3">
      <h2>Market regime</h2>
      <div class="kpi"><span class="badge" style="background:{regime_color}">{regime_label}</span></div>
      <div class="kpi-sub">{len(market_alerts)} market alert(s)</div>
    </div>

    <div class="card col-3">
      <h2>Portfolio P&amp;L</h2>
      <div class="kpi {'pos-gain' if total_pnl >= 0 else 'pos-loss'}">
        {f"${total_pnl:+,.0f}"}
      </div>
      <div class="kpi-sub">{portfolio_pct:+.2%} of cost basis · {len(positions)} positions</div>
    </div>

    <div class="card col-3">
      <h2>Critical alerts</h2>
      <div class="kpi" style="color:{'var(--critical)' if total_critical else 'var(--ok)'}">{total_critical}</div>
      <div class="kpi-sub">across positions + market</div>
    </div>

    <div class="card col-3">
      <h2>Warning / Info</h2>
      <div class="kpi"><span style="color:var(--warning)">{total_warning}</span> /
        <span style="color:var(--info)">{total_info}</span></div>
      <div class="kpi-sub">management signals</div>
    </div>

    <div class="card col-8">
      <h2>Positions</h2>
      {_render_positions_table(positions)}
    </div>

    <div class="card col-4">
      <h2>Active alerts</h2>
      {_render_alerts_list(market_alerts, positions)}
    </div>

    <div class="card col-6">
      <h2>Cumulative P&amp;L % per position</h2>
      <canvas id="pnlChart" height="180"></canvas>
    </div>

    <div class="card col-6">
      <h2>Alert count over time</h2>
      <canvas id="alertsChart" height="180"></canvas>
    </div>
  </div>

  <div class="footer">Regenerate with:
    <code>canslim dashboard --history out/monitor/ --out out/monitor/dashboard.html</code>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <script>
    const data = {data_json};

    // Common dark-theme tweaks
    Chart.defaults.color = '#8891a3';
    Chart.defaults.borderColor = '#242a37';

    (function renderPnL() {{
      const ctx = document.getElementById('pnlChart');
      if (!ctx || !data.pnl_timeseries) return;
      const labels = data.pnl_timeseries.labels || [];
      const datasets = (data.pnl_timeseries.series || []).map((s, i) => ({{
        label: s.ticker,
        data: s.values,
        borderColor: palette(i),
        backgroundColor: palette(i) + '30',
        tension: 0.25,
        fill: false,
        pointRadius: 2,
      }}));
      new Chart(ctx, {{
        type: 'line',
        data: {{ labels, datasets }},
        options: {{
          plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10 }} }} }},
          scales: {{
            y: {{ ticks: {{ callback: v => v.toFixed(1) + '%' }} }}
          }},
          responsive: true,
          maintainAspectRatio: false,
        }}
      }});
    }})();

    (function renderAlerts() {{
      const ctx = document.getElementById('alertsChart');
      if (!ctx || !data.alerts_timeseries) return;
      const labels = data.alerts_timeseries.labels || [];
      const series = data.alerts_timeseries.series || {{}};
      new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels,
          datasets: [
            {{ label: 'critical', data: series.critical || [], backgroundColor: '#c0392b', stack: 's' }},
            {{ label: 'warning',  data: series.warning  || [], backgroundColor: '#e67e22', stack: 's' }},
            {{ label: 'info',     data: series.info     || [], backgroundColor: '#2676d3', stack: 's' }},
          ],
        }},
        options: {{
          plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10 }} }} }},
          scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true }} }},
          responsive: true,
          maintainAspectRatio: false,
        }}
      }});
    }})();

    function palette(i) {{
      const colors = ['#27ae60', '#2676d3', '#e67e22', '#c0392b', '#9b59b6',
                      '#16a085', '#f39c12', '#34495e', '#e91e63', '#795548'];
      return colors[i % colors.length];
    }}
  </script>
</body>
</html>
"""
    return html


def _render_positions_table(positions: list[dict]) -> str:
    if not positions:
        return '<div style="color:var(--muted);font-size:13px">No positions tracked.</div>'
    rows = []
    for p in sorted(positions, key=lambda x: -(x.get("unrealized_pct") or 0)):
        pct = p.get("unrealized_pct")
        usd = p.get("unrealized_usd")
        cls = "pos-gain" if (pct or 0) >= 0 else "pos-loss"
        pct_s = f'<span class="{cls}">{pct:+.1%}</span>' if pct is not None else "—"
        usd_s = f'<span class="{cls}">${usd:+,.0f}</span>' if usd is not None else "—"
        alerts = p.get("alerts", [])
        crit = sum(1 for a in alerts if a.get("severity") == "critical")
        alert_badge = (
            f'<span class="badge b-critical">{crit} CRIT</span> '
            if crit else ""
        ) + (f'<span class="badge b-info">{len(alerts)}</span>' if alerts else "—")
        price = p.get("current_price")
        rows.append(
            f'<tr><td><b>{escape(p.get("ticker",""))}</b></td>'
            f'<td class="num">${p.get("entry_price",0):.2f}</td>'
            f'<td class="num">{"$"+format(price,".2f") if price else "—"}</td>'
            f'<td class="num">{pct_s}</td>'
            f'<td class="num">{usd_s}</td>'
            f'<td class="num">${p.get("stop_loss",0):.2f}</td>'
            f'<td class="num">{p.get("days_held",0)}d</td>'
            f'<td>{alert_badge}</td></tr>'
        )
    return (
        '<table><thead><tr>'
        '<th>Ticker</th><th>Entry</th><th>Current</th><th>P&amp;L %</th>'
        '<th>P&amp;L $</th><th>Stop</th><th>Held</th><th>Alerts</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_alerts_list(market_alerts: list[dict], positions: list[dict]) -> str:
    all_alerts: list[tuple[str, dict]] = []
    for a in market_alerts:
        all_alerts.append(("SPY", a))
    for p in positions:
        for a in p.get("alerts", []):
            all_alerts.append((p.get("ticker", "?"), a))
    if not all_alerts:
        return '<div style="color:var(--muted);font-size:13px">No active alerts. 🟢</div>'
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    all_alerts.sort(key=lambda x: severity_order.get(x[1].get("severity", "info"), 3))

    out = []
    for ticker, a in all_alerts[:30]:
        sev = a.get("severity", "info")
        out.append(
            f'<div class="alert-row {sev}">'
            f'<div class="alert-title">{escape(ticker)} · {escape(a.get("signal",""))} '
            f'<span class="badge b-{sev}">{sev.upper()}</span></div>'
            f'<div class="alert-msg">{escape(a.get("message",""))}</div>'
            f'<div class="alert-action"><b>→</b> {escape(a.get("action",""))}</div>'
            f'</div>'
        )
    return "".join(out)


def _build_timeseries(snapshots: list[dict]) -> dict:
    if not snapshots:
        return {"pnl_timeseries": {"labels": [], "series": []},
                "alerts_timeseries": {"labels": [], "series": {}}}

    labels = [s.get("generated_at", "")[:19].replace("T", " ") for s in snapshots]

    # P&L per ticker over time — only include tickers present in latest snapshot
    latest_tickers = {p.get("ticker") for p in snapshots[-1].get("positions", [])}
    pnl_by_ticker: dict[str, list[float | None]] = {t: [] for t in latest_tickers}
    for snap in snapshots:
        positions = snap.get("positions", [])
        per_ticker = {p.get("ticker"): p.get("unrealized_pct") for p in positions}
        for t in latest_tickers:
            val = per_ticker.get(t)
            pnl_by_ticker[t].append(round((val or 0) * 100, 2))

    pnl_series = [{"ticker": t, "values": vs} for t, vs in pnl_by_ticker.items()]

    # Alert counts over time
    counts = {"critical": [], "warning": [], "info": []}
    for snap in snapshots:
        c = w = i = 0
        for p in snap.get("positions", []):
            for a in p.get("alerts", []):
                sev = a.get("severity")
                if sev == "critical":
                    c += 1
                elif sev == "warning":
                    w += 1
                elif sev == "info":
                    i += 1
        for a in snap.get("market_alerts", []):
            sev = a.get("severity")
            if sev == "critical":
                c += 1
            elif sev == "warning":
                w += 1
            elif sev == "info":
                i += 1
        counts["critical"].append(c)
        counts["warning"].append(w)
        counts["info"].append(i)

    return {
        "pnl_timeseries": {"labels": labels, "series": pnl_series},
        "alerts_timeseries": {"labels": labels, "series": counts},
    }
