"""Parser registry — factory + discovery.

Usage::

    registry = ParserRegistry()
    registry.register(ClaudeModelParser())

    parser = registry.get("claude")
    result = await parser.fetch_and_parse(client)

    # Or fetch all at once:
    results, errors = await registry.fetch_all(client)
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .base import ModelParser, ParseResult

logger = logging.getLogger(__name__)


class ParserRegistry:
    """Registry of model parsers keyed by provider_id."""

    def __init__(self) -> None:
        self._parsers: dict[str, ModelParser] = {}

    def register(self, parser: ModelParser) -> None:
        self._parsers[parser.provider_id] = parser

    def get(self, provider_id: str) -> ModelParser | None:
        return self._parsers.get(provider_id)

    @property
    def providers(self) -> list[str]:
        return list(self._parsers.keys())

    async def fetch_all(
        self,
        client: httpx.AsyncClient,
        providers: list[str] | None = None,
    ) -> tuple[dict[str, ParseResult], dict[str, str]]:
        """Fetch models from all (or selected) parsers concurrently.

        Returns (results, errors) tuple.  Errors contain human-readable
        messages suitable for display in the avatar UI.
        """
        results: dict[str, ParseResult] = {}
        errors: dict[str, str] = {}
        targets = providers or list(self._parsers.keys())

        async def _fetch_one(pid: str) -> None:
            parser = self._parsers.get(pid)
            if parser is None:
                return
            try:
                results[pid] = await parser.fetch_and_parse(client)
            except Exception as e:
                msg = f"Model discovery failed for {pid}: {e}"
                logger.warning(msg)
                errors[pid] = str(e)

        await asyncio.gather(*[_fetch_one(pid) for pid in targets])
        return results, errors


def create_default_registry() -> ParserRegistry:
    """Create registry with all built-in provider parsers."""
    from .claude_parser import ClaudeModelParser
    from .codex_parser import CodexModelParser
    from .gemini_parser import GeminiModelParser

    registry = ParserRegistry()
    registry.register(ClaudeModelParser())
    registry.register(GeminiModelParser())
    registry.register(CodexModelParser())
    return registry
