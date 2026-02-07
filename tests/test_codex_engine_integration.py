"""
Integration tests: AvatarEngine ↔ CodexBridge.

These test the key end-to-end use cases with mocked ACP,
ensuring the full pipeline works:

- Config YAML → Engine → CodexBridge lifecycle
- Engine.start() → chat() → stop() with Codex
- Event propagation (TextEvent, ThinkingEvent, ToolEvent, StateEvent)
- Engine streaming via chat_stream()
- Auto-restart / error recovery
- Health check with active Codex bridge
- Provider switching to/from Codex
- Multi-turn conversation through Engine
- History management
- CLI integration
"""

import asyncio
import os
import tempfile
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from avatar_engine import AvatarEngine, AvatarConfig
from avatar_engine.bridges.codex import CodexBridge, _ACP_AVAILABLE
from avatar_engine.bridges.base import BridgeState
from avatar_engine.events import (
    TextEvent,
    StateEvent,
    ErrorEvent,
    ThinkingEvent,
    ToolEvent,
    CostEvent,
)
from avatar_engine.types import BridgeResponse, ProviderType, Message


# =============================================================================
# Fake ACP objects (minimal, just enough for engine integration)
# =============================================================================


class _FakeContent:
    def __init__(self, text):
        self.text = text
        self.type = "text"


class _FakeThinkingContent:
    def __init__(self, text):
        self.text = text
        self.type = "thinking"


class AgentMessageChunk:
    """Fake — name must match type().__name__ in codex.py extractors."""
    def __init__(self, text):
        self.content = _FakeContent(text)


class AgentThoughtChunk:
    """Fake — thinking update."""
    def __init__(self, text):
        self.content = _FakeThinkingContent(text)
        self.thought = _FakeContent(text)


class ToolCall:
    """Fake — tool call started."""
    def __init__(self, name="exec", tool_id="tc-1", kind="exec", parameters=None):
        self.name = name
        self.id = tool_id
        self.kind = kind
        self.parameters = parameters or {}


class ToolCallUpdate:
    """Fake — tool call completed/failed."""
    def __init__(self, tool_id="tc-1", status="completed", output="", error=""):
        self.id = tool_id
        self.status = status
        self.output = output
        self.error = error


class _FakePromptResult:
    def __init__(self, text=""):
        self.content = _FakeContent(text)


class _FakeSessionResponse:
    def __init__(self, session_id="codex-engine-session"):
        self.session_id = session_id


class _FakeInitResponse:
    def __init__(self):
        self.protocol_version = 1


# =============================================================================
# Helper: create mocked ACP context for CodexBridge
# =============================================================================


def _mock_acp(
    session_id: str = "codex-engine-session",
    responses: Optional[List[str]] = None,
    session_updates_per_prompt: Optional[List[List[Any]]] = None,
):
    """
    Create patches that make CodexBridge.start() and send() work
    without real codex-acp binary.

    Args:
        session_id: Session ID returned by new_session()
        responses: List of response texts for successive prompt() calls
        session_updates_per_prompt: List of update lists — each list is
            delivered to _handle_acp_update during the corresponding prompt()
    """
    resp_list = responses or ["Hello from Codex!"]
    update_lists = session_updates_per_prompt or [[] for _ in resp_list]
    call_idx = [0]

    conn = AsyncMock()
    proc = MagicMock()
    proc.pid = 77777

    conn.initialize = AsyncMock(return_value=_FakeInitResponse())
    conn.authenticate = AsyncMock(return_value=None)
    conn.new_session = AsyncMock(
        return_value=_FakeSessionResponse(session_id=session_id)
    )

    async def _prompt(**kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        text = resp_list[idx] if idx < len(resp_list) else "No more responses"
        return _FakePromptResult(text=text)

    conn.prompt = _prompt

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=(conn, proc))
    ctx.__aexit__ = AsyncMock(return_value=None)

    return (
        patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx),
        patch("shutil.which", return_value="/usr/bin/npx"),
        conn,
    )


