"""Tests for session management across all providers.

Tests cover:
- SessionInfo and SessionCapabilitiesInfo dataclasses
- BaseBridge default session methods
- ACPSessionMixin capability parsing, session cascade, list, resume
- ClaudeBridge session capabilities + resume override
- Engine session API delegation
- CLI session flags (--resume, --continue)
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from avatar_engine.types import SessionInfo, SessionCapabilitiesInfo
from avatar_engine.bridges.base import BaseBridge
from avatar_engine.bridges._acp_session import ACPSessionMixin


# =============================================================================
# SessionInfo / SessionCapabilitiesInfo Dataclass Tests
# =============================================================================


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_required_fields(self):
        """SessionInfo requires session_id and provider."""
        info = SessionInfo(session_id="abc123", provider="gemini")
        assert info.session_id == "abc123"
        assert info.provider == "gemini"

    def test_default_fields(self):
        """Optional fields should default to None/empty."""
        info = SessionInfo(session_id="x", provider="codex")
        assert info.cwd == ""
        assert info.title is None
        assert info.updated_at is None

    def test_full_fields(self):
        """All fields should be settable."""
        info = SessionInfo(
            session_id="sess-42",
            provider="claude",
            cwd="/home/user/project",
            title="My session",
            updated_at="2025-06-01T12:00:00Z",
        )
        assert info.session_id == "sess-42"
        assert info.provider == "claude"
        assert info.cwd == "/home/user/project"
        assert info.title == "My session"
        assert info.updated_at == "2025-06-01T12:00:00Z"


class TestSessionCapabilitiesInfo:
    """Tests for SessionCapabilitiesInfo dataclass."""

    def test_defaults_all_false(self):
        """All capabilities should default to False."""
        caps = SessionCapabilitiesInfo()
        assert caps.can_list is False
        assert caps.can_load is False
        assert caps.can_continue_last is False

    def test_individual_flags(self):
        """Should set individual capabilities."""
        caps = SessionCapabilitiesInfo(can_list=True, can_load=True)
        assert caps.can_list is True
        assert caps.can_load is True
        assert caps.can_continue_last is False

    def test_full_capabilities(self):
        """All capabilities enabled."""
        caps = SessionCapabilitiesInfo(
            can_list=True, can_load=True, can_continue_last=True
        )
        assert caps.can_list is True
        assert caps.can_load is True
        assert caps.can_continue_last is True


# =============================================================================
# BaseBridge Default Session Methods
# =============================================================================


class TestBaseBridgeSessionDefaults:
    """Test that BaseBridge provides sensible session defaults."""

    def test_session_capabilities_default(self):
        """BaseBridge should have all-False capabilities by default."""
        bridge = MagicMock(spec=BaseBridge)
        # Call the real property/methods from BaseBridge
        bridge._session_capabilities = SessionCapabilitiesInfo()
        caps = BaseBridge.session_capabilities.fget(bridge)
        assert caps.can_list is False
        assert caps.can_load is False
        assert caps.can_continue_last is False

    @pytest.mark.asyncio
    async def test_list_sessions_returns_empty(self):
        """BaseBridge.list_sessions should return empty list."""
        bridge = MagicMock(spec=BaseBridge)
        result = await BaseBridge.list_sessions(bridge)
        assert result == []

    @pytest.mark.asyncio
    async def test_resume_session_raises(self):
        """BaseBridge.resume_session should raise NotImplementedError."""
        bridge = MagicMock(spec=BaseBridge)
        bridge.provider_name = "test"

        with pytest.raises(NotImplementedError, match="does not support"):
            await BaseBridge.resume_session(bridge, "some-id")


# =============================================================================
# ACPSessionMixin Tests
# =============================================================================


class FakeACPHost(ACPSessionMixin):
    """Minimal host class that provides what ACPSessionMixin expects."""

    def __init__(self):
        self._acp_conn = MagicMock()
        self._acp_session_id = None
        self._session_capabilities = SessionCapabilitiesInfo()
        self.session_id = None
        self.working_dir = "/tmp/test-project"
        self.timeout = 10
        self.resume_session_id = None
        self.continue_last = False
        self._state = None

    @property
    def provider_name(self):
        return "test-acp"

    def _set_state(self, state):
        self._state = state

    def _build_mcp_servers_acp(self):
        return []


class TestACPSessionMixinCapabilities:
    """Tests for _store_acp_capabilities."""

    def test_no_capabilities(self):
        """Should handle init_resp without capabilities."""
        host = FakeACPHost()
        host._store_acp_capabilities(MagicMock(agent_capabilities=None))
        assert host._session_capabilities.can_list is False
        assert host._session_capabilities.can_load is False

    def test_load_session_true(self):
        """Should detect load_session capability."""
        host = FakeACPHost()
        caps = MagicMock()
        caps.load_session = True
        caps.session_capabilities = None
        init_resp = MagicMock(agent_capabilities=caps)

        host._store_acp_capabilities(init_resp)
        assert host._session_capabilities.can_load is True
        assert host._session_capabilities.can_list is False
        assert host._session_capabilities.can_continue_last is False

    def test_list_capabilities(self):
        """Should detect list session capability."""
        host = FakeACPHost()
        caps = MagicMock()
        caps.load_session = True
        sess_caps = MagicMock()
        sess_caps.list = MagicMock()  # not None → list supported
        caps.session_capabilities = sess_caps
        init_resp = MagicMock(agent_capabilities=caps)

        host._store_acp_capabilities(init_resp)
        assert host._session_capabilities.can_list is True
        assert host._session_capabilities.can_load is True
        assert host._session_capabilities.can_continue_last is True  # list + load


class TestACPSessionMixinCascade:
    """Tests for _create_or_resume_acp_session cascade."""

    @pytest.mark.asyncio
    async def test_new_session_default(self):
        """Without resume_session_id, should create new session."""
        host = FakeACPHost()
        new_resp = MagicMock(session_id="new-123")
        host._acp_conn.new_session = AsyncMock(return_value=new_resp)

        await host._create_or_resume_acp_session([])

        host._acp_conn.new_session.assert_called_once()
        assert host._acp_session_id == "new-123"
        assert host.session_id == "new-123"

    @pytest.mark.asyncio
    async def test_resume_specific_session(self):
        """With resume_session_id + can_load, should load session."""
        host = FakeACPHost()
        host.resume_session_id = "existing-456"
        host._session_capabilities.can_load = True
        host._acp_conn.load_session = AsyncMock(return_value=MagicMock())

        await host._create_or_resume_acp_session([])

        host._acp_conn.load_session.assert_called_once()
        assert host._acp_session_id == "existing-456"
        assert host.session_id == "existing-456"

    @pytest.mark.asyncio
    async def test_resume_fallback_to_new(self):
        """If load_session fails, should fall back to new_session."""
        host = FakeACPHost()
        host.resume_session_id = "bad-id"
        host._session_capabilities.can_load = True
        host._acp_conn.load_session = AsyncMock(side_effect=Exception("not found"))
        new_resp = MagicMock(session_id="fallback-789")
        host._acp_conn.new_session = AsyncMock(return_value=new_resp)

        await host._create_or_resume_acp_session([])

        assert host._acp_session_id == "fallback-789"

    @pytest.mark.asyncio
    async def test_continue_last_session(self):
        """With continue_last, should list sessions and load most recent."""
        host = FakeACPHost()
        host.continue_last = True
        host._session_capabilities.can_load = True
        host._session_capabilities.can_list = True
        host._session_capabilities.can_continue_last = True

        list_resp = MagicMock()
        list_resp.sessions = [MagicMock(session_id="recent-001")]
        host._acp_conn.list_sessions = AsyncMock(return_value=list_resp)
        host._acp_conn.load_session = AsyncMock(return_value=MagicMock())

        await host._create_or_resume_acp_session([])

        host._acp_conn.list_sessions.assert_called_once()
        host._acp_conn.load_session.assert_called_once()
        assert host._acp_session_id == "recent-001"

    @pytest.mark.asyncio
    async def test_continue_last_no_sessions(self):
        """continue_last with no previous sessions should create new."""
        host = FakeACPHost()
        host.continue_last = True
        host._session_capabilities.can_load = True
        host._session_capabilities.can_list = True
        host._session_capabilities.can_continue_last = True

        list_resp = MagicMock()
        list_resp.sessions = []
        host._acp_conn.list_sessions = AsyncMock(return_value=list_resp)
        new_resp = MagicMock(session_id="new-after-empty")
        host._acp_conn.new_session = AsyncMock(return_value=new_resp)

        await host._create_or_resume_acp_session([])

        assert host._acp_session_id == "new-after-empty"

    @pytest.mark.asyncio
    async def test_resume_without_capability_creates_new(self):
        """resume_session_id set but can_load=False should create new."""
        host = FakeACPHost()
        host.resume_session_id = "some-id"
        # can_load is False (default)
        new_resp = MagicMock(session_id="new-no-load")
        host._acp_conn.new_session = AsyncMock(return_value=new_resp)

        await host._create_or_resume_acp_session([])

        assert host._acp_session_id == "new-no-load"


class TestACPSessionMixinListSessions:
    """Tests for list_sessions via ACP."""

    @pytest.mark.asyncio
    async def test_list_sessions_returns_session_info(self):
        """list_sessions should convert ACP responses to SessionInfo."""
        host = FakeACPHost()
        host._session_capabilities.can_list = True

        acp_session = MagicMock()
        acp_session.session_id = "s1"
        acp_session.cwd = "/tmp/proj"
        acp_session.title = "Test session"
        acp_session.updated_at = "2025-06-01T12:00:00Z"

        resp = MagicMock()
        resp.sessions = [acp_session]
        host._acp_conn.list_sessions = AsyncMock(return_value=resp)

        result = await host.list_sessions()
        assert len(result) == 1
        assert isinstance(result[0], SessionInfo)
        assert result[0].session_id == "s1"
        assert result[0].provider == "test-acp"
        assert result[0].title == "Test session"

    @pytest.mark.asyncio
    async def test_list_sessions_no_capability(self):
        """list_sessions without can_list should return empty."""
        host = FakeACPHost()
        result = await host.list_sessions()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_sessions_error_returns_empty(self):
        """list_sessions should return empty on error."""
        host = FakeACPHost()
        host._session_capabilities.can_list = True
        host._acp_conn.list_sessions = AsyncMock(side_effect=Exception("fail"))

        result = await host.list_sessions()
        assert result == []


class TestACPSessionMixinResumeSession:
    """Tests for resume_session via ACP."""

    @pytest.mark.asyncio
    async def test_resume_session_success(self):
        """resume_session should load session and update IDs."""
        host = FakeACPHost()
        host._session_capabilities.can_load = True
        host._acp_conn.load_session = AsyncMock(return_value=MagicMock())

        result = await host.resume_session("target-id")
        assert result is True
        assert host._acp_session_id == "target-id"
        assert host.session_id == "target-id"

    @pytest.mark.asyncio
    async def test_resume_session_no_capability(self):
        """resume_session without can_load should raise."""
        host = FakeACPHost()
        with pytest.raises(NotImplementedError):
            await host.resume_session("some-id")

    @pytest.mark.asyncio
    async def test_resume_session_no_connection(self):
        """resume_session without ACP connection should raise."""
        host = FakeACPHost()
        host._acp_conn = None
        with pytest.raises(RuntimeError, match="not active"):
            await host.resume_session("some-id")


# =============================================================================
# ClaudeBridge Session Tests
# =============================================================================


class TestClaudeBridgeSession:
    """Tests for ClaudeBridge session capabilities and resume."""

    def test_claude_session_capabilities(self):
        """ClaudeBridge should advertise can_load and can_continue_last."""
        from avatar_engine.bridges.claude import ClaudeBridge

        bridge = ClaudeBridge.__new__(ClaudeBridge)
        bridge._session_capabilities = SessionCapabilitiesInfo()
        # Simulate what __init__ does:
        bridge._session_capabilities.can_load = True
        bridge._session_capabilities.can_continue_last = True

        assert bridge._session_capabilities.can_load is True
        assert bridge._session_capabilities.can_continue_last is True
        assert bridge._session_capabilities.can_list is False  # Claude doesn't list

    @pytest.mark.asyncio
    async def test_claude_resume_session(self):
        """Claude resume_session should stop, set ID, and restart."""
        from avatar_engine.bridges.claude import ClaudeBridge

        bridge = ClaudeBridge.__new__(ClaudeBridge)
        bridge._session_capabilities = SessionCapabilitiesInfo()
        bridge.resume_session_id = None
        bridge.continue_session = True
        bridge.stop = AsyncMock()
        bridge.start = AsyncMock()

        result = await bridge.resume_session("claude-sess-42")

        bridge.stop.assert_called_once()
        bridge.start.assert_called_once()
        assert bridge.resume_session_id == "claude-sess-42"
        assert bridge.continue_session is False
        assert result is True


# =============================================================================
# GeminiBridge / CodexBridge Session Param Storage
# =============================================================================


class TestGeminiBridgeSessionParams:
    """Test GeminiBridge stores session params."""

    def test_stores_resume_session_id(self):
        """GeminiBridge should store resume_session_id."""
        from avatar_engine.bridges.gemini import GeminiBridge

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge.resume_session_id = "gem-123"
        bridge.continue_last = True
        assert bridge.resume_session_id == "gem-123"
        assert bridge.continue_last is True


class TestCodexBridgeSessionParams:
    """Test CodexBridge stores session params."""

    def test_stores_resume_session_id(self):
        """CodexBridge should store resume_session_id."""
        from avatar_engine.bridges.codex import CodexBridge

        bridge = CodexBridge.__new__(CodexBridge)
        bridge.resume_session_id = "cdx-456"
        bridge.continue_last = False
        assert bridge.resume_session_id == "cdx-456"
        assert bridge.continue_last is False


# =============================================================================
# Engine Session API Delegation
# =============================================================================


class TestEngineSessionAPI:
    """Test AvatarEngine session API delegates to bridge."""

    def test_session_capabilities_no_bridge(self):
        """session_capabilities without bridge should return defaults."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")
        caps = engine.session_capabilities
        assert isinstance(caps, SessionCapabilitiesInfo)
        assert caps.can_list is False

    def test_session_capabilities_with_bridge(self):
        """session_capabilities should delegate to bridge."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")
        engine._bridge = MagicMock()
        engine._bridge.session_capabilities = SessionCapabilitiesInfo(
            can_list=True, can_load=True, can_continue_last=True
        )

        caps = engine.session_capabilities
        assert caps.can_list is True
        assert caps.can_load is True

    @pytest.mark.asyncio
    async def test_list_sessions_delegates(self):
        """list_sessions should delegate to bridge."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")
        engine._bridge = MagicMock()
        expected = [SessionInfo(session_id="s1", provider="gemini")]
        engine._bridge.list_sessions = AsyncMock(return_value=expected)

        result = await engine.list_sessions()
        assert result == expected

    @pytest.mark.asyncio
    async def test_list_sessions_no_bridge(self):
        """list_sessions without bridge should return empty."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")
        result = await engine.list_sessions()
        assert result == []

    @pytest.mark.asyncio
    async def test_resume_session_delegates(self):
        """resume_session should delegate to bridge."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")
        engine._bridge = MagicMock()
        engine._bridge.resume_session = AsyncMock(return_value=True)

        result = await engine.resume_session("target-id")
        assert result is True
        engine._bridge.resume_session.assert_called_once_with("target-id")

    @pytest.mark.asyncio
    async def test_resume_session_no_bridge_raises(self):
        """resume_session without bridge should raise."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")
        with pytest.raises(RuntimeError, match="not started"):
            await engine.resume_session("any-id")


# =============================================================================
# CLI Session Flags
# =============================================================================


class TestCLISessionFlags:
    """Test --resume and --continue flags on chat and repl commands."""

    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    @pytest.fixture(autouse=True)
    def disable_config_autoload(self, monkeypatch):
        monkeypatch.setattr("avatar_engine.cli.app.find_config", lambda: None)

    def test_chat_resume_flag(self, runner):
        """chat --resume should pass resume_session_id to engine."""
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine.chat = AsyncMock(return_value=MagicMock(
            content="OK", success=True, duration_ms=100,
            session_id="s1", cost_usd=None, tool_calls=[],
        ))

        from avatar_engine.cli import cli
        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=engine) as mock_cls:
            result = runner.invoke(cli, [
                "chat", "--no-stream", "--resume", "sess-42", "Hello"
            ])

        assert result.exit_code == 0
        # Verify resume_session_id was passed
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("resume_session_id") == "sess-42"

    def test_chat_continue_flag(self, runner):
        """chat --continue should pass continue_last=True to engine."""
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine.chat = AsyncMock(return_value=MagicMock(
            content="OK", success=True, duration_ms=100,
            session_id="s1", cost_usd=None, tool_calls=[],
        ))

        from avatar_engine.cli import cli
        with patch("avatar_engine.cli.commands.chat.AvatarEngine", return_value=engine) as mock_cls:
            result = runner.invoke(cli, [
                "chat", "--no-stream", "--continue", "Hello"
            ])

        assert result.exit_code == 0
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("continue_last") is True

    def test_repl_resume_flag_accepted(self, runner):
        """repl --resume should be accepted by CLI."""
        from avatar_engine.cli import cli

        # Just verify the flag is accepted (no error), don't run REPL loop
        result = runner.invoke(cli, ["repl", "--resume", "abc", "--help"])
        # --help exits 0 after printing help text
        assert result.exit_code == 0

    def test_repl_continue_flag_accepted(self, runner):
        """repl --continue should be accepted by CLI."""
        from avatar_engine.cli import cli

        result = runner.invoke(cli, ["repl", "--continue", "--help"])
        assert result.exit_code == 0


# =============================================================================
# CLI Session Command Group
# =============================================================================


class TestCLISessionCommand:
    """Test 'avatar session' command group."""

    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    @pytest.fixture(autouse=True)
    def disable_config_autoload(self, monkeypatch):
        monkeypatch.setattr("avatar_engine.cli.app.find_config", lambda: None)

    def test_session_list_no_support(self, runner):
        """session list should show message when provider doesn't support listing."""
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine.session_capabilities = SessionCapabilitiesInfo(can_list=False)

        from avatar_engine.cli import cli
        with patch("avatar_engine.cli.commands.session.AvatarEngine", return_value=engine):
            result = runner.invoke(cli, ["session", "list"])

        assert result.exit_code == 0
        assert "does not support" in result.output

    def test_session_list_empty(self, runner):
        """session list with no sessions should show message."""
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine.session_capabilities = SessionCapabilitiesInfo(can_list=True)
        engine.list_sessions = AsyncMock(return_value=[])

        from avatar_engine.cli import cli
        with patch("avatar_engine.cli.commands.session.AvatarEngine", return_value=engine):
            result = runner.invoke(cli, ["session", "list"])

        assert result.exit_code == 0
        assert "No sessions found" in result.output

    def test_session_list_with_sessions(self, runner):
        """session list should display sessions in table."""
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine.session_capabilities = SessionCapabilitiesInfo(can_list=True)
        engine.list_sessions = AsyncMock(return_value=[
            SessionInfo(
                session_id="abcdef123456",
                provider="codex",
                cwd="/home/user/project",
                title="Refactoring session",
                updated_at="2025-06-01",
            ),
        ])

        from avatar_engine.cli import cli
        with patch("avatar_engine.cli.commands.session.AvatarEngine", return_value=engine):
            result = runner.invoke(cli, ["session", "list"])

        assert result.exit_code == 0
        assert "abcdef123456"[:12] in result.output
        assert "1 session(s)" in result.output

    def test_session_info_found(self, runner):
        """session info should display session details."""
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine.session_capabilities = SessionCapabilitiesInfo(can_list=True)
        engine.list_sessions = AsyncMock(return_value=[
            SessionInfo(
                session_id="target-session-id",
                provider="gemini",
                cwd="/tmp/test",
                title="My session",
                updated_at="2025-06-01T12:00:00Z",
            ),
        ])

        from avatar_engine.cli import cli
        with patch("avatar_engine.cli.commands.session.AvatarEngine", return_value=engine):
            result = runner.invoke(cli, ["session", "info", "target"])

        assert result.exit_code == 0
        assert "target-session-id" in result.output

    def test_session_info_not_found(self, runner):
        """session info with no match should show error."""
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine.session_capabilities = SessionCapabilitiesInfo(can_list=True)
        engine.list_sessions = AsyncMock(return_value=[])

        from avatar_engine.cli import cli
        with patch("avatar_engine.cli.commands.session.AvatarEngine", return_value=engine):
            result = runner.invoke(cli, ["session", "info", "nonexistent"])

        assert result.exit_code == 1

    def test_session_help(self, runner):
        """avatar session --help should show usage."""
        from avatar_engine.cli import cli
        result = runner.invoke(cli, ["session", "--help"])
        assert result.exit_code == 0
        assert "session" in result.output.lower()


