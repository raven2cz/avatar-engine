"""
Real chat integration tests.

These tests make actual API calls to Claude and Gemini.
Run with: pytest tests/integration/test_real_chat.py -v

IMPORTANT: These tests consume API credits!
"""

import asyncio
import pytest

from avatar_engine import AvatarEngine
from avatar_engine.events import TextEvent, StateEvent, ErrorEvent
from avatar_engine.bridges.base import BridgeState


# =============================================================================
# Gemini Real Chat Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiRealChat:
    """Real chat tests with Gemini CLI."""

    @pytest.mark.asyncio
    async def test_simple_chat(self, skip_if_no_gemini):
        """Basic chat should work with real Gemini."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        try:
            await engine.start()

            response = await engine.chat("What is 2+2? Reply with just the number.")

            assert response.success is True, f"Chat failed: {response.error}"
            assert response.content is not None
            assert len(response.content) > 0
            # Should contain "4" somewhere
            assert "4" in response.content, f"Expected '4' in response: {response.content}"

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_streaming_chat(self, skip_if_no_gemini):
        """Streaming should yield real chunks."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        try:
            await engine.start()

            chunks = []
            async for chunk in engine.chat_stream("Say hello in exactly 3 words."):
                chunks.append(chunk)

            assert len(chunks) > 0, "No chunks received"
            full_response = "".join(chunks)
            assert len(full_response) > 0, "Empty response"

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, skip_if_no_gemini):
        """Multi-turn conversation should maintain context."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        try:
            await engine.start()

            # First turn - give a name
            resp1 = await engine.chat("My name is TestBot. Remember this.")
            assert resp1.success is True

            # Second turn - ask about the name
            resp2 = await engine.chat("What is my name?")
            assert resp2.success is True
            # Should remember the name
            assert "TestBot" in resp2.content or "testbot" in resp2.content.lower()

            # Verify history
            history = engine.get_history()
            assert len(history) >= 4  # 2 user + 2 assistant

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_events_fire_during_chat(self, skip_if_no_gemini):
        """Events should fire during real chat."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        state_events = []
        text_events = []

        @engine.on(StateEvent)
        def on_state(e):
            state_events.append(e)

        @engine.on(TextEvent)
        def on_text(e):
            text_events.append(e)

        try:
            await engine.start()

            async for _ in engine.chat_stream("Say hello."):
                pass

            # Should have state events
            assert len(state_events) >= 1, "No state events"

            # Should have text events from streaming
            assert len(text_events) >= 1, "No text events"

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_health_check(self, skip_if_no_gemini):
        """Health check should work with real bridge."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        try:
            await engine.start()

            health = engine.get_health()
            assert health.healthy is True
            assert health.provider == "gemini"
            assert health.state == "ready"

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_unicode_content(self, skip_if_no_gemini):
        """Should handle Unicode content."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        try:
            await engine.start()

            response = await engine.chat("Translate 'hello' to Czech. Reply with just the Czech word.")
            assert response.success is True
            # Should contain Czech greeting
            assert "Ahoj" in response.content or "ahoj" in response.content.lower() or "Dobrý" in response.content

        finally:
            await engine.stop()


# =============================================================================
# Claude Real Chat Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.slow
class TestClaudeRealChat:
    """Real chat tests with Claude CLI."""

    @pytest.mark.asyncio
    async def test_simple_chat(self, skip_if_no_claude):
        """Basic chat should work with real Claude."""
        engine = AvatarEngine(provider="claude", timeout=120)

        try:
            await engine.start()

            response = await engine.chat("What is 2+2? Reply with just the number.")

            assert response.success is True, f"Chat failed: {response.error}"
            assert response.content is not None
            assert "4" in response.content

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_streaming_chat(self, skip_if_no_claude):
        """Streaming should yield real chunks."""
        engine = AvatarEngine(provider="claude", timeout=120)

        try:
            await engine.start()

            chunks = []
            async for chunk in engine.chat_stream("Say hello in exactly 3 words."):
                chunks.append(chunk)

            assert len(chunks) > 0, "No chunks received"
            full_response = "".join(chunks)
            assert len(full_response) > 0

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_session_id_extracted(self, skip_if_no_claude):
        """Session ID should be extracted from Claude response."""
        engine = AvatarEngine(provider="claude", timeout=120)

        try:
            await engine.start()

            response = await engine.chat("Hi")

            assert response.success is True
            # Claude should provide session ID
            assert engine.session_id is not None or response.session_id is not None

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_cost_tracking(self, skip_if_no_claude):
        """Claude should track costs."""
        engine = AvatarEngine(
            provider="claude",
            timeout=120,
            max_budget_usd=1.0,  # Safety limit
        )

        try:
            await engine.start()

            response = await engine.chat("Say hello.")

            assert response.success is True
            # Cost info may be in response
            if response.cost_usd is not None:
                assert response.cost_usd >= 0

        finally:
            await engine.stop()


# =============================================================================
# Provider Switching Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestProviderSwitching:
    """Test switching between real providers."""

    @pytest.mark.asyncio
    async def test_switch_gemini_to_claude(self, skip_if_no_gemini, skip_if_no_claude):
        """Should be able to switch from Gemini to Claude."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        try:
            await engine.start()

            # Chat with Gemini
            resp1 = await engine.chat("Say 'Gemini here'")
            assert resp1.success is True
            assert engine.current_provider == "gemini"

            # Switch to Claude
            await engine.switch_provider("claude")
            assert engine.current_provider == "claude"

            # Chat with Claude
            resp2 = await engine.chat("Say 'Claude here'")
            assert resp2.success is True

        finally:
            await engine.stop()


# =============================================================================
# Error Recovery Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestRealErrorRecovery:
    """Test error recovery with real providers."""

    @pytest.mark.asyncio
    async def test_timeout_handling(self, skip_if_no_gemini):
        """Should handle timeout gracefully."""
        # Very short timeout to force timeout
        engine = AvatarEngine(provider="gemini", timeout=1)

        try:
            await engine.start()

            # This might timeout or succeed quickly
            response = await engine.chat("Count from 1 to 1000 slowly.")

            # Either succeeds or fails gracefully
            assert response is not None
            if not response.success:
                assert response.error is not None

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_recovers_after_error(self, skip_if_no_gemini):
        """Engine should recover after an error."""
        engine = AvatarEngine(provider="gemini", timeout=60)

        try:
            await engine.start()

            # Normal chat
            resp1 = await engine.chat("Say hello.")
            assert resp1.success is True

            # Another chat should still work
            resp2 = await engine.chat("Say goodbye.")
            assert resp2.success is True

        finally:
            await engine.stop()


# =============================================================================
# Config Loading Tests
# =============================================================================


@pytest.mark.integration
class TestConfigLoading:
    """Test loading configuration from files."""

    @pytest.mark.asyncio
    async def test_from_yaml_config(self, skip_if_no_gemini, tmp_path):
        """Should load config from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
provider: gemini
gemini:
  timeout: 60
  approval_mode: yolo
engine:
  max_history: 10
""")

        engine = AvatarEngine.from_config(str(config_file))

        try:
            await engine.start()

            response = await engine.chat("Hi")
            assert response.success is True

        finally:
            await engine.stop()
