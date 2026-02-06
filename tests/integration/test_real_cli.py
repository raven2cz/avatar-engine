"""
Real CLI integration tests.

These tests run actual CLI commands with real providers.
Run with: pytest tests/integration/test_real_cli.py -v
"""

import subprocess
import pytest


# =============================================================================
# CLI Availability Tests
# =============================================================================


@pytest.mark.integration
class TestCLIAvailability:
    """Test that CLI tools are available."""

    def test_avatar_cli_installed(self):
        """Avatar CLI should be available."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "avatar" in result.stdout.lower() or "Usage" in result.stdout

    def test_avatar_version(self):
        """Avatar version command should work."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_avatar_health_check_cli(self):
        """Avatar health --check-cli should work."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "health", "--check-cli"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        # Should show tool status
        assert "claude" in result.stdout.lower() or "gemini" in result.stdout.lower()


# =============================================================================
# Real Chat CLI Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiCLI:
    """Real Gemini CLI tests."""

    def test_chat_command_basic(self, skip_if_no_gemini):
        """avatar chat should work with Gemini."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "gemini",
                "chat", "--no-stream",
                "What is 2+2? Reply with just the number."
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "4" in result.stdout

    def test_chat_command_json(self, skip_if_no_gemini):
        """avatar chat --json should output valid JSON."""
        import json

        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "gemini",
                "chat", "--json", "--no-stream",
                "Say hello"
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Extract last JSON object from stdout (logging may precede it)
        lines = result.stdout.strip().splitlines()
        json_str = ""
        for line in reversed(lines):
            json_str = line + json_str
            try:
                data = json.loads(json_str)
                break
            except json.JSONDecodeError:
                json_str = "\n" + json_str
                continue
        else:
            # Try finding JSON by looking for the opening brace
            start = result.stdout.rfind("{")
            assert start >= 0, f"No JSON found in stdout: {result.stdout[:500]}"
            data = json.loads(result.stdout[start:])

        assert "content" in data
        assert "success" in data
        assert data["success"] is True

    def test_chat_command_streaming(self, skip_if_no_gemini):
        """avatar chat --stream should stream output."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "gemini",
                "chat", "--stream",
                "Count from 1 to 5."
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should have some output
        assert len(result.stdout) > 0


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.slow
class TestClaudeCLI:
    """Real Claude CLI tests."""

    def test_chat_command_basic(self, skip_if_no_claude):
        """avatar chat should work with Claude."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "claude",
                "chat", "--no-stream",
                "What is 2+2? Reply with just the number."
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "4" in result.stdout

    def test_chat_command_json(self, skip_if_no_claude):
        """avatar chat --json should output valid JSON for Claude."""
        import json

        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "claude",
                "chat", "--json", "--no-stream",
                "Say hello"
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Extract last JSON object from stdout (logging may precede it)
        start = result.stdout.rfind("{")
        assert start >= 0, f"No JSON found in stdout: {result.stdout[:500]}"
        data = json.loads(result.stdout[start:])
        assert data["success"] is True


# =============================================================================
# MCP CLI Tests
# =============================================================================


@pytest.mark.integration
class TestMCPCLI:
    """MCP command tests."""

    def test_mcp_list(self):
        """avatar mcp list should work."""
        result = subprocess.run(
            ["python", "-m", "avatar_engine.cli", "mcp", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_mcp_add_remove(self, tmp_path):
        """avatar mcp add/remove should work."""
        config = tmp_path / "mcp.json"

        # Add server
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "mcp", "add", "test-server", "python", "server.py",
                "--config", str(config)
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert config.exists()

        # Verify content
        import json
        data = json.loads(config.read_text())
        assert "test-server" in data.get("mcpServers", {})

        # Remove server
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "mcp", "remove", "test-server",
                "--config", str(config)
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

        # Verify removed
        data = json.loads(config.read_text())
        assert "test-server" not in data.get("mcpServers", {})


# =============================================================================
# Health CLI Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestHealthCLI:
    """Health command tests with real providers."""

    def test_health_gemini(self, skip_if_no_gemini):
        """avatar health should work with Gemini."""
        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "-p", "gemini",
                "health"
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0
        assert "healthy" in result.stdout.lower() or "Bridge" in result.stdout
