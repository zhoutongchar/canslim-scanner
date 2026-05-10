# canslim

CANSLIM stock scanner with pluggable data providers and criteria.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp canslim.example.yaml canslim.yaml
# Edit canslim.yaml: paste your FMP free-tier API key under providers.fmp.api_key,
# or export FMP_API_KEY in your shell.

canslim check-providers
canslim scan --config canslim.yaml --universe sp500 --dry-run
canslim scan --config canslim.yaml --universe sp500
```

Reports land in `out/runs/<YYYY-MM-DD>/report.md`.

## Architecture

- `canslim/providers/` — `DataProvider` ABC plus `yfinance` and `fmp` implementations. Parquet-backed cache with per-kind TTL.
- `canslim/universe/` — loaders for `sp500`, `us_all` (NASDAQ + NYSE listings), `custom` (tickers.txt).
- `canslim/criteria/` — one module per CANSLIM letter. Registered via `pyproject.toml` entry points; third-party packages can ship more.
- `canslim/scanner.py` — async orchestrator with pre-filter, shared feature bundles, concurrency + backoff.
- `canslim/report.py` — markdown + parquet writers.

See `canslim.example.yaml` for configurable thresholds.
