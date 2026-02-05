"""Tests for avatar_engine.utils.rate_limit module."""

import asyncio
import time
import pytest
from avatar_engine.utils.rate_limit import RateLimiter, RateLimiterSync, RateLimitConfig


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        cfg = RateLimitConfig()
        assert cfg.requests_per_minute == 60
        assert cfg.burst == 10
        assert cfg.enabled is True

    def test_custom_values(self):
        """Should accept custom values."""
        cfg = RateLimitConfig(requests_per_minute=30, burst=5, enabled=False)
        assert cfg.requests_per_minute == 30
        assert cfg.burst == 5
        assert cfg.enabled is False


class TestRateLimiter:
    """Tests for RateLimiter async class."""

    @pytest.mark.asyncio
    async def test_disabled_returns_immediately(self):
        """When disabled, acquire should return 0 immediately."""
        limiter = RateLimiter(enabled=False)
        start = time.monotonic()
        wait = await limiter.acquire()
        elapsed = time.monotonic() - start
        assert wait == 0.0
        assert elapsed < 0.01

    @pytest.mark.asyncio
    async def test_burst_capacity(self):
        """Should allow burst requests without waiting."""
        limiter = RateLimiter(requests_per_minute=60, burst=3)
        waits = []
        for _ in range(3):
            wait = await limiter.acquire()
            waits.append(wait)
        # All burst requests should be immediate
        assert all(w == 0.0 for w in waits)

    @pytest.mark.asyncio
    async def test_throttles_after_burst(self):
        """Should throttle after burst capacity is exhausted."""
        limiter = RateLimiter(requests_per_minute=600, burst=2)
        # Use burst capacity
        await limiter.acquire()
        await limiter.acquire()
        # Next request should wait
        start = time.monotonic()
        wait = await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should have waited some time (at least 0.05s at 600 rpm)
        assert wait > 0.0
        assert elapsed >= wait * 0.9  # Allow 10% tolerance

    def test_try_acquire_returns_true_with_tokens(self):
        """try_acquire should return True when tokens available."""
        limiter = RateLimiter(burst=5)
        assert limiter.try_acquire() is True

    def test_try_acquire_returns_false_without_tokens(self):
        """try_acquire should return False when no tokens."""
        limiter = RateLimiter(requests_per_minute=600, burst=1)
        limiter.try_acquire()  # Use the one token
        assert limiter.try_acquire() is False

    def test_get_stats(self):
        """Should return statistics."""
        limiter = RateLimiter(burst=5)
        limiter.try_acquire()
        limiter.try_acquire()
        stats = limiter.get_stats()
        assert stats["total_requests"] == 2
        assert stats["enabled"] is True
        assert "available_tokens" in stats

    def test_reset(self):
        """reset should restore initial state."""
        limiter = RateLimiter(burst=5)
        limiter.try_acquire()
        limiter.try_acquire()
        limiter.reset()
        stats = limiter.get_stats()
        assert stats["total_requests"] == 0
        assert stats["available_tokens"] == 5.0

    def test_set_enabled(self):
        """Should be able to enable/disable."""
        limiter = RateLimiter(enabled=True)
        assert limiter.is_enabled is True
        limiter.set_enabled(False)
        assert limiter.is_enabled is False

    def test_properties(self):
        """Should expose configuration via properties."""
        limiter = RateLimiter(requests_per_minute=30, burst=5, enabled=True)
        assert limiter.requests_per_minute == 30
        assert limiter.burst == 5
        assert limiter.is_enabled is True


class TestRateLimiterSync:
    """Tests for RateLimiterSync class."""

    def test_disabled_returns_immediately(self):
        """When disabled, acquire should return 0 immediately."""
        limiter = RateLimiterSync(enabled=False)
        wait = limiter.acquire()
        assert wait == 0.0

    def test_burst_capacity(self):
        """Should allow burst requests without waiting."""
        limiter = RateLimiterSync(requests_per_minute=60, burst=3)
        for _ in range(3):
            wait = limiter.acquire()
            assert wait == 0.0

    def test_try_acquire(self):
        """try_acquire should work for sync limiter."""
        limiter = RateLimiterSync(burst=2)
        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is True
        # Burst exhausted
        assert limiter.try_acquire() is False


class TestRateLimiterConcurrency:
    """Tests for concurrent access to rate limiter."""

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """Should handle concurrent acquire calls safely."""
        limiter = RateLimiter(requests_per_minute=600, burst=5)

        async def make_request(i):
            await limiter.acquire()
            return i

        # Run 10 concurrent requests
        tasks = [make_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        stats = limiter.get_stats()
        assert stats["total_requests"] == 10