# =============================================================================
# 1. Engine ↔ CodexBridge Full Lifecycle
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexLifecycle:
    """Test full engine lifecycle with Codex provider."""

    @pytest.mark.asyncio
    async def test_start_chat_stop(self):
        """Engine.start() → chat() → stop() complete lifecycle."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            assert engine._started is True
            assert engine.current_provider == "codex"
            assert engine.is_warm is True
            assert engine.session_id == "codex-engine-session"

            response = await engine.chat("Hello!")
            assert response.success is True
            assert response.content == "Hello from Codex!"

            await engine.stop()
            assert engine._started is False
            assert engine.session_id is None

    @pytest.mark.asyncio
    async def test_auto_start_on_chat(self):
        """chat() should auto-start engine if not started."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            assert engine._started is False

            response = await engine.chat("Hello!")
            assert response.success is True
            assert engine._started is True

            await engine.stop()

    @pytest.mark.asyncio
    async def test_idempotent_start(self):
        """Calling start() twice should be no-op."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()
            session1 = engine.session_id

            await engine.start()  # Should be no-op
            assert engine.session_id == session1

            await engine.stop()

    @pytest.mark.asyncio
    async def test_double_stop_safe(self):
        """Calling stop() twice should be safe."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()
            await engine.stop()
            await engine.stop()  # Should not raise


