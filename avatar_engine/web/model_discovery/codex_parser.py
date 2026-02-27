"""Codex/OpenAI model parser — scrapes developers.openai.com docs.

Expected page structure:
  - Model names/IDs in text content
  - Model IDs match: gpt-{version}[-variant]
  - Page may contain image filenames (gpt-5.3-codex.jpg) — must be excluded
"""

from __future__ import annotations

import re

from .base import ModelParser, ParseResult

# Matches: gpt-5.3-codex, gpt-5.1, gpt-5-codex-mini, etc.
_MODEL_PATTERN = re.compile(r"\bgpt-[\d.]+-[\w-]+|\bgpt-[\d.]+")

# File extensions and trailing dots to strip
_FILE_EXT = re.compile(r"\.(jpg|jpeg|png|gif|svg|webp|pdf)$", re.IGNORECASE)
_TRAILING_DOT = re.compile(r"\.+$")


class CodexModelParser(ModelParser):
    """Parser for Codex/OpenAI model documentation."""

    @property
    def provider_id(self) -> str:
        return "codex"

    @property
    def source_url(self) -> str:
        return "https://developers.openai.com/codex/models/"

    def parse(self, html: str) -> ParseResult:
        raw = set(_MODEL_PATTERN.findall(html))

        # Clean: remove file extensions, trailing dots
        cleaned: set[str] = set()
        for m in raw:
            if _FILE_EXT.search(m):
                continue
            m = _TRAILING_DOT.sub("", m)
            if m:
                cleaned.add(m)

        models = sorted(cleaned, key=_sort_key)

        return ParseResult(
            provider="codex",
            models=models,
            default_model=models[0] if models else None,
            source_url=self.source_url,
        )


def _sort_key(model: str) -> tuple:
    """Sort: highest version first, codex variants before base."""
    # Extract version (e.g., 5.3, 5.1, 5)
    ver_match = re.search(r"(\d+(?:\.\d+)?)", model)
    ver = float(ver_match.group(1)) if ver_match else 0.0

    # Codex-specific variants first, then base models
    has_codex = 0 if "codex" in model else 1

    # spark/mini at the end
    is_light = 1 if ("spark" in model or "mini" in model) else 0

    return (-ver, has_codex, is_light, model)
