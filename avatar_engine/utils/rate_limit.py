"""
Rate limiting utilities for Avatar Engine.

Provides protection against API rate limits.
"""

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Optional


def _validate_rate_limit_params(requests_per_minute: int, burst: int) -> None:
    """Validate rate limiter numeric parameters."""
    if requests_per_minute <= 0:
        raise ValueError("requests_per_minute must be greater than 0")
    if burst <= 0:
        raise ValueError("burst must be greater than 0")


@dataclass
class RateLimitConfig:
    """
    Rate limit configuration.

    Attributes:
        requests_per_minute: Maximum requests allowed per minute
        burst: Allow burst of requests (up to this many) before throttling
        enabled: Whether rate limiting is active
    """

    requests_per_minute: int = 60
    burst: int = 10
    enabled: bool = True

    def __post_init__(self) -> None:
        _validate_rate_limit_params(
            requests_per_minute=self.requests_per_minute,
            burst=self.burst,
        )


class RateLimiter:
    """
    Async rate limiter using token bucket algorithm.

    Usage:
        limiter = RateLimiter(requests_per_minute=60)
        await limiter.acquire()  # Will wait if rate limit exceeded
        # ... make API call ...

    Thread-safe for asyncio concurrent access.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst: int = 10,
        enabled: bool = True,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Max requests per minute
            burst: Max burst size (instant requests allowed)
            enabled: Whether limiting is active
        """
        _validate_rate_limit_params(
            requests_per_minute=requests_per_minute,
            burst=burst,
        )
        self._rpm = requests_per_minute
        self._burst = burst
        self._enabled = enabled

        # Token bucket state
        self._tokens = float(burst)  # Start with full burst capacity
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

        # Stats
        self._total_requests = 0
        self._total_wait_time = 0.0
        self._throttled_count = 0

    @property
    def is_enabled(self) -> bool:
        """Check if rate limiting is enabled."""
        return self._enabled

    @property
    def requests_per_minute(self) -> int:
        """Get configured requests per minute."""
        return self._rpm

    @property
    def burst(self) -> int:
        """Get configured burst size."""
        return self._burst

    async def acquire(self) -> float:
        """
        Acquire permission to make a request.

        Returns immediately if tokens are available, otherwise waits
        until a token becomes available.

        Returns:
            Wait time in seconds (0 if no wait was needed)
        """
        if not self._enabled:
            return 0.0

        async with self._lock:
            return await self._acquire_locked()

    async def _acquire_locked(self) -> float:
        """Internal acquire with lock already held."""
        # Refill tokens based on time elapsed
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        # Token refill rate: rpm / 60 = tokens per second
        refill_rate = self._rpm / 60.0
        self._tokens = min(self._burst, self._tokens + elapsed * refill_rate)

        self._total_requests += 1

        if self._tokens >= 1.0:
            # Token available, consume it
            self._tokens -= 1.0
            return 0.0

        # Need to wait for tokens
        wait_time = (1.0 - self._tokens) / refill_rate
        self._throttled_count += 1
        self._total_wait_time += wait_time

        # Release lock while waiting
        self._lock.release()
        try:
            await asyncio.sleep(wait_time)
        finally:
            await self._lock.acquire()

        # Consume token after wait
        self._tokens = 0.0
        self._last_update = time.monotonic()
        return wait_time

    def try_acquire(self) -> bool:
        """
        Try to acquire permission without waiting.

        Returns:
            True if request can proceed, False if rate limited
        """
        if not self._enabled:
            return True

        # Update tokens
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        refill_rate = self._rpm / 60.0
        self._tokens = min(self._burst, self._tokens + elapsed * refill_rate)

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            self._total_requests += 1
            return True

        return False

    def get_stats(self) -> dict:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with:
                - total_requests: Total requests processed
                - throttled_count: Number of requests that were throttled
                - total_wait_time: Total time spent waiting (seconds)
                - available_tokens: Current available tokens
        """
        return {
            "total_requests": self._total_requests,
            "throttled_count": self._throttled_count,
            "total_wait_time": self._total_wait_time,
            "available_tokens": self._tokens,
            "enabled": self._enabled,
        }

    def reset(self) -> None:
        """Reset rate limiter to initial state."""
        self._tokens = float(self._burst)
        self._last_update = time.monotonic()
        self._total_requests = 0
        self._total_wait_time = 0.0
        self._throttled_count = 0

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable rate limiting."""
        self._enabled = enabled


class RateLimiterSync:
    """
    Synchronous rate limiter for non-async code.

    Same token bucket algorithm as RateLimiter but uses
    time.sleep instead of asyncio.sleep.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst: int = 10,
        enabled: bool = True,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Max requests per minute
            burst: Max burst size
            enabled: Whether limiting is active
        """
        _validate_rate_limit_params(
            requests_per_minute=requests_per_minute,
            burst=burst,
        )
        self._rpm = requests_per_minute
        self._burst = burst
        self._enabled = enabled

        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()  # RC-12: thread-safe token bucket

    def acquire(self) -> float:
        """
        Acquire permission to make a request.

        Returns:
            Wait time in seconds (0 if no wait was needed)
        """
        if not self._enabled:
            return 0.0

        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._last_update = now

            refill_rate = self._rpm / 60.0
            self._tokens = min(self._burst, self._tokens + elapsed * refill_rate)

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0

            wait_time = (1.0 - self._tokens) / refill_rate

        # Sleep OUTSIDE lock to avoid blocking other threads
        time.sleep(wait_time)

        with self._lock:
            self._tokens = 0.0
            self._last_update = time.monotonic()
        return wait_time

    def try_acquire(self) -> bool:
        """Try to acquire without waiting."""
        if not self._enabled:
            return True

        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._last_update = now

            refill_rate = self._rpm / 60.0
            self._tokens = min(self._burst, self._tokens + elapsed * refill_rate)

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True

            return False
