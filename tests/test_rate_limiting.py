from __future__ import annotations

import asyncio

from canslim.config import CacheConfig, ProviderConfig
from canslim.providers.cache import CacheStore
from canslim.providers.yfinance_provider import YFinanceProvider


class _Ticker:
    def __init__(self, owner) -> None:
        self.owner = owner

    def get_info(self) -> dict:
        self.owner.calls += 1
        return {
            "floatShares": 123_000_000,
            "sharesOutstanding": 150_000_000,
            "marketCap": 42_000_000_000,
            "heldPercentInstitutions": 0.73,
        }


class _YFinance:
    def __init__(self) -> None:
        self.calls = 0

    def Ticker(self, _ticker: str) -> _Ticker:
        return _Ticker(self)


def test_float_and_institutional_share_one_quote_request(tmp_path):
    provider = YFinanceProvider(
        ProviderConfig(concurrency=8, requests_per_second=10_000),
        CacheConfig(root=str(tmp_path)),
        CacheStore(tmp_path),
    )
    fake = _YFinance()
    provider._yf = fake

    async def run():
        return await asyncio.gather(
            provider.get_shares_float("AAPL"),
            provider.get_institutional("AAPL"),
        )

    shares_float, institutional = asyncio.run(run())

    assert fake.calls == 1
    assert shares_float == 123_000_000
    assert institutional is not None
    assert institutional.inst_own_pct == 0.73


def test_rate_limit_defers_all_quote_requests_before_retry(tmp_path):
    class YFRateLimitError(Exception):
        pass

    class FlakyTicker(_Ticker):
        def get_info(self) -> dict:
            self.owner.calls += 1
            if self.owner.calls == 1:
                raise YFRateLimitError("Too Many Requests")
            return {
                "floatShares": 123_000_000,
                "sharesOutstanding": 150_000_000,
                "marketCap": 42_000_000_000,
                "heldPercentInstitutions": 0.73,
            }

    class FlakyYFinance(_YFinance):
        def Ticker(self, _ticker: str) -> FlakyTicker:
            return FlakyTicker(self)

    class ImmediateLimiter:
        def __init__(self) -> None:
            self.deferrals: list[float] = []

        async def acquire(self) -> None:
            return None

        async def defer(self, seconds: float) -> None:
            self.deferrals.append(seconds)

    provider = YFinanceProvider(
        ProviderConfig(concurrency=8, requests_per_second=10_000, max_retries=2),
        CacheConfig(root=str(tmp_path)),
        CacheStore(tmp_path),
    )
    fake = FlakyYFinance()
    limiter = ImmediateLimiter()
    provider._yf = fake
    provider._quote_rate_limiter = limiter

    result = asyncio.run(provider.get_shares_float("MSFT"))

    assert result == 123_000_000
    assert fake.calls == 2
    assert limiter.deferrals == [15.0]
