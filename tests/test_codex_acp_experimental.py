"""
Experimental ACP communication tests for Codex bridge.

These tests validate ACP protocol patterns, message parsing,
state machine transitions, and communication edge cases.

They are "scratch" tests — exploring the integration surface
before having a real codex-acp binary to test against.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from avatar_engine.bridges.codex import (
    CodexBridge,
    _ACP_AVAILABLE,
    _extract_text_from_update,
    _extract_text_from_result,
    _extract_thinking_from_update,
    _extract_tool_event_from_update,
)
from avatar_engine.bridges.base import BridgeState
from avatar_engine.types import BridgeResponse, Message


# =============================================================================
# Fake ACP objects — simulate real protocol messages
# =============================================================================


class FakeTextContent:
    """Simulates content.text from ACP message chunks."""

    def __init__(self, text: str, content_type: str = "text"):
        self.text = text
        self.type = content_type


class FakeThinkingContent:
    """Simulates content.text with type=thinking from ACP."""

    def __init__(self, text: str):
        self.text = text
        self.type = "thinking"


class AgentMessageChunk:
    """Simulates AgentMessageChunk from codex-acp ACP stream."""

    def __init__(self, text: str):
        self.content = FakeTextContent(text)


class AgentThoughtChunk:
    """Simulates AgentThoughtChunk from codex-acp ACP stream."""

    def __init__(self, text: str):
        self.content = FakeThinkingContent(text)  # type=thinking so text extraction skips it
        self.thought = FakeTextContent(text)


class ToolCall:
    """Simulates ToolCall from codex-acp ACP stream."""

    def __init__(self, name: str = "exec", tool_id: str = "t-1",
                 kind: str = "exec", parameters: Optional[dict] = None):
        self.name = name
        self.id = tool_id
        self.kind = kind
        self.parameters = parameters or {}


class ToolCallUpdate:
    """Simulates ToolCallUpdate from codex-acp ACP stream."""

    def __init__(self, tool_id: str = "t-1", status: str = "completed",
                 output: str = "", error: str = ""):
        self.id = tool_id
        self.status = status
        self.output = output
        self.error = error


class FakePromptResult:
    """Simulates ACP PromptResponse with content blocks."""

    def __init__(self, blocks: Optional[list] = None, text: str = ""):
        if blocks is not None:
            self.content = blocks
        elif text:
            self.content = FakeTextContent(text)
        else:
            self.content = []


class FakeSessionResponse:
    """Simulates ACP new_session() response."""

    def __init__(self, session_id: str = "codex-session-001"):
        self.session_id = session_id
        self.modes = ["default"]
        self.models = ["gpt-5.3-codex"]
        self.config_options = {}


class FakeInitResponse:
    """Simulates ACP initialize() response."""

    def __init__(self):
        self.protocol_version = 1
        self.capabilities = {}


# =============================================================================
# ACP Message Flow Tests — simulate the full protocol sequence
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestACPMessageFlow:
    """Test the ACP message flow patterns that CodexBridge uses.

    Each test simulates a different communication pattern between
    Python ACP SDK and codex-acp adapter.
    """

    def _make_mock_acp_context(
        self,
        session_id: str = "codex-session-001",
        prompt_result: Optional[Any] = None,
        session_updates: Optional[List[Any]] = None,
    ):
        """Create a fully mocked ACP context manager + connection."""
        conn = AsyncMock()
        proc = MagicMock()
        proc.pid = 99999

        # initialize() → FakeInitResponse
        conn.initialize = AsyncMock(return_value=FakeInitResponse())

        # authenticate() → None
        conn.authenticate = AsyncMock(return_value=None)

        # new_session() → FakeSessionResponse
        conn.new_session = AsyncMock(
            return_value=FakeSessionResponse(session_id=session_id)
        )

        # prompt() → FakePromptResult (optionally triggers session_updates via side_effect)
        result = prompt_result or FakePromptResult(text="Hello from Codex!")

        async def _prompt_side_effect(**kwargs):
            """Simulate session updates being emitted during prompt."""
            if session_updates:
                # In real ACP, session_update() is called on the client
                # during prompt. Here we simulate that by calling the bridge's
                # _handle_acp_update() directly.
                bridge = kwargs.get("_bridge")
                if bridge:
                    for update in session_updates:
                        bridge._handle_acp_update(session_id, update)
            return result

        conn.prompt = AsyncMock(return_value=result)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=(conn, proc))
        ctx.__aexit__ = AsyncMock(return_value=None)

        return ctx, conn, proc

    @pytest.mark.asyncio
    async def test_full_lifecycle_spawn_init_auth_session_prompt(self):
        """Test the complete ACP lifecycle:
        spawn → initialize → authenticate → new_session → prompt → cleanup.
        """
        ctx, conn, proc = self._make_mock_acp_context()

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                # Verify lifecycle calls were made in order
                conn.initialize.assert_called_once_with(protocol_version=1)
                conn.authenticate.assert_called_once_with(method_id="chatgpt")
                conn.new_session.assert_called_once()

                assert bridge.state == BridgeState.READY
                assert bridge.session_id == "codex-session-001"

                # Now prompt
                response = await bridge.send("Hello ACP!")
                conn.prompt.assert_called_once()

                assert response.success is True
                assert response.session_id == "codex-session-001"

                await bridge.stop()
                assert bridge.state == BridgeState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_protocol_version_negotiation(self):
        """ACP always initializes with protocol_version=1."""
        ctx, conn, proc = self._make_mock_acp_context()

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                # Verify protocol version
                call_kwargs = conn.initialize.call_args
                assert call_kwargs == ({"protocol_version": 1},) or \
                    call_kwargs[1].get("protocol_version") == 1

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_auth_method_passed_to_authenticate(self):
        """Auth method should be correctly passed to ACP authenticate()."""
        for auth in ["chatgpt", "codex-api-key", "openai-api-key"]:
            ctx, conn, proc = self._make_mock_acp_context()

            with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge(auth_method=auth)
                    await bridge.start()

                    conn.authenticate.assert_called_once_with(method_id=auth)
                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_session_created_with_working_dir(self):
        """new_session() should receive working directory."""
        ctx, conn, proc = self._make_mock_acp_context()

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge(working_dir="/home/test/project")
                await bridge.start()

                call_kwargs = conn.new_session.call_args[1]
                assert call_kwargs["cwd"] == "/home/test/project"

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_session_created_with_mcp_servers(self):
        """new_session() should receive MCP server configs in ACP format."""
        ctx, conn, proc = self._make_mock_acp_context()

        mcp_servers = {
            "avatar-tools": {
                "command": "/usr/bin/python",
                "args": ["mcp_tools.py"],
                "env": {"TOOL_DEBUG": "1"},
            }
        }

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge(mcp_servers=mcp_servers)
                await bridge.start()

                call_kwargs = conn.new_session.call_args[1]
                mcp_list = call_kwargs["mcp_servers"]

                assert len(mcp_list) == 1
                assert mcp_list[0]["name"] == "avatar-tools"
                assert mcp_list[0]["command"] == "/usr/bin/python"
                assert mcp_list[0]["args"] == ["mcp_tools.py"]
                assert {"name": "TOOL_DEBUG", "value": "1"} in mcp_list[0]["env"]

                await bridge.stop()


# =============================================================================
# ACP Session Update Stream Tests — validate event parsing
# =============================================================================


class TestACPSessionUpdateStream:
    """Test parsing of ACP session_update notifications.

    In real codex-acp, session updates stream back during prompt():
    - AgentMessageChunk → text content
    - AgentThoughtChunk → thinking/reasoning
    - ToolCall → tool invocation started
    - ToolCallUpdate → tool completed/failed
    - Plan → agent planning (logged but not emitted)
    """

    def test_text_streaming_accumulation(self):
        """Multiple AgentMessageChunk updates should accumulate text."""
        chunks = [
            AgentMessageChunk("Hello"),
            AgentMessageChunk(", "),
            AgentMessageChunk("world"),
            AgentMessageChunk("!"),
        ]

        accumulated = ""
        for chunk in chunks:
            text = _extract_text_from_update(chunk)
            if text:
                accumulated += text

        assert accumulated == "Hello, world!"

    def test_thinking_then_text_interleaved(self):
        """Thinking and text updates should be correctly separated."""
        updates = [
            AgentThoughtChunk("Let me think about this..."),
            AgentMessageChunk("Here is my "),
            AgentThoughtChunk("The user wants a greeting."),
            AgentMessageChunk("answer: Hello!"),
        ]

        text_parts = []
        thinking_parts = []

        for update in updates:
            text = _extract_text_from_update(update)
            thinking = _extract_thinking_from_update(update)

            if text and "Thought" not in type(update).__name__:
                text_parts.append(text)
            if thinking:
                thinking_parts.append(thinking)

        assert "".join(text_parts) == "Here is my answer: Hello!"
        assert len(thinking_parts) == 2
        assert "think about this" in thinking_parts[0]

    def test_tool_call_then_result_sequence(self):
        """ToolCall followed by ToolCallUpdate should map to started → completed."""
        updates = [
            ToolCall(name="exec", tool_id="tc-1", kind="shell", parameters={"command": "ls"}),
            ToolCallUpdate(tool_id="tc-1", status="completed", output="file1.py\nfile2.py"),
        ]

        events = []
        for update in updates:
            event = _extract_tool_event_from_update(update)
            if event:
                events.append(event)

        assert len(events) == 2

        # First event: tool call started
        assert events[0]["type"] == "tool_call"
        assert events[0]["tool_name"] == "exec"
        assert events[0]["status"] == "started"
        assert events[0]["parameters"]["command"] == "ls"

        # Second event: tool result
        assert events[1]["type"] == "tool_result"
        assert events[1]["status"] == "completed"
        assert "file1.py" in events[1]["result"]

    def test_tool_call_failure_sequence(self):
        """Failed tool call should be detected."""
        updates = [
            ToolCall(name="patch", tool_id="tc-2"),
            ToolCallUpdate(tool_id="tc-2", status="failed", error="Permission denied"),
        ]

        events = []
        for update in updates:
            event = _extract_tool_event_from_update(update)
            if event:
                events.append(event)

        assert events[1]["status"] == "failed"
        assert "Permission denied" in events[1]["error"]

    def test_multiple_tool_calls_in_sequence(self):
        """Multiple tool calls in a single response."""
        updates = [
            AgentMessageChunk("Let me check the files..."),
            ToolCall(name="exec", tool_id="tc-1", parameters={"command": "ls"}),
            ToolCallUpdate(tool_id="tc-1", status="completed", output="src/"),
            ToolCall(name="exec", tool_id="tc-2", parameters={"command": "cat src/main.py"}),
            ToolCallUpdate(tool_id="tc-2", status="completed", output="def main(): pass"),
            AgentMessageChunk("Here is the file content."),
        ]

        text_parts = []
        tool_events = []

        for update in updates:
            text = _extract_text_from_update(update)
            tool_event = _extract_tool_event_from_update(update)

            if text:
                text_parts.append(text)
            if tool_event:
                tool_events.append(tool_event)

        assert len(text_parts) == 2
        assert len(tool_events) == 4  # 2 calls + 2 results

    def test_dict_style_updates(self):
        """Test handling of dict-style ACP updates (fallback path)."""
        dict_msg = {
            "type": "AgentMessageChunk",
            "content": {"text": "Hello from dict"},
        }
        text = _extract_text_from_update(dict_msg)
        assert text == "Hello from dict"

        dict_thought = {
            "type": "AgentThoughtChunk",
            "content": {"text": "Thinking..."},
        }
        thought = _extract_thinking_from_update(dict_thought)
        assert thought == "Thinking..."

    def test_dict_style_tool_call(self):
        """Test dict-style ToolCall parsing."""
        dict_tool = {
            "type": "ToolCall",
            "name": "exec",
            "id": "t-dict-1",
            "kind": "shell",
            "parameters": {"command": "pwd"},
        }
        event = _extract_tool_event_from_update(dict_tool)
        assert event is not None
        assert event["tool_name"] == "exec"
        assert event["parameters"]["command"] == "pwd"

    def test_dict_style_tool_update(self):
        """Test dict-style ToolCallUpdate parsing."""
        dict_update = {
            "type": "ToolCallUpdate",
            "id": "t-dict-1",
            "status": "completed",
            "output": "/home/user",
        }
        event = _extract_tool_event_from_update(dict_update)
        assert event is not None
        assert event["status"] == "completed"
        assert event["result"] == "/home/user"

    def test_empty_content_chunk(self):
        """Empty text chunks should return None or empty."""
        chunk = AgentMessageChunk("")
        text = _extract_text_from_update(chunk)
        # Empty string is still technically text
        assert text == ""

    def test_content_list_blocks(self):
        """Content as a list of blocks (multi-part message)."""

        class MultiBlockMessage:
            def __init__(self):
                self.content = [
                    FakeTextContent("Part 1. "),
                    FakeTextContent("Part 2."),
                ]

        update = MultiBlockMessage()
        text = _extract_text_from_update(update)
        assert text == "Part 1. Part 2."

    def test_content_list_with_thinking_blocks(self):
        """Content list with mixed text and thinking blocks."""

        class MixedBlockMessage:
            def __init__(self):
                self.content = [
                    FakeThinkingContent("I should be careful."),
                    FakeTextContent("Here is my answer."),
                ]

        update = MixedBlockMessage()
        text = _extract_text_from_update(update)
        # Should skip thinking blocks and only return text
        assert text == "Here is my answer."


# =============================================================================
# ACP Result Extraction Tests
# =============================================================================


class TestACPResultExtraction:
    """Test extraction of text from ACP PromptResponse objects."""

    def test_simple_text_result(self):
        """Simple text result from prompt."""
        result = FakePromptResult(text="Hello from Codex!")
        text = _extract_text_from_result(result)
        assert text == "Hello from Codex!"

    def test_multi_block_result(self):
        """Result with multiple content blocks."""
        blocks = [
            FakeTextContent("First paragraph.\n\n"),
            FakeTextContent("Second paragraph."),
        ]
        result = FakePromptResult(blocks=blocks)
        text = _extract_text_from_result(result)
        assert text == "First paragraph.\n\nSecond paragraph."

    def test_empty_result(self):
        """Empty result should return empty string."""
        result = FakePromptResult(blocks=[])
        text = _extract_text_from_result(result)
        assert text == ""

    def test_result_with_dict_blocks(self):
        """Result with dict-style content blocks."""

        class DictBlockResult:
            def __init__(self):
                self.content = [
                    {"text": "From dict block 1. "},
                    {"text": "From dict block 2."},
                ]

        result = DictBlockResult()
        text = _extract_text_from_result(result)
        assert text == "From dict block 1. From dict block 2."

    def test_result_without_content_attr(self):
        """Result without content attribute should return empty."""
        result = MagicMock(spec=[])  # No attributes
        text = _extract_text_from_result(result)
        assert text == ""


# =============================================================================
# ACP State Machine Tests — bridge state transitions
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestACPStateMachine:
    """Test state transitions during ACP lifecycle."""

    def _make_mock_ctx(self, session_id="s-1"):
        conn = AsyncMock()
        proc = MagicMock()
        proc.pid = 11111

        conn.initialize = AsyncMock(return_value=FakeInitResponse())
        conn.authenticate = AsyncMock(return_value=None)
        conn.new_session = AsyncMock(
            return_value=FakeSessionResponse(session_id=session_id)
        )
        conn.prompt = AsyncMock(return_value=FakePromptResult(text="OK"))

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=(conn, proc))
        ctx.__aexit__ = AsyncMock(return_value=None)

        return ctx, conn

    @pytest.mark.asyncio
    async def test_state_transitions_full_lifecycle(self):
        """DISCONNECTED → WARMING_UP → READY → BUSY → READY → DISCONNECTED."""
        ctx, conn = self._make_mock_ctx()
        states = []

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()

                # Track state changes
                original_set_state = bridge._set_state
                def track_state(state):
                    states.append(state)
                    original_set_state(state)
                bridge._set_state = track_state

                assert bridge.state == BridgeState.DISCONNECTED

                await bridge.start()
                # Should have gone through WARMING_UP → READY
                assert BridgeState.WARMING_UP in states
                assert bridge.state == BridgeState.READY

                await bridge.send("Hello")
                # Should have gone BUSY → READY
                assert BridgeState.BUSY in states
                assert bridge.state == BridgeState.READY

                await bridge.stop()
                assert bridge.state == BridgeState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_state_on_auth_failure_continues(self, caplog):
        """Generic auth failure should warn but continue (auth is optional for some modes).

        CodexBridge treats auth errors as non-fatal since some auth methods
        (e.g. auto-detect) may raise but the session can still work.
        """
        ctx, conn = self._make_mock_ctx()
        conn.authenticate = AsyncMock(side_effect=RuntimeError("Auth failed"))

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                with caplog.at_level(logging.WARNING, logger="avatar_engine.bridges.codex"):
                    await bridge.start()

                # Auth failures are non-fatal — bridge continues to session creation
                assert bridge.state == BridgeState.READY
                assert "authenticate issue" in caplog.text.lower()
                await bridge.stop()

    @pytest.mark.asyncio
    async def test_state_on_session_failure(self, caplog):
        """State should go to ERROR on session creation failure."""
        ctx, conn = self._make_mock_ctx()
        conn.new_session = AsyncMock(side_effect=RuntimeError("Session failed"))

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()

                with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                    with pytest.raises(RuntimeError, match="Session failed"):
                        await bridge.start()

                assert bridge.state == BridgeState.ERROR
                assert "start failed" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_state_on_prompt_timeout(self):
        """State should go to ERROR on prompt timeout."""
        ctx, conn = self._make_mock_ctx()

        async def slow_prompt(**kwargs):
            await asyncio.sleep(10)
            return FakePromptResult(text="too late")

        conn.prompt = slow_prompt

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge(timeout=0.1)
                await bridge.start()

                response = await bridge.send("Hello")
                assert response.success is False
                assert "timeout" in response.error.lower()
                assert bridge.state == BridgeState.ERROR

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_state_recovery_after_error(self, caplog):
        """Bridge should be able to restart after error state."""
        ctx1, conn1 = self._make_mock_ctx(session_id="s-error")
        # Use session failure (which IS fatal) instead of auth failure (non-fatal)
        conn1.new_session = AsyncMock(side_effect=RuntimeError("Session creation failed"))

        ctx2, conn2 = self._make_mock_ctx(session_id="s-recovered")

        call_count = [0]
        def make_ctx(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ctx1
            return ctx2

        with patch("avatar_engine.bridges.codex.spawn_agent_process", side_effect=make_ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()

                # First attempt: fails (session creation error is fatal)
                with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                    with pytest.raises(RuntimeError, match="Session creation failed"):
                        await bridge.start()
                assert bridge.state == BridgeState.ERROR
                assert "start failed" in caplog.text.lower()

                # Second attempt: succeeds
                await bridge.start()
                assert bridge.state == BridgeState.READY
                assert bridge.session_id == "s-recovered"

                await bridge.stop()


# =============================================================================
# ACP Event Routing Tests — verify events reach callbacks
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestACPEventRouting:
    """Test that ACP events are correctly routed to callbacks."""

    def _make_bridge_with_tracking(self):
        """Create a bridge with event and output tracking."""
        bridge = CodexBridge()
        events = []
        outputs = []

        bridge.on_event(lambda e: events.append(e))
        bridge.on_output(lambda t: outputs.append(t))

        return bridge, events, outputs

    def test_text_update_routes_to_output_callback(self):
        """AgentMessageChunk should trigger on_output callback."""
        bridge, events, outputs = self._make_bridge_with_tracking()

        bridge._handle_acp_update("s-1", AgentMessageChunk("Hello!"))

        assert len(outputs) == 1
        assert outputs[0] == "Hello!"

    def test_text_update_routes_to_event_callback(self):
        """AgentMessageChunk should emit acp_update event."""
        bridge, events, outputs = self._make_bridge_with_tracking()

        bridge._handle_acp_update("s-1", AgentMessageChunk("Hello!"))

        # Should have at least an acp_update event
        acp_events = [e for e in events if e.get("type") == "acp_update"]
        assert len(acp_events) >= 1
        assert acp_events[-1].get("text") == "Hello!"

    def test_thinking_update_routes_to_event_callback(self):
        """AgentThoughtChunk should emit thinking event."""
        bridge, events, outputs = self._make_bridge_with_tracking()

        bridge._handle_acp_update("s-1", AgentThoughtChunk("Let me reason..."))

        thinking_events = [e for e in events if e.get("type") == "thinking"]
        assert len(thinking_events) == 1
        assert thinking_events[0]["thought"] == "Let me reason..."

    def test_tool_call_routes_to_event_callback(self):
        """ToolCall should emit tool_call event."""
        bridge, events, outputs = self._make_bridge_with_tracking()

        bridge._handle_acp_update("s-1", ToolCall(name="exec", tool_id="tc-1"))

        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool_name"] == "exec"

    def test_tool_result_routes_to_event_callback(self):
        """ToolCallUpdate should emit tool_result event."""
        bridge, events, outputs = self._make_bridge_with_tracking()

        bridge._handle_acp_update(
            "s-1",
            ToolCallUpdate(tool_id="tc-1", status="completed", output="done"),
        )

        tool_events = [e for e in events if e.get("type") == "tool_result"]
        assert len(tool_events) == 1
        assert tool_events[0]["status"] == "completed"

    def test_text_accumulates_in_buffer(self):
        """Multiple text updates should accumulate in _acp_text_buffer."""
        bridge, events, outputs = self._make_bridge_with_tracking()

        bridge._handle_acp_update("s-1", AgentMessageChunk("Hello"))
        bridge._handle_acp_update("s-1", AgentMessageChunk(", "))
        bridge._handle_acp_update("s-1", AgentMessageChunk("world!"))

        assert bridge._acp_text_buffer == "Hello, world!"

    def test_complex_update_sequence(self):
        """Test a realistic sequence of mixed updates."""
        bridge, events, outputs = self._make_bridge_with_tracking()

        # Realistic sequence: thinking → text → tool → result → text
        bridge._handle_acp_update("s-1", AgentThoughtChunk("I need to check the file."))
        bridge._handle_acp_update("s-1", AgentMessageChunk("Let me check..."))
        bridge._handle_acp_update("s-1", ToolCall(name="exec", tool_id="tc-1",
                                                   parameters={"command": "cat main.py"}))
        bridge._handle_acp_update("s-1", ToolCallUpdate(tool_id="tc-1", status="completed",
                                                          output="def main(): pass"))
        bridge._handle_acp_update("s-1", AgentMessageChunk(" Here's the result."))

        # Verify events
        thinking_events = [e for e in events if e.get("type") == "thinking"]
        tool_call_events = [e for e in events if e.get("type") == "tool_call"]
        tool_result_events = [e for e in events if e.get("type") == "tool_result"]

        assert len(thinking_events) == 1
        assert len(tool_call_events) == 1
        assert len(tool_result_events) == 1

        # Verify text accumulation
        assert bridge._acp_text_buffer == "Let me check... Here's the result."

        # Verify output callback was called for text (not thinking)
        assert len(outputs) == 2  # Two text chunks


# =============================================================================
# ACP Permission/Approval Tests
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestACPPermissionHandling:
    """Test permission request handling in ACP flow."""

    def test_auto_approve_returns_first_option(self):
        """Auto-approve should return the first available option."""
        from avatar_engine.bridges.codex import _CodexACPClient

        client = _CodexACPClient(auto_approve=True)
        options = MagicMock()
        options.options = [
            {"outcome": "approved"},
            {"outcome": "approved_for_session"},
            {"outcome": "abort"},
        ]

        result = asyncio.run(
            client.request_permission(options, "s-1", "tc-1")
        )
        assert result["outcome"] == {"outcome": "approved"}

    def test_auto_approve_fallback_when_no_options(self):
        """Auto-approve should use fallback when options list is empty."""
        from avatar_engine.bridges.codex import _CodexACPClient

        client = _CodexACPClient(auto_approve=True)
        options = MagicMock()
        options.options = []

        result = asyncio.run(
            client.request_permission(options, "s-1", "tc-1")
        )
        assert result["outcome"]["outcome"] == "approved"

    def test_manual_deny_returns_cancelled(self, caplog):
        """Manual mode should deny with cancelled outcome and log warning."""
        from avatar_engine.bridges.codex import _CodexACPClient

        client = _CodexACPClient(auto_approve=False)
        options = MagicMock()

        with caplog.at_level(logging.WARNING, logger="avatar_engine.bridges.codex"):
            result = asyncio.run(
                client.request_permission(options, "s-1", "tc-1")
            )
        assert result["outcome"]["outcome"] == "cancelled"
        assert "denied" in caplog.text.lower() or "auto_approve=False" in caplog.text


# =============================================================================
# ACP Environment and Command Building Tests
# =============================================================================


class TestACPCommandBuilding:
    """Test how CodexBridge builds the ACP subprocess command."""

    def test_default_command_is_npx(self):
        """Default executable should be npx with codex-acp package."""
        bridge = CodexBridge()
        assert bridge.executable == "npx"
        assert bridge.executable_args == ["@zed-industries/codex-acp"]

    def test_custom_executable(self):
        """Custom executable path should be used."""
        bridge = CodexBridge(executable="/usr/local/bin/codex-acp", executable_args=[])
        assert bridge.executable == "/usr/local/bin/codex-acp"
        assert bridge.executable_args == []

    def test_custom_executable_args(self):
        """Custom executable args should be used."""
        bridge = CodexBridge(executable_args=["@custom/codex-acp", "--verbose"])
        assert bridge.executable_args == ["@custom/codex-acp", "--verbose"]

    def test_env_vars_passed_to_subprocess(self):
        """Environment variables should be included in subprocess."""
        bridge = CodexBridge(env={"CODEX_API_KEY": "sk-test-123"})
        env = bridge._build_subprocess_env()

        assert "CODEX_API_KEY" in env
        assert env["CODEX_API_KEY"] == "sk-test-123"

    def test_env_inherits_system_env(self):
        """Subprocess env should inherit from system environment."""
        bridge = CodexBridge(env={"CUSTOM": "value"})
        env = bridge._build_subprocess_env()

        # Should have PATH from system
        assert "PATH" in env
        assert "CUSTOM" in env

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
    async def test_executable_not_found_raises(self, caplog):
        """Missing executable should raise FileNotFoundError and log error."""
        with patch("shutil.which", return_value=None):
            bridge = CodexBridge(executable="nonexistent-binary")

            with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                with pytest.raises(FileNotFoundError, match="Executable not found"):
                    await bridge.start()
            assert "start failed" in caplog.text.lower()


# =============================================================================
# ACP Multi-Turn Conversation Tests
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestACPMultiTurnConversation:
    """Test multi-turn conversation behavior through ACP."""

    def _make_ctx(self, responses: Optional[List[str]] = None):
        """Create mock context with optional sequence of prompt responses."""
        resp_list = responses or ["Response 1", "Response 2", "Response 3"]
        resp_iter = iter(resp_list)

        conn = AsyncMock()
        proc = MagicMock()
        proc.pid = 22222

        conn.initialize = AsyncMock(return_value=FakeInitResponse())
        conn.authenticate = AsyncMock(return_value=None)
        conn.new_session = AsyncMock(
            return_value=FakeSessionResponse(session_id="multi-turn-session")
        )

        async def _prompt(**kwargs):
            try:
                text = next(resp_iter)
            except StopIteration:
                text = "No more responses"
            return FakePromptResult(text=text)

        conn.prompt = _prompt

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=(conn, proc))
        ctx.__aexit__ = AsyncMock(return_value=None)

        return ctx

    @pytest.mark.asyncio
    async def test_multi_turn_maintains_session(self):
        """Multiple sends should reuse the same session."""
        ctx = self._make_ctx(["Hello!", "How are you?", "Goodbye!"])

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                r1 = await bridge.send("Hi")
                r2 = await bridge.send("How are you?")
                r3 = await bridge.send("Bye")

                # All should use same session
                assert r1.session_id == "multi-turn-session"
                assert r2.session_id == "multi-turn-session"
                assert r3.session_id == "multi-turn-session"

                # History should accumulate
                assert len(bridge.get_history()) == 6  # 3 user + 3 assistant

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_history_content_accuracy(self):
        """History should accurately record prompts and responses."""
        ctx = self._make_ctx(["First answer", "Second answer"])

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                await bridge.send("First question")
                await bridge.send("Second question")

                history = bridge.get_history()
                assert history[0].role == "user"
                assert history[0].content == "First question"
                assert history[1].role == "assistant"
                assert history[1].content == "First answer"
                assert history[2].role == "user"
                assert history[2].content == "Second question"
                assert history[3].role == "assistant"
                assert history[3].content == "Second answer"

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_text_buffer_resets_between_turns(self):
        """Text buffer should reset between sends."""
        ctx = self._make_ctx(["Response A", "Response B"])

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                await bridge.send("Turn 1")
                # Buffer should be cleared for next turn
                assert bridge._acp_text_buffer == ""

                await bridge.send("Turn 2")
                assert bridge._acp_text_buffer == ""

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_events_reset_between_turns(self):
        """Events list should reset between sends."""
        ctx = self._make_ctx(["R1", "R2"])

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                await bridge.send("Turn 1")
                events_after_1 = len(bridge._acp_events)

                await bridge.send("Turn 2")
                # Events should have been cleared before turn 2
                # (the events we see now are only from turn 2)
                assert len(bridge._acp_events) == 0  # Buffer was cleared at start of send

                await bridge.stop()


# =============================================================================
# ACP Auth Edge Cases
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestACPAuthEdgeCases:
    """Test authentication edge cases in ACP flow."""

    def _make_ctx_with_auth(self, auth_behavior):
        """Create mock context with custom auth behavior."""
        conn = AsyncMock()
        proc = MagicMock()
        proc.pid = 33333

        conn.initialize = AsyncMock(return_value=FakeInitResponse())
        conn.authenticate = auth_behavior
        conn.new_session = AsyncMock(
            return_value=FakeSessionResponse(session_id="auth-test")
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=(conn, proc))
        ctx.__aexit__ = AsyncMock(return_value=None)

        return ctx

    @pytest.mark.asyncio
    async def test_auth_not_supported_continues(self):
        """If authenticate raises 'not supported', should continue."""
        ctx = self._make_ctx_with_auth(
            AsyncMock(side_effect=Exception("method not supported"))
        )

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                # Should succeed despite auth "failure"
                assert bridge.state == BridgeState.READY
                await bridge.stop()

    @pytest.mark.asyncio
    async def test_auth_not_implemented_continues(self):
        """If authenticate raises 'not implemented', should continue."""
        ctx = self._make_ctx_with_auth(
            AsyncMock(side_effect=Exception("not implemented"))
        )

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                assert bridge.state == BridgeState.READY
                await bridge.stop()

    @pytest.mark.asyncio
    async def test_auth_timeout(self, caplog):
        """Auth timeout should raise with helpful message and log error."""
        async def slow_auth(**kwargs):
            await asyncio.sleep(10)

        ctx = self._make_ctx_with_auth(slow_auth)

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge(timeout=0.1)

                with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                    with pytest.raises(RuntimeError, match="timed out"):
                        await bridge.start()
                assert "timed out" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_auth_generic_error_warns_but_continues(self, caplog):
        """Generic auth error should warn but continue to session creation."""
        ctx = self._make_ctx_with_auth(
            AsyncMock(side_effect=Exception("some random error"))
        )

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                with caplog.at_level(logging.WARNING, logger="avatar_engine.bridges.codex"):
                    await bridge.start()

                # Should continue despite error (with warning)
                assert bridge.state == BridgeState.READY
                assert "authenticate issue" in caplog.text.lower()
                await bridge.stop()


# =============================================================================
# ACP Cleanup / Resource Management Tests
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestACPCleanup:
    """Test ACP resource cleanup on stop/error."""

    def _make_ctx(self):
        conn = AsyncMock()
        proc = MagicMock()
        proc.pid = 44444

        conn.initialize = AsyncMock(return_value=FakeInitResponse())
        conn.authenticate = AsyncMock(return_value=None)
        conn.new_session = AsyncMock(
            return_value=FakeSessionResponse(session_id="cleanup-test")
        )
        conn.prompt = AsyncMock(return_value=FakePromptResult(text="OK"))

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=(conn, proc))
        ctx.__aexit__ = AsyncMock(return_value=None)

        return ctx

    @pytest.mark.asyncio
    async def test_stop_calls_aexit(self):
        """stop() should call __aexit__ on ACP context."""
        ctx = self._make_ctx()

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()
                await bridge.stop()

                ctx.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_clears_acp_state(self):
        """stop() should clear all ACP state."""
        ctx = self._make_ctx()

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                assert bridge._acp_conn is not None
                assert bridge._acp_session_id is not None

                await bridge.stop()

                assert bridge._acp_conn is None
                assert bridge._acp_proc is None
                assert bridge._acp_session_id is None

    @pytest.mark.asyncio
    async def test_cleanup_handles_aexit_error(self):
        """Cleanup should handle __aexit__ errors gracefully."""
        ctx = self._make_ctx()
        ctx.__aexit__ = AsyncMock(side_effect=Exception("Cleanup error"))

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()

                # Should not raise
                await bridge.stop()
                assert bridge._acp_conn is None

    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self):
        """Calling stop() twice should be safe."""
        ctx = self._make_ctx()

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()
                await bridge.start()
                await bridge.stop()
                await bridge.stop()  # Should not raise

                assert bridge.state == BridgeState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_cleanup_on_start_failure(self, caplog):
        """ACP context should be cleaned up if start fails partway."""
        ctx = self._make_ctx()
        # Make new_session fail after init+auth succeed
        conn_mock = (await ctx.__aenter__())[0]
        conn_mock.new_session = AsyncMock(side_effect=RuntimeError("Session boom"))

        # Reset the context mock for fresh usage
        ctx2 = self._make_ctx()
        conn2 = AsyncMock()
        proc2 = MagicMock()
        proc2.pid = 55555
        conn2.initialize = AsyncMock(return_value=FakeInitResponse())
        conn2.authenticate = AsyncMock(return_value=None)
        conn2.new_session = AsyncMock(side_effect=RuntimeError("Session boom"))
        ctx2.__aenter__ = AsyncMock(return_value=(conn2, proc2))
        ctx2.__aexit__ = AsyncMock(return_value=None)

        with patch("avatar_engine.bridges.codex.spawn_agent_process", return_value=ctx2):
            with patch("shutil.which", return_value="/usr/bin/npx"):
                bridge = CodexBridge()

                with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                    with pytest.raises(RuntimeError, match="Session boom"):
                        await bridge.start()

                # ACP context should have been cleaned up
                ctx2.__aexit__.assert_called_once()
                assert bridge._acp_conn is None
                assert "start failed" in caplog.text.lower()


# =============================================================================
# MCP Server ACP Format Conversion Tests
# =============================================================================


class TestMCPServerACPConversion:
    """Test conversion of MCP server configs to ACP format."""

    def test_basic_server_conversion(self):
        """Basic MCP server should be converted correctly."""
        bridge = CodexBridge(mcp_servers={
            "tools": {
                "command": "python",
                "args": ["server.py"],
            }
        })
        result = bridge._build_mcp_servers_acp()

        assert len(result) == 1
        assert result[0]["name"] == "tools"
        assert result[0]["command"] == "python"
        assert result[0]["args"] == ["server.py"]
        assert result[0]["env"] == []

    def test_server_with_env_conversion(self):
        """MCP server with env vars should convert env to list format."""
        bridge = CodexBridge(mcp_servers={
            "tools": {
                "command": "python",
                "args": [],
                "env": {"KEY1": "val1", "KEY2": "val2"},
            }
        })
        result = bridge._build_mcp_servers_acp()

        env_list = result[0]["env"]
        assert len(env_list) == 2
        env_dict = {e["name"]: e["value"] for e in env_list}
        assert env_dict["KEY1"] == "val1"
        assert env_dict["KEY2"] == "val2"

    def test_multiple_servers_conversion(self):
        """Multiple MCP servers should all be converted."""
        bridge = CodexBridge(mcp_servers={
            "server-a": {"command": "python", "args": ["a.py"]},
            "server-b": {"command": "node", "args": ["b.js"]},
        })
        result = bridge._build_mcp_servers_acp()

        assert len(result) == 2
        names = {r["name"] for r in result}
        assert "server-a" in names
        assert "server-b" in names

    def test_empty_mcp_servers(self):
        """Empty or None MCP servers should return empty list."""
        bridge = CodexBridge(mcp_servers=None)
        assert bridge._build_mcp_servers_acp() == []

        bridge = CodexBridge(mcp_servers={})
        assert bridge._build_mcp_servers_acp() == []

    def test_server_without_args(self):
        """Server without args key should default to empty list."""
        bridge = CodexBridge(mcp_servers={
            "simple": {"command": "/usr/bin/server"},
        })
        result = bridge._build_mcp_servers_acp()

        assert result[0]["args"] == []
