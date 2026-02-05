"""Tests for avatar_engine.config module."""

import os
import tempfile
import pytest
from pathlib import Path

from avatar_engine.config import AvatarConfig
from avatar_engine.types import ProviderType


class TestAvatarConfigFromDict:
    """Tests for AvatarConfig.from_dict()."""

    def test_default_values(self):
        """Empty dict should use sensible defaults."""
        config = AvatarConfig.from_dict({})

        assert config.provider == ProviderType.GEMINI
        assert config.model is None
        assert config.timeout == 120
        assert config.max_history == 100
        assert config.auto_restart is True
        assert config.max_restarts == 3
        assert config.log_level == "INFO"

    def test_provider_gemini(self):
        """Should parse gemini provider correctly."""
        config = AvatarConfig.from_dict({"provider": "gemini"})
        assert config.provider == ProviderType.GEMINI

    def test_provider_claude(self):
        """Should parse claude provider correctly."""
        config = AvatarConfig.from_dict({"provider": "claude"})
        assert config.provider == ProviderType.CLAUDE

    def test_provider_case_insensitive(self):
        """Provider should be case-insensitive."""
        config = AvatarConfig.from_dict({"provider": "GEMINI"})
        assert config.provider == ProviderType.GEMINI

    def test_gemini_config(self):
        """Should extract gemini-specific config."""
        data = {
            "provider": "gemini",
            "gemini": {
                "model": "gemini-3-pro-preview",
                "timeout": 180,
                "approval_mode": "yolo",
                "generation_config": {
                    "temperature": 0.8,
                    "thinking_level": "high",
                },
            },
        }
        config = AvatarConfig.from_dict(data)

        assert config.model == "gemini-3-pro-preview"
        assert config.timeout == 180
        assert config.gemini_config["approval_mode"] == "yolo"
        assert config.gemini_config["generation_config"]["temperature"] == 0.8

    def test_claude_config(self):
        """Should extract claude-specific config."""
        data = {
            "provider": "claude",
            "claude": {
                "model": "claude-sonnet-4-5",
                "timeout": 90,
                "permission_mode": "acceptEdits",
                "allowed_tools": ["Read", "Edit"],
            },
        }
        config = AvatarConfig.from_dict(data)

        assert config.model == "claude-sonnet-4-5"
        assert config.timeout == 90
        assert config.claude_config["permission_mode"] == "acceptEdits"
        assert config.claude_config["allowed_tools"] == ["Read", "Edit"]

    def test_engine_config(self):
        """Should extract engine settings."""
        data = {
            "engine": {
                "working_dir": "/tmp/test",
                "max_history": 50,
                "auto_restart": False,
                "max_restarts": 5,
            },
        }
        config = AvatarConfig.from_dict(data)

        assert config.working_dir == "/tmp/test"
        assert config.max_history == 50
        assert config.auto_restart is False
        assert config.max_restarts == 5

    def test_avatar_config_alias(self):
        """'avatar' key should work as alias for 'engine'."""
        data = {
            "avatar": {
                "max_history": 200,
            },
        }
        config = AvatarConfig.from_dict(data)
        assert config.max_history == 200

    def test_logging_config(self):
        """Should extract logging settings."""
        data = {
            "logging": {
                "level": "DEBUG",
                "file": "/var/log/avatar.log",
            },
        }
        config = AvatarConfig.from_dict(data)

        assert config.log_level == "DEBUG"
        assert config.log_file == "/var/log/avatar.log"

    def test_provider_kwargs(self):
        """provider_kwargs should contain non-common fields."""
        data = {
            "provider": "gemini",
            "gemini": {
                "model": "test",
                "timeout": 60,
                "approval_mode": "yolo",
                "auth_method": "oauth-personal",
                "acp_enabled": True,
            },
        }
        config = AvatarConfig.from_dict(data)

        # Common fields should not be in kwargs
        assert "model" not in config.provider_kwargs
        assert "timeout" not in config.provider_kwargs

        # Provider-specific fields should be in kwargs
        assert config.provider_kwargs["approval_mode"] == "yolo"
        assert config.provider_kwargs["auth_method"] == "oauth-personal"
        assert config.provider_kwargs["acp_enabled"] is True


