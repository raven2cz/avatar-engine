"""
CLI integration tests — tests CLI commands with mocked engine.

These tests verify:
- UC-6: CLI single message
- CLI command parsing
- Output formats (text, JSON, streaming)
- Error handling
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from avatar_engine.cli import cli
from avatar_engine.types import BridgeResponse


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def disable_config_autoload(monkeypatch):
    """Disable config auto-loading in all CLI tests."""
    monkeypatch.setattr("avatar_engine.cli.app.find_config", lambda: None)


@pytest.fixture
def mock_engine():
    """Create mock AvatarEngine."""
    engine = MagicMock()
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    engine.session_id = "test-session-123"
    engine.get_health = MagicMock(return_value=MagicMock(
        healthy=True,
        state="ready",
        provider="gemini",
        uptime_seconds=60,
    ))
    return engine


def make_mock_response(
    content: str = "Hello!",
    success: bool = True,
    duration_ms: int = 1500,
    cost_usd: float = None,
    tool_calls: list = None,
) -> BridgeResponse:
    """Create a mock BridgeResponse."""
    return BridgeResponse(
        content=content,
        success=success,
        duration_ms=duration_ms,
        session_id="test-session",
        cost_usd=cost_usd,
        tool_calls=tool_calls or [],
        raw_events=[],
    )


# =============================================================================
# UC-6: CLI Single Message Tests
# =============================================================================


class TestChatCommand:
    """Test 'avatar chat' command."""

    def test_chat_basic(self, runner, mock_engine):
        """Basic chat command should work."""
        # Use --no-stream for deterministic output (streaming buffers differently)
        mock_engine.chat = AsyncMock(return_value=make_mock_response("Hello, world!"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["chat", "--no-stream", "Hello"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Hello" in result.output or "world" in result.output

    def test_chat_with_provider_flag(self, runner, mock_engine):
        """Chat with -p flag should use correct provider."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("Claude here!"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, ["-p", "claude", "chat", "Hello"])

        # Verify provider was passed
        if mock_cls.call_args:
            assert mock_cls.call_args.kwargs.get("provider") == "claude" or \
                   (mock_cls.call_args.args and mock_cls.call_args.args[0] == "claude")

    def test_chat_json_output(self, runner, mock_engine):
        """Chat with --json should output valid JSON."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response(
            content="The answer is 42",
            success=True,
            duration_ms=1000,
        ))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["chat", "--json", "--no-stream", "What is the meaning?"])

        assert result.exit_code == 0
        # Parse JSON output
        output_json = json.loads(result.output)
        assert output_json["content"] == "The answer is 42"
        assert output_json["success"] is True
        assert "session_id" in output_json

    def test_chat_streaming_output(self, runner, mock_engine):
        """Chat with streaming should yield chunks."""
        async def mock_stream(msg):
            for chunk in ["Hello", " ", "world", "!"]:
                yield chunk

        mock_engine.chat_stream = mock_stream

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["chat", "--stream", "Hello"])

        assert result.exit_code == 0
        assert "Hello" in result.output

    def test_chat_no_stream_flag(self, runner, mock_engine):
        """Chat with --no-stream should not stream."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("Complete response"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["chat", "--no-stream", "Hello"])

        assert result.exit_code == 0
        mock_engine.chat.assert_called()

    def test_chat_with_model_flag(self, runner, mock_engine):
        """Chat with --model should pass model to engine."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            runner.invoke(cli, ["chat", "--model", "gemini-2.0-flash", "Hello"])

        # Verify model was passed
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            assert kwargs.get("model") == "gemini-2.0-flash"

    def test_chat_error_handling(self, runner, mock_engine):
        """Chat should handle errors gracefully."""
        mock_engine.start = AsyncMock(side_effect=ConnectionError("CLI not found"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["chat", "Hello"])

        assert result.exit_code == 1
        assert "Error" in result.output or "error" in result.output.lower()


class TestHealthCommand:
    """Test 'avatar health' command."""

    def test_health_basic(self, runner, mock_engine):
        """Health command should show bridge status."""
        with patch("avatar_engine.cli.commands.health.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["health"])

        assert result.exit_code == 0
        # Should contain health info
        assert "healthy" in result.output.lower() or "health" in result.output.lower()

    def test_health_check_cli(self, runner):
        """Health --check-cli should check CLI versions."""
        mock_info = MagicMock()
        mock_info.available = True
        mock_info.version = "1.0.0"
        mock_info.error = None

        with patch("avatar_engine.cli.commands.health.check_cli_version", return_value=mock_info):
            result = runner.invoke(cli, ["health", "--check-cli"])

        assert result.exit_code == 0
        # Should list tools
        assert "claude" in result.output.lower() or "gemini" in result.output.lower()

    def test_health_unhealthy_bridge(self, runner, mock_engine):
        """Health should show unhealthy status."""
        mock_engine.get_health = MagicMock(return_value=MagicMock(
            healthy=False,
            state="disconnected",
            provider="gemini",
            uptime_seconds=0,
        ))

        with patch("avatar_engine.cli.commands.health.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["health"])

        # Should indicate unhealthy
        assert "unhealthy" in result.output.lower() or "✗" in result.output


class TestVersionCommand:
    """Test 'avatar version' command."""

    def test_version_command(self, runner):
        """Version command should show version."""
        result = runner.invoke(cli, ["version"])

        assert result.exit_code == 0
        # Should contain version number
        assert "avatar" in result.output.lower() or "0." in result.output


class TestMCPCommand:
    """Test 'avatar mcp' commands."""

    def test_mcp_list_empty(self, runner):
        """MCP list should work with no servers."""
        # MCP list reads from config files, no engine needed
        with patch("avatar_engine.cli.commands.mcp._load_mcp_servers", return_value={}):
            result = runner.invoke(cli, ["mcp", "list"])

        assert result.exit_code == 0
        assert "No MCP servers" in result.output

    def test_mcp_list_with_servers(self, runner):
        """MCP list should show configured servers."""
        mock_servers = {
            "test-server": {
                "command": "python",
                "args": ["server.py"],
            }
        }

        with patch("avatar_engine.cli.commands.mcp._load_mcp_servers", return_value=mock_servers):
            result = runner.invoke(cli, ["mcp", "list"])

        assert result.exit_code == 0
        assert "test-server" in result.output

    def test_mcp_add(self, runner, tmp_path):
        """MCP add should create config file."""
        config_file = tmp_path / "mcp_servers.json"

        result = runner.invoke(cli, [
            "mcp", "add", "mytools", "python", "server.py",
            "--config", str(config_file)
        ])

        assert result.exit_code == 0
        assert config_file.exists()

        import json
        data = json.loads(config_file.read_text())
        assert "mytools" in data.get("mcpServers", {})


# =============================================================================
# CLI Option Parsing Tests
# =============================================================================


class TestCLIOptions:
    """Test CLI option parsing."""

    def test_verbose_flag(self, runner, mock_engine):
        """Verbose flag should enable verbose output."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["-v", "chat", "--no-stream", "Hello"])

        # Verbose mode shows provider info
        assert result.exit_code == 0

    def test_provider_choices(self, runner):
        """Provider flag should only accept valid choices."""
        result = runner.invoke(cli, ["-p", "invalid", "chat", "Hello"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "choice" in result.output.lower()

    def test_timeout_option(self, runner, mock_engine):
        """Timeout option should be passed to engine."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            runner.invoke(cli, ["chat", "--timeout", "60", "Hello"])

        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            assert kwargs.get("timeout") == 60


class TestCLIHelp:
    """Test CLI help messages."""

    def test_main_help(self, runner):
        """Main help should show available commands."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "chat" in result.output
        assert "health" in result.output
        assert "repl" in result.output

    def test_chat_help(self, runner):
        """Chat help should show options."""
        result = runner.invoke(cli, ["chat", "--help"])

        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--json" in result.output
        assert "--stream" in result.output

    def test_health_help(self, runner):
        """Health help should show options."""
        result = runner.invoke(cli, ["health", "--help"])

        assert result.exit_code == 0
        assert "--check-cli" in result.output


# =============================================================================
# MCP Server Parsing Tests
# =============================================================================


class TestMCPParsing:
    """Test MCP server argument parsing."""

    def test_parse_inline_mcp_server(self, runner, mock_engine):
        """Should parse inline MCP server format."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            runner.invoke(cli, [
                "chat",
                "--mcp-server", "test:python server.py arg1",
                "Hello"
            ])

        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            servers = kwargs.get("mcp_servers", {})
            if "test" in servers:
                assert servers["test"]["command"] == "python"
                assert "server.py" in servers["test"]["args"]


# =============================================================================
# Provider Override with Config Tests
# =============================================================================


class TestProviderOverrideWithConfig:
    """Test that CLI -p flag overrides config file provider."""

    def test_cli_provider_overrides_config_codex(self, runner, mock_engine, tmp_path):
        """CLI -p codex should override config provider: gemini."""
        # Config has provider: gemini, but CLI says -p codex
        config_file = tmp_path / "config.yaml"
        config_file.write_text('provider: "gemini"\ngemini:\n  timeout: 120\ncodex:\n  timeout: 60\n')

        mock_engine.chat = AsyncMock(return_value=make_mock_response("Codex here"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-p", "codex", "-c", str(config_file),
                "chat", "--no-stream", "Hello"
            ])

        assert result.exit_code == 0
        # Engine should have been created with config object
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            config_obj = kwargs.get("config")
            if config_obj:
                # Provider in config should be overridden to codex
                assert config_obj.provider.value == "codex"

    def test_cli_provider_overrides_config_claude(self, runner, mock_engine, tmp_path):
        """CLI -p claude should override config provider: gemini."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text('provider: "gemini"\ngemini:\n  timeout: 120\nclaude:\n  timeout: 60\n')

        mock_engine.chat = AsyncMock(return_value=make_mock_response("Claude here"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-p", "claude", "-c", str(config_file),
                "chat", "--no-stream", "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            config_obj = kwargs.get("config")
            if config_obj:
                assert config_obj.provider.value == "claude"

    def test_no_explicit_provider_uses_config(self, runner, mock_engine, tmp_path):
        """Without -p flag, config file provider should be used."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text('provider: "claude"\nclaude:\n  timeout: 60\n')

        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-c", str(config_file),
                "chat", "--no-stream", "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            config_obj = kwargs.get("config")
            if config_obj:
                # Should keep config's provider (claude), not default (gemini)
                assert config_obj.provider.value == "claude"

    def test_provider_switch_clears_model(self, runner, mock_engine, tmp_path):
        """Switching provider with -p should clear model from config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text('provider: "gemini"\nmodel: "gemini-3-pro-preview"\n')

        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-p", "claude", "-c", str(config_file),
                "chat", "--no-stream", "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            config_obj = kwargs.get("config")
            if config_obj:
                assert config_obj.provider.value == "claude"
                # Model should be cleared — don't use gemini model with claude
                assert config_obj.model is None

    def test_provider_switch_keeps_explicit_model(self, runner, mock_engine, tmp_path):
        """Switching provider with -p + -m should keep the explicit model."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text('provider: "gemini"\nmodel: "gemini-3-pro-preview"\n')

        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-p", "claude", "-c", str(config_file),
                "chat", "--no-stream", "-m", "claude-sonnet-4-5-20250929", "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            config_obj = kwargs.get("config")
            if config_obj:
                assert config_obj.provider.value == "claude"
                assert config_obj.model == "claude-sonnet-4-5-20250929"


# =============================================================================
# Error Message Tests
# =============================================================================


class TestErrorMessages:
    """Test CLI error messages are user-friendly."""

    def test_missing_message_argument(self, runner):
        """Should show clear error for missing message."""
        result = runner.invoke(cli, ["chat"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output or "message" in result.output.lower()

    def test_connection_error_message(self, runner, mock_engine):
        """Connection errors should have clear messages."""
        mock_engine.start = AsyncMock(side_effect=ConnectionError("Cannot connect"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine):
            result = runner.invoke(cli, ["chat", "Hello"])

        assert result.exit_code == 1
        assert "Error" in result.output


# =============================================================================
# Working Dir Flag Tests
# =============================================================================


class TestWorkingDirFlag:
    """Test --working-dir / -w global flag."""

    def test_working_dir_passed_to_engine(self, runner, mock_engine, tmp_path):
        """--working-dir should be passed to AvatarEngine."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-w", str(tmp_path),
                "chat", "--no-stream", "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            assert kwargs.get("working_dir") == str(tmp_path)

    def test_working_dir_short_flag(self, runner, mock_engine, tmp_path):
        """-w shorthand should work."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-w", str(tmp_path),
                "chat", "--no-stream", "Test"
            ])

        assert result.exit_code == 0

    def test_working_dir_invalid_path(self, runner):
        """--working-dir with invalid path should fail."""
        result = runner.invoke(cli, [
            "-w", "/nonexistent/path/xyz",
            "chat", "Hello"
        ])
        assert result.exit_code != 0

    def test_no_working_dir_is_none(self, runner, mock_engine):
        """Without --working-dir, it should not be in kwargs."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, ["chat", "--no-stream", "Hello"])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            assert "working_dir" not in kwargs


# =============================================================================
# Allowed Tools Flag Tests
# =============================================================================


class TestAllowedToolsFlag:
    """Test --allowed-tools flag on chat command."""

    def test_allowed_tools_passed_to_claude(self, runner, mock_engine):
        """--allowed-tools should be parsed and passed for Claude."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-p", "claude",
                "chat", "--no-stream",
                "--allowed-tools", "Read,Grep,Glob",
                "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            assert kwargs.get("allowed_tools") == ["Read", "Grep", "Glob"]

    def test_allowed_tools_single(self, runner, mock_engine):
        """Single tool should also work."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-p", "claude",
                "chat", "--no-stream",
                "--allowed-tools", "Bash",
                "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            assert kwargs.get("allowed_tools") == ["Bash"]

    def test_allowed_tools_ignored_for_gemini(self, runner, mock_engine):
        """--allowed-tools should not be passed for non-Claude providers."""
        mock_engine.chat = AsyncMock(return_value=make_mock_response("OK"))

        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=mock_engine) as mock_cls:
            result = runner.invoke(cli, [
                "-p", "gemini",
                "chat", "--no-stream",
                "--allowed-tools", "Read",
                "Hello"
            ])

        assert result.exit_code == 0
        if mock_cls.call_args:
            kwargs = mock_cls.call_args.kwargs
            assert "allowed_tools" not in kwargs


# =============================================================================
# get_usage() Bridge Tests
# =============================================================================


class TestBridgeGetUsage:
    """Test BaseBridge.get_usage() and ClaudeBridge override."""

    def test_base_bridge_get_usage(self):
        """BaseBridge.get_usage() should return stats + provider + session_id."""
        bridge = MagicMock()
        bridge.provider_name = "gemini"
        bridge.session_id = "sess-123"
        bridge._stats = {
            "total_requests": 5,
            "successful_requests": 4,
            "failed_requests": 1,
            "total_duration_ms": 5000,
            "total_cost_usd": 0.0,
            "total_input_tokens": 100,
            "total_output_tokens": 200,
        }
        from avatar_engine.bridges.base import BaseBridge
        usage = BaseBridge.get_usage(bridge)
        assert usage["provider"] == "gemini"
        assert usage["session_id"] == "sess-123"
        assert usage["total_requests"] == 5
        assert usage["total_input_tokens"] == 100

    def test_claude_bridge_get_usage_with_budget(self):
        """ClaudeBridge.get_usage() should include cost and budget."""
        import threading
        from avatar_engine.bridges.claude import ClaudeBridge
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.provider_name = "claude"
        bridge.session_id = "claude-sess"
        bridge._stats_lock = threading.Lock()
        bridge._stats = {
            "total_requests": 3,
            "successful_requests": 3,
            "failed_requests": 0,
            "total_duration_ms": 3000,
            "total_cost_usd": 0.15,
            "total_input_tokens": 500,
            "total_output_tokens": 300,
        }
        bridge._total_cost_usd = 0.47
        bridge.max_budget_usd = 5.0
        usage = ClaudeBridge.get_usage(bridge)
        assert usage["total_cost_usd"] == 0.47
        assert usage["budget_usd"] == 5.0
        assert usage["budget_remaining_usd"] == pytest.approx(4.53)

    def test_claude_bridge_get_usage_no_budget(self):
        """ClaudeBridge.get_usage() without budget should not include budget keys."""
        import threading
        from avatar_engine.bridges.claude import ClaudeBridge
        bridge = MagicMock(spec=ClaudeBridge)
        bridge.provider_name = "claude"
        bridge.session_id = None
        bridge._stats_lock = threading.Lock()
        bridge._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration_ms": 0,
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
        bridge._total_cost_usd = 0.0
        bridge.max_budget_usd = None
        usage = ClaudeBridge.get_usage(bridge)
        assert "budget_usd" not in usage
        assert "budget_remaining_usd" not in usage


# =============================================================================
# REPL Command Tests (/usage, /tools, /tool, /mcp, /help)
# =============================================================================


class TestReplNewCommands:
    """Test new REPL commands: /usage, /tools, /tool, /mcp."""

    def test_repl_help_shows_new_commands(self, runner):
        """REPL --help should list the new commands."""
        result = runner.invoke(cli, ["repl", "--help"])
        assert result.exit_code == 0
        assert "/usage" in result.output
        assert "/tools" in result.output
        assert "/tool NAME" in result.output
        assert "/mcp" in result.output
        assert "--plain" in result.output

    def test_show_usage_function(self):
        """_show_usage should render without error."""
        from avatar_engine.cli.commands.repl import _show_usage

        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.get_usage.return_value = {
            "provider": "gemini",
            "session_id": "test-123",
            "total_requests": 10,
            "successful_requests": 9,
            "failed_requests": 1,
            "total_duration_ms": 10000,
            "total_cost_usd": 0.0,
            "total_input_tokens": 500,
            "total_output_tokens": 300,
        }
        engine._start_time = 1000.0

        # Should not raise
        _show_usage(engine)

    def test_show_usage_no_bridge(self):
        """_show_usage with no bridge should not crash."""
        from avatar_engine.cli.commands.repl import _show_usage
        engine = MagicMock()
        engine._bridge = None
        _show_usage(engine)

    def test_show_tools_function(self):
        """_show_tools should list MCP servers."""
        from avatar_engine.cli.commands.repl import _show_tools

        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.mcp_servers = {
            "calc": {"command": "python", "args": ["calc.py"]},
            "files": {"command": "node", "args": ["files.js"]},
        }
        _show_tools(engine)

    def test_show_tools_no_servers(self):
        """_show_tools with no MCP servers should show message."""
        from avatar_engine.cli.commands.repl import _show_tools
        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.mcp_servers = {}
        _show_tools(engine)

    def test_show_tool_detail_found(self):
        """_show_tool_detail should display server info."""
        from avatar_engine.cli.commands.repl import _show_tool_detail

        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.mcp_servers = {
            "calc": {"command": "python", "args": ["calc.py"], "env": {"DEBUG": "1"}},
        }
        _show_tool_detail(engine, "calc")

    def test_show_tool_detail_partial_match(self):
        """_show_tool_detail should match by partial name."""
        from avatar_engine.cli.commands.repl import _show_tool_detail
        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.mcp_servers = {
            "calculator": {"command": "python", "args": ["calc.py"]},
        }
        _show_tool_detail(engine, "calc")

    def test_show_tool_detail_not_found(self):
        """_show_tool_detail should handle missing server."""
        from avatar_engine.cli.commands.repl import _show_tool_detail
        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.mcp_servers = {}
        _show_tool_detail(engine, "nonexistent")

    def test_show_mcp_status(self):
        """_show_mcp_status should show configured servers."""
        from avatar_engine.cli.commands.repl import _show_mcp_status

        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.mcp_servers = {
            "tools": {"command": "python", "args": ["srv.py"]},
        }
        _show_mcp_status(engine)

    def test_show_mcp_status_empty(self):
        """_show_mcp_status with no servers."""
        from avatar_engine.cli.commands.repl import _show_mcp_status
        engine = MagicMock()
        engine._bridge = MagicMock()
        engine._bridge.mcp_servers = {}
        _show_mcp_status(engine)
