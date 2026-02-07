"""Tests for avatar_engine.engine module."""

import signal
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from avatar_engine import AvatarEngine, AvatarConfig
from avatar_engine.types import ProviderType, BridgeState


class TestAvatarEngineInit:
    """Tests for AvatarEngine initialization."""

    def test_default_provider(self):
        """Default provider should be Gemini."""
        engine = AvatarEngine()
        assert engine._provider == ProviderType.GEMINI

    def test_gemini_provider_string(self):
        """Should accept 'gemini' as string."""
        engine = AvatarEngine(provider="gemini")
        assert engine._provider == ProviderType.GEMINI

    def test_claude_provider_string(self):
        """Should accept 'claude' as string."""
        engine = AvatarEngine(provider="claude")
        assert engine._provider == ProviderType.CLAUDE

    def test_codex_provider_string(self):
        """Should accept 'codex' as string."""
        engine = AvatarEngine(provider="codex")
        assert engine._provider == ProviderType.CODEX

    def test_provider_enum(self):
        """Should accept ProviderType enum."""
        engine = AvatarEngine(provider=ProviderType.CLAUDE)
        assert engine._provider == ProviderType.CLAUDE

    def test_custom_model(self):
        """Should accept custom model."""
        engine = AvatarEngine(model="gemini-2.5-flash")
        assert engine._model == "gemini-2.5-flash"

    def test_custom_timeout(self):
        """Should accept custom timeout."""
        engine = AvatarEngine(timeout=60)
        assert engine._timeout == 60

    def test_system_prompt(self):
        """Should accept system prompt."""
        engine = AvatarEngine(system_prompt="Be helpful")
        assert engine._system_prompt == "Be helpful"


class TestAvatarEngineFromConfig:
    """Tests for AvatarEngine.from_config."""

    def test_from_config_object(self):
        """Should create engine from AvatarConfig object."""
        config = AvatarConfig(
            provider=ProviderType.CLAUDE,
            model="claude-sonnet-4-5",
            timeout=90,
        )
        engine = AvatarEngine(config=config)
        assert engine._provider == ProviderType.CLAUDE
        assert engine._model == "claude-sonnet-4-5"
        assert engine._timeout == 90


class TestAvatarEngineProperties:
    """Tests for AvatarEngine properties."""

    def test_current_provider(self):
        """current_provider should return provider value."""
        engine = AvatarEngine(provider="claude")
        assert engine.current_provider == "claude"

    def test_session_id_not_started(self):
        """session_id should be None when not started."""
        engine = AvatarEngine()
        assert engine.session_id is None

    def test_is_warm_not_started(self):
        """is_warm should be False when not started."""
        engine = AvatarEngine()
        assert engine.is_warm is False

    def test_restart_count_initial(self):
        """restart_count should be 0 initially."""
        engine = AvatarEngine()
        assert engine.restart_count == 0

    def test_max_restarts_default(self):
        """max_restarts should default to 3."""
        engine = AvatarEngine()
        assert engine.max_restarts == 3


class TestAvatarEngineBridgeCreation:
    """Tests for bridge creation."""

    def test_create_codex_bridge(self):
        """Should create CodexBridge for codex provider."""
        from avatar_engine.bridges.codex import CodexBridge
        engine = AvatarEngine(provider="codex")
        bridge = engine._create_bridge()
        assert isinstance(bridge, CodexBridge)
        assert bridge.provider_name == "codex"

    def test_create_codex_bridge_with_config(self):
        """Should create CodexBridge from config."""
        from avatar_engine.bridges.codex import CodexBridge
        config = AvatarConfig.from_dict({
            "provider": "codex",
            "codex": {
                "auth_method": "openai-api-key",
                "approval_mode": "auto",
                "sandbox_mode": "read-only",
            },
        })
        engine = AvatarEngine(config=config)
        bridge = engine._create_bridge()
        assert isinstance(bridge, CodexBridge)
        assert bridge.auth_method == "openai-api-key"
        assert bridge.approval_mode == "auto"
        assert bridge.sandbox_mode == "read-only"

    def test_create_codex_bridge_with_model(self):
        """Should pass model to CodexBridge."""
        from avatar_engine.bridges.codex import CodexBridge
        engine = AvatarEngine(provider="codex", model="o3")
        bridge = engine._create_bridge()
        assert isinstance(bridge, CodexBridge)
        assert bridge.model == "o3"


