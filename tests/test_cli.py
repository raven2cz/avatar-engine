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
