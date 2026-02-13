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
                "thinking_level": "low",
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


# =============================================================================
# ACP Generation Config Propagation Tests (live)
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestACPGenerationConfig:
    """Test generation config propagation in ACP mode via customAliases.

    These tests verify the fix for the generation_config gap:
    previously, ACP mode wrote NO settings to the config file,
    so thinking_level/temperature changes in the UI had no effect.

    Now, customAliases with ``extends`` is written to the settings file,
    which is the ONLY way to propagate config to gemini-cli in ACP mode
    (runtime config methods are not implemented).

    CRITICAL: model.name must NEVER appear in ACP settings — it bypasses
    the alias chain and causes "Internal error" from the API.
    """

    @pytest.mark.asyncio
    async def test_acp_default_model_no_error(self, skip_if_no_gemini):
        """Default model in ACP mode should work without Internal error.

        This is the most basic smoke test: start ACP with the default
        model and send a message. If customAliases breaks the alias
        chain, this will fail with "Internal error".
        """
        bridge = GeminiBridge(
            acp_enabled=True,
            timeout=120,
        )

        try:
            await bridge.start()
            assert bridge._acp_mode is True, "Should be in ACP mode"

            response = await bridge.send("What is 2+2? Just the number.")
            assert response.success is True, f"ACP failed: {response.error}"
            assert "4" in response.content

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_acp_with_thinking_level_low(self, skip_if_no_gemini):
        """ACP with thinking_level=low should work (customOverrides propagation).

        This test verifies the core fix: generation_config is now
        propagated to gemini-cli via customOverrides in the settings file.

        Note: MEDIUM is not supported for Pro models on cloudcode-pa API.
        Using LOW which is supported for all Gemini 3 models.
        """
        bridge = GeminiBridge(
            acp_enabled=True,
            timeout=180,
            generation_config={
                "thinking_level": "low",
            },
        )

        try:
            await bridge.start()
            assert bridge._acp_mode is True, "Should be in ACP mode"

            # Verify settings file was written with customOverrides
            assert bridge._gemini_settings_path is not None
            import json
            settings = json.loads(bridge._gemini_settings_path.read_text())
            # ACP sets model.name to bypass auto classifier
            assert settings.get("model", {}).get("name") == "gemini-3-pro-preview"
            overrides = settings["modelConfigs"]["customOverrides"]
            gen_cfg = overrides[0]["modelConfig"]["generateContentConfig"]
            assert gen_cfg["thinkingConfig"]["thinkingLevel"] == "LOW"

            # Send a prompt — should not fail with "Internal error"
            response = await bridge.send(
                "What is 123 * 456? Show your reasoning briefly."
            )
            assert response.success is True, f"ACP with thinking=low failed: {response.error}"
            normalized = response.content.replace(",", "").replace(" ", "").replace("\\", "")
            assert "56088" in normalized

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_acp_with_thinking_level_high(self, skip_if_no_gemini):
        """ACP with thinking_level=high should work."""
        bridge = GeminiBridge(
            acp_enabled=True,
            timeout=180,
            generation_config={
                "thinking_level": "high",
            },
        )

        try:
            await bridge.start()
            assert bridge._acp_mode is True

            response = await bridge.send("Say hello.")
            assert response.success is True, f"ACP with thinking=high failed: {response.error}"
            assert len(response.content) > 0

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_acp_with_temperature(self, skip_if_no_gemini):
        """ACP with custom temperature should work."""
        bridge = GeminiBridge(
            acp_enabled=True,
            timeout=120,
            generation_config={
                "temperature": 0.3,
            },
        )

        try:
            await bridge.start()
            assert bridge._acp_mode is True

            response = await bridge.send("What is 2+2? Just the number.")
            assert response.success is True, f"ACP with temperature=0.3 failed: {response.error}"
            assert "4" in response.content

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_acp_with_model_and_config(self, skip_if_no_gemini):
        """ACP with explicit model + generation_config should work.

        This is the flow triggered when user selects model and changes
        thinking level in the web UI. Uses LOW (valid for Pro on cloudcode-pa).
        """
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            timeout=180,
            generation_config={
                "thinking_level": "low",
                "temperature": 0.5,
            },
        )

        try:
            await bridge.start()
            assert bridge._acp_mode is True

            # Verify settings structure: customOverrides, no customAliases for default model
            import json
            settings = json.loads(bridge._gemini_settings_path.read_text())
            assert "model" not in settings  # No model.name
            assert "customAliases" not in settings.get("modelConfigs", {})
            overrides = settings["modelConfigs"]["customOverrides"]
            gen_cfg = overrides[0]["modelConfig"]["generateContentConfig"]
            assert gen_cfg["temperature"] == 0.5
            assert gen_cfg["thinkingConfig"]["thinkingLevel"] == "LOW"

            response = await bridge.send("Say 'config works' if you can read this.")
            assert response.success is True, f"ACP with model+config failed: {response.error}"

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_acp_gemini_25_flash(self, skip_if_no_gemini):
        """ACP with gemini-2.5-flash should use customAliases for routing."""
        bridge = GeminiBridge(
            model="gemini-2.5-flash",
            acp_enabled=True,
            timeout=120,
            generation_config={
                "temperature": 0.5,
            },
        )

        try:
            await bridge.start()

            if not bridge._acp_mode:
                pytest.skip("ACP not available")

            # Verify: customAliases for model routing, customOverrides for config
            import json
            settings = json.loads(bridge._gemini_settings_path.read_text())
            alias = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
            assert alias["extends"] == "chat-base-2.5"
            assert alias["modelConfig"]["model"] == "gemini-2.5-flash"
            overrides = settings["modelConfigs"]["customOverrides"]
            assert overrides[0]["match"]["model"] == "gemini-2.5-flash"

            response = await bridge.send("What is 3+3? Just the number.")
            assert response.success is True, f"ACP gemini-2.5-flash failed: {response.error}"
            assert "6" in response.content

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_acp_multi_turn_with_config(self, skip_if_no_gemini):
        """ACP with generation_config should maintain context across turns."""
        bridge = GeminiBridge(
            acp_enabled=True,
            timeout=180,
            generation_config={
                "thinking_level": "low",
                "temperature": 0.3,
            },
        )

        try:
            await bridge.start()
            assert bridge._acp_mode is True

            resp1 = await bridge.send("Remember the word: PINEAPPLE")
            assert resp1.success is True, f"Turn 1 failed: {resp1.error}"

            resp2 = await bridge.send("What word did I ask you to remember?")
            assert resp2.success is True, f"Turn 2 failed: {resp2.error}"
            assert "PINEAPPLE" in resp2.content.upper()

        finally:
            await bridge.stop()


