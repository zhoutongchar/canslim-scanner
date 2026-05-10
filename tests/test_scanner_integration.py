from __future__ import annotations

import asyncio

import pytest

from canslim.config import ProviderConfig, Settings
from canslim.scanner import Scanner


@pytest.mark.slow
def test_scan_small_set_live(tmp_path):
    """Live integration test against yfinance. FMP disabled — we expect fallbacks to kick in.

    Run with: pytest -q -m slow
    """
    settings = Settings(
        providers={
            "yfinance": ProviderConfig(enabled=True, concurrency=4),
            "fmp": ProviderConfig(enabled=False),
        },
    )
    settings.cache.root = str(tmp_path / "cache")
    settings.scanner.out_dir = str(tmp_path / "out")

    scanner = Scanner(settings)
    try:
        tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
        results, manifest = asyncio.run(scanner.scan(tickers, dry_run=False))
    finally:
        asyncio.run(scanner.close())

    assert manifest.universe_size == 5
    assert manifest.candidates_after_prefilter >= 1
    assert len(results) >= 5
    # should have at least one scanned result; individual pass/fail is market-dependent
    scanned = [r for r in results if r.status == "scanned"]
    assert len(scanned) >= 1
