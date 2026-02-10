"""
Codex ACP bridge tests.

These tests verify:
- CodexBridge initialization and configuration
- ACP lifecycle (spawn → initialize → authenticate → new_session → prompt)
- Text extraction from AgentMessageChunk
- Thinking extraction from AgentThoughtChunk
- Tool call event mapping (ToolCall, ToolCallUpdate)
- Approval auto-accept callback
- Error handling (auth failure, session failure, timeout)
- Cleanup on stop
- MCP server configuration conversion
- State management
- Statistics tracking
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from avatar_engine.bridges.codex import (
    CodexBridge,
    _extract_text_from_update,
    _extract_text_from_result,
    _extract_thinking_from_update,
    _extract_tool_event_from_update,
    _ACP_AVAILABLE,
)
from avatar_engine.bridges.base import BridgeState, BridgeResponse, Message


# =============================================================================
# Mock Helpers
# =============================================================================


def _make_mock_conn_proc(session_id="codex-session-123"):
    """Create mock ACP connection and process for connect_to_agent pattern."""
    conn = AsyncMock()
    proc = AsyncMock()
    proc.stdin = MagicMock()
    proc.stdout = MagicMock()
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock()

    # Mock initialize
    init_resp = MagicMock()
    init_resp.protocol_version = 1
    init_resp.capabilities = {}
    conn.initialize = AsyncMock(return_value=init_resp)

    # Mock authenticate
    conn.authenticate = AsyncMock(return_value=None)

    # Mock new_session
    session_resp = MagicMock()
    session_resp.session_id = session_id
    conn.new_session = AsyncMock(return_value=session_resp)

    # Mock prompt
    prompt_resp = MagicMock()
    prompt_resp.content = MagicMock()
    prompt_resp.content.text = "Hello from Codex!"
    conn.prompt = AsyncMock(return_value=prompt_resp)

    # Mock close
    conn.close = AsyncMock()

    return conn, proc


class _ContentBlock:
    """Fake content block for testing."""
    def __init__(self, text, type_="text"):
        self.text = text
        self.type = type_


# Use exact class names that match type().__name__ checks in codex.py

class AgentMessageChunk:
    """Fake AgentMessageChunk — name must match type().__name__ check."""
    def __init__(self, text):
        self.content = _ContentBlock(text, "text")


class AgentThoughtChunk:
    """Fake AgentThoughtChunk — name must match type().__name__ check."""
    def __init__(self, thought):
        self.thought = _ContentBlock(thought, "thinking")


class ToolCall:
    """Fake ToolCall — name must match type().__name__ == 'ToolCall' check."""
    def __init__(self, name="exec", id="tc-1", kind="Execute", parameters=None):
        self.name = name
        self.id = id
        self.kind = kind
        self.parameters = parameters or {}


class ToolCallUpdate:
    """Fake ToolCallUpdate — name must match type().__name__ == 'ToolCallUpdate' check."""
    def __init__(self, id="tc-1", status="completed", output=None, error=None):
        self.id = id
        self.status = status
        self.output = output
        self.error = error


def _make_text_update(text: str):
    """Create a fake AgentMessageChunk update."""
    return AgentMessageChunk(text)


def _make_thinking_update(thought: str):
    """Create a fake AgentThoughtChunk update."""
    return AgentThoughtChunk(thought)


def _make_tool_call_update(name="exec", tool_id="tc-1", kind="Execute"):
    """Create a fake ToolCall update."""
    return ToolCall(name=name, id=tool_id, kind=kind)


def _make_tool_call_result_update(tool_id="tc-1", output="success", error=None, status="completed"):
    """Create a fake ToolCallUpdate update."""
    return ToolCallUpdate(id=tool_id, status=status, output=output, error=error)


# =============================================================================
# Initialization Tests
# =============================================================================


class TestCodexBridgeInit:
    """Tests for CodexBridge initialization."""

    def test_default_values(self):
        """Should have sensible defaults."""
        bridge = CodexBridge()
        assert bridge.executable == "npx"
        assert bridge.executable_args == ["@zed-industries/codex-acp"]
        assert bridge.model == ""
        assert bridge.timeout == 120
        assert bridge.auth_method == "chatgpt"
        assert bridge.approval_mode == "auto"
        assert bridge.sandbox_mode == "workspace-write"
        assert bridge.state == BridgeState.DISCONNECTED

    def test_custom_values(self):
        """Should accept custom values."""
        bridge = CodexBridge(
            executable="/usr/local/bin/codex-acp",
            executable_args=[],
            model="o3",
            timeout=60,
            auth_method="openai-api-key",
            approval_mode="manual",
            sandbox_mode="read-only",
        )
        assert bridge.executable == "/usr/local/bin/codex-acp"
        assert bridge.executable_args == []
        assert bridge.model == "o3"
        assert bridge.timeout == 60
        assert bridge.auth_method == "openai-api-key"
        assert bridge.approval_mode == "manual"
        assert bridge.sandbox_mode == "read-only"

    def test_provider_name(self):
        """Should return correct provider name."""
        bridge = CodexBridge()
        assert bridge.provider_name == "codex"

    def test_is_persistent(self):
        """Should always be persistent (ACP warm session)."""
        bridge = CodexBridge()
        assert bridge.is_persistent is True

    def test_custom_env(self):
        """Should accept custom environment variables."""
        bridge = CodexBridge(env={"CODEX_API_KEY": "sk-test"})
        assert bridge.env == {"CODEX_API_KEY": "sk-test"}

    def test_mcp_servers_stored(self):
        """Should store MCP server configuration."""
        mcp = {"tools": {"command": "python", "args": ["tools.py"]}}
        bridge = CodexBridge(mcp_servers=mcp)
        assert bridge.mcp_servers == mcp

    def test_system_prompt_stored(self):
        """Should store system prompt."""
        bridge = CodexBridge(system_prompt="You are a helpful assistant.")
        assert bridge.system_prompt == "You are a helpful assistant."

    def test_working_dir_default(self):
        """Should default to cwd if not specified."""
        bridge = CodexBridge()
        assert bridge.working_dir  # Should not be empty

    def test_working_dir_custom(self):
        """Should accept custom working directory."""
        bridge = CodexBridge(working_dir="/tmp/test")
        assert bridge.working_dir == "/tmp/test"


# =============================================================================
# Auth Method Tests
# =============================================================================


class TestCodexAuthMethods:
    """Test authentication method configurations."""

    def test_chatgpt_auth(self):
        """ChatGPT auth should be the default."""
        bridge = CodexBridge()
        assert bridge.auth_method == "chatgpt"

    def test_codex_api_key_auth(self):
        """Should accept codex-api-key auth."""
        bridge = CodexBridge(auth_method="codex-api-key")
        assert bridge.auth_method == "codex-api-key"

    def test_openai_api_key_auth(self):
        """Should accept openai-api-key auth."""
        bridge = CodexBridge(auth_method="openai-api-key")
        assert bridge.auth_method == "openai-api-key"


# =============================================================================
# Config Files (Zero Footprint)
# =============================================================================


class TestCodexConfigFiles:
    """Test that Codex requires no config files (Zero Footprint)."""

    def test_setup_config_files_is_noop(self, tmp_path):
        """Should not create any files."""
        bridge = CodexBridge(working_dir=str(tmp_path))
        bridge._setup_config_files()

        # No files should be created
        files = list(tmp_path.iterdir())
        assert len(files) == 0

    def test_no_sandbox_created(self):
        """Should not create a ConfigSandbox."""
        bridge = CodexBridge()
        bridge._setup_config_files()
        assert not hasattr(bridge, "_sandbox") or bridge._sandbox is None


# =============================================================================
# MCP Server Conversion Tests
# =============================================================================


class TestCodexMCPConversion:
    """Test MCP server config conversion to ACP format."""

    def test_empty_mcp_servers(self):
        """Should return empty list when no MCP servers."""
        bridge = CodexBridge()
        result = bridge._build_mcp_servers_acp()
        assert result == []

    def test_single_mcp_server(self):
        """Should convert single MCP server to ACP format."""
        bridge = CodexBridge(mcp_servers={
            "tools": {
                "command": "python",
                "args": ["tools.py"],
            }
        })
        result = bridge._build_mcp_servers_acp()
        assert len(result) == 1
        assert result[0]["name"] == "tools"
        assert result[0]["command"] == "python"
        assert result[0]["args"] == ["tools.py"]
        assert result[0]["env"] == []

    def test_mcp_server_with_env(self):
        """Should convert env dict to list of {name, value} objects."""
        bridge = CodexBridge(mcp_servers={
            "tools": {
                "command": "python",
                "args": ["tools.py"],
                "env": {"API_KEY": "secret", "DEBUG": "1"},
            }
        })
        result = bridge._build_mcp_servers_acp()
        assert len(result) == 1
        env_list = result[0]["env"]
        assert len(env_list) == 2
        env_dict = {e["name"]: e["value"] for e in env_list}
        assert env_dict["API_KEY"] == "secret"
        assert env_dict["DEBUG"] == "1"

    def test_multiple_mcp_servers(self):
        """Should convert multiple MCP servers."""
        bridge = CodexBridge(mcp_servers={
            "tools": {"command": "python", "args": ["tools.py"]},
            "db": {"command": "node", "args": ["db-server.js"]},
        })
        result = bridge._build_mcp_servers_acp()
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"tools", "db"}


# =============================================================================
# Text Extraction Tests
# =============================================================================


class TestTextExtraction:
    """Test text extraction from ACP updates."""

    def test_extract_text_from_message_chunk(self):
        """Should extract text from AgentMessageChunk."""
        update = _make_text_update("Hello!")
        text = _extract_text_from_update(update)
        assert text == "Hello!"

    def test_extract_text_from_dict(self):
        """Should extract text from dict-style update."""
        update = {
            "type": "AgentMessageChunk",
            "content": {"text": "Hello dict!"},
        }
        text = _extract_text_from_update(update)
        assert text == "Hello dict!"

    def test_extract_text_from_dict_skips_reasoning_content(self):
        """Dict AgentMessageChunk with thinking/reasoning block should be skipped."""
        update = {
            "type": "AgentMessageChunk",
            "content": {"type": "thinking", "text": "internal thought"},
        }
        text = _extract_text_from_update(update)
        assert text is None

    def test_extract_text_from_dict_list_skips_reasoning_blocks(self):
        """Dict content list should only include text blocks, not reasoning."""
        update = {
            "type": "AgentMessageChunk",
            "content": [
                {"type": "thinking", "text": "hidden"},
                {"type": "text", "text": "visible"},
            ],
        }
        text = _extract_text_from_update(update)
        assert text == "visible"

    def test_extract_text_from_content_list(self):
        """Should extract text from content block list."""
        update = MagicMock()
        block1 = MagicMock()
        block1.text = "Part 1"
        block1.type = "text"
        block2 = MagicMock()
        block2.text = "Part 2"
        block2.type = "text"
        update.content = [block1, block2]
        text = _extract_text_from_update(update)
        assert text == "Part 1Part 2"

    def test_skip_thinking_blocks_in_text(self):
        """Should skip thinking blocks when extracting text."""
        update = MagicMock()
        update.content = MagicMock()
        update.content.text = "thinking content"
        update.content.type = "thinking"
        text = _extract_text_from_update(update)
        assert text is None

    def test_extract_text_returns_none_for_empty(self):
        """Should return None for updates without text."""
        update = MagicMock(spec=[])  # No attributes
        text = _extract_text_from_update(update)
        assert text is None

    def test_extract_text_from_result(self):
        """Should extract text from PromptResponse."""
        result = MagicMock()
        result.content = MagicMock()
        result.content.text = "Response text"
        text = _extract_text_from_result(result)
        assert text == "Response text"

    def test_extract_text_from_result_list(self):
        """Should extract text from result with content list."""
        result = MagicMock()
        block = MagicMock()
        block.text = "Block text"
        result.content = [block]
        text = _extract_text_from_result(result)
        assert text == "Block text"

    def test_extract_text_from_result_dict(self):
        """Should extract text from result with dict blocks."""
        result = MagicMock()
        result.content = [{"text": "Dict block"}]
        text = _extract_text_from_result(result)
        assert text == "Dict block"

    def test_extract_text_from_result_empty(self):
        """Should return empty string for empty result."""
        result = MagicMock(spec=[])
        text = _extract_text_from_result(result)
        assert text == ""


# =============================================================================
# Thinking Extraction Tests
# =============================================================================


class TestThinkingExtraction:
    """Test thinking content extraction from ACP updates."""

    def test_extract_thinking_from_thought_attr(self):
        """Should extract thinking from thought.text attribute."""
        update = _make_thinking_update("Let me think...")
        thinking = _extract_thinking_from_update(update)
        assert thinking == "Let me think..."

    def test_extract_thinking_from_thought_string(self):
        """Should extract thinking from string thought attribute."""
        update = MagicMock()
        update.thought = "Direct string thought"
        thinking = _extract_thinking_from_update(update)
        assert thinking == "Direct string thought"

    def test_extract_thinking_from_content_type(self):
        """Should extract thinking from content with type=thinking."""
        update = MagicMock()
        update.thought = None
        content = MagicMock()
        content.type = "thinking"
        content.text = "Thinking content"
        update.content = content
        thinking = _extract_thinking_from_update(update)
        assert thinking == "Thinking content"

    def test_extract_thinking_from_content_list(self):
        """Should extract thinking from content list with thinking block."""
        update = MagicMock()
        update.thought = None
        block = MagicMock()
        block.type = "thinking"
        block.text = "Listed thinking"
        update.content = [block]
        thinking = _extract_thinking_from_update(update)
        assert thinking == "Listed thinking"

    def test_extract_thinking_from_dict(self):
        """Should extract thinking from dict-style update."""
        update = {"thought": "Dict thought"}
        thinking = _extract_thinking_from_update(update)
        assert thinking == "Dict thought"

    def test_extract_thinking_from_dict_type(self):
        """Should extract thinking from dict with AgentThoughtChunk type."""
        update = {
            "type": "AgentThoughtChunk",
            "content": {"text": "Typed dict thought"},
        }
        thinking = _extract_thinking_from_update(update)
        assert thinking == "Typed dict thought"

    def test_no_thinking_returns_none(self):
        """Should return None when no thinking content."""
        update = MagicMock()
        update.thought = None
        update.content = MagicMock()
        update.content.type = "text"
        update.content.text = "Just text"
        thinking = _extract_thinking_from_update(update)
        assert thinking is None


# =============================================================================
# Tool Event Extraction Tests
# =============================================================================


class TestToolEventExtraction:
    """Test tool call event extraction from ACP updates."""

    def test_extract_tool_call_started(self):
        """Should extract ToolCall as started event."""
        update = _make_tool_call_update(name="npm test", tool_id="tc-1", kind="Execute")
        event = _extract_tool_event_from_update(update)
        assert event is not None
        assert event["type"] == "tool_call"
        assert event["tool_name"] == "npm test"
        assert event["tool_id"] == "tc-1"
        assert event["kind"] == "Execute"
        assert event["status"] == "started"

    def test_extract_tool_call_completed(self):
        """Should extract ToolCallUpdate as completed event."""
        update = _make_tool_call_result_update(
            tool_id="tc-1", output="Tests passed", status="completed"
        )
        event = _extract_tool_event_from_update(update)
        assert event is not None
        assert event["type"] == "tool_result"
        assert event["tool_id"] == "tc-1"
        assert event["status"] == "completed"
        assert event["result"] == "Tests passed"
        assert event["error"] is None

    def test_extract_tool_call_failed(self):
        """Should extract failed ToolCallUpdate."""
        update = _make_tool_call_result_update(
            tool_id="tc-2", output=None, error="Command failed", status="failed"
        )
        event = _extract_tool_event_from_update(update)
        assert event is not None
        assert event["type"] == "tool_result"
        assert event["status"] == "failed"
        assert event["error"] == "Command failed"

    def test_extract_tool_call_from_dict(self):
        """Should extract tool call from dict-style update."""
        update = {
            "type": "ToolCall",
            "name": "git status",
            "id": "tc-3",
            "kind": "Execute",
            "parameters": {},
        }
        event = _extract_tool_event_from_update(update)
        assert event is not None
        assert event["tool_name"] == "git status"

    def test_extract_tool_result_from_dict(self):
        """Should extract tool result from dict-style update."""
        update = {
            "type": "ToolCallUpdate",
            "id": "tc-3",
            "status": "completed",
            "output": "branch main",
        }
        event = _extract_tool_event_from_update(update)
        assert event is not None
        assert event["status"] == "completed"
        assert event["result"] == "branch main"

    def test_no_tool_event_for_text(self):
        """Should return None for non-tool updates."""
        update = _make_text_update("Just text")
        event = _extract_tool_event_from_update(update)
        assert event is None


# =============================================================================
# ACP Client Tests
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestCodexACPClient:
    """Test _CodexACPClient callback behavior."""

    def test_auto_approve_permission(self):
        """Should auto-approve when auto_approve=True with typed response."""
        from avatar_engine.bridges.codex import _CodexACPClient

        client = _CodexACPClient(auto_approve=True)
        options = MagicMock()
        opt = MagicMock()
        opt.option_id = "approve-once"
        options.options = [opt]

        result = asyncio.run(
            client.request_permission(options, "session-1", "tool-call")
        )
        assert hasattr(result, "outcome")
        assert result.outcome.option_id == "approve-once"
        assert result.outcome.outcome == "selected"

    def test_deny_permission(self, caplog):
        """Should deny when auto_approve=False with typed DeniedOutcome."""
        from avatar_engine.bridges.codex import _CodexACPClient

        client = _CodexACPClient(auto_approve=False)
        options = MagicMock()

        with caplog.at_level(logging.WARNING, logger="avatar_engine.bridges.codex"):
            result = asyncio.run(
                client.request_permission(options, "session-1", "tool-call")
            )
        assert hasattr(result, "outcome")
        assert result.outcome.outcome == "cancelled"
        assert "denied" in caplog.text.lower() or "auto_approve=False" in caplog.text

    def test_session_update_callback(self):
        """Should call on_update callback for session updates."""
        from avatar_engine.bridges.codex import _CodexACPClient

        updates = []
        client = _CodexACPClient(on_update=lambda sid, u: updates.append((sid, u)))

        asyncio.run(
            client.session_update("sess-1", "update-data")
        )
        assert len(updates) == 1
        assert updates[0] == ("sess-1", "update-data")

    def test_session_update_no_callback(self):
        """Should handle session update without callback."""
        from avatar_engine.bridges.codex import _CodexACPClient

        client = _CodexACPClient(on_update=None)
        # Should not raise
        asyncio.run(
            client.session_update("sess-1", "update-data")
        )


# =============================================================================
# ACP Lifecycle Tests (mocked)
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestCodexACPLifecycle:
    """Test ACP lifecycle with mocked connect_to_agent."""

    @pytest.mark.asyncio
    async def test_start_full_lifecycle(self):
        """Should complete full ACP lifecycle: connect → init → auth → session."""
        conn, proc = _make_mock_conn_proc()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()

                    assert bridge.state == BridgeState.READY
                    assert bridge.session_id == "codex-session-123"
                    assert bridge._acp_session_id == "codex-session-123"

                    conn.initialize.assert_awaited_once()
                    conn.authenticate.assert_awaited_once_with(method_id="chatgpt")
                    conn.new_session.assert_awaited_once()

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_start_with_api_key_auth(self):
        """Should use correct auth method."""
        conn, proc = _make_mock_conn_proc()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge(auth_method="openai-api-key")
                    await bridge.start()

                    conn.authenticate.assert_awaited_once_with(method_id="openai-api-key")

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_start_with_mcp_servers(self):
        """Should pass MCP servers to new_session."""
        conn, proc = _make_mock_conn_proc()

        mcp = {
            "tools": {
                "command": "python",
                "args": ["tools.py"],
                "env": {"KEY": "val"},
            }
        }

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge(mcp_servers=mcp)
                    await bridge.start()

                    call_kwargs = conn.new_session.call_args
                    mcp_arg = call_kwargs.kwargs.get("mcp_servers", call_kwargs[1].get("mcp_servers"))
                    assert len(mcp_arg) == 1
                    assert mcp_arg[0]["name"] == "tools"
                    assert mcp_arg[0]["command"] == "python"

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up_acp(self):
        """Should clean up ACP connection and process on stop."""
        conn, proc = _make_mock_conn_proc()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()
                    await bridge.stop()

                    assert bridge._acp_conn is None
                    assert bridge._acp_proc is None
                    assert bridge._acp_session_id is None
                    assert bridge.state == BridgeState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_start_fails_without_executable(self, caplog):
        """Should raise when executable not found and log error."""
        with patch("shutil.which", return_value=None):
            bridge = CodexBridge()
            with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                with pytest.raises(FileNotFoundError, match="Executable not found"):
                    await bridge.start()
            assert "start failed" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_start_auth_timeout(self, caplog):
        """Should raise on auth timeout and log error."""
        conn, proc = _make_mock_conn_proc()
        conn.authenticate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge(timeout=1)
                    with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                        with pytest.raises(RuntimeError, match="authentication timed out"):
                            await bridge.start()
                    assert "timed out" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_start_auth_not_supported(self):
        """Should continue if auth returns 'not supported'."""
        conn, proc = _make_mock_conn_proc()
        conn.authenticate = AsyncMock(side_effect=Exception("method not supported"))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()
                    assert bridge.state == BridgeState.READY
                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_start_session_failure(self, caplog):
        """Should raise on session creation failure and log error."""
        conn, proc = _make_mock_conn_proc()
        conn.new_session = AsyncMock(side_effect=Exception("Session error"))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                        with pytest.raises(Exception, match="Session error"):
                            await bridge.start()
                    assert bridge.state == BridgeState.ERROR
                    assert "start failed" in caplog.text.lower()


# =============================================================================
# Send Tests (mocked ACP)
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestCodexSend:
    """Test send() through mocked ACP session."""

    @pytest.mark.asyncio
    async def test_send_basic(self):
        """Should send prompt and return response."""
        conn, proc = _make_mock_conn_proc()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()

                    response = await bridge.send("Hello!")

                    assert response.success is True
                    assert response.content == "Hello from Codex!"
                    assert response.session_id == "codex-session-123"
                    assert response.duration_ms >= 0

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_with_streaming_text(self):
        """Should use accumulated text buffer from ACP updates."""
        conn, proc = _make_mock_conn_proc()

        async def mock_prompt(**kwargs):
            bridge._handle_acp_update("codex-session-123", _make_text_update("Hello "))
            bridge._handle_acp_update("codex-session-123", _make_text_update("World!"))
            return MagicMock()

        conn.prompt = mock_prompt

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()

                    response = await bridge.send("Hi")

                    assert response.success is True
                    assert response.content == "Hello World!"

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_timeout(self):
        """Should handle timeout gracefully."""
        conn, proc = _make_mock_conn_proc()
        conn.prompt = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge(timeout=1)
                    await bridge.start()

                    response = await bridge.send("Hello")

                    assert response.success is False
                    assert "timeout" in response.error.lower()
                    assert bridge.state == BridgeState.ERROR

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_error(self, caplog):
        """Should handle send errors gracefully and log error."""
        conn, proc = _make_mock_conn_proc()
        conn.prompt = AsyncMock(side_effect=RuntimeError("API error"))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()

                    with caplog.at_level(logging.ERROR, logger="avatar_engine.bridges.codex"):
                        response = await bridge.send("Hello")

                    assert response.success is False
                    assert "API error" in response.error
                    assert bridge.state == BridgeState.ERROR
                    assert "send failed" in caplog.text.lower()

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_auto_starts(self):
        """Should auto-start if disconnected."""
        conn, proc = _make_mock_conn_proc()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    assert bridge.state == BridgeState.DISCONNECTED

                    response = await bridge.send("Hello")

                    assert response.success is True
                    assert bridge.state == BridgeState.READY

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_history_tracking(self):
        """Should track conversation history."""
        conn, proc = _make_mock_conn_proc()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()

                    await bridge.send("Hello")
                    await bridge.send("How are you?")

                    history = bridge.get_history()
                    assert len(history) == 4  # 2 user + 2 assistant
                    assert history[0].role == "user"
                    assert history[0].content == "Hello"
                    assert history[1].role == "assistant"
                    assert history[2].role == "user"
                    assert history[2].content == "How are you?"

                    await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_stats_tracking(self):
        """Should track usage statistics."""
        conn, proc = _make_mock_conn_proc()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()

                    await bridge.send("Hello")
                    await bridge.send("Again")

                    stats = bridge.get_stats()
                    assert stats["total_requests"] == 2
                    assert stats["successful_requests"] == 2
                    assert stats["failed_requests"] == 0
                    assert stats["total_duration_ms"] >= 0

                    await bridge.stop()


# =============================================================================
# Stream Tests (mocked ACP)
# =============================================================================


@pytest.mark.skipif(not _ACP_AVAILABLE, reason="ACP SDK not installed")
class TestCodexStream:
    """Test send_stream() through mocked ACP session."""

    @pytest.mark.asyncio
    async def test_stream_basic(self):
        """Should stream text chunks."""
        conn, proc = _make_mock_conn_proc()

        async def mock_prompt(**kwargs):
            bridge._handle_acp_update("codex-session-123", _make_text_update("Hello "))
            bridge._handle_acp_update("codex-session-123", _make_text_update("World!"))
            return MagicMock()

        conn.prompt = mock_prompt

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("avatar_engine.bridges.codex.connect_to_agent", return_value=conn):
                with patch("shutil.which", return_value="/usr/bin/npx"):
                    bridge = CodexBridge()
                    await bridge.start()

                    chunks = []
                    async for chunk in bridge.send_stream("Hi"):
                        chunks.append(chunk)

                    assert chunks == ["Hello ", "World!"]
                    assert bridge.state == BridgeState.READY

                    await bridge.stop()


# =============================================================================
# State Management Tests
# =============================================================================


class TestCodexBridgeState:
    """Test Codex bridge state management."""

    def test_initial_state(self):
        """Should start disconnected."""
        bridge = CodexBridge()
        assert bridge.state == BridgeState.DISCONNECTED

    def test_state_change_callback(self):
        """Should call state change callback."""
        bridge = CodexBridge()
        states = []
        bridge.on_state_change(lambda s, d="": states.append(s))

        bridge._set_state(BridgeState.WARMING_UP)
        bridge._set_state(BridgeState.READY)

        assert states == [BridgeState.WARMING_UP, BridgeState.READY]


# =============================================================================
# Event Handling Tests
# =============================================================================


class TestCodexEventHandling:
    """Test ACP update event handling."""

    def test_handle_text_update(self):
        """Should accumulate text and emit event."""
        bridge = CodexBridge()
        events = []
        bridge.on_event(lambda e: events.append(e))

        update = _make_text_update("Hello!")
        bridge._handle_acp_update("sess-1", update)

        assert bridge._acp_text_buffer == "Hello!"
        assert len(bridge._acp_events) > 0

    def test_handle_thinking_update(self):
        """Should emit thinking event."""
        bridge = CodexBridge()
        events = []
        bridge.on_event(lambda e: events.append(e))

        update = _make_thinking_update("Let me think...")
        bridge._handle_acp_update("sess-1", update)

        thinking_events = [e for e in events if e.get("type") == "thinking"]
        assert len(thinking_events) == 1
        assert thinking_events[0]["thought"] == "Let me think..."

    def test_suppresses_text_duplicate_of_thinking(self):
        """If ACP duplicates reasoning as text, text output should be suppressed."""
        bridge = CodexBridge()
        streamed = []
        bridge._on_output = lambda chunk: streamed.append(chunk)

        class _DupUpdate:
            def __init__(self):
                self.thought = _ContentBlock("Preparing project inspection plan", "thinking")
                self.content = _ContentBlock("Preparing project inspection plan", "text")

        bridge._handle_acp_update("sess-1", _DupUpdate())
        assert bridge._acp_text_buffer == ""
        assert streamed == []

    def test_handle_tool_call_update(self):
        """Should emit tool call event."""
        bridge = CodexBridge()
        events = []
        bridge.on_event(lambda e: events.append(e))

        update = _make_tool_call_update(name="npm test", tool_id="tc-1")
        bridge._handle_acp_update("sess-1", update)

        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool_name"] == "npm test"
        assert tool_events[0]["status"] == "started"

    def test_handle_tool_result_update(self):
        """Should emit tool result event."""
        bridge = CodexBridge()
        events = []
        bridge.on_event(lambda e: events.append(e))

        update = _make_tool_call_result_update(tool_id="tc-1", output="OK")
        bridge._handle_acp_update("sess-1", update)

        result_events = [e for e in events if e.get("type") == "tool_result"]
        assert len(result_events) == 1
        assert result_events[0]["status"] == "completed"

    def test_handle_output_callback(self):
        """Should call on_output callback for text."""
        bridge = CodexBridge()
        output = []
        bridge.on_output(lambda t: output.append(t))

        update = _make_text_update("chunk1")
        bridge._handle_acp_update("sess-1", update)

        assert output == ["chunk1"]


# =============================================================================
# Health Check Tests
# =============================================================================


class TestCodexBridgeHealth:
    """Test health check functionality."""

    def test_unhealthy_when_disconnected(self):
        """Should be unhealthy when disconnected."""
        bridge = CodexBridge()
        assert bridge.is_healthy() is False

    def test_check_health_disconnected(self):
        """Should return health dict when disconnected."""
        bridge = CodexBridge()
        health = bridge.check_health()

        assert health["healthy"] is False
        assert health["state"] == "disconnected"
        assert health["provider"] == "codex"


# =============================================================================
# Abstract Method Stub Tests
# =============================================================================


class TestCodexAbstractMethods:
    """Test that abstract method stubs raise NotImplementedError."""

    def test_build_persistent_command(self):
        """Should raise NotImplementedError."""
        bridge = CodexBridge()
        with pytest.raises(NotImplementedError):
            bridge._build_persistent_command()

    def test_format_user_message(self):
        """Should raise NotImplementedError."""
        bridge = CodexBridge()
        with pytest.raises(NotImplementedError):
            bridge._format_user_message("test")

    def test_build_oneshot_command(self):
        """Should raise NotImplementedError."""
        bridge = CodexBridge()
        with pytest.raises(NotImplementedError):
            bridge._build_oneshot_command("test")

    def test_is_turn_complete(self):
        """Should detect result events."""
        bridge = CodexBridge()
        assert bridge._is_turn_complete({"type": "result"}) is True
        assert bridge._is_turn_complete({"type": "message"}) is False

    def test_parse_session_id(self):
        """Should return ACP session ID."""
        bridge = CodexBridge()
        bridge._acp_session_id = "test-sess"
        assert bridge._parse_session_id([]) == "test-sess"

    def test_parse_content(self):
        """Should parse content from ACP events."""
        bridge = CodexBridge()
        events = [
            {"type": "acp_update", "text": "Hello "},
            {"type": "acp_update", "text": "World"},
            {"type": "thinking", "thought": "skip"},
        ]
        content = bridge._parse_content(events)
        assert content == "Hello World"

    def test_parse_tool_calls(self):
        """Should parse tool calls from events."""
        bridge = CodexBridge()
        events = [
            {"type": "tool_call", "tool_name": "exec", "parameters": {}, "tool_id": "t1", "kind": "Execute"},
            {"type": "acp_update", "text": "skip"},
        ]
        calls = bridge._parse_tool_calls(events)
        assert len(calls) == 1
        assert calls[0]["tool"] == "exec"
        assert calls[0]["kind"] == "Execute"

    def test_parse_usage(self):
        """Should parse usage from events."""
        bridge = CodexBridge()
        events = [
            {"type": "token_usage", "usage": {"input": 100, "output": 50}},
        ]
        usage = bridge._parse_usage(events)
        assert usage["input"] == 100
        assert usage["output"] == 50

    def test_parse_usage_returns_none(self):
        """Should return None when no usage events."""
        bridge = CodexBridge()
        usage = bridge._parse_usage([])
        assert usage is None

    def test_extract_text_delta(self):
        """Should extract text delta from ACP update events."""
        bridge = CodexBridge()
        assert bridge._extract_text_delta({"type": "acp_update", "text": "hi"}) == "hi"
        assert bridge._extract_text_delta({"type": "acp_update"}) is None
        assert bridge._extract_text_delta({"type": "thinking"}) is None


# =============================================================================
# ACP Not Available Tests
# =============================================================================


class TestCodexWithoutACP:
    """Test behavior when ACP SDK is not installed."""

    @pytest.mark.asyncio
    async def test_start_raises_without_acp(self):
        """Should raise RuntimeError when ACP SDK is not available."""
        with patch("avatar_engine.bridges.codex._ACP_AVAILABLE", False):
            bridge = CodexBridge()
            with pytest.raises(RuntimeError, match="agent-client-protocol SDK not installed"):
                await bridge.start()
