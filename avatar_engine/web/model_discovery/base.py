"""Abstract base class for model parsers.

Each parser is responsible for:
1. Fetching its provider's documentation page
2. Extracting model identifiers from HTML
3. Determining which model is the default (most capable)
4. Filtering out non-chat models (embeddings, TTS, image gen, etc.)

To add a new provider parser:
1. Create a new file (e.g., mistral_parser.py)
2. Subclass ModelParser, implement provider_id, source_url, parse()
3. Register in registry.py via create_default_registry()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx


@dataclass
class ParseResult:
    """Result of parsing a provider's model documentation."""

    provider: str
    models: list[str]
    default_model: str | None
    source_url: str
    legacy_models: list[str] = field(default_factory=list)


class ModelParser(ABC):
    """Abstract parser for provider documentation pages."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Provider identifier matching PROVIDERS config (e.g., 'gemini')."""
        ...

    @property
    @abstractmethod
    def source_url(self) -> str:
        """Documentation URL to scrape."""
        ...

    @abstractmethod
    def parse(self, html: str) -> ParseResult:
        """Parse HTML content and extract model identifiers.

        Must return non-empty models list or raise ValueError
        if page structure changed and parsing failed.
        """
        ...

    async def fetch_and_parse(self, client: httpx.AsyncClient) -> ParseResult:
        """Fetch page and parse. Subclasses can override for multi-page scraping."""
        resp = await client.get(self.source_url, headers=self._headers())
        resp.raise_for_status()
        result = self.parse(resp.text)
        if not result.models:
            raise ValueError(
                f"No models parsed from {self.source_url} — "
                f"page structure may have changed, parser needs update"
            )
        return result

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "AvatarEngine/1.2 ModelDiscovery",
            "Accept": "text/html,application/xhtml+xml,*/*",
        }
