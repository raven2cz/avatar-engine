"""Tests for safety instructions feature."""

import textwrap
import pytest
from unittest.mock import patch, MagicMock

from avatar_engine import AvatarEngine, AvatarConfig
from avatar_engine.safety import DEFAULT_SAFETY_INSTRUCTIONS
from avatar_engine.types import ProviderType


class TestSafetyInstructions:
    """Tests for safety instructions prepended to system prompt."""

    def test_safety_instructions_default_true(self):
        """AvatarEngine has safety_instructions=True by default."""
        engine = AvatarEngine()
        assert engine._safety_instructions is True

    def test_safety_instructions_prepended(self):
        """Bridge receives safety instructions + user prompt when enabled."""
        engine = AvatarEngine(
            provider="gemini",
            system_prompt="Be helpful.",
        )
        bridge = engine._create_bridge()
        assert bridge.system_prompt.startswith(DEFAULT_SAFETY_INSTRUCTIONS)
        assert bridge.system_prompt.endswith("Be helpful.")
        assert "\n\n" in bridge.system_prompt

    def test_safety_instructions_disabled(self):
        """safety_instructions=False → bridge gets only user prompt."""
        engine = AvatarEngine(
            provider="gemini",
            system_prompt="Be helpful.",
            safety_instructions=False,
        )
        bridge = engine._create_bridge()
        assert bridge.system_prompt == "Be helpful."
        assert DEFAULT_SAFETY_INSTRUCTIONS not in bridge.system_prompt

    def test_safety_instructions_without_user_prompt(self):
        """With no user prompt, bridge gets only safety instructions."""
        engine = AvatarEngine(provider="gemini")
        bridge = engine._create_bridge()
        assert bridge.system_prompt == DEFAULT_SAFETY_INSTRUCTIONS

    def test_safety_instructions_from_config(self):
        """Config with safety_instructions: false disables safety."""
        config = AvatarConfig(
            provider=ProviderType.GEMINI,
            system_prompt="Custom prompt.",
            safety_instructions=False,
        )
        engine = AvatarEngine(config=config)
        assert engine._safety_instructions is False
        bridge = engine._create_bridge()
        assert bridge.system_prompt == "Custom prompt."
        assert DEFAULT_SAFETY_INSTRUCTIONS not in bridge.system_prompt
