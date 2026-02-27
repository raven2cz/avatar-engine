"""Live canary tests — fetch real documentation pages and verify parsing.

Run with: uv run pytest tests/test_model_discovery_live.py -v

These tests hit real URLs. When they FAIL, it means the documentation
page structure changed and the corresponding parser needs updating.

NOT included in default test run — use explicitly or via CI scheduled job.
"""

from __future__ import annotations

import httpx
import pytest

from avatar_engine.web.model_discovery import fetch_models, invalidate_cache
from avatar_engine.web.model_discovery.claude_parser import ClaudeModelParser
from avatar_engine.web.model_discovery.codex_parser import CodexModelParser
from avatar_engine.web.model_discovery.gemini_parser import GeminiModelParser


@pytest.mark.live
@pytest.mark.asyncio
class TestClaudeParserLive:
    async def test_fetch_and_parse_real_page(self) -> None:
        parser = ClaudeModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)

        assert len(result.models) >= 2, f"Expected ≥2 current models, got: {result.models}"
        assert result.default_model is not None
        assert all(m.startswith("claude-") for m in result.models)
        # Every model should have tier + version
        for m in result.models:
            parts = m.split("-")
            assert len(parts) >= 4, f"Model ID too short: {m}"
            assert parts[1] in ("opus", "sonnet", "haiku"), f"Unknown tier in: {m}"

    async def test_no_dated_ids_in_current(self) -> None:
        parser = ClaudeModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)

        for m in result.models:
            assert not any(c.isdigit() and len(c) == 8 for c in m.split("-")), \
                f"Dated ID in current models: {m}"


@pytest.mark.live
@pytest.mark.asyncio
class TestGeminiParserLive:
    async def test_fetch_and_parse_real_page(self) -> None:
        parser = GeminiModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)

        assert len(result.models) >= 3, f"Expected ≥3 models, got: {result.models}"
        assert all(m.startswith("gemini-") for m in result.models)

    async def test_no_non_chat_models(self) -> None:
        parser = GeminiModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)

        blacklist = ["embedding", "tts", "audio", "computer-use", "robotics"]
        for m in result.models:
            for term in blacklist:
                assert term not in m, f"Non-chat model leaked through: {m}"

    async def test_all_have_dotted_version(self) -> None:
        parser = GeminiModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)

        for m in result.models:
            assert "." in m, f"Model without dotted version: {m}"


@pytest.mark.live
@pytest.mark.asyncio
class TestCodexParserLive:
    async def test_fetch_and_parse_real_page(self) -> None:
        parser = CodexModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)

        assert len(result.models) >= 2, f"Expected ≥2 models, got: {result.models}"
        assert all(m.startswith("gpt-") for m in result.models)

    async def test_no_file_extensions(self) -> None:
        parser = CodexModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)

        for m in result.models:
            assert not m.endswith((".jpg", ".png", ".gif", ".")), \
                f"File artifact in models: {m}"


@pytest.mark.live
@pytest.mark.asyncio
class TestFullDiscoveryLive:
    async def test_fetch_all_providers(self) -> None:
        """End-to-end: all three providers return valid models."""
        invalidate_cache()
        result = await fetch_models()

        for provider in ["claude", "gemini", "codex"]:
            assert provider in result, f"Missing provider: {provider}"
            assert len(result[provider]["models"]) >= 2, \
                f"{provider}: too few models: {result[provider]['models']}"
            assert result[provider]["defaultModel"] is not None, \
                f"{provider}: no default model"

        assert "fetched_at" in result

    async def test_no_errors_when_all_pages_up(self) -> None:
        """When all pages are accessible, no errors expected."""
        invalidate_cache()
        result = await fetch_models()

        if "errors" in result:
            pytest.fail(
                f"Discovery errors (page structure may have changed): {result['errors']}"
            )

    async def test_cache_works(self) -> None:
        """Second call should use cache (no HTTP)."""
        invalidate_cache()
        result1 = await fetch_models()
        result2 = await fetch_models()
        # Same fetched_at = came from cache
        assert result1["fetched_at"] == result2["fetched_at"]
