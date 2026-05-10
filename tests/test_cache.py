from __future__ import annotations

import pandas as pd

from canslim.providers.cache import CacheStore


def test_df_roundtrip(tmp_path):
    c = CacheStore(tmp_path)
    df = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    c.write_df("prices", "yfinance", "AAPL", df)

    out = c.read_df("prices", "yfinance", "AAPL")
    assert out is not None
    assert list(out["close"]) == [1.0, 2.0]
    assert "fetched_at" in out.columns


def test_freshness(tmp_path):
    c = CacheStore(tmp_path)
    c.write_df("prices", "yfinance", "AAPL", pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2026-01-01"])))
    assert c.is_fresh("prices", "yfinance", "AAPL", ttl_hours=1.0)
    assert not c.is_fresh("prices", "yfinance", "AAPL", ttl_hours=0.0)


def test_json_roundtrip(tmp_path):
    c = CacheStore(tmp_path)
    c.write_json("info", "yfinance", "AAPL", {"float_shares": 1_000_000.0})
    data = c.read_json("info", "yfinance", "AAPL")
    assert data is not None
    assert data["float_shares"] == 1_000_000.0


def test_budget_meta(tmp_path):
    c = CacheStore(tmp_path)
    assert c.read_meta("fmp_budget") == {}
    c.write_meta("fmp_budget", {"date": "2026-04-20", "used": 7})
    assert c.read_meta("fmp_budget")["used"] == 7


def test_negative_cache_roundtrip(tmp_path):
    c = CacheStore(tmp_path)
    assert c.read_failure("prices", "yfinance", "ZZZ") is None
    c.record_failure("prices", "yfinance", "ZZZ", "404 from upstream")
    rec = c.read_failure("prices", "yfinance", "ZZZ")
    assert rec is not None
    assert rec["error"] == "404 from upstream"
    assert rec["retry_count"] == 1
    # recording again bumps retry_count and refreshes last_seen
    c.record_failure("prices", "yfinance", "ZZZ", "404 again")
    rec2 = c.read_failure("prices", "yfinance", "ZZZ")
    assert rec2["retry_count"] == 2
    # fresh within a wide TTL
    assert c.is_failure_fresh("prices", "yfinance", "ZZZ", ttl_hours=24.0)
    # not fresh within a zero TTL
    assert not c.is_failure_fresh("prices", "yfinance", "ZZZ", ttl_hours=0.0)
    c.clear_failure("prices", "yfinance", "ZZZ")
    assert c.read_failure("prices", "yfinance", "ZZZ") is None


def test_list_failures(tmp_path):
    c = CacheStore(tmp_path)
    c.record_failure("prices", "yfinance", "AAA", "x")
    c.record_failure("fundamentals", "fmp", "BBB", "y")
    found = c.list_failures()
    assert len(found) == 2
    tickers = {f["ticker"] for f in found}
    assert tickers == {"AAA", "BBB"}
