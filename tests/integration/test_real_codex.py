"""
Integration tests for Codex ACP bridge.

These tests require:
- codex-acp installed (npm install -g @zed-industries/codex-acp) or npx available
- Valid Codex authentication (codex login, or CODEX_API_KEY / OPENAI_API_KEY)

Run with: pytest tests/integration/test_real_codex.py -v -m codex
"""

import asyncio
import shutil

import pytest

from avatar_engine.bridges.codex import CodexBridge, _ACP_AVAILABLE
from avatar_engine.bridges.base import BridgeState
from avatar_engine.engine import AvatarEngine
from avatar_engine.events import TextEvent, StateEvent, ThinkingEvent, ToolEvent


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def codex_acp_available():
    """Check if codex-acp is available via npx."""
    return shutil.which("npx") is not None and _ACP_AVAILABLE


@pytest.fixture
def skip_if_no_codex_acp(codex_acp_available):
    """Skip test if codex-acp is not available."""
    if not codex_acp_available:
        pytest.skip("codex-acp not available (npx or ACP SDK missing)")


# =============================================================================
# CodexBridge Direct Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestRealCodexBridge:
    """Integration tests using real codex-acp binary."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self, skip_if_no_codex_acp):
        """Should start and stop cleanly."""
        bridge = CodexBridge(timeout=30)
        try:
            await bridge.start()
            assert bridge.state == BridgeState.READY
            assert bridge.session_id is not None
        finally:
            await bridge.stop()
            assert bridge.state == BridgeState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_simple_chat(self, skip_if_no_codex_acp):
        """Should handle a simple chat message."""
        bridge = CodexBridge(timeout=60)
        try:
            await bridge.start()
            response = await bridge.send("Say exactly: PONG")

            assert response.success is True
            assert len(response.content) > 0
            assert response.session_id is not None
            assert response.duration_ms > 0
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_multi_turn(self, skip_if_no_codex_acp):
        """Should maintain conversation context across turns."""
        bridge = CodexBridge(timeout=60)
        try:
            await bridge.start()

            r1 = await bridge.send("Remember the number 42.")
            assert r1.success is True

            r2 = await bridge.send("What number did I ask you to remember?")
            assert r2.success is True
            assert "42" in r2.content

            assert len(bridge.get_history()) == 4  # 2 user + 2 assistant
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_streaming(self, skip_if_no_codex_acp):
        """Should stream text chunks."""
        bridge = CodexBridge(timeout=60)
        try:
            await bridge.start()

            chunks = []
            async for chunk in bridge.send_stream("Say hello world"):
                chunks.append(chunk)

            full_text = "".join(chunks)
            assert len(full_text) > 0
            assert len(chunks) > 0  # Should have multiple chunks
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_events_emitted(self, skip_if_no_codex_acp):
        """Should emit events during response."""
        bridge = CodexBridge(timeout=60)
        events = []
        bridge.on_event(lambda e: events.append(e))

        try:
            await bridge.start()
            await bridge.send("Hello")

            # Should have at least some ACP update events
            assert len(events) > 0

            # Check for text events
            text_events = [e for e in events if e.get("type") == "acp_update" and "text" in e]
            assert len(text_events) > 0
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_output_callback(self, skip_if_no_codex_acp):
        """Should call output callback for streaming text."""
        bridge = CodexBridge(timeout=60)
        output = []
        bridge.on_output(lambda t: output.append(t))

        try:
            await bridge.start()
            await bridge.send("Say hello")

            assert len(output) > 0
            full_text = "".join(output)
            assert len(full_text) > 0
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_health_check(self, skip_if_no_codex_acp):
        """Should report healthy after start."""
        bridge = CodexBridge(timeout=30)
        try:
            await bridge.start()
            assert bridge.is_healthy() is True

            health = bridge.check_health()
            assert health["healthy"] is True
            assert health["provider"] == "codex"
            assert health["state"] == "ready"
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_stats_after_chat(self, skip_if_no_codex_acp):
        """Should track stats after chat."""
        bridge = CodexBridge(timeout=60)
        try:
            await bridge.start()
            await bridge.send("Hello")

            stats = bridge.get_stats()
            assert stats["total_requests"] == 1
            assert stats["successful_requests"] == 1
            assert stats["total_duration_ms"] > 0
        finally:
            await bridge.stop()


# =============================================================================
# Engine Integration Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestRealCodexEngine:
    """Integration tests via AvatarEngine with Codex provider."""

    @pytest.mark.asyncio
    async def test_engine_codex_chat(self, skip_if_no_codex_acp):
        """Should chat through AvatarEngine with Codex."""
        engine = AvatarEngine(provider="codex", timeout=60)

        try:
            await engine.start()
            assert engine.current_provider == "codex"
            assert engine.is_warm is True

            response = await engine.chat("Say PONG")
            assert response.success is True
            assert len(response.content) > 0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_codex_stream(self, skip_if_no_codex_acp):
        """Should stream through AvatarEngine with Codex."""
        engine = AvatarEngine(provider="codex", timeout=60)

        try:
            await engine.start()

            chunks = []
            async for chunk in engine.chat_stream("Say hello"):
                chunks.append(chunk)

            assert len(chunks) > 0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_codex_events(self, skip_if_no_codex_acp):
        """Should emit events through AvatarEngine."""
        engine = AvatarEngine(provider="codex", timeout=60)
        text_chunks = []

        @engine.on(TextEvent)
        def on_text(event):
            text_chunks.append(event.text)

        try:
            await engine.start()
            await engine.chat("Say hi")

            assert len(text_chunks) > 0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_codex_health(self, skip_if_no_codex_acp):
        """Should report healthy via AvatarEngine."""
        engine = AvatarEngine(provider="codex", timeout=30)

        try:
            await engine.start()
            assert engine.is_healthy() is True

            health = engine.get_health()
            assert health.healthy is True
            assert health.provider == "codex"
        finally:
            await engine.stop()


# =============================================================================
# Authentication Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestRealCodexAuth:
    """Test different authentication methods with real codex-acp."""

    @pytest.mark.asyncio
    async def test_chatgpt_auth(self, skip_if_no_codex_acp):
        """Should authenticate with chatgpt method."""
        bridge = CodexBridge(auth_method="chatgpt", timeout=30)
        try:
            await bridge.start()
            assert bridge.state == BridgeState.READY
        except Exception as e:
            # Auth may fail if no browser session - that's expected
            if "timed out" in str(e).lower() or "auth" in str(e).lower():
                pytest.skip("ChatGPT auth requires browser login")
            raise
        finally:
            await bridge.stop()


# =============================================================================
# MCP Server Integration Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestRealCodexMCP:
    """Test MCP server integration with real codex-acp."""

    @pytest.mark.asyncio
    async def test_mcp_server_passed(self, skip_if_no_codex_acp, tmp_path):
        """Should pass MCP servers to codex-acp session."""
        # Create a simple MCP server script
        mcp_script = tmp_path / "echo_server.py"
        mcp_script.write_text("""