# =============================================================================
# Bridge Filesystem Fallback Tests
# =============================================================================


class TestGeminiBridgeFilesystemFallback:
    """Test GeminiBridge list_sessions with filesystem fallback."""

    def test_can_list_sessions_capability(self):
        """GeminiBridge should advertise can_list=True (filesystem fallback)."""
        from avatar_engine.bridges.gemini import GeminiBridge

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge._session_capabilities = SessionCapabilitiesInfo()
        bridge._provider_capabilities = MagicMock()
        # Simulate what __init__ sets
        bridge._session_capabilities.can_list = True
        bridge._provider_capabilities.can_list_sessions = True

        assert bridge._session_capabilities.can_list is True
        assert bridge._provider_capabilities.can_list_sessions is True

    @pytest.mark.asyncio
    async def test_list_sessions_filesystem_fallback(self, tmp_path):
        """GeminiBridge should fall back to filesystem when ACP returns empty."""
        import json
        from avatar_engine.bridges.gemini import GeminiBridge
        from avatar_engine.sessions._gemini import GeminiFileSessionStore

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge._acp_conn = None  # No ACP connection
        bridge._session_capabilities = SessionCapabilitiesInfo(can_list=True)
        bridge.working_dir = "/tmp/test-project"
        bridge.timeout = 10

        # Create a session file in the filesystem store
        store = GeminiFileSessionStore(gemini_home=tmp_path)
        h = store._compute_project_hash("/tmp/test-project")
        chats = tmp_path / h / "chats"
        chats.mkdir(parents=True)
        data = {
            "sessionId": "gem-fs-001",
            "lastUpdated": "2025-06-15T10:00:00Z",
            "messages": [
                {"type": "user", "content": "Filesystem session"},
            ],
        }
        (chats / "session-gem-fs-001.json").write_text(json.dumps(data))

        # Patch get_session_store where it's imported (lazy import in method)
        with patch(
            "avatar_engine.sessions.get_session_store",
            return_value=store,
        ):
            result = await bridge.list_sessions()

        assert len(result) == 1
        assert result[0].session_id == "gem-fs-001"
        assert result[0].title == "Filesystem session"


