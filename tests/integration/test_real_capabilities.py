"""
Real integration tests for Phase 6: Diagnostics, ToolPolicy, ProviderCapabilities.

Tests that capabilities are correctly reported by real provider bridges
and that diagnostic events surface from stderr.

Run with: pytest tests/integration/test_real_capabilities.py -v
"""

import pytest

from avatar_engine import AvatarEngine
from avatar_engine.events import DiagnosticEvent
from avatar_engine.types import ProviderCapabilities


# =============================================================================
# Provider Capabilities — Gemini
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiCapabilities:
    """Test that Gemini bridge reports correct capabilities."""

    @pytest.mark.asyncio
    async def test_capabilities_after_start(self, skip_if_no_gemini):
        engine = AvatarEngine(provider="gemini", timeout=60)
        try:
            await engine.start()
            caps = engine.capabilities
            assert isinstance(caps, ProviderCapabilities)
            assert caps.thinking_supported is True
            assert caps.system_prompt_method == "injected"
            assert caps.streaming is True
            assert caps.mcp_supported is True
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_diagnostic_events_from_stderr(self, skip_if_no_gemini):
        """Gemini may emit stderr lines — they should surface as DiagnosticEvent."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        diagnostics = []

        @engine.on(DiagnosticEvent)
        def on_diag(e):
            diagnostics.append(e)

        try:
            await engine.start()
            # Just do a simple chat — stderr may or may not produce output
            response = await engine.chat("Hi")
            assert response.success is True
            # We can't guarantee stderr output, but handler should not crash
            # If there are diagnostics, verify structure
            for d in diagnostics:
                assert d.message != ""
                assert d.level in ("info", "warning", "error", "debug")
                assert d.source == "stderr"
        finally:
            await engine.stop()


# =============================================================================
# Provider Capabilities — Claude
# =============================================================================


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.slow
class TestClaudeCapabilities:
    """Test that Claude bridge reports correct capabilities."""

    @pytest.mark.asyncio
    async def test_capabilities_after_start(self, skip_if_no_claude):
        engine = AvatarEngine(provider="claude", timeout=120)
        try:
            await engine.start()
            caps = engine.capabilities
            assert isinstance(caps, ProviderCapabilities)
            assert caps.cost_tracking is True
            assert caps.budget_enforcement is True
            assert caps.system_prompt_method == "native"
            assert caps.streaming is True
            assert caps.mcp_supported is True
        finally:
            await engine.stop()


# =============================================================================
# Provider Capabilities — Codex
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestCodexCapabilities:
    """Test that Codex bridge reports correct capabilities."""

    @pytest.mark.asyncio
    async def test_capabilities_after_start(self, skip_if_no_codex_acp):
        engine = AvatarEngine(provider="codex", timeout=120)
        try:
            await engine.start()
            caps = engine.capabilities
            assert isinstance(caps, ProviderCapabilities)
            assert caps.thinking_supported is True
            assert caps.system_prompt_method == "injected"
            assert caps.streaming is True
            assert caps.mcp_supported is True
        finally:
            await engine.stop()