class TestAvatarEngineHealth:
    """Tests for AvatarEngine health methods."""

    def test_is_healthy_not_started(self):
        """is_healthy should return False when not started."""
        engine = AvatarEngine()
        assert engine.is_healthy() is False

    def test_get_health_not_started(self):
        """get_health should return unhealthy status when not started."""
        engine = AvatarEngine()
        health = engine.get_health()
        assert health.healthy is False
        assert health.state == "not_started"


class TestAvatarEngineHistory:
    """Tests for AvatarEngine history methods."""

    def test_get_history_not_started(self):
        """get_history should return empty list when not started."""
        engine = AvatarEngine()
        assert engine.get_history() == []


class TestAvatarEngineRestartLogic:
    """Tests for auto-restart logic."""

    def test_should_restart_initial(self):
        """_should_restart should return True initially."""
        engine = AvatarEngine()
        assert engine._should_restart() is True

    def test_should_restart_after_max(self):
        """_should_restart should return False after max restarts."""
        engine = AvatarEngine()
        engine._restart_count = 3
        assert engine._should_restart() is False

    def test_reset_restart_count(self):
        """reset_restart_count should reset to 0."""
        engine = AvatarEngine()
        engine._restart_count = 2
        engine.reset_restart_count()
        assert engine._restart_count == 0

    def test_should_restart_with_config(self):
        """_should_restart should respect config.max_restarts."""
        config = AvatarConfig(max_restarts=5)
        engine = AvatarEngine(config=config)
        engine._restart_count = 3
        assert engine._should_restart() is True
        engine._restart_count = 5
        assert engine._should_restart() is False

    def test_should_restart_when_disabled(self):
        """_should_restart should return False when auto_restart=False."""
        config = AvatarConfig(auto_restart=False)
        engine = AvatarEngine(config=config)
        assert engine._should_restart() is False


class TestAvatarEngineHealthCheckConfig:
    """Tests for health check configuration."""

    def test_default_health_check_interval(self):
        """Default health check interval should be 30 seconds."""
        engine = AvatarEngine()
        assert engine._get_health_check_interval() == 30

    def test_custom_health_check_interval(self):
        """Should use config health_check_interval."""
        config = AvatarConfig(health_check_interval=60)
        engine = AvatarEngine(config=config)
        assert engine._get_health_check_interval() == 60

    def test_disabled_health_check(self):
        """health_check_interval=0 should disable health checks."""
        config = AvatarConfig(health_check_interval=0)
        engine = AvatarEngine(config=config)
        assert engine._get_health_check_interval() == 0


class TestAvatarEngineSignalHandling:
    """Tests for graceful shutdown signal handling."""

    def test_signal_handlers_not_installed_initially(self):
        """Signal handlers should not be installed by default."""
        engine = AvatarEngine()
        assert engine._signal_handlers_installed is False

    def test_install_signal_handlers(self):
        """install_signal_handlers should set flag to True."""
        engine = AvatarEngine()
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        try:
            engine.install_signal_handlers()
            assert engine._signal_handlers_installed is True
            # Verify handlers were changed
            assert signal.getsignal(signal.SIGTERM) != original_sigterm
            assert signal.getsignal(signal.SIGINT) != original_sigint
        finally:
            # Clean up
            engine.remove_signal_handlers()

    def test_remove_signal_handlers(self):
        """remove_signal_handlers should restore original handlers."""
        engine = AvatarEngine()
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        engine.install_signal_handlers()
        engine.remove_signal_handlers()

        assert engine._signal_handlers_installed is False
        assert signal.getsignal(signal.SIGTERM) == original_sigterm
        assert signal.getsignal(signal.SIGINT) == original_sigint

    def test_install_signal_handlers_idempotent(self):
        """Installing signal handlers multiple times should be safe."""
        engine = AvatarEngine()

        try:
            engine.install_signal_handlers()
            engine.install_signal_handlers()  # Should be no-op
            assert engine._signal_handlers_installed is True
        finally:
            engine.remove_signal_handlers()

    def test_remove_signal_handlers_idempotent(self):
        """Removing signal handlers multiple times should be safe."""
        engine = AvatarEngine()
        engine.remove_signal_handlers()  # Should be no-op
        engine.remove_signal_handlers()  # Should be no-op
        assert engine._signal_handlers_installed is False

    def test_initiate_shutdown_sets_flag(self):
        """_initiate_shutdown should set _shutting_down flag."""
        engine = AvatarEngine()
        assert engine._shutting_down is False
        engine._initiate_shutdown()
        assert engine._shutting_down is True
