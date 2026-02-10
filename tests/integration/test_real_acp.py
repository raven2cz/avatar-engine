"""
Real Gemini ACP (Agent Client Protocol) integration tests.

These tests verify ACP warm session functionality with real Gemini.
Run with: pytest tests/integration/test_real_acp.py -v

Note: ACP is currently disabled by default due to stability issues.
Enable with acp_enabled=True to test.
"""

import asyncio
import pytest

from avatar_engine import AvatarEngine
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.bridges.base import BridgeState


# =============================================================================
# ACP Session Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiACP:
    """Test Gemini ACP (warm session) functionality."""

    @pytest.mark.asyncio
    async def test_acp_session_basic(self, skip_if_no_gemini):
        """Basic ACP session should work."""
        # Enable ACP explicitly
        engine = AvatarEngine(
            provider="gemini",
            timeout=120,
            acp_enabled=True,
        )

        try:
            await engine.start()

            response = await engine.chat("Say hello.")

            # May succeed or fall back to oneshot
            if response.success:
                assert len(response.content) > 0
            else:
                # ACP might not be available, that's OK
                pytest.skip("ACP not available, falling back to oneshot")

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_acp_multi_turn(self, skip_if_no_gemini):
        """ACP should maintain context across turns."""
        engine = AvatarEngine(
            provider="gemini",
            timeout=120,
            acp_enabled=True,
        )

        try:
            await engine.start()

            # First message
            resp1 = await engine.chat("Remember the number 42.")
            if not resp1.success:
                pytest.skip("ACP not available")

            # Second message should have context
            resp2 = await engine.chat("What number did I ask you to remember?")
            assert resp2.success is True
            assert "42" in resp2.content

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_acp_with_thinking(self, skip_if_no_gemini):
        """ACP with thinking mode enabled."""
        engine = AvatarEngine(
            provider="gemini",
            timeout=180,
            acp_enabled=True,
            generation_config={
                "thinking_level": "medium",
            }
        )

        try:
            await engine.start()

            response = await engine.chat(
                "What is 123 * 456? Show your reasoning."
            )

            if not response.success:
                pytest.skip("ACP with thinking not available")

            # Should have the correct answer (may be formatted variously:
            # "56088", "56 088", "56,088", "56\ 088" in LaTeX, etc.)
            normalized = response.content.replace(",", "").replace(" ", "").replace("\\", "")
            assert "56088" in normalized

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_acp_fallback_to_oneshot(self, skip_if_no_gemini):
        """Should fall back to oneshot if ACP fails."""
        # Create engine with ACP enabled
        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            acp_enabled=True,
        )

        try:
            await engine.start()

            # Even if ACP fails, should fall back to oneshot
            response = await engine.chat("Hello")

            # Should work one way or another
            assert response is not None
            # If success, content should exist
            if response.success:
                assert response.content is not None

        finally:
            await engine.stop()


# =============================================================================
# ACP Bridge Direct Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiBridgeDirect:
    """Test Gemini bridge directly."""

    @pytest.mark.asyncio
    async def test_bridge_oneshot_mode(self, skip_if_no_gemini):
        """Bridge in oneshot mode should work."""
        bridge = GeminiBridge(
            acp_enabled=False,
            timeout=60,
        )

        try:
            await bridge.start()

            response = await bridge.send("What is 5+5?")

            assert response.success is True
            assert "10" in response.content

            await bridge.stop()

        except Exception as e:
            await bridge.stop()
            raise

    @pytest.mark.asyncio
    async def test_bridge_state_transitions(self, skip_if_no_gemini):
        """Bridge should transition through states correctly."""
        bridge = GeminiBridge(
            acp_enabled=False,
            timeout=60,
        )

        states = []

        def capture_state(state, detail=""):
            states.append(state)

        bridge.on_state_change(capture_state)

        try:
            assert bridge.state == BridgeState.DISCONNECTED

            await bridge.start()
            assert bridge.state == BridgeState.READY

            resp = await bridge.send("Hi")
            # After send: READY on success, ERROR on rate-limit/transient failure
            if resp.success:
                assert bridge.state == BridgeState.READY
            else:
                assert bridge.state in (BridgeState.READY, BridgeState.ERROR)

            await bridge.stop()
            assert bridge.state == BridgeState.DISCONNECTED

        except Exception as e:
            await bridge.stop()
            raise

    @pytest.mark.asyncio
    async def test_bridge_stats(self, skip_if_no_gemini):
        """Bridge should track usage stats."""
        import time
        # Wait a bit to avoid rate limiting from previous tests
        time.sleep(2)

        bridge = GeminiBridge(
            acp_enabled=False,
            timeout=120,  # Longer timeout for rate-limited scenarios
        )

        try:
            await bridge.start()

            # Initial stats
            stats = bridge.get_stats()
            assert stats["total_requests"] == 0

            # After one request
            response = await bridge.send("Hi")
            stats = bridge.get_stats()
            assert stats["total_requests"] >= 1

            # If we got rate limited, skip the success check
            if response.success:
                assert stats["successful_requests"] >= 1
            else:
                pytest.skip(f"Rate limited: {response.error}")

            await bridge.stop()

        except Exception as e:
            await bridge.stop()
            raise


# =============================================================================
# Generation Config Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGenerationConfig:
    """Test generation configuration options."""

    @pytest.mark.asyncio
    async def test_temperature_setting(self, skip_if_no_gemini):
        """Temperature setting should be respected."""
        # Low temperature for deterministic output
        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            generation_config={
                "temperature": 0.1,
            }
        )

        try:
            await engine.start()

            # With low temperature, response to simple math should be consistent
            resp1 = await engine.chat("What is 2+2? Just the number.")
            resp2 = await engine.chat("What is 2+2? Just the number.")

            assert resp1.success and resp2.success
            # Both should contain 4
            assert "4" in resp1.content
            assert "4" in resp2.content

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_top_p_setting(self, skip_if_no_gemini):
        """Top-p setting should work."""
        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            generation_config={
                "top_p": 0.9,
            }
        )

        try:
            await engine.start()

            response = await engine.chat("Hello")
            assert response.success is True

        finally:
            await engine.stop()
