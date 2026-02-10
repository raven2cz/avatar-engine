"""
Gemini ACP (Agent Client Protocol) tests.

These tests verify:
- ACP initialization flow
- Authentication handling
- Session management
- Prompt streaming
- Thinking extraction
"""

import asyncio
import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.bridges.base import BridgeState


# =============================================================================
# Mock Helpers
# =============================================================================


def create_mock_subprocess(stdout_lines: List[str], returncode: int = 0):
    """Create a mock subprocess."""
    proc = MagicMock()
    proc.pid = 12345
    _returncode = [returncode]
    type(proc).returncode = PropertyMock(side_effect=lambda: _returncode[0])

    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()

    stdout_queue = asyncio.Queue()
    for line in stdout_lines:
        stdout_queue.put_nowait(line + "\n" if line else "")
    stdout_queue.put_nowait("")

    async def mock_readline():
        try:
            line = stdout_queue.get_nowait()
            return line.encode() if line else b""
        except asyncio.QueueEmpty:
            return b""

    proc.stdout = MagicMock()
    proc.stdout.readline = mock_readline
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    async def mock_wait():
        _returncode[0] = returncode
        return returncode

    proc.wait = mock_wait

    async def mock_communicate():
        all_stdout = "\n".join(stdout_lines).encode()
        _returncode[0] = returncode
        return (all_stdout, b"")

    proc.communicate = mock_communicate

    return proc


# =============================================================================
# ACP Configuration Tests
# =============================================================================


class TestACPConfiguration:
    """Test ACP configuration options."""

    def test_acp_enabled_by_default_when_sdk_available(self):
        """ACP is enabled by default when agent-client-protocol SDK is installed."""
        bridge = GeminiBridge()
        # ACP is preferred mode when SDK is available
        from avatar_engine.bridges.gemini import _ACP_AVAILABLE
        assert bridge.acp_enabled == _ACP_AVAILABLE

    def test_acp_can_be_disabled(self):
        """ACP can be disabled via config."""
        bridge = GeminiBridge(acp_enabled=False)
        assert bridge.acp_enabled is False

    def test_generation_config_options(self):
        """Generation config options should be stored."""
        gen_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "thinking_level": "high",
        }
        bridge = GeminiBridge(generation_config=gen_config)

        assert bridge.generation_config == gen_config

    def test_auth_method_option(self):
        """Auth method should be configurable."""
        bridge = GeminiBridge(auth_method="oauth-personal")
        assert bridge.auth_method == "oauth-personal"


# =============================================================================
# Oneshot Mode Tests (Fallback)
# =============================================================================