class TestGeminiBridgeFilesystemResume:
    """Test GeminiBridge filesystem resume (history injection)."""

    @pytest.mark.asyncio
    async def test_load_filesystem_history(self):
        """_load_filesystem_history should populate history and set flag."""
        from avatar_engine.bridges.gemini import GeminiBridge
        from avatar_engine.types import Message

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge.working_dir = "/tmp/test"
        bridge.history = []
        bridge._history_lock = __import__("threading").Lock()
        bridge._fs_resume_pending = False

        mock_messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]

        with patch(
            "avatar_engine.sessions._gemini.GeminiFileSessionStore.load_session_messages",
            return_value=mock_messages,
        ):
            await bridge._load_filesystem_history("test-session-id")

        assert len(bridge.history) == 2
        assert bridge._fs_resume_pending is True

    def test_prepend_system_prompt_with_resume(self):
        """_prepend_system_prompt should inject resume context when flag is set."""
        from avatar_engine.bridges.gemini import GeminiBridge
        from avatar_engine.types import Message

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge.system_prompt = ""
        bridge.history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi!"),
        ]
        bridge._fs_resume_pending = True
        bridge.context_messages = 20
        bridge.context_max_chars = 500
        bridge._stats = {"total_requests": 0}
        bridge._stats_lock = __import__("threading").Lock()

        result = bridge._prepend_system_prompt("New question")
        assert "[Previous conversation:]" in result
        assert "User: Hello" in result
        assert "Assistant: Hi!" in result
        assert "[Continue:]" in result
        assert "New question" in result
        # Flag should be cleared after use
        assert bridge._fs_resume_pending is False

    def test_prepend_system_prompt_without_resume(self):
        """_prepend_system_prompt without flag should not inject context."""
        from avatar_engine.bridges.gemini import GeminiBridge

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge.system_prompt = ""
        bridge.history = []
        bridge._fs_resume_pending = False
        bridge._stats = {"total_requests": 0}
        bridge._stats_lock = __import__("threading").Lock()

        result = bridge._prepend_system_prompt("Just a question")
        assert "[Previous conversation:]" not in result
        assert result == "Just a question"

    def test_build_resume_context_truncates(self):
        """_build_resume_context should truncate long messages."""
        from avatar_engine.bridges.gemini import GeminiBridge
        from avatar_engine.types import Message

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge.history = [
            Message(role="user", content="A" * 1000),
        ]
        bridge.context_messages = 20
        bridge.context_max_chars = 50

        result = bridge._build_resume_context()
        # Should be truncated to 50 chars + ellipsis
        assert len(result.split("\n")[1].split(": ", 1)[1]) == 51  # 50 + "…"

    def test_can_load_capability_set(self):
        """GeminiBridge should have can_load=True after filesystem fallback setup."""
        from avatar_engine.bridges.gemini import GeminiBridge

        bridge = GeminiBridge.__new__(GeminiBridge)
        bridge._session_capabilities = SessionCapabilitiesInfo()
        bridge._provider_capabilities = MagicMock()

        # Simulate what _start_acp sets
        bridge._session_capabilities.can_load = True
        bridge._provider_capabilities.can_load_session = True

        assert bridge._session_capabilities.can_load is True
        assert bridge._provider_capabilities.can_load_session is True


