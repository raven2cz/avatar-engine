"""Dynamic model discovery via web scraping of provider documentation.

Public API::

    from avatar_engine.web.model_discovery import fetch_models, invalidate_cache

    # Fetch models (cached 24h)
    result = await fetch_models()
    # {"claude": {"models": [...], ...}, "gemini": {...}, ...}

    # Force refresh
    invalidate_cache()
    result = await fetch_models()

Sources:
  - Claude:  https://platform.claude.com/docs/en/about-claude/models/overview
  - Gemini:  https://ai.google.dev/gemini-api/docs/models
  - Codex:   https://developers.openai.com/codex/models/
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from .base import ModelParser, ParseResult
from .cache import ModelCache
from .registry import ParserRegistry, create_default_registry

__all__ = [
    "fetch_models",
    "invalidate_cache",
    "get_registry",
    "ModelParser",
    "ParseResult",
    "ParserRegistry",
    "ModelCache",
]

_registry = create_default_registry()
_cache = ModelCache(ttl=86400)


async def fetch_models(providers: list[str] | None = None) -> dict[str, Any]:
    """Fetch models from documentation pages.

    Returns JSON-serializable dict with model lists per provider.
    Errors are included in the response (not raised) so partial
    success is possible.
    """
    cached = _cache.get()
    if cached:
        return _serialize(cached.results, cached.errors, cached.fetched_at)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        results, errors = await _registry.fetch_all(client, providers)

    ts = datetime.now(timezone.utc).isoformat()
    if results:
        _cache.set(results, errors, ts)

    return _serialize(results, errors, ts)


def invalidate_cache() -> None:
    """Force cache invalidation for next fetch."""
    _cache.invalidate()


def get_registry() -> ParserRegistry:
    """Access the parser registry (for testing or extension)."""
    return _registry


def _serialize(
    results: dict[str, ParseResult],
    errors: dict[str, str],
    fetched_at: str,
) -> dict[str, Any]:
    """Convert ParseResults to JSON-serializable dict."""
    data: dict[str, Any] = {}

    for pid, result in results.items():
        data[pid] = {
            "models": result.models,
            "defaultModel": result.default_model,
            "source": result.source_url,
        }
        if result.legacy_models:
            data[pid]["legacyModels"] = result.legacy_models

    if errors:
        data["errors"] = errors

    data["fetched_at"] = fetched_at
    return data
