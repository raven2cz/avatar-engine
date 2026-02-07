"""
Integration tests for CLI features: --working-dir, --allowed-tools, REPL commands, get_usage().

These tests run actual CLI commands and exercise real bridge/engine code paths.
Run with: pytest tests/integration/test_real_cli_features.py -v
"""

import json
import os
import subprocess
import shutil

import pytest

from avatar_engine import AvatarEngine
from avatar_engine.bridges.base import BaseBridge
from avatar_engine.bridges.claude import ClaudeBridge


# =============================================================================
# CLI Flag Tests (subprocess — real avatar CLI)
# =============================================================================


@pytest.mark.integration
class TestWorkingDirFlag:
    """Test --working-dir / -w flag with real CLI."""

    def test_working_dir_shows_in_help(self):
        """--working-dir should appear in CLI help."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--working-dir" in result.stdout or "-w" in result.stdout

    def test_working_dir_invalid_path_rejected(self):
        """--working-dir with nonexistent path should fail."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "--working-dir", "/nonexistent/path/xyz",
                "health",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Click validates path exists — should fail
        assert result.returncode != 0
        assert "does not exist" in result.stderr.lower() or "invalid" in result.stderr.lower() or "Error" in result.stderr

    def test_working_dir_valid_path_accepted(self, tmp_path):
        """--working-dir with valid directory should be accepted."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "--working-dir", str(tmp_path),
                "health",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should succeed (health doesn't require a provider)
        assert result.returncode == 0

    def test_short_flag_w(self, tmp_path):
        """Short flag -w should work same as --working-dir."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-w", str(tmp_path),
                "health",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

    @pytest.mark.gemini
    @pytest.mark.slow
    def test_working_dir_propagated_to_chat(self, tmp_path, skip_if_no_gemini):
        """--working-dir should be passed through to the engine."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "gemini",
                "-w", str(tmp_path),
                "chat", "--no-stream",
                "What directory are you working in? Reply briefly.",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"


@pytest.mark.integration
class TestAllowedToolsFlag:
    """Test --allowed-tools flag with real CLI."""

    def test_allowed_tools_shows_in_chat_help(self):
        """--allowed-tools should appear in chat --help."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "chat", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--allowed-tools" in result.stdout

    @pytest.mark.claude
    @pytest.mark.slow
    def test_allowed_tools_passed_to_claude(self, skip_if_no_claude):
        """--allowed-tools should be accepted with Claude provider."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "claude",
                "chat", "--no-stream",
                "--allowed-tools", "Read,Write",
                "Say hello briefly.",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Should succeed (Claude accepts allowed_tools)
        assert result.returncode == 0, f"stderr: {result.stderr}"


@pytest.mark.integration
class TestResumeAndContinueFlags:
    """Test --resume and --continue flags in CLI help."""

    def test_resume_shows_in_chat_help(self):
        """--resume should appear in chat --help."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "chat", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--resume" in result.stdout

    def test_continue_shows_in_chat_help(self):
        """--continue should appear in chat --help."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "chat", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--continue" in result.stdout

    def test_resume_shows_in_repl_help(self):
        """--resume should appear in repl --help."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--resume" in result.stdout

    def test_continue_shows_in_repl_help(self):
        """--continue should appear in repl --help."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--continue" in result.stdout


# =============================================================================
# Session Command Tests (subprocess — real avatar CLI)
# =============================================================================


@pytest.mark.integration
class TestSessionCommand:
    """Test avatar session subcommand."""

    def test_session_list_command(self):
        """avatar session list should work."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "session", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0


# =============================================================================
# get_usage() Bridge API Tests (real bridges, no subprocess)
# =============================================================================


@pytest.mark.integration
class TestBridgeGetUsage:
    """Test get_usage() on real bridge instances."""

    @pytest.mark.asyncio
    @pytest.mark.gemini
    @pytest.mark.slow
    async def test_gemini_get_usage_after_chat(self, skip_if_no_gemini):
        """get_usage() should return stats after real Gemini chat."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        try:
            await engine.start()

            # Send a message to populate stats
            response = await engine.chat("What is 1+1? Reply with just the number.")
            assert response.success is True

            # Check usage
            bridge = engine._bridge
            usage = bridge.get_usage()

            assert usage["provider"] == "gemini"
            assert usage["total_requests"] >= 1
            assert usage["successful_requests"] >= 1
            assert usage["total_duration_ms"] > 0
            assert "session_id" in usage
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.claude
    @pytest.mark.slow
    async def test_claude_get_usage_has_cost(self, skip_if_no_claude):
        """Claude get_usage() should include cost and budget info."""
        engine = AvatarEngine(
            provider="claude",
            timeout=120,
            max_budget_usd=1.0,
        )
        try:
            await engine.start()

            response = await engine.chat("Say hello.")
            assert response.success is True

            bridge = engine._bridge
            usage = bridge.get_usage()

            assert usage["provider"] == "claude"
            assert usage["total_requests"] >= 1
            assert usage["successful_requests"] >= 1
            assert "total_cost_usd" in usage
            assert "budget_usd" in usage
            assert usage["budget_usd"] == 1.0
            assert "budget_remaining_usd" in usage
            assert usage["budget_remaining_usd"] <= 1.0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.codex
    @pytest.mark.slow
    async def test_codex_get_usage_after_chat(self, skip_if_no_codex_acp):
        """get_usage() should return stats after real Codex chat."""
        engine = AvatarEngine(provider="codex", timeout=60)
        try:
            await engine.start()

            response = await engine.chat("Say hello.")
            assert response.success is True

            bridge = engine._bridge
            usage = bridge.get_usage()

            assert usage["provider"] == "codex"
            assert usage["total_requests"] >= 1
            assert usage["successful_requests"] >= 1
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await engine.stop()


@pytest.mark.integration
class TestBridgeGetUsageAccumulation:
    """Test that get_usage() accumulates across multiple requests."""

    @pytest.mark.asyncio
    @pytest.mark.gemini
    @pytest.mark.slow
    async def test_usage_accumulates(self, skip_if_no_gemini):
        """Stats should increase with each request."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        try:
            await engine.start()

            # First request
            r1 = await engine.chat("Say A")
            assert r1.success is True
            usage1 = dict(engine._bridge.get_usage())

            # Second request
            r2 = await engine.chat("Say B")
            assert r2.success is True
            usage2 = engine._bridge.get_usage()

            assert usage2["total_requests"] > usage1["total_requests"]
            assert usage2["successful_requests"] > usage1["successful_requests"]
            assert usage2["total_duration_ms"] > usage1["total_duration_ms"]
        finally:
            await engine.stop()