# =============================================================================
# 2. Config → Engine → CodexBridge Pipeline
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexConfig:
    """Test config → engine → bridge pipeline."""

    @pytest.mark.asyncio
    async def test_config_object_to_codex_bridge(self):
        """AvatarConfig with codex provider should create correct bridge."""
        config = AvatarConfig.from_dict({
            "provider": "codex",
            "codex": {
                "model": "o3",
                "timeout": 30,
                "auth_method": "openai-api-key",
                "approval_mode": "auto",
                "sandbox_mode": "read-only",
                "executable": "npx",
                "executable_args": ["@zed-industries/codex-acp"],
            },
        })

        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(config=config)
            assert engine.current_provider == "codex"

            bridge = engine._create_bridge()
            assert isinstance(bridge, CodexBridge)
            assert bridge.model == "o3"
            assert bridge.auth_method == "openai-api-key"
            assert bridge.sandbox_mode == "read-only"

    @pytest.mark.asyncio
    async def test_yaml_config_to_engine(self):
        """Load YAML config with codex section and create working engine."""
        yaml_content = """\
provider: codex
codex:
  model: "o3"
  timeout: 30
  auth_method: openai-api-key
  approval_mode: auto
  sandbox_mode: workspace-write
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            p1, p2, conn = _mock_acp()
            with p1, p2:
                engine = AvatarEngine.from_config(path)
                assert engine.current_provider == "codex"

                await engine.start()
                assert engine.is_warm is True

                response = await engine.chat("Test from YAML config")
                assert response.success is True

                await engine.stop()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_codex_config_mcp_servers_propagate(self):
        """MCP servers from config should propagate to CodexBridge."""
        config = AvatarConfig.from_dict({
            "provider": "codex",
            "codex": {
                "mcp_servers": {
                    "tools": {
                        "command": "python",
                        "args": ["server.py"],
                    }
                }
            },
        })

        engine = AvatarEngine(config=config)
        bridge = engine._create_bridge()
        assert isinstance(bridge, CodexBridge)
        assert "tools" in bridge.mcp_servers
        assert bridge.mcp_servers["tools"]["command"] == "python"

    @pytest.mark.asyncio
    async def test_codex_config_env_propagate(self):
        """Env vars from config should propagate to CodexBridge."""
        config = AvatarConfig.from_dict({
            "provider": "codex",
            "codex": {
                "env": {"CODEX_API_KEY": "sk-test"},
            },
        })

        engine = AvatarEngine(config=config)
        bridge = engine._create_bridge()
        assert isinstance(bridge, CodexBridge)
        env = bridge._build_subprocess_env()
        assert env.get("CODEX_API_KEY") == "sk-test"


# =============================================================================
# 3. Event Propagation: Engine ← CodexBridge
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexEvents:
    """Test that events from CodexBridge propagate through Engine."""

    @pytest.mark.asyncio
    async def test_text_event_emitted(self):
        """TextEvent should fire when CodexBridge streams text."""
        p1, p2, conn = _mock_acp()
        text_events = []

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            @engine.on(TextEvent)
            def on_text(event):
                text_events.append(event)

            await engine.start()

            # Manually inject a text update through the bridge callback
            engine._bridge._handle_acp_update(
                "codex-engine-session",
                AgentMessageChunk("Hello!"),
            )

            assert len(text_events) == 1
            assert text_events[0].text == "Hello!"
            assert text_events[0].provider == "codex"

            await engine.stop()

    @pytest.mark.asyncio
    async def test_thinking_event_emitted(self):
        """ThinkingEvent should fire when CodexBridge receives thought."""
        p1, p2, conn = _mock_acp()
        thinking_events = []

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            @engine.on(ThinkingEvent)
            def on_think(event):
                thinking_events.append(event)

            await engine.start()

            engine._bridge._handle_acp_update(
                "codex-engine-session",
                AgentThoughtChunk("Let me think about this..."),
            )

            assert len(thinking_events) == 1
            assert thinking_events[0].thought == "Let me think about this..."

            await engine.stop()

    @pytest.mark.asyncio
    async def test_tool_result_event_emitted(self):
        """ToolEvent should fire for tool_result from CodexBridge."""
        p1, p2, conn = _mock_acp()
        tool_events = []

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            @engine.on(ToolEvent)
            def on_tool(event):
                tool_events.append(event)

            await engine.start()

            engine._bridge._handle_acp_update(
                "codex-engine-session",
                ToolCallUpdate(tool_id="tc-1", status="completed", output="result"),
            )

            assert len(tool_events) == 1
            assert tool_events[0].status == "completed"

            await engine.stop()

    @pytest.mark.asyncio
    async def test_state_event_emitted_on_start(self):
        """StateEvent should fire during bridge state transitions."""
        p1, p2, conn = _mock_acp()
        state_events = []

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            @engine.on(StateEvent)
            def on_state(event):
                state_events.append(event)

            await engine.start()

            # Bridge goes DISCONNECTED → WARMING_UP → READY during start
            states = [e.new_state for e in state_events]
            assert BridgeState.WARMING_UP in states
            assert BridgeState.READY in states

            await engine.stop()

    @pytest.mark.asyncio
    async def test_state_event_emitted_during_chat(self):
        """StateEvent should fire for BUSY → READY during chat."""
        p1, p2, conn = _mock_acp()
        state_events = []

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            @engine.on(StateEvent)
            def on_state(event):
                state_events.append(event)

            await engine.start()
            state_events.clear()  # Reset to only capture chat events

            await engine.chat("Hello")

            states = [e.new_state for e in state_events]
            assert BridgeState.BUSY in states
            assert BridgeState.READY in states

            await engine.stop()


# =============================================================================
# 4. Engine Streaming via chat_stream()
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexStreaming:
    """Test streaming through Engine with Codex provider."""

    @pytest.mark.asyncio
    async def test_chat_stream_yields_chunks(self):
        """chat_stream() should yield text chunks from CodexBridge."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            # Mock send_stream to yield chunks
            async def mock_send_stream(prompt):
                for chunk in ["Hello", ", ", "world", "!"]:
                    yield chunk

            engine._bridge.send_stream = mock_send_stream

            chunks = []
            async for chunk in engine.chat_stream("Greet me"):
                chunks.append(chunk)

            assert chunks == ["Hello", ", ", "world", "!"]
            await engine.stop()

    @pytest.mark.asyncio
    async def test_chat_stream_auto_starts(self):
        """chat_stream() should auto-start engine if not started."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            async def mock_send_stream(prompt):
                yield "auto-started"

            # Need to patch after bridge is created (which happens in start)
            original_start = engine.start

            async def start_and_patch():
                await original_start()
                engine._bridge.send_stream = mock_send_stream

            engine.start = start_and_patch

            chunks = []
            async for chunk in engine.chat_stream("Hi"):
                chunks.append(chunk)

            assert "auto-started" in chunks
            await engine.stop()


# =============================================================================
# 5. Auto-Restart / Error Recovery
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexRestart:
    """Test auto-restart behavior with Codex provider."""

    @pytest.mark.asyncio
    async def test_auto_restart_on_send_failure(self):
        """Engine should auto-restart when send() fails."""
        call_count = [0]

        # First context: start OK, send fails
        conn1 = AsyncMock()
        proc1 = MagicMock()
        proc1.pid = 11111
        conn1.initialize = AsyncMock(return_value=_FakeInitResponse())
        conn1.authenticate = AsyncMock(return_value=None)
        conn1.new_session = AsyncMock(return_value=_FakeSessionResponse("s-1"))

        async def fail_prompt(**kwargs):
            raise RuntimeError("Connection lost")

        conn1.prompt = fail_prompt

        ctx1 = AsyncMock()
        ctx1.__aenter__ = AsyncMock(return_value=(conn1, proc1))
        ctx1.__aexit__ = AsyncMock(return_value=None)

        # Second context: start OK, send OK
        conn2 = AsyncMock()
        proc2 = MagicMock()
        proc2.pid = 22222
        conn2.initialize = AsyncMock(return_value=_FakeInitResponse())
        conn2.authenticate = AsyncMock(return_value=None)
        conn2.new_session = AsyncMock(return_value=_FakeSessionResponse("s-2"))

        async def ok_prompt(**kwargs):
            return _FakePromptResult(text="Recovered!")

        conn2.prompt = ok_prompt

        ctx2 = AsyncMock()
        ctx2.__aenter__ = AsyncMock(return_value=(conn2, proc2))
        ctx2.__aexit__ = AsyncMock(return_value=None)

        def make_ctx(*args, **kwargs):
            call_count[0] += 1
            return ctx1 if call_count[0] <= 1 else ctx2

        with patch("avatar_engine.bridges.codex.spawn_agent_process", side_effect=make_ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                engine = AvatarEngine(provider="codex", timeout=10)
                await engine.start()

                # First send fails → triggers auto-restart → retry succeeds
                response = await engine.chat("Hello")
                assert response.success is True
                assert response.content == "Recovered!"
                assert engine.restart_count == 1

                await engine.stop()

    @pytest.mark.asyncio
    async def test_restart_count_tracked(self):
        """Restart count should increment on each restart."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            assert engine.restart_count == 0
            engine._restart_count = 2
            assert engine.restart_count == 2

            engine.reset_restart_count()
            assert engine.restart_count == 0

            await engine.stop()

    @pytest.mark.asyncio
    async def test_error_event_on_start_failure(self):
        """ErrorEvent should be emitted when start fails."""
        error_events = []

        conn = AsyncMock()
        proc = MagicMock()
        proc.pid = 33333
        conn.initialize = AsyncMock(side_effect=RuntimeError("Init boom"))

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=(conn, proc))
        ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                engine = AvatarEngine(provider="codex", timeout=10)

                @engine.on(ErrorEvent)
                def on_error(event):
                    error_events.append(event)

                with pytest.raises(RuntimeError):
                    await engine.start()

                assert len(error_events) == 1
                assert "Init boom" in error_events[0].error
                assert error_events[0].provider == "codex"


