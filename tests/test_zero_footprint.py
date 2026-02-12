"""
Zero Footprint Configuration Tests.

Verify that Avatar Engine writes ZERO files to the host project directory.
All config goes to temp sandbox, CLI flags, or env vars.
"""

import json
from pathlib import Path

import pytest

from avatar_engine.config_sandbox import ConfigSandbox
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.bridges.claude import ClaudeBridge


# =============================================================================
# ConfigSandbox Tests
# =============================================================================


class TestConfigSandbox:
    """Test ConfigSandbox temp file management."""

    def test_creates_temp_dir(self):
        sandbox = ConfigSandbox()
        assert sandbox.root.exists()
        assert sandbox.root.is_dir()
        assert "avatar-" in sandbox.root.name
        sandbox.cleanup()

    def test_cleanup_removes_all(self):
        sandbox = ConfigSandbox()
        root = sandbox.root
        sandbox.write_gemini_settings({"previewFeatures": True})
        sandbox.write_system_prompt("test")
        sandbox.write_mcp_config({"t": {"command": "x", "args": []}})
        assert any(root.iterdir())  # has files
        sandbox.cleanup()
        assert not root.exists()

    def test_cleanup_idempotent(self):
        sandbox = ConfigSandbox()
        sandbox.cleanup()
        sandbox.cleanup()  # should not raise

    def test_write_gemini_settings(self):
        sandbox = ConfigSandbox()
        path = sandbox.write_gemini_settings(
            {"model": {"name": "test"}, "previewFeatures": True}
        )
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["model"]["name"] == "test"
        assert data["previewFeatures"] is True
        sandbox.cleanup()

    def test_write_system_prompt(self):
        sandbox = ConfigSandbox()
        path = sandbox.write_system_prompt("Jsi AI avatar.")
        assert path.exists()
        assert path.read_text() == "Jsi AI avatar."
        sandbox.cleanup()

    def test_write_mcp_config(self):
        sandbox = ConfigSandbox()
        servers = {
            "tools": {"command": "python", "args": ["mcp.py"], "env": {"K": "V"}}
        }
        path = sandbox.write_mcp_config(servers)
        data = json.loads(path.read_text())
        assert "mcpServers" in data
        assert data["mcpServers"]["tools"]["command"] == "python"
        assert data["mcpServers"]["tools"]["env"]["K"] == "V"
        sandbox.cleanup()

    def test_write_mcp_config_no_env(self):
        sandbox = ConfigSandbox()
        servers = {"tools": {"command": "python", "args": ["mcp.py"]}}
        path = sandbox.write_mcp_config(servers)
        data = json.loads(path.read_text())
        assert "env" not in data["mcpServers"]["tools"]
        sandbox.cleanup()

    def test_write_claude_settings(self):
        sandbox = ConfigSandbox()
        path = sandbox.write_claude_settings(
            {"permissions": {"allow": ["Read"]}}
        )
        data = json.loads(path.read_text())
        assert data["permissions"]["allow"] == ["Read"]
        sandbox.cleanup()

    def test_write_json_schema(self):
        sandbox = ConfigSandbox()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        path = sandbox.write_json_schema(schema)
        data = json.loads(path.read_text())
        assert data["type"] == "object"
        sandbox.cleanup()

    def test_multiple_sandboxes_isolated(self):
        s1 = ConfigSandbox(session_id="aaa")
        s2 = ConfigSandbox(session_id="bbb")
        assert s1.root != s2.root
        s1.write_gemini_settings({"x": 1})
        s2.write_gemini_settings({"x": 2})
        assert json.loads((s1.root / "gemini-settings.json").read_text())["x"] == 1
        assert json.loads((s2.root / "gemini-settings.json").read_text())["x"] == 2
        s1.cleanup()
        s2.cleanup()

    def test_session_id_in_dirname(self):
        sandbox = ConfigSandbox(session_id="myid123")
        assert "avatar-myid123-" in sandbox.root.name
        sandbox.cleanup()


# =============================================================================
# Gemini Bridge Zero Footprint Tests
# =============================================================================