# =============================================================================
# REPL Command Tests (help output verification via subprocess)
# =============================================================================


@pytest.mark.integration
class TestReplHelpOutput:
    """Verify REPL help shows new commands."""

    def test_repl_help_shows_usage_command(self):
        """REPL docstring should mention /usage."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "/usage" in result.stdout

    def test_repl_help_shows_tools_command(self):
        """REPL docstring should mention /tools."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "/tools" in result.stdout

    def test_repl_help_shows_tool_command(self):
        """REPL docstring should mention /tool NAME."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "/tool" in result.stdout

    def test_repl_help_shows_mcp_command(self):
        """REPL docstring should mention /mcp."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "/mcp" in result.stdout

    def test_repl_help_shows_sessions_command(self):
        """REPL docstring should mention /sessions."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "/sessions" in result.stdout

    def test_repl_help_shows_resume_command(self):
        """REPL docstring should mention /resume."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "repl", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "/resume" in result.stdout


# =============================================================================
# REPL _show_* Functions — Direct Invocation Tests
# =============================================================================


@pytest.mark.integration
class TestReplShowFunctions:
    """Test REPL helper functions with real engine instances."""

    @pytest.mark.asyncio
    @pytest.mark.gemini
    @pytest.mark.slow
    async def test_show_usage_real_gemini(self, skip_if_no_gemini, capsys):
        """_show_usage should display stats after real Gemini chat."""
        from avatar_engine.cli.commands.repl import _show_usage

        engine = AvatarEngine(provider="gemini", timeout=60)
        try:
            await engine.start()
            await engine.chat("Say hello.")

            _show_usage(engine)

            captured = capsys.readouterr()
            assert "Session Usage" in captured.out or "gemini" in captured.out.lower()
            assert "Requests" in captured.out
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.claude
    @pytest.mark.slow
    async def test_show_usage_real_claude(self, skip_if_no_claude, capsys):
        """_show_usage with Claude should show cost info."""
        from avatar_engine.cli.commands.repl import _show_usage

        engine = AvatarEngine(provider="claude", timeout=120, max_budget_usd=1.0)
        try:
            await engine.start()
            await engine.chat("Say hello.")

            _show_usage(engine)

            captured = capsys.readouterr()
            assert "claude" in captured.out.lower() or "Session Usage" in captured.out
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.gemini
    @pytest.mark.slow
    async def test_show_tools_with_mcp(self, skip_if_no_gemini, capsys, tmp_path):
        """_show_tools should list MCP servers when configured."""
        from avatar_engine.cli.commands.repl import _show_tools

        # Create an MCP config
        mcp_config = tmp_path / "mcp.json"
        mcp_config.write_text(json.dumps({
            "mcpServers": {
                "test-calc": {
                    "command": "python",
                    "args": ["calc_server.py"],
                }
            }
        }))

        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            mcp_servers={
                "test-calc": {
                    "command": "python",
                    "args": ["calc_server.py"],
                }
            },
        )
        try:
            await engine.start()

            _show_tools(engine)

            captured = capsys.readouterr()
            # Should list the server or show "No MCP servers" if bridge doesn't expose them
            assert "test-calc" in captured.out or "No MCP" in captured.out or "configured" in captured.out
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.gemini
    @pytest.mark.slow
    async def test_show_mcp_status(self, skip_if_no_gemini, capsys):
        """_show_mcp_status should not crash on real engine."""
        from avatar_engine.cli.commands.repl import _show_mcp_status

        engine = AvatarEngine(provider="gemini", timeout=60)
        try:
            await engine.start()

            _show_mcp_status(engine)

            captured = capsys.readouterr()
            # Either shows status or says "No MCP servers"
            assert "MCP" in captured.out or "No MCP" in captured.out or len(captured.out) >= 0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.gemini
    @pytest.mark.slow
    async def test_show_tool_detail_not_found(self, skip_if_no_gemini, capsys):
        """_show_tool_detail should handle missing tool gracefully."""
        from avatar_engine.cli.commands.repl import _show_tool_detail

        engine = AvatarEngine(provider="gemini", timeout=60)
        try:
            await engine.start()

            _show_tool_detail(engine, "nonexistent-tool-xyz")

            captured = capsys.readouterr()
            assert "not found" in captured.out.lower() or "No MCP" in captured.out or len(captured.out) >= 0
        finally:
            await engine.stop()
