"""Claude model parser — scrapes platform.claude.com docs.

Expected page structure:
  - HTML tables with "Claude API alias" and "Claude API ID" columns
  - Current models in "Latest models comparison" section
  - Legacy models in "Legacy models" section
  - Model IDs match: claude-{tier}-{major}-{minor}[-datestring]
"""

from __future__ import annotations

import re

from .base import ModelParser, ParseResult

# Matches: claude-opus-4-6, claude-sonnet-4-5-20250929, etc.
# Requires at least tier + major + minor (3 parts after 'claude-')
_MODEL_PATTERN = re.compile(r"\bclaude-(?:opus|sonnet|haiku)-\d+-[\w.-]+")

# Bedrock/Vertex suffixes to exclude
_PLATFORM_SUFFIX = re.compile(r"-v\d+(?::.*)?$")

# Date suffix indicates a pinned snapshot, not an alias
_DATE_SUFFIX = re.compile(r"-\d{8}")


class ClaudeModelParser(ModelParser):
    """Parser for Claude model documentation."""

    @property
    def provider_id(self) -> str:
        return "claude"

    @property
    def source_url(self) -> str:
        return "https://platform.claude.com/docs/en/about-claude/models/overview"

    def parse(self, html: str) -> ParseResult:
        raw = set(_MODEL_PATTERN.findall(html))

        # Filter out Bedrock IDs (ending in -v1, -v1:0)
        clean = {m for m in raw if not _PLATFORM_SUFFIX.search(m)}

        # Separate aliases (no date) from dated snapshots
        aliases = sorted(
            [m for m in clean if not _DATE_SUFFIX.search(m)],
            key=_sort_key,
        )

        # Determine current vs legacy based on version numbers
        # Current = highest version per tier
        current, legacy = _split_current_legacy(aliases)

        return ParseResult(
            provider="claude",
            models=current,
            default_model=current[0] if current else None,
            source_url=self.source_url,
            legacy_models=legacy,
        )


def _split_current_legacy(aliases: list[str]) -> tuple[list[str], list[str]]:
    """Split aliases into current (latest per tier) and legacy."""
    # Group by tier
    tiers: dict[str, list[str]] = {}
    for m in aliases:
        parts = m.split("-")
        tier = parts[1] if len(parts) > 1 else "unknown"
        tiers.setdefault(tier, []).append(m)

    current: list[str] = []
    legacy: list[str] = []

    for tier, models in tiers.items():
        # Sort by version descending
        models.sort(key=_sort_key)
        if models:
            current.append(models[0])
            legacy.extend(models[1:])

    # Re-sort both lists
    current.sort(key=_sort_key)
    legacy.sort(key=_sort_key)
    return current, legacy


def _sort_key(model: str) -> tuple:
    """Sort: opus first, then sonnet, then haiku. Higher version first."""
    tier_order = {"opus": 0, "sonnet": 1, "haiku": 2}
    parts = model.split("-")
    tier = parts[1] if len(parts) > 1 else ""
    version = _version_num(parts[2:]) if len(parts) > 2 else 0.0
    return (tier_order.get(tier, 9), -version, model)


def _version_num(parts: list[str]) -> float:
    """Extract numeric version from parts like ['4', '6'] → 4.6."""
    nums = []
    for p in parts:
        try:
            nums.append(p)
        except ValueError:
            break
    try:
        return float(".".join(nums[:2]))
    except (ValueError, IndexError):
        return 0.0