class TestAvatarConfigLoad:
    """Tests for AvatarConfig.load() from YAML files."""

    def test_load_simple_yaml(self):
        """Should load simple YAML config."""
        yaml_content = """
provider: claude
claude:
  model: claude-sonnet-4-5
  timeout: 60
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            try:
                config = AvatarConfig.load(f.name)
                assert config.provider == ProviderType.CLAUDE
                assert config.model == "claude-sonnet-4-5"
                assert config.timeout == 60
            finally:
                os.unlink(f.name)

    def test_load_full_yaml(self):
        """Should load full YAML config with all sections."""
        yaml_content = """
provider: gemini

gemini:
  model: gemini-3-pro-preview
  timeout: 120
  approval_mode: yolo
  generation_config:
    temperature: 1.0
    thinking_level: high

engine:
  working_dir: /tmp/avatar
  max_history: 100

logging:
  level: INFO
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            try:
                config = AvatarConfig.load(f.name)
                assert config.provider == ProviderType.GEMINI
                assert config.model == "gemini-3-pro-preview"
                assert config.working_dir == "/tmp/avatar"
                assert config.gemini_config["generation_config"]["thinking_level"] == "high"
            finally:
                os.unlink(f.name)

    def test_load_nonexistent_file(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            AvatarConfig.load("/nonexistent/path/config.yaml")

    def test_load_empty_yaml(self):
        """Should handle empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            try:
                config = AvatarConfig.load(f.name)
                assert config.provider == ProviderType.GEMINI  # Default
            finally:
                os.unlink(f.name)


class TestAvatarConfigMethods:
    """Tests for AvatarConfig helper methods."""

    def test_get_provider_config_gemini(self):
        """get_provider_config should return gemini config for gemini provider."""
        config = AvatarConfig.from_dict({
            "provider": "gemini",
            "gemini": {"model": "test-model"},
            "claude": {"model": "other-model"},
        })
        pcfg = config.get_provider_config()
        assert pcfg["model"] == "test-model"

    def test_get_provider_config_claude(self):
        """get_provider_config should return claude config for claude provider."""
        config = AvatarConfig.from_dict({
            "provider": "claude",
            "gemini": {"model": "test-model"},
            "claude": {"model": "other-model"},
        })
        pcfg = config.get_provider_config()
        assert pcfg["model"] == "other-model"

    def test_get_working_dir_empty(self):
        """get_working_dir should return cwd when empty."""
        config = AvatarConfig.from_dict({})
        wd = config.get_working_dir()
        assert wd == os.getcwd()

    def test_get_working_dir_absolute(self):
        """get_working_dir should handle absolute paths."""
        config = AvatarConfig.from_dict({
            "engine": {"working_dir": "/tmp"},
        })
        wd = config.get_working_dir()
        assert wd == "/tmp"

    def test_get_working_dir_expands_tilde(self):
        """get_working_dir should expand ~."""
        config = AvatarConfig.from_dict({
            "engine": {"working_dir": "~/test"},
        })
        wd = config.get_working_dir()
        assert wd.startswith(str(Path.home()))
        assert "~" not in wd

    def test_to_dict(self):
        """to_dict should serialize config back to dict."""
        original = {
            "provider": "claude",
            "gemini": {"model": "g"},
            "claude": {"model": "c"},
            "engine": {
                "working_dir": "/tmp",
                "max_history": 50,
                "auto_restart": True,
                "max_restarts": 2,
            },
            "logging": {
                "level": "DEBUG",
                "file": "test.log",
            },
        }
        config = AvatarConfig.from_dict(original)
        result = config.to_dict()

        assert result["provider"] == "claude"
        assert result["gemini"]["model"] == "g"
        assert result["claude"]["model"] == "c"
        assert result["engine"]["max_history"] == 50
        assert result["logging"]["level"] == "DEBUG"

    def test_save_and_load(self):
        """save() should write loadable YAML."""
        config = AvatarConfig.from_dict({
            "provider": "gemini",
            "gemini": {"model": "test"},
        })

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            path = f.name

        try:
            config.save(path)
            loaded = AvatarConfig.load(path)

            assert loaded.provider == config.provider
            assert loaded.gemini_config["model"] == "test"
        finally:
            os.unlink(path)