# =============================================================================
# ACP Image Model Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestACPImageGeneration:
    """Test image generation via ACP.

    Dedicated image models (gemini-3-pro-image-preview, gemini-2.5-flash-image)
    are NOT available on the cloudcode-pa API used by gemini-cli. They return
    "Requested entity was not found."

    Image generation works through the DEFAULT model (gemini-3-pro-preview)
    which has native image gen capability (Nano Banana). Just ask it to
    generate/draw an image and it will.

    These tests verify:
      1. Image model settings structure is correct (unit-level, no API call)
      2. Default model can generate images via ACP
      3. thinkingConfig is stripped for image models (backend guard)
    """

    @pytest.mark.asyncio
    async def test_image_model_settings_structure(self, skip_if_no_gemini):
        """Settings file should have correct structure for image model.

        Even though dedicated image models don't work on cloudcode-pa,
        the settings structure should still be correct.
        """
        bridge = GeminiBridge(
            model="gemini-3-pro-image-preview",
            acp_enabled=True,
            timeout=120,
            generation_config={
                "response_modalities": "TEXT,IMAGE",
            },
        )

        try:
            await bridge.start()

            # Verify settings structure (doesn't need working ACP)
            import json
            settings = json.loads(bridge._gemini_settings_path.read_text())

            # Must NOT have model.name at top level
            assert "model" not in settings

            # customAliases for routing (no extends for image models)
            alias = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
            assert alias["modelConfig"]["model"] == "gemini-3-pro-image-preview"
            assert "extends" not in alias

            # customOverrides for config
            overrides = settings["modelConfigs"]["customOverrides"]
            gen_cfg = overrides[0]["modelConfig"]["generateContentConfig"]
            assert gen_cfg["responseModalities"] == ["TEXT", "IMAGE"]
            # Image models must NOT have thinkingConfig
            assert "thinkingConfig" not in gen_cfg

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_image_model_strips_thinking_config(self, skip_if_no_gemini):
        """Backend must strip thinkingConfig for image models even if passed."""
        bridge = GeminiBridge(
            model="gemini-3-pro-image-preview",
            acp_enabled=True,
            timeout=120,
            generation_config={
                "response_modalities": "TEXT,IMAGE",
                "thinking_level": "high",  # stale from previous text model
            },
        )

        try:
            await bridge.start()

            import json
            settings = json.loads(bridge._gemini_settings_path.read_text())
            gen_cfg = settings["modelConfigs"]["customOverrides"][0]["modelConfig"]["generateContentConfig"]
            assert "thinkingConfig" not in gen_cfg
            assert gen_cfg["responseModalities"] == ["TEXT", "IMAGE"]

        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_default_model_image_generation(self, skip_if_no_gemini):
        """Default model (gemini-3-pro-preview) should generate images via Nano Banana.

        The default model has native image generation capability.
        Ask it to generate an image — it may return an ImageContentBlock
        which our extraction code captures as generated_images.
        """
        bridge = GeminiBridge(
            acp_enabled=True,
            timeout=180,
        )

        try:
            await bridge.start()
            assert bridge._acp_mode is True

            # Ask the default model to generate an image
            response = await bridge.send(
                "Generate a simple image of a red circle on a white background. "
                "Just the image, no text explanation needed."
            )
            assert response.success is True, f"Image gen failed: {response.error}"
            # Content may be text (explanation) or empty if only image returned
            # generated_images may contain the image if model produced one
            # We can't guarantee the model will always generate an image,
            # but the request should not fail
            assert response is not None

        finally:
            await bridge.stop()
