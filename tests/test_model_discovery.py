"""Unit tests for model discovery — parsing, registry, cache.

Uses fixture HTML snapshots from tests/fixtures/ for deterministic testing.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from avatar_engine.web.model_discovery.base import ParseResult
from avatar_engine.web.model_discovery.cache import ModelCache
from avatar_engine.web.model_discovery.claude_parser import ClaudeModelParser
from avatar_engine.web.model_discovery.codex_parser import CodexModelParser
from avatar_engine.web.model_discovery.gemini_parser import GeminiModelParser
from avatar_engine.web.model_discovery.registry import (
    ParserRegistry,
    create_default_registry,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def claude_html() -> str:
    return (FIXTURES / "claude_models.html").read_text()


@pytest.fixture
def gemini_html() -> str:
    return (FIXTURES / "gemini_models.html").read_text()


@pytest.fixture
def codex_html() -> str:
    return (FIXTURES / "codex_models.html").read_text()


# ---------------------------------------------------------------------------
# Claude parser
# ---------------------------------------------------------------------------


class TestClaudeParser:
    def test_parse_current_models(self, claude_html: str) -> None:
        result = ClaudeModelParser().parse(claude_html)
        assert "claude-opus-4-6" in result.models
        assert "claude-sonnet-4-6" in result.models
        assert "claude-haiku-4-5" in result.models

    def test_default_is_opus(self, claude_html: str) -> None:
        result = ClaudeModelParser().parse(claude_html)
        assert result.default_model == "claude-opus-4-6"

    def test_separates_legacy(self, claude_html: str) -> None:
        result = ClaudeModelParser().parse(claude_html)
        # Legacy should contain older models
        assert "claude-opus-4-0" in result.legacy_models
        assert "claude-sonnet-4-0" in result.legacy_models
        # Legacy should NOT be in current
        for m in result.legacy_models:
            assert m not in result.models

    def test_excludes_dated_ids(self, claude_html: str) -> None:
        result = ClaudeModelParser().parse(claude_html)
        all_models = result.models + result.legacy_models
        assert not any("20250" in m for m in all_models)

    def test_excludes_bedrock_ids(self, claude_html: str) -> None:
        result = ClaudeModelParser().parse(claude_html)
        all_models = result.models + result.legacy_models
        assert not any(m.endswith("-v1") for m in all_models)

    def test_provider_id(self) -> None:
        assert ClaudeModelParser().provider_id == "claude"

    def test_source_url(self) -> None:
        assert "platform.claude.com" in ClaudeModelParser().source_url

    def test_parse_empty_html_returns_empty(self) -> None:
        result = ClaudeModelParser().parse("<html></html>")
        assert result.models == []
        assert result.default_model is None

    def test_current_has_at_least_two(self, claude_html: str) -> None:
        result = ClaudeModelParser().parse(claude_html)
        assert len(result.models) >= 2


# ---------------------------------------------------------------------------
# Gemini parser
# ---------------------------------------------------------------------------


class TestGeminiParser:
    def test_parse_models(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert len(result.models) >= 3

    def test_excludes_tts(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert not any("tts" in m for m in result.models)

    def test_excludes_image(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        # image as a standalone suffix (gemini-3-pro-image-preview)
        # but allow models where "image" is not the primary function
        for m in result.models:
            assert "image" not in m.split("-")

    def test_excludes_embedding(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert not any("embedding" in m for m in result.models)

    def test_excludes_audio(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert not any("audio" in m for m in result.models)

    def test_excludes_computer_use(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert not any("computer-use" in m for m in result.models)

    def test_all_start_with_gemini(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert all(m.startswith("gemini-") for m in result.models)

    def test_all_have_dotted_version(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert all("." in m for m in result.models)

    def test_sorted_by_version_desc(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        # First model should have highest version
        assert "3.1" in result.models[0] or "3.0" in result.models[0]

    def test_default_is_latest(self, gemini_html: str) -> None:
        result = GeminiModelParser().parse(gemini_html)
        assert result.default_model is not None
        assert "3.1" in result.default_model or "3" in result.default_model

    def test_provider_id(self) -> None:
        assert GeminiModelParser().provider_id == "gemini"

    def test_parse_empty_html_returns_empty(self) -> None:
        result = GeminiModelParser().parse("<html></html>")
        assert result.models == []


# ---------------------------------------------------------------------------
# Codex parser
# ---------------------------------------------------------------------------


class TestCodexParser:
    def test_parse_models(self, codex_html: str) -> None:
        result = CodexModelParser().parse(codex_html)
        assert "gpt-5.3-codex" in result.models
        assert "gpt-5.3-codex-spark" in result.models

    def test_excludes_image_filenames(self, codex_html: str) -> None:
        result = CodexModelParser().parse(codex_html)
        assert not any(m.endswith(".jpg") for m in result.models)
        assert not any(m.endswith(".png") for m in result.models)

    def test_no_trailing_dots(self, codex_html: str) -> None:
        result = CodexModelParser().parse(codex_html)
        assert not any(m.endswith(".") for m in result.models)

    def test_all_start_with_gpt(self, codex_html: str) -> None:
        result = CodexModelParser().parse(codex_html)
        assert all(m.startswith("gpt-") for m in result.models)

    def test_sorted_by_version_desc(self, codex_html: str) -> None:
        result = CodexModelParser().parse(codex_html)
        assert result.models[0].startswith("gpt-5.3")

    def test_default_is_best_codex(self, codex_html: str) -> None:
        result = CodexModelParser().parse(codex_html)
        assert result.default_model == "gpt-5.3-codex"

    def test_provider_id(self) -> None:
        assert CodexModelParser().provider_id == "codex"

    def test_parse_empty_html_returns_empty(self) -> None:
        result = CodexModelParser().parse("<html></html>")
        assert result.models == []


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestParserRegistry:
    def test_register_and_get(self) -> None:
        registry = ParserRegistry()
        parser = ClaudeModelParser()
        registry.register(parser)
        assert registry.get("claude") is parser

    def test_get_unknown_returns_none(self) -> None:
        registry = ParserRegistry()
        assert registry.get("unknown") is None

    def test_providers_list(self) -> None:
        registry = ParserRegistry()
        registry.register(ClaudeModelParser())
        registry.register(GeminiModelParser())
        assert set(registry.providers) == {"claude", "gemini"}

    def test_default_registry_has_all_providers(self) -> None:
        registry = create_default_registry()
        assert set(registry.providers) == {"claude", "gemini", "codex"}

    @pytest.mark.asyncio
    async def test_fetch_all_with_mock_client(self) -> None:
        """Test fetch_all with mocked HTTP responses."""
        registry = ParserRegistry()
        registry.register(ClaudeModelParser())

        # Mock client that returns fixture HTML
        html = (FIXTURES / "claude_models.html").read_text()
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        results, errors = await registry.fetch_all(mock_client)
        assert "claude" in results
        assert len(errors) == 0
        assert len(results["claude"].models) >= 2

    @pytest.mark.asyncio
    async def test_fetch_all_captures_errors(self) -> None:
        """Parser failures are captured in errors dict, not raised."""
        registry = ParserRegistry()
        registry.register(ClaudeModelParser())

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

        results, errors = await registry.fetch_all(mock_client)
        assert len(results) == 0
        assert "claude" in errors
        assert "Connection refused" in errors["claude"]

    @pytest.mark.asyncio
    async def test_fetch_all_filters_providers(self) -> None:
        """Only fetch requested providers."""
        registry = create_default_registry()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("should not be called"))

        # Request only unknown provider — should skip everything
        results, errors = await registry.fetch_all(mock_client, providers=["unknown"])
        assert len(results) == 0
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestModelCache:
    def test_empty_cache_returns_none(self) -> None:
        cache = ModelCache()
        assert cache.get() is None

    def test_set_and_get(self) -> None:
        cache = ModelCache()
        result = ParseResult(
            provider="test", models=["m1"], default_model="m1", source_url="http://x"
        )
        cache.set({"test": result}, {})
        entry = cache.get()
        assert entry is not None
        assert "test" in entry.results

    def test_ttl_expiry(self) -> None:
        cache = ModelCache(ttl=0)  # Expire immediately
        result = ParseResult(
            provider="test", models=["m1"], default_model="m1", source_url="http://x"
        )
        cache.set({"test": result}, {})
        # TTL=0 means it's already expired
        time.sleep(0.01)
        assert cache.get() is None

    def test_invalidate(self) -> None:
        cache = ModelCache()
        result = ParseResult(
            provider="test", models=["m1"], default_model="m1", source_url="http://x"
        )
        cache.set({"test": result}, {})
        cache.invalidate()
        assert cache.get() is None

    def test_stores_errors(self) -> None:
        cache = ModelCache()
        result = ParseResult(
            provider="test", models=["m1"], default_model="m1", source_url="http://x"
        )
        cache.set({"test": result}, {"gemini": "parse failed"})
        entry = cache.get()
        assert entry is not None
        assert entry.errors == {"gemini": "parse failed"}
