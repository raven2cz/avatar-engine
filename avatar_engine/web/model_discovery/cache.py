"""In-memory cache with TTL for parsed model results."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .base import ParseResult


@dataclass
class CacheEntry:
    results: dict[str, ParseResult]
    errors: dict[str, str]
    timestamp: float
    fetched_at: str = ""


class ModelCache:
    """Thread-safe in-memory cache with configurable TTL."""

    def __init__(self, ttl: int = 86400) -> None:
        self._ttl = ttl
        self._entry: CacheEntry | None = None

    def get(self) -> CacheEntry | None:
        if self._entry and (time.time() - self._entry.timestamp) < self._ttl:
            return self._entry
        return None

    def set(
        self,
        results: dict[str, ParseResult],
        errors: dict[str, str],
        fetched_at: str = "",
    ) -> None:
        self._entry = CacheEntry(
            results=results,
            errors=errors,
            timestamp=time.time(),
            fetched_at=fetched_at,
        )

    def invalidate(self) -> None:
        self._entry = None