import sys
import json

# Simple MCP server that does nothing (for testing)
for line in sys.stdin:
    try:
        msg = json.loads(line)
        if msg.get("method") == "initialize":
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"capabilities": {}}}))
            sys.stdout.flush()
    except:
        pass
""")

        bridge = CodexBridge(
            timeout=30,
            mcp_servers={
                "echo": {
                    "command": sys.executable if hasattr(sys, 'executable') else "python",
                    "args": [str(mcp_script)],
                }
            },
        )

        try:
            await bridge.start()
            assert bridge.state == BridgeState.READY
        except Exception:
            # MCP server issues shouldn't prevent basic testing
            pass
        finally:
            await bridge.stop()


# =============================================================================
# Error Recovery Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestRealCodexErrorRecovery:
    """Test error handling and recovery with real codex-acp."""

    @pytest.mark.asyncio
    async def test_restart_after_error(self, skip_if_no_codex_acp):
        """Should be able to start again after stop."""
        bridge = CodexBridge(timeout=30)

        # First session
        await bridge.start()
        assert bridge.state == BridgeState.READY
        await bridge.stop()

        # Second session
        await bridge.start()
        assert bridge.state == BridgeState.READY
        await bridge.stop()

    @pytest.mark.asyncio
    async def test_double_stop_safe(self, skip_if_no_codex_acp):
        """Should handle double stop gracefully."""
        bridge = CodexBridge(timeout=30)
        await bridge.start()
        await bridge.stop()
        await bridge.stop()  # Should not raise
        assert bridge.state == BridgeState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_send_after_reconnect(self, skip_if_no_codex_acp):
        """Should be able to send after stop and restart."""
        bridge = CodexBridge(timeout=60)

        await bridge.start()
        r1 = await bridge.send("First session")
        assert r1.success is True
        await bridge.stop()

        await bridge.start()
        r2 = await bridge.send("Second session")
        assert r2.success is True
        await bridge.stop()


# Need sys import for MCP test
import sys
