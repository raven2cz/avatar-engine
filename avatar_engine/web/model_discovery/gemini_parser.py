"""Gemini model parser — scrapes ai.google.dev docs.

Expected page structure:
  - Model cards/sections with model identifiers
  - Model IDs use dotted versions: gemini-2.5-flash, gemini-3.1-pro-preview
  - Many non-chat models to filter: TTS, image, audio, embeddings, etc.

Note: Page also contains hyphenated URL variants (gemini-2-5-flash).
      We prefer dotted versions as those are the canonical API model IDs.
"""

from __future__ import annotations

import re

from .base import ModelParser, ParseResult

# Matches dotted versions: gemini-2.5-flash, gemini-3.1-pro-preview
# Does NOT match hyphenated URL slugs: gemini-2-5-flash
_MODEL_PATTERN = re.compile(r"\bgemini-\d+(?:\.\d+)?-[\w-]+")

# Non-chat model patterns to exclude
_EXCLUDE = re.compile(
    r"(?:"
    r"tts|"
    r"image|"
    r"audio|"
    r"embedding|"
    r"computer-use|"
    r"deprecated|"
    r"live-preview|"
    r"robotics|"
    r"native-audio"
    r")",
    re.IGNORECASE,
)


class GeminiModelParser(ModelParser):
    """Parser for Gemini model documentation."""

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def source_url(self) -> str:
        return "https://ai.google.dev/gemini-api/docs/models"

    def parse(self, html: str) -> ParseResult:
        raw = set(_MODEL_PATTERN.findall(html))

        # Filter: only dotted versions, exclude non-chat models
        models = sorted(
            [m for m in raw if not _EXCLUDE.search(m) and "." in m],
            key=_sort_key,
        )

        return ParseResult(
            provider="gemini",
            models=models,
            default_model=models[0] if models else None,
            source_url=self.source_url,
        )


def _sort_key(model: str) -> tuple:
    """Sort: highest version first, pro before flash, shorter names first."""
    # Extract version number (e.g., 3.1, 2.5, 2.0)
    ver_match = re.search(r"(\d+\.\d+)", model)
    ver = float(ver_match.group(1)) if ver_match else 0.0

    # Tier: pro < flash < flash-lite (pro should come first)
    if "pro" in model:
        tier = 0
    elif "flash-lite" in model:
        tier = 2
    elif "flash" in model:
        tier = 1
    else:
        tier = 3

    # Prefer shorter names (less preview/variant suffixes)
    return (-ver, tier, len(model), model)