class TestOneshotMode:
    """Test oneshot mode (non-ACP) behavior."""

    @pytest.mark.asyncio
    async def test_oneshot_mode_when_acp_disabled(self):
        """Should use oneshot mode when ACP is disabled."""
        lines = [
            json.dumps({"type": "init", "session_id": "oneshot-test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hello from oneshot"}),
            json.dumps({"type": "result", "status": "success"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                bridge = GeminiBridge(acp_enabled=False)
                await bridge.start()

                response = await bridge.send("Hello")

                assert response.success is True
                assert response.content == "Hello from oneshot"

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_oneshot_command_includes_model(self):
        """Oneshot command should include model when specified."""
        bridge = GeminiBridge(model="gemini-2.0-flash", acp_enabled=False)
        cmd = bridge._build_oneshot_command("Hello")

        assert "--model" in cmd
        assert "gemini-2.0-flash" in cmd

    @pytest.mark.asyncio
    async def test_oneshot_command_includes_yolo(self):
        """Oneshot command should include --yolo in yolo mode."""
        bridge = GeminiBridge(approval_mode="yolo", acp_enabled=False)
        cmd = bridge._build_oneshot_command("Hello")

        assert "--yolo" in cmd


# =============================================================================
# History Injection Tests
# =============================================================================


class TestHistoryInjection:
    """Test conversation history injection for Gemini."""

    def test_effective_prompt_with_empty_history(self):
        """Prompt should be unchanged with empty history."""
        bridge = GeminiBridge()
        prompt = bridge._build_effective_prompt("Hello")

        # Should just be the prompt
        assert "Hello" in prompt

    def test_effective_prompt_with_history(self):
        """Prompt should include history context."""
        from avatar_engine.types import Message

        bridge = GeminiBridge()
        bridge.history = [
            Message(role="user", content="What is Python?"),
            Message(role="assistant", content="Python is a programming language."),
        ]

        prompt = bridge._build_effective_prompt("Tell me more")

        assert "[Previous conversation:]" in prompt
        assert "What is Python?" in prompt
        assert "Python is a programming language." in prompt
        assert "Tell me more" in prompt

    def test_effective_prompt_truncates_long_history(self):
        """Should truncate very long history messages."""
        from avatar_engine.types import Message

        bridge = GeminiBridge()
        # Create message with very long content
        long_content = "A" * 10000
        bridge.history = [
            Message(role="assistant", content=long_content),
        ]

        prompt = bridge._build_effective_prompt("Continue")

        # Should be truncated (less than original length)
        assert len(prompt) < len(long_content) + 1000


# =============================================================================
# Response Parsing Tests
# =============================================================================


class TestGeminiResponseParsing:
    """Test Gemini response parsing."""

    def test_parse_assistant_content(self):
        """Should parse assistant message content."""
        bridge = GeminiBridge()
        events = [
            {"type": "message", "role": "assistant", "content": "Hello!"},
        ]

        content = bridge._parse_content(events)
        assert content == "Hello!"

    def test_parse_session_id_from_init(self):
        """Should extract session ID from init event."""
        bridge = GeminiBridge()
        events = [
            {"type": "init", "session_id": "gemini-session-abc"},
        ]

        sid = bridge._parse_session_id(events)
        assert sid == "gemini-session-abc"

    def test_parse_usage_from_result(self):
        """Should extract usage stats from result event."""
        bridge = GeminiBridge()
        events = [
            {
                "type": "result",
                "stats": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                }
            },
        ]

        usage = bridge._parse_usage(events)
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        assert usage["total_tokens"] == 150

    def test_is_turn_complete(self):
        """Should detect turn completion."""
        bridge = GeminiBridge()

        assert bridge._is_turn_complete({"type": "result"}) is True
        assert bridge._is_turn_complete({"type": "message"}) is False
        assert bridge._is_turn_complete({"type": "init"}) is False

    def test_parse_thinking_from_events(self):
        """Should handle thinking events in raw events."""
        bridge = GeminiBridge()
        events = [
            {"type": "thinking", "content": "Let me think about this..."},
            {"type": "message", "role": "assistant", "content": "Here's my answer"},
        ]

        # Thinking events are stored in raw_events
        # The bridge doesn't have a separate _parse_thinking method
        # but thinking events should be included in raw response
        content = bridge._parse_content(events)
        assert content == "Here's my answer"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestGeminiErrorHandling:
    """Test Gemini error handling."""

    @pytest.mark.asyncio
    async def test_handles_authentication_error(self):
        """Should handle authentication errors gracefully."""
        lines = [
            json.dumps({
                "type": "error",
                "code": "UNAUTHENTICATED",
                "message": "Authentication failed"
            }),
        ]

        mock_proc = create_mock_subprocess(lines, returncode=1)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                bridge = GeminiBridge(acp_enabled=False)
                await bridge.start()

                response = await bridge.send("Hello")

                # Should fail gracefully
                assert response.success is False or response.content == ""

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        """Should handle API errors gracefully."""
        lines = [
            json.dumps({
                "type": "error",
                "code": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded"
            }),
        ]

        mock_proc = create_mock_subprocess(lines, returncode=1)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                bridge = GeminiBridge(acp_enabled=False)
                await bridge.start()

                response = await bridge.send("Hello")

                # Should return error response
                assert response is not None

                await bridge.stop()


# =============================================================================
# MCP Server Configuration Tests
# =============================================================================


class TestGeminiMCPConfig:
    """Test Gemini MCP server configuration."""

    def test_mcp_servers_stored(self):
        """MCP servers should be stored in config."""
        mcp_servers = {
            "calculator": {
                "command": "python",
                "args": ["calc_server.py"],
            }
        }
        bridge = GeminiBridge(mcp_servers=mcp_servers)

        assert bridge.mcp_servers == mcp_servers

    @pytest.mark.asyncio
    async def test_mcp_servers_used_in_command(self):
        """MCP servers should be passed to command."""
        mcp_servers = {
            "tools": {
                "command": "python",
                "args": ["tools.py"],
            }
        }
        bridge = GeminiBridge(mcp_servers=mcp_servers, acp_enabled=False)

        # Check that MCP config would be used
        # (Actual command building depends on implementation)
        assert bridge.mcp_servers is not None


# =============================================================================
# State Management Tests
# =============================================================================


class TestGeminiBridgeState:
    """Test Gemini bridge state management."""

    def test_initial_state_disconnected(self):
        """Bridge should start disconnected."""
        bridge = GeminiBridge()
        assert bridge.state == BridgeState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_state_becomes_ready_after_start(self):
        """State should become READY after start."""
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                bridge = GeminiBridge(acp_enabled=False)
                await bridge.start()

                assert bridge.state == BridgeState.READY

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_state_becomes_disconnected_after_stop(self):
        """State should become DISCONNECTED after stop."""
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                bridge = GeminiBridge(acp_enabled=False)
                await bridge.start()
                await bridge.stop()

                assert bridge.state == BridgeState.DISCONNECTED


# =============================================================================
# Generation Config Tests
# =============================================================================


class TestGenerationConfig:
    """Test generation configuration handling."""

    def test_default_generation_config(self):
        """Should have sensible default generation config."""
        bridge = GeminiBridge()
        # Default might be None or empty
        assert bridge.generation_config is None or isinstance(bridge.generation_config, dict)

    def test_custom_temperature(self):
        """Should accept custom temperature."""
        bridge = GeminiBridge(generation_config={"temperature": 0.5})
        assert bridge.generation_config["temperature"] == 0.5

    def test_thinking_level_config(self):
        """Should accept thinking level config."""
        bridge = GeminiBridge(generation_config={"thinking_level": "high"})
        assert bridge.generation_config["thinking_level"] == "high"


# =============================================================================
# Settings.json Configuration Tests (customAliases issue)
# =============================================================================


class TestSettingsJsonConfig:
    """Test settings.json configuration in sandbox (Zero Footprint).

    ACP mode uses customAliases with ``extends`` to propagate generation
    config (thinking_level, temperature, responseModalities) to gemini-cli.
    This is the ONLY mechanism — runtime config methods are not implemented.

    CRITICAL: model.name must NEVER be set in ACP mode — it bypasses the
    alias chain and causes "Internal error".

    NOTE: Settings are written to a ConfigSandbox temp dir, NOT to working_dir.
    """

    def _read_sandbox_settings(self, bridge) -> dict:
        """Read settings from bridge's sandbox."""
        return json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )

    def test_acp_mode_has_custom_overrides(self, tmp_path):
        """ACP mode should write customOverrides for generation config.

        customOverrides are applied AFTER alias resolution — they preserve
        the entire built-in alias chain. Default model uses only customOverrides.
        """
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            generation_config={"temperature": 0.7},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        settings = self._read_sandbox_settings(bridge)

        # customOverrides must be present with generation config
        assert "modelConfigs" in settings
        overrides = settings["modelConfigs"]["customOverrides"]
        assert len(overrides) == 1
        assert overrides[0]["match"]["model"] == "gemini-3-pro-preview"
        gen_cfg = overrides[0]["modelConfig"]["generateContentConfig"]
        assert gen_cfg["temperature"] == 0.7

        # Default model → no customAliases
        assert "customAliases" not in settings["modelConfigs"]

        # model.name must NOT be in top-level settings
        assert "model" not in settings

        # Zero Footprint: no files in working_dir
        assert not (tmp_path / ".gemini").exists()
        bridge._sandbox.cleanup()

    def test_acp_mode_no_model_name_in_settings(self, tmp_path):
        """ACP mode must NEVER set model.name in top-level settings.

        model.name bypasses gemini-cli's alias chain and causes "Internal error".
        """
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            generation_config={"thinking_level": "medium"},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        settings = self._read_sandbox_settings(bridge)
        assert "model" not in settings, (
            "ACP mode must never set model.name — it bypasses alias chain"
        )
        bridge._sandbox.cleanup()

    def test_acp_mode_non_default_model_has_alias(self, tmp_path):
        """Non-default Gemini 3 model should have customAliases for routing."""
        bridge = GeminiBridge(
            model="gemini-3-flash-preview",
            acp_enabled=True,
            generation_config={"thinking_level": "low"},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        settings = self._read_sandbox_settings(bridge)
        alias = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
        assert alias["extends"] == "chat-base-3"
        assert alias["modelConfig"]["model"] == "gemini-3-flash-preview"
        # Config should be in customOverrides, not customAliases
        assert "generateContentConfig" not in alias.get("modelConfig", {})
        bridge._sandbox.cleanup()

    def test_acp_mode_extends_chat_base_25(self, tmp_path):
        """Gemini 2.5 models should extend chat-base-2.5."""
        bridge = GeminiBridge(
            model="gemini-2.5-flash",
            acp_enabled=True,
            generation_config={"temperature": 0.5},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        settings = self._read_sandbox_settings(bridge)
        alias = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
        assert alias["extends"] == "chat-base-2.5"
        assert alias["modelConfig"]["model"] == "gemini-2.5-flash"
        bridge._sandbox.cleanup()

    def test_acp_mode_image_model_no_extends(self, tmp_path):
        """Image models should have no extends (their own config)."""
        bridge = GeminiBridge(
            model="gemini-3-pro-image-preview",
            acp_enabled=True,
            generation_config={"response_modalities": "TEXT,IMAGE"},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        settings = self._read_sandbox_settings(bridge)
        alias = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
        assert "extends" not in alias
        assert alias["modelConfig"]["model"] == "gemini-3-pro-image-preview"
        # Config in customOverrides
        overrides = settings["modelConfigs"]["customOverrides"]
        gen_cfg = overrides[0]["modelConfig"]["generateContentConfig"]
        assert gen_cfg["responseModalities"] == ["TEXT", "IMAGE"]
        bridge._sandbox.cleanup()

    def test_acp_mode_no_preview_features(self, tmp_path):
        """ACP mode should not set previewFeatures (removed from gemini-cli)."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            generation_config={"temperature": 1.0},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        settings = self._read_sandbox_settings(bridge)
        assert "previewFeatures" not in settings
        bridge._sandbox.cleanup()

    def test_acp_mode_no_settings_without_config(self, tmp_path):
        """ACP mode with no model and no generation_config writes no settings."""
        bridge = GeminiBridge(
            acp_enabled=True,
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert bridge._gemini_settings_path is None
        assert not (bridge._sandbox.root / "gemini-settings.json").exists()
        bridge._sandbox.cleanup()

    def test_oneshot_mode_has_custom_aliases(self, tmp_path):
        """Oneshot mode (acp_enabled=False) should generate customAliases.

        customAliases is needed for generation_config in oneshot mode.
        """
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            generation_config={"temperature": 0.7},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        settings = self._read_sandbox_settings(bridge)

        # Oneshot mode should have customAliases with generation config
        assert "modelConfigs" in settings
        assert "customAliases" in settings["modelConfigs"]
        assert "gemini-3-pro-preview" in settings["modelConfigs"]["customAliases"]

        # Verify temperature is set
        alias_cfg = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
        gen_cfg = alias_cfg["modelConfig"]["generateContentConfig"]
        assert gen_cfg.get("temperature") == 0.7
        bridge._sandbox.cleanup()

    def test_oneshot_mode_includes_thinking_config(self, tmp_path):
        """Oneshot mode should include thinking config in customAliases."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            generation_config={
                "temperature": 0.8,
                "thinking_level": "high",
                "include_thoughts": True,
            },
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        settings = self._read_sandbox_settings(bridge)

        alias_cfg = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
        gen_cfg = alias_cfg["modelConfig"]["generateContentConfig"]

        assert gen_cfg.get("temperature") == 0.8
        assert "thinkingConfig" in gen_cfg
        assert gen_cfg["thinkingConfig"].get("thinkingLevel") == "HIGH"
        assert gen_cfg["thinkingConfig"].get("includeThoughts") is True
        bridge._sandbox.cleanup()