class TestGeminiBridgeZeroFootprint:
    """Verify Gemini bridge writes ZERO files to working_dir."""

    def test_no_files_in_working_dir_acp(self, tmp_path):
        """ACP mode: _setup_config_files must not create any files in working_dir."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            system_prompt="Test prompt",
            generation_config={"temperature": 0.7},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # working_dir must be completely untouched
        assert not (tmp_path / ".gemini").exists()
        assert not (tmp_path / "GEMINI.md").exists()
        assert list(tmp_path.iterdir()) == []
        bridge._sandbox.cleanup()

    def test_no_files_in_working_dir_oneshot(self, tmp_path):
        """Oneshot mode: _setup_config_files must not create any files in working_dir."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            system_prompt="Test prompt",
            generation_config={"temperature": 0.7},
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert not (tmp_path / ".gemini").exists()
        assert not (tmp_path / "GEMINI.md").exists()
        assert list(tmp_path.iterdir()) == []
        bridge._sandbox.cleanup()

    def test_sandbox_has_settings_oneshot(self, tmp_path):
        """Sandbox must contain gemini-settings.json in oneshot mode."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert bridge._sandbox is not None
        settings_path = bridge._sandbox.root / "gemini-settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text())
        assert data["model"]["name"] == "gemini-3-pro-preview"
        bridge._sandbox.cleanup()

    def test_sandbox_has_settings_acp(self, tmp_path):
        """ACP mode writes customOverrides for generation config."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert bridge._sandbox is not None
        assert bridge._gemini_settings_path is not None
        data = json.loads(bridge._gemini_settings_path.read_text())
        # Must have customOverrides but NOT model.name
        assert "model" not in data
        assert "modelConfigs" in data
        overrides = data["modelConfigs"]["customOverrides"]
        assert len(overrides) == 1
        assert overrides[0]["match"]["model"] == "gemini-3-pro-preview"
        # Default model → no customAliases
        assert "customAliases" not in data["modelConfigs"]
        bridge._sandbox.cleanup()

    def test_sandbox_has_system_prompt(self, tmp_path):
        """Sandbox must contain system.md when system_prompt is set."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            system_prompt="Jsi avatar.",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        prompt_path = bridge._sandbox.root / "system.md"
        assert prompt_path.exists()
        assert prompt_path.read_text() == "Jsi avatar."
        bridge._sandbox.cleanup()

    def test_env_has_system_settings_path(self, tmp_path):
        """_build_subprocess_env must set GEMINI_CLI_SYSTEM_SETTINGS_PATH in oneshot mode."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        env = bridge._build_subprocess_env()

        assert "GEMINI_CLI_SYSTEM_SETTINGS_PATH" in env
        assert Path(env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"]).exists()
        bridge._sandbox.cleanup()

    def test_env_has_system_settings_path_acp(self, tmp_path):
        """ACP mode sets GEMINI_CLI_SYSTEM_SETTINGS_PATH for customAliases."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        env = bridge._build_subprocess_env()

        assert "GEMINI_CLI_SYSTEM_SETTINGS_PATH" in env
        assert Path(env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"]).exists()
        bridge._sandbox.cleanup()

    def test_env_has_system_md_when_prompt_set(self, tmp_path):
        """_build_subprocess_env must set GEMINI_SYSTEM_MD when system_prompt is provided."""
        bridge = GeminiBridge(
            system_prompt="Hello",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        env = bridge._build_subprocess_env()

        assert "GEMINI_SYSTEM_MD" in env
        assert Path(env["GEMINI_SYSTEM_MD"]).exists()
        bridge._sandbox.cleanup()

    def test_env_no_system_md_when_no_prompt(self, tmp_path):
        """_build_subprocess_env must NOT set GEMINI_SYSTEM_MD when no system_prompt."""
        bridge = GeminiBridge(working_dir=str(tmp_path))
        bridge._setup_config_files()
        env = bridge._build_subprocess_env()

        assert "GEMINI_SYSTEM_MD" not in env
        bridge._sandbox.cleanup()

    def test_acp_settings_has_custom_overrides(self, tmp_path):
        """ACP mode writes settings with customOverrides for generation config."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            generation_config={"temperature": 0.5},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert bridge._gemini_settings_path is not None
        data = json.loads(bridge._gemini_settings_path.read_text())
        overrides = data["modelConfigs"]["customOverrides"]
        assert overrides[0]["modelConfig"]["generateContentConfig"]["temperature"] == 0.5
        # Default model → no customAliases
        assert "customAliases" not in data["modelConfigs"]
        # model.name must NOT be in top-level
        assert "model" not in data
        bridge._sandbox.cleanup()

    def test_oneshot_settings_have_custom_aliases(self, tmp_path):
        """Oneshot mode sandbox settings must include customAliases."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            generation_config={"temperature": 0.5},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        data = json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )
        assert "modelConfigs" in data
        alias = data["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]
        assert alias["modelConfig"]["generateContentConfig"]["temperature"] == 0.5
        bridge._sandbox.cleanup()

    def test_acp_settings_always_generated(self, tmp_path):
        """ACP mode always generates settings (to bypass auto classifier)."""
        bridge = GeminiBridge(
            acp_enabled=True,
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # ACP always generates settings with default model + customOverrides
        assert bridge._gemini_settings_path is not None
        data = json.loads(bridge._gemini_settings_path.read_text())
        assert data["model"]["name"] == "gemini-3-pro-preview"
        # MCP servers NOT in settings (passed via ACP protocol)
        assert "mcpServers" not in data
        bridge._sandbox.cleanup()

    def test_oneshot_settings_have_mcp_servers(self, tmp_path):
        """Oneshot mode must include MCP servers in sandbox settings."""
        bridge = GeminiBridge(
            acp_enabled=False,
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        data = json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )
        assert "mcpServers" in data
        assert "tools" in data["mcpServers"]
        bridge._sandbox.cleanup()

    def test_oneshot_settings_thinking_config(self, tmp_path):
        """Oneshot settings must include thinkingConfig in customAliases."""
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

        data = json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )
        gen_cfg = data["modelConfigs"]["customAliases"]["gemini-3-pro-preview"][
            "modelConfig"
        ]["generateContentConfig"]
        assert gen_cfg["temperature"] == 0.8
        assert gen_cfg["thinkingConfig"]["thinkingLevel"] == "HIGH"
        assert gen_cfg["thinkingConfig"]["includeThoughts"] is True
        bridge._sandbox.cleanup()

    def test_host_files_preserved(self, tmp_path):
        """Host app's existing .gemini/ and GEMINI.md must not be touched."""
        # Create host app's config
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        (gemini_dir / "settings.json").write_text('{"host": true}')
        (tmp_path / "GEMINI.md").write_text("Host instructions")

        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            system_prompt="Avatar prompt",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # Host files unchanged
        assert json.loads((gemini_dir / "settings.json").read_text()) == {"host": True}
        assert (tmp_path / "GEMINI.md").read_text() == "Host instructions"
        bridge._sandbox.cleanup()


# =============================================================================
# Claude Bridge Zero Footprint Tests
# =============================================================================


class TestClaudeBridgeZeroFootprint:
    """Verify Claude bridge writes ZERO files to working_dir."""

    def test_no_files_in_working_dir(self, tmp_path):
        """_setup_config_files must not create any files in working_dir."""
        bridge = ClaudeBridge(
            model="claude-sonnet-4-5",
            system_prompt="Test",
            allowed_tools=["Read", "Grep"],
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            json_schema={"type": "object"},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # working_dir must be completely untouched
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / "mcp_servers.json").exists()
        assert not (tmp_path / ".claude_schema.json").exists()
        assert list(tmp_path.iterdir()) == []
        bridge._sandbox.cleanup()

    def test_command_has_settings_flag(self, tmp_path):
        """Persistent command must use --settings flag."""
        bridge = ClaudeBridge(
            allowed_tools=["Read"],
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--settings" in cmd
        settings_idx = cmd.index("--settings")
        settings_path = cmd[settings_idx + 1]
        assert Path(settings_path).exists()
        # Settings file must NOT be in working_dir
        assert str(tmp_path) not in settings_path
        bridge._sandbox.cleanup()

    def test_command_has_mcp_config_in_sandbox(self, tmp_path):
        """--mcp-config must point to sandbox, not working_dir."""
        bridge = ClaudeBridge(
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--mcp-config" in cmd
        mcp_idx = cmd.index("--mcp-config")
        mcp_path = cmd[mcp_idx + 1]
        # MCP config must NOT be in working_dir
        assert str(tmp_path) not in mcp_path
        assert Path(mcp_path).exists()
        bridge._sandbox.cleanup()

    def test_no_mcp_config_when_no_servers(self, tmp_path):
        """--mcp-config must not appear when no MCP servers configured."""
        bridge = ClaudeBridge(working_dir=str(tmp_path))
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--mcp-config" not in cmd
        bridge._sandbox.cleanup()

    def test_no_claude_md_written(self, tmp_path):
        """CLAUDE.md must NOT be written (--append-system-prompt used instead)."""
        bridge = ClaudeBridge(
            system_prompt="Test prompt",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert not (tmp_path / "CLAUDE.md").exists()
        bridge._sandbox.cleanup()

    def test_command_has_append_system_prompt(self, tmp_path):
        """System prompt must be passed via --append-system-prompt flag."""
        bridge = ClaudeBridge(
            system_prompt="Jsi avatar.",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--append-system-prompt" in cmd
        idx = cmd.index("--append-system-prompt")
        assert cmd[idx + 1] == "Jsi avatar."
        bridge._sandbox.cleanup()

    def test_no_system_prompt_flag_when_empty(self, tmp_path):
        """No --append-system-prompt when system_prompt is empty."""
        bridge = ClaudeBridge(working_dir=str(tmp_path))
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--append-system-prompt" not in cmd
        bridge._sandbox.cleanup()

    def test_json_schema_in_sandbox(self, tmp_path):
        """--json-schema must point to sandbox temp file."""
        bridge = ClaudeBridge(
            json_schema={"type": "object"},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--json-schema" in cmd
        idx = cmd.index("--json-schema")
        schema_path = cmd[idx + 1]
        # Schema must NOT be in working_dir
        assert str(tmp_path) not in schema_path
        assert Path(schema_path).exists()
        bridge._sandbox.cleanup()

    def test_no_json_schema_when_not_set(self, tmp_path):
        """--json-schema must not appear when not configured."""
        bridge = ClaudeBridge(working_dir=str(tmp_path))
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--json-schema" not in cmd
        bridge._sandbox.cleanup()

    def test_settings_contain_permissions(self, tmp_path):
        """Sandbox settings must contain permissions from allowed_tools."""
        bridge = ClaudeBridge(
            allowed_tools=["Read", "Grep", "mcp__tools__*"],
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        data = json.loads(bridge._claude_settings_path.read_text())
        assert data["permissions"]["allow"] == ["Read", "Grep", "mcp__tools__*"]
        bridge._sandbox.cleanup()

    def test_host_files_preserved(self, tmp_path):
        """Host app's existing .claude/ and CLAUDE.md must not be touched."""
        # Create host app's config
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text('{"host": true}')
        (tmp_path / "CLAUDE.md").write_text("Host instructions")

        bridge = ClaudeBridge(
            system_prompt="Avatar prompt",
            allowed_tools=["Read"],
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # Host files unchanged
        assert json.loads((claude_dir / "settings.json").read_text()) == {"host": True}
        assert (tmp_path / "CLAUDE.md").read_text() == "Host instructions"
        bridge._sandbox.cleanup()


# =============================================================================
# Integration: Sandbox Lifecycle Tests
# =============================================================================


class TestSandboxLifecycle:
    """Test sandbox creation and cleanup through bridge lifecycle."""

    @pytest.mark.asyncio
    async def test_gemini_sandbox_cleaned_on_stop(self, tmp_path):
        """Sandbox must be cleaned when bridge.stop() is called."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        sandbox_root = bridge._sandbox.root
        assert sandbox_root.exists()

        await bridge.stop()
        assert not sandbox_root.exists()
        assert bridge._sandbox is None

    @pytest.mark.asyncio
    async def test_claude_sandbox_cleaned_on_stop(self, tmp_path):
        """Sandbox must be cleaned when bridge.stop() is called."""
        bridge = ClaudeBridge(working_dir=str(tmp_path))
        bridge._setup_config_files()
        sandbox_root = bridge._sandbox.root
        assert sandbox_root.exists()

        await bridge.stop()
        assert not sandbox_root.exists()
        assert bridge._sandbox is None

    @pytest.mark.asyncio
    async def test_stop_without_setup_no_error(self, tmp_path):
        """stop() must not fail if _setup_config_files was never called."""
        bridge = GeminiBridge(working_dir=str(tmp_path))
        await bridge.stop()  # should not raise

    def test_concurrent_sandboxes_isolated(self, tmp_path):
        """Two bridge instances must have separate sandboxes."""
        bridge_a = GeminiBridge(
            system_prompt="Avatar A",
            working_dir=str(tmp_path),
        )
        bridge_b = GeminiBridge(
            system_prompt="Avatar B",
            working_dir=str(tmp_path),
        )

        bridge_a._setup_config_files()
        bridge_b._setup_config_files()

        assert bridge_a._sandbox.root != bridge_b._sandbox.root

        prompt_a = (bridge_a._sandbox.root / "system.md").read_text()
        prompt_b = (bridge_b._sandbox.root / "system.md").read_text()
        assert prompt_a == "Avatar A"
        assert prompt_b == "Avatar B"

        # No files in working_dir
        assert not (tmp_path / ".gemini").exists()
        assert not (tmp_path / "GEMINI.md").exists()

        bridge_a._sandbox.cleanup()
        bridge_b._sandbox.cleanup()