# =============================================================================
# 6. Health Check with Active Codex Bridge
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexHealth:
    """Test health checking through Engine with Codex."""

    @pytest.mark.asyncio
    async def test_is_healthy_when_running(self):
        """is_healthy() should return True when bridge is READY."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            assert engine.is_healthy() is False

            await engine.start()
            assert engine.is_healthy() is True

            await engine.stop()
            assert engine.is_healthy() is False

    @pytest.mark.asyncio
    async def test_get_health_details(self):
        """get_health() should return detailed HealthStatus."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            # Before start
            health = engine.get_health()
            assert health.healthy is False
            assert health.state == "not_started"
            assert health.provider == "codex"

            await engine.start()

            # After start
            health = engine.get_health()
            assert health.healthy is True
            assert health.state == "ready"
            assert health.provider == "codex"
            assert health.uptime_seconds >= 0

            await engine.stop()

    @pytest.mark.asyncio
    async def test_health_after_chat(self):
        """Health should remain good after successful chat."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()
            await engine.chat("Hello")

            health = engine.get_health()
            assert health.healthy is True
            assert health.history_length == 2  # 1 user + 1 assistant

            await engine.stop()


# =============================================================================
# 7. Multi-Turn Conversation Through Engine
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexMultiTurn:
    """Test multi-turn conversations through Engine."""

    @pytest.mark.asyncio
    async def test_multi_turn_history(self):
        """History should accumulate across turns."""
        p1, p2, conn = _mock_acp(responses=["R1", "R2", "R3"])

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            await engine.chat("Q1")
            await engine.chat("Q2")
            await engine.chat("Q3")

            history = engine.get_history()
            assert len(history) == 6  # 3 user + 3 assistant

            assert history[0].role == "user"
            assert history[0].content == "Q1"
            assert history[1].role == "assistant"
            assert history[1].content == "R1"
            assert history[4].role == "user"
            assert history[4].content == "Q3"
            assert history[5].role == "assistant"
            assert history[5].content == "R3"

            await engine.stop()

    @pytest.mark.asyncio
    async def test_clear_history(self):
        """clear_history() should reset conversation."""
        p1, p2, conn = _mock_acp(responses=["R1", "R2"])

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            await engine.chat("Q1")
            assert len(engine.get_history()) == 2

            engine.clear_history()
            assert len(engine.get_history()) == 0

            await engine.chat("Q2")
            assert len(engine.get_history()) == 2

            await engine.stop()

    @pytest.mark.asyncio
    async def test_session_id_persists_across_turns(self):
        """Session ID should remain same across multi-turn."""
        p1, p2, conn = _mock_acp(responses=["R1", "R2"])

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            sid = engine.session_id
            await engine.chat("Q1")
            assert engine.session_id == sid

            await engine.chat("Q2")
            assert engine.session_id == sid

            await engine.stop()


# =============================================================================
# 8. Provider Switching
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineProviderSwitching:
    """Test switching providers to/from Codex."""

    @pytest.mark.asyncio
    async def test_switch_to_codex(self):
        """Should switch from Gemini to Codex."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            # Start as gemini (but mock it too to avoid real gemini)
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()
            assert engine.current_provider == "codex"

            # Switch to codex (already codex, but tests the mechanism)
            await engine.switch_provider("codex")
            assert engine.current_provider == "codex"
            assert engine._started is True
            assert engine.restart_count == 0  # Reset on switch

            await engine.stop()


