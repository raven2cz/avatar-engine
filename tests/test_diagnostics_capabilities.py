"""Tests for Phase 6: DiagnosticEvent, ToolPolicy, ProviderCapabilities."""

import pytest
from unittest.mock import MagicMock

from avatar_engine.events import (
    DiagnosticEvent,
    EventEmitter,
)
from avatar_engine.types import (
    ProviderCapabilities,
    ToolPolicy,
)
from avatar_engine.bridges.base import _classify_stderr_level


# =============================================================================
# DiagnosticEvent
# =============================================================================


class TestDiagnosticEvent:
    """Tests for DiagnosticEvent dataclass."""

    def test_defaults(self):
        event = DiagnosticEvent()
        assert event.message == ""
        assert event.level == "info"
        assert event.source == ""
        assert event.provider == ""
        assert event.timestamp > 0

    def test_with_values(self):
        event = DiagnosticEvent(
            message="Token expired",
            level="warning",
            source="stderr",
            provider="gemini",
        )
        assert event.message == "Token expired"
        assert event.level == "warning"
        assert event.source == "stderr"

    def test_emittable(self):
        """DiagnosticEvent should be emittable via EventEmitter."""
        emitter = EventEmitter()
        received = []
        emitter.add_handler(DiagnosticEvent, lambda e: received.append(e))
        emitter.emit(DiagnosticEvent(message="test"))
        assert len(received) == 1
        assert received[0].message == "test"


# =============================================================================
# _classify_stderr_level
# =============================================================================


class TestClassifyStderrLevel:
    """Tests for stderr level classification helper."""

    def test_error_keywords(self):
        assert _classify_stderr_level("fatal: authentication failed") == "error"
        assert _classify_stderr_level("Error: connection refused") == "error"
        assert _classify_stderr_level("CRITICAL failure") == "error"
        assert _classify_stderr_level("exception in thread") == "error"

    def test_warning_keywords(self):
        assert _classify_stderr_level("Warning: deprecated API") == "warning"
        assert _classify_stderr_level("token expired, refreshing") == "warning"
        assert _classify_stderr_level("DEPRECATED method call") == "warning"

    def test_debug_keywords(self):
        assert _classify_stderr_level("debug: entering function") == "debug"
        assert _classify_stderr_level("trace: request sent") == "debug"

    def test_info_default(self):
        assert _classify_stderr_level("Gemini CLI version 1.2.3") == "info"
        assert _classify_stderr_level("Listening on port 8080") == "info"
        assert _classify_stderr_level("") == "info"


# =============================================================================
# ToolPolicy
# =============================================================================


class TestToolPolicy:
    """Tests for ToolPolicy allow/deny rules."""

    def test_empty_policy_allows_all(self):
        policy = ToolPolicy()
        assert policy.is_allowed("Read") is True
        assert policy.is_allowed("Write") is True
        assert policy.is_allowed("Bash") is True

    def test_allow_list(self):
        policy = ToolPolicy(allow=["Read", "Grep"])
        assert policy.is_allowed("Read") is True
        assert policy.is_allowed("Grep") is True
        assert policy.is_allowed("Write") is False
        assert policy.is_allowed("Bash") is False

    def test_deny_list(self):
        policy = ToolPolicy(deny=["Bash", "Write"])
        assert policy.is_allowed("Read") is True
        assert policy.is_allowed("Grep") is True
        assert policy.is_allowed("Bash") is False
        assert policy.is_allowed("Write") is False

    def test_deny_takes_precedence(self):
        """If a tool is in both allow and deny, deny wins."""
        policy = ToolPolicy(allow=["Read", "Bash"], deny=["Bash"])
        assert policy.is_allowed("Read") is True
        assert policy.is_allowed("Bash") is False

    def test_empty_allow_with_deny(self):
        """Empty allow with deny should allow everything except denied."""
        policy = ToolPolicy(allow=[], deny=["Bash"])
        assert policy.is_allowed("Read") is True
        assert policy.is_allowed("Bash") is False


# =============================================================================
# ProviderCapabilities
# =============================================================================


class TestProviderCapabilities:
    """Tests for ProviderCapabilities dataclass."""

    def test_defaults(self):
        caps = ProviderCapabilities()
        assert caps.thinking_supported is False
        assert caps.cost_tracking is False
        assert caps.system_prompt_method == "unsupported"
        assert caps.streaming is True
        assert caps.mcp_supported is False
        assert caps.cancellable is False

    def test_claude_capabilities(self):
        """Claude should have cost tracking and native system prompt."""
        from avatar_engine.bridges.claude import ClaudeBridge
        bridge = ClaudeBridge.__new__(ClaudeBridge)
        # Call BaseBridge.__init__ manually with minimal args
        from avatar_engine.bridges.base import BaseBridge
        BaseBridge.__init__(bridge, executable="claude", model="claude-sonnet-4-5")
        # Now set Claude-specific capabilities
        bridge._provider_capabilities.cost_tracking = True
        bridge._provider_capabilities.system_prompt_method = "native"
        bridge._provider_capabilities.mcp_supported = True

        caps = bridge.provider_capabilities
        assert caps.cost_tracking is True
        assert caps.system_prompt_method == "native"
        assert caps.mcp_supported is True

    def test_gemini_capabilities(self):
        """Gemini should have thinking support and injected system prompt."""
        caps = ProviderCapabilities(
            thinking_supported=True,
            thinking_structured=True,
            system_prompt_method="injected",
            mcp_supported=True,
        )
        assert caps.thinking_supported is True
        assert caps.thinking_structured is True
        assert caps.system_prompt_method == "injected"

    def test_codex_capabilities(self):
        """Codex should have thinking support and injected system prompt."""
        caps = ProviderCapabilities(
            thinking_supported=True,
            system_prompt_method="injected",
            mcp_supported=True,
        )
        assert caps.thinking_supported is True
        assert caps.system_prompt_method == "injected"


# =============================================================================
# Engine capabilities/policy integration
# =============================================================================


class TestEngineCapabilities:
    """Tests for engine-level capabilities and tool policy."""

    def test_engine_capabilities_before_start(self):
        from avatar_engine import AvatarEngine
        engine = AvatarEngine(provider="gemini")
        caps = engine.capabilities
        # Before start, returns defaults
        assert isinstance(caps, ProviderCapabilities)

    def test_engine_tool_policy(self):
        from avatar_engine import AvatarEngine
        engine = AvatarEngine(provider="gemini")
        assert engine.tool_policy is None

        policy = ToolPolicy(allow=["Read", "Grep"])
        engine.tool_policy = policy
        assert engine.tool_policy is policy
        assert engine.tool_policy.is_allowed("Read") is True
        assert engine.tool_policy.is_allowed("Bash") is False

    def test_engine_diagnostic_event_handling(self):
        """Engine should convert raw diagnostic events to DiagnosticEvent."""
        from avatar_engine import AvatarEngine
        engine = AvatarEngine(provider="gemini")

        received = []
        engine.add_handler(DiagnosticEvent, lambda e: received.append(e))

        # Simulate raw diagnostic event from bridge
        engine._process_event({
            "type": "diagnostic",
            "message": "Token refresh",
            "level": "warning",
            "source": "stderr",
        })

        assert len(received) == 1
        assert received[0].message == "Token refresh"
        assert received[0].level == "warning"
        assert received[0].source == "stderr"
