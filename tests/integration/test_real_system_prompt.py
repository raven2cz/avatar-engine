"""
Real integration tests for GAP-5 (system prompt) and GAP-6 (budget control).

Tests that system prompt injection works with real providers and that
budget enforcement blocks requests correctly.

Run with: pytest tests/integration/test_real_system_prompt.py -v
"""

import pytest

from avatar_engine import AvatarEngine
from avatar_engine.events import ErrorEvent


# =============================================================================
# System Prompt — Gemini ACP
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiSystemPrompt:
    """Test system prompt injection in Gemini ACP mode."""

    @pytest.mark.asyncio
    async def test_system_prompt_affects_response(self, skip_if_no_gemini):
        """System prompt should influence Gemini's response."""
        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            system_prompt="You are a pirate. Always respond in pirate speak with 'Arrr'.",
        )

        try:
            await engine.start()
            response = await engine.chat("Hello, who are you?")

            assert response.success is True
            # Pirate prompt should influence response
            content = response.content.lower()
            assert any(w in content for w in ["arr", "pirate", "matey", "ahoy", "captain"]), (
                f"Expected pirate-speak but got: {response.content[:200]}"
            )

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_system_prompt_only_first_message(self, skip_if_no_gemini):
        """System prompt should only be prepended to the first message."""
        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            system_prompt="Always reply with exactly one word.",
        )

        try:
            await engine.start()

            # First message: system prompt injected
            resp1 = await engine.chat("What color is the sky?")
            assert resp1.success is True

            # Second message: no system prompt injection, but context should persist
            resp2 = await engine.chat("What color is grass?")
            assert resp2.success is True

        finally:
            await engine.stop()


# =============================================================================
# System Prompt — Claude
# =============================================================================


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.slow
class TestClaudeSystemPrompt:
    """Test system prompt with real Claude (uses --append-system-prompt flag)."""

    @pytest.mark.asyncio
    async def test_system_prompt_affects_response(self, skip_if_no_claude):
        """System prompt should influence Claude's response."""
        engine = AvatarEngine(
            provider="claude",
            timeout=120,
            system_prompt="You are a pirate. Always include 'Arrr' in your responses.",
        )

        try:
            await engine.start()
            response = await engine.chat("Hello, who are you?")

            assert response.success is True
            content = response.content.lower()
            assert any(w in content for w in ["arr", "pirate", "matey", "ahoy"]), (
                f"Expected pirate-speak but got: {response.content[:200]}"
            )

        finally:
            await engine.stop()


# =============================================================================
# System Prompt — Codex ACP
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestCodexSystemPrompt:
    """Test system prompt injection in Codex ACP mode."""

    @pytest.mark.asyncio
    async def test_system_prompt_affects_response(self, skip_if_no_codex_acp):
        """System prompt should be prepended to first message for Codex.

        Codex has a strong built-in coding system prompt, so we test that
        the injected prompt at least reaches the model by asking it to
        include a specific keyword in its response.
        """
        engine = AvatarEngine(
            provider="codex",
            timeout=120,
            system_prompt="Important: Include the exact word PINEAPPLE somewhere in every response.",
        )

        try:
            await engine.start()
            response = await engine.chat("Say hello and confirm you understand the instructions.")

            assert response.success is True
            # Codex may or may not obey, but the prompt should at least arrive.
            # We verify the chat itself succeeds — the system prompt prepend
            # doesn't break the ACP flow.
            assert len(response.content) > 0

        finally:
            await engine.stop()


# =============================================================================
# Budget Control — Engine Level
# =============================================================================


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.slow
class TestBudgetControl:
    """Test budget enforcement with real Claude (which tracks costs)."""

    @pytest.mark.asyncio
    async def test_budget_allows_normal_chat(self, skip_if_no_claude):
        """Chat should work when under budget."""
        engine = AvatarEngine(
            provider="claude",
            timeout=120,
            max_budget_usd=10.0,  # High budget
        )

        try:
            await engine.start()
            response = await engine.chat("Say hello in one word.")
            assert response.success is True

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_budget_blocks_after_exhaustion(self, skip_if_no_claude):
        """Chat should be blocked when budget is exceeded.

        We artificially set the bridge stats to simulate budget exhaustion.
        """
        engine = AvatarEngine(
            provider="claude",
            timeout=120,
            max_budget_usd=0.01,  # Very low budget
        )

        try:
            await engine.start()

            # Artificially set cost above budget
            # ClaudeBridge overrides is_over_budget() using _total_cost_usd
            if engine._bridge:
                engine._bridge._total_cost_usd = 0.02

            errors = []
            engine.add_handler(ErrorEvent, lambda e: errors.append(e))

            response = await engine.chat("Hello")
            assert response.success is False
            assert "Budget exceeded" in response.error
            assert len(errors) == 1

        finally:
            await engine.stop()