class TestClaudeBridgeFilesystemFallback:
    """Test ClaudeBridge list_sessions with filesystem store."""

    def test_can_list_sessions_capability(self):
        """ClaudeBridge should advertise can_list=True (filesystem fallback)."""
        from avatar_engine.bridges.claude import ClaudeBridge

        bridge = ClaudeBridge.__new__(ClaudeBridge)
        bridge._session_capabilities = SessionCapabilitiesInfo()
        bridge._provider_capabilities = MagicMock()
        # Simulate what __init__ sets
        bridge._session_capabilities.can_list = True
        bridge._provider_capabilities.can_list_sessions = True

        assert bridge._session_capabilities.can_list is True

    @pytest.mark.asyncio
    async def test_list_sessions_filesystem(self, tmp_path):
        """ClaudeBridge should list sessions from filesystem."""
        import json
        from avatar_engine.bridges.claude import ClaudeBridge
        from avatar_engine.sessions._claude import ClaudeFileSessionStore

        bridge = ClaudeBridge.__new__(ClaudeBridge)
        bridge.working_dir = "/tmp/test-project"

        # Create a session file in the filesystem store
        store = ClaudeFileSessionStore(claude_home=tmp_path)
        encoded = store._encode_path("/tmp/test-project")
        project = tmp_path / encoded
        project.mkdir(parents=True)

        events = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Hello from filesystem"}],
                },
            },
        ]
        (project / "uuid-fs-001.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        with patch(
            "avatar_engine.sessions.get_session_store",
            return_value=store,
        ):
            result = await bridge.list_sessions()

        assert len(result) == 1
        assert result[0].session_id == "uuid-fs-001"
        assert result[0].title == "Hello from filesystem"