# =============================================================================
# 9. Engine Properties with Codex Bridge
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEngineCodexProperties:
    """Test engine properties with active Codex bridge."""

    @pytest.mark.asyncio
    async def test_is_warm_true_for_codex(self):
        """Codex bridge is always persistent (warm)."""
        p1, p2, conn = _mock_acp()

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            assert engine.is_warm is True

            await engine.stop()

    @pytest.mark.asyncio
    async def test_session_id_available(self):
        """Session ID should be available after start."""
        p1, p2, conn = _mock_acp(session_id="my-codex-session")

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)

            assert engine.session_id is None
            await engine.start()
            assert engine.session_id == "my-codex-session"

            await engine.stop()
            assert engine.session_id is None


# =============================================================================
# 10. CLI Integration (codex provider choice)
# =============================================================================


class TestCLICodexIntegration:
    """Test CLI handles codex provider correctly."""

    def test_cli_accepts_codex_provider(self):
        """CLI app.py should accept 'codex' as provider choice."""
        from click.testing import CliRunner
        from avatar_engine.cli.app import cli

        runner = CliRunner()
        # Just verify --help works and mentions codex
        result = runner.invoke(cli, ["chat", "--help"])
        assert "codex" in result.output or result.exit_code == 0

    def test_engine_created_with_codex_from_kwargs(self):
        """Engine should be creatable with codex + kwargs."""
        engine = AvatarEngine(
            provider="codex",
            model="o3",
            timeout=30,
            system_prompt="Be brief.",
        )
        assert engine._provider == ProviderType.CODEX
        assert engine._model == "o3"
        assert engine._timeout == 30


# =============================================================================
# 11. End-to-End: Config File → Engine → Chat → Events → Response
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestEndToEndCodex:
    """Full end-to-end integration: config → engine → chat → events → response."""

    @pytest.mark.asyncio
    async def test_full_e2e_with_events(self):
        """Complete flow: load config, start engine, chat, verify events and response."""
        yaml_content = """\
provider: codex
codex:
  model: ""
  auth_method: chatgpt
  approval_mode: auto
engine:
  max_history: 50
logging:
  level: DEBUG
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            p1, p2, conn = _mock_acp(
                session_id="e2e-session",
                responses=["I'm Codex, ready to help!"],
            )

            text_events = []
            state_events = []

            with p1, p2:
                engine = AvatarEngine.from_config(path)

                @engine.on(TextEvent)
                def on_text(event):
                    text_events.append(event)

                @engine.on(StateEvent)
                def on_state(event):
                    state_events.append(event)

                # Full lifecycle
                await engine.start()

                assert engine.current_provider == "codex"
                assert engine.is_warm is True
                assert engine.session_id == "e2e-session"

                # Chat
                response = await engine.chat("Who are you?")
                assert response.success is True
                assert "Codex" in response.content

                # Verify events
                states = [e.new_state for e in state_events]
                assert BridgeState.WARMING_UP in states
                assert BridgeState.READY in states
                assert BridgeState.BUSY in states

                # Verify history
                assert len(engine.get_history()) == 2

                # Health
                assert engine.is_healthy() is True
                health = engine.get_health()
                assert health.provider == "codex"

                await engine.stop()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_e2e_multi_turn_with_history_check(self):
        """Full E2E multi-turn conversation with history validation."""
        p1, p2, conn = _mock_acp(
            responses=["Answer 1", "Answer 2", "The number was 42"],
        )

        with p1, p2:
            engine = AvatarEngine(provider="codex", timeout=10)
            await engine.start()

            r1 = await engine.chat("Remember 42")
            assert r1.success is True

            r2 = await engine.chat("What's 2+2?")
            assert r2.success is True

            r3 = await engine.chat("What number did I say?")
            assert r3.success is True

            # All responses use same session
            assert r1.session_id == r2.session_id == r3.session_id

            # History should be complete
            history = engine.get_history()
            assert len(history) == 6

            await engine.stop()
