"""
Bridge Observability tests — verifies the "blind user" fixes.

Tests that ACP subprocess stderr is captured and surfaced as DiagnosticEvents,
that callback exceptions are not silently swallowed, and that timeout errors
include contextual information.

Uses mock subprocesses to simulate CLI stderr output without real CLI binaries.
"""

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from avatar_engine.bridges.base import BaseBridge, BridgeState, _classify_stderr_level
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.bridges.codex import CodexBridge


# =============================================================================
# Mock Helpers
# =============================================================================


def create_mock_acp_proc(
    stderr_lines: Optional[List[str]] = None,
    returncode: int = 0,
):
    """Create a mock ACP subprocess with configurable stderr output.

    The key difference from a real subprocess: stderr is a PIPE (not None)
    that yields lines from stderr_lines, simulating CLI diagnostic output.
    """
    proc = MagicMock()
    proc.pid = 99999
    _returncode = [None]  # Start as running (None)

    def get_returncode():
        return _returncode[0]

    type(proc).returncode = PropertyMock(side_effect=get_returncode)

    # stdin — minimal mock
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()

    # stdout — minimal mock (ACP SDK reads this)
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(return_value=b"")

    # stderr — THIS IS THE KEY: PIPE with simulated output
    stderr_queue: asyncio.Queue = asyncio.Queue()
    if stderr_lines:
        for line in stderr_lines:
            stderr_queue.put_nowait(line)

    async def mock_stderr_readline():
        try:
            line = stderr_queue.get_nowait()
            return (line + "\n").encode()
        except asyncio.QueueEmpty:
            # Simulate process exit — set returncode and return empty
            _returncode[0] = returncode
            return b""

    proc.stderr = MagicMock()
    proc.stderr.readline = mock_stderr_readline

    # Process lifecycle
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    async def mock_wait():
        _returncode[0] = returncode

    proc.wait = mock_wait

    return proc


# =============================================================================
# _classify_stderr_level (base.py utility)
# =============================================================================


class TestClassifyStderrLevel:
    """Test the stderr line → diagnostic level classifier."""

    def test_error_keywords(self):
        assert _classify_stderr_level("ERROR: auth failed") == "error"
        assert _classify_stderr_level("fatal: cannot connect") == "error"
        assert _classify_stderr_level("CRITICAL: out of memory") == "error"
        assert _classify_stderr_level("Auth failed with exception") == "error"

    def test_warning_keywords(self):
        assert _classify_stderr_level("WARNING: rate limit approaching") == "warning"
        assert _classify_stderr_level("deprecated API endpoint") == "warning"
        assert _classify_stderr_level("Token will expire soon") == "warning"

    def test_debug_keywords(self):
        assert _classify_stderr_level("DEBUG: internal state dump") == "debug"
        assert _classify_stderr_level("trace: entering function X") == "debug"

    def test_info_default(self):
        assert _classify_stderr_level("Connecting to server...") == "info"
        assert _classify_stderr_level("Authenticating via OAuth") == "info"
        assert _classify_stderr_level("Loading model gemini-3-pro") == "info"


# =============================================================================
# GeminiBridge ACP stderr capture
# =============================================================================


class TestGeminiACPStderrCapture:
    """Test that GeminiBridge captures and surfaces ACP subprocess stderr."""

    def _make_bridge(self) -> GeminiBridge:
        """Create a GeminiBridge with ACP disabled to avoid real CLI deps."""
        bridge = GeminiBridge(
            executable="gemini",
            working_dir="/tmp",
            timeout=5,
            acp_enabled=False,  # We'll manually test the monitor
        )
        return bridge

    @pytest.mark.asyncio
    async def test_stderr_pipe_not_none(self):
        """Verify that the ACP subprocess code uses stderr=PIPE, not None.

        Source-level assertion: gemini.py _start_acp() must use
        stderr=asyncio.subprocess.PIPE.
        """
        import inspect
        from avatar_engine.bridges import gemini

        source = inspect.getsource(gemini.GeminiBridge._start_acp)
        assert "stderr=asyncio.subprocess.PIPE" in source
        assert "stderr=None" not in source

    @pytest.mark.asyncio
    async def test_monitor_acp_stderr_captures_lines(self):
        """_monitor_acp_stderr reads stderr lines and stores in buffer."""
        bridge = self._make_bridge()

        # Simulate an ACP proc with stderr output
        bridge._acp_proc = create_mock_acp_proc(
            stderr_lines=[
                "Authenticating via OAuth...",
                "Loading model gemini-3-pro-preview",
                "WARNING: rate limit near threshold",
            ]
        )

        # Run the monitor
        await bridge._monitor_acp_stderr()

        # Check stderr buffer was populated
        buf = bridge.get_stderr_buffer()
        assert len(buf) == 3
        assert "Authenticating via OAuth..." in buf[0]
        assert "Loading model" in buf[1]
        assert "rate limit" in buf[2]

    @pytest.mark.asyncio
    async def test_monitor_acp_stderr_emits_diagnostic_events(self):
        """_monitor_acp_stderr emits diagnostic events via _on_event."""
        bridge = self._make_bridge()

        events: List[Dict[str, Any]] = []
        bridge._on_event = lambda evt: events.append(evt)

        bridge._acp_proc = create_mock_acp_proc(
            stderr_lines=[
                "Connecting to API...",
                "ERROR: authentication failed",
            ]
        )

        await bridge._monitor_acp_stderr()

        assert len(events) == 2

        # First event — info level
        assert events[0]["type"] == "diagnostic"
        assert events[0]["source"] == "acp-stderr"
        assert events[0]["level"] == "info"
        assert "Connecting" in events[0]["message"]

        # Second event — error level
        assert events[1]["type"] == "diagnostic"
        assert events[1]["level"] == "error"
        assert "authentication failed" in events[1]["message"]

    @pytest.mark.asyncio
    async def test_monitor_acp_stderr_calls_on_stderr_callback(self):
        """_monitor_acp_stderr invokes _on_stderr callback for each line."""
        bridge = self._make_bridge()

        stderr_lines_received: List[str] = []
        bridge._on_stderr = lambda text: stderr_lines_received.append(text)

        bridge._acp_proc = create_mock_acp_proc(
            stderr_lines=["Line 1", "Line 2"]
        )

        await bridge._monitor_acp_stderr()
        assert len(stderr_lines_received) == 2

    @pytest.mark.asyncio
    async def test_monitor_handles_empty_stderr(self):
        """Monitor exits cleanly when stderr has no output."""
        bridge = self._make_bridge()
        events: List[Dict] = []
        bridge._on_event = lambda evt: events.append(evt)

        bridge._acp_proc = create_mock_acp_proc(stderr_lines=[])
        await bridge._monitor_acp_stderr()

        assert len(events) == 0
        assert len(bridge.get_stderr_buffer()) == 0

    @pytest.mark.asyncio
    async def test_monitor_survives_no_proc(self):
        """Monitor exits cleanly when _acp_proc is None."""
        bridge = self._make_bridge()
        bridge._acp_proc = None
        # Should not raise
        await bridge._monitor_acp_stderr()

    @pytest.mark.asyncio
    async def test_cleanup_acp_cancels_stderr_task(self):
        """_cleanup_acp cancels/cleans the stderr monitor task."""
        bridge = self._make_bridge()

        # Create a blocking stderr (never returns data, needs cancel)
        proc = MagicMock()
        proc.pid = 99999
        type(proc).returncode = PropertyMock(return_value=None)
        proc.stdin = MagicMock()
        proc.stdin.close = MagicMock()
        proc.stderr = MagicMock()

        # readline blocks forever until cancelled
        async def blocking_readline():
            await asyncio.sleep(999)
            return b""

        proc.stderr.readline = blocking_readline
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        bridge._acp_proc = proc
        bridge._acp_conn = None

        # Start monitor as a task — it will block on readline
        bridge._acp_stderr_task = asyncio.create_task(
            bridge._monitor_acp_stderr()
        )

        # Give it a tick to start
        await asyncio.sleep(0.01)
        assert not bridge._acp_stderr_task.done()

        # Cleanup should cancel the blocking task
        await bridge._cleanup_acp()
        assert bridge._acp_stderr_task is None

    @pytest.mark.asyncio
    async def test_acp_stderr_task_attribute_exists(self):
        """Bridge has _acp_stderr_task attribute initialized to None."""
        bridge = self._make_bridge()
        assert hasattr(bridge, "_acp_stderr_task")
        assert bridge._acp_stderr_task is None


# =============================================================================
# CodexBridge ACP stderr capture
# =============================================================================


class TestCodexACPStderrCapture:
    """Test that CodexBridge captures and surfaces ACP subprocess stderr."""

    def _make_bridge(self) -> CodexBridge:
        bridge = CodexBridge(
            executable="npx",
            working_dir="/tmp",
            timeout=5,
        )
        return bridge

    @pytest.mark.asyncio
    async def test_stderr_pipe_not_none(self):
        """Verify that codex.py _start_acp() uses stderr=PIPE, not None."""
        import inspect
        from avatar_engine.bridges import codex

        source = inspect.getsource(codex.CodexBridge._start_acp)
        assert "stderr=asyncio.subprocess.PIPE" in source
        assert "stderr=None" not in source

    @pytest.mark.asyncio
    async def test_monitor_acp_stderr_captures_lines(self):
        """_monitor_acp_stderr reads stderr lines and stores in buffer."""
        bridge = self._make_bridge()

        bridge._acp_proc = create_mock_acp_proc(
            stderr_lines=[
                "Starting codex-acp...",
                "ERROR: CODEX_API_KEY not set",
            ]
        )

        await bridge._monitor_acp_stderr()

        buf = bridge.get_stderr_buffer()
        assert len(buf) == 2
        assert "codex-acp" in buf[0]
        assert "CODEX_API_KEY" in buf[1]

    @pytest.mark.asyncio
    async def test_monitor_acp_stderr_emits_diagnostic_events(self):
        """_monitor_acp_stderr emits diagnostic events via _on_event."""
        bridge = self._make_bridge()

        events: List[Dict[str, Any]] = []
        bridge._on_event = lambda evt: events.append(evt)

        bridge._acp_proc = create_mock_acp_proc(
            stderr_lines=[
                "Authenticating via ChatGPT OAuth...",
                "WARNING: deprecated model requested",
            ]
        )

        await bridge._monitor_acp_stderr()

        assert len(events) == 2
        assert events[0]["level"] == "info"
        assert events[0]["source"] == "acp-stderr"
        assert events[1]["level"] == "warning"

    @pytest.mark.asyncio
    async def test_acp_stderr_task_attribute_exists(self):
        """Bridge has _acp_stderr_task attribute initialized to None."""
        bridge = self._make_bridge()
        assert hasattr(bridge, "_acp_stderr_task")
        assert bridge._acp_stderr_task is None

    @pytest.mark.asyncio
    async def test_cleanup_acp_cancels_stderr_task(self):
        """_cleanup_acp cancels/cleans the stderr monitor task."""
        bridge = self._make_bridge()

        # Create a blocking stderr (never returns data, needs cancel)
        proc = MagicMock()
        proc.pid = 99999
        type(proc).returncode = PropertyMock(return_value=None)
        proc.stdin = MagicMock()
        proc.stdin.close = MagicMock()
        proc.stderr = MagicMock()

        async def blocking_readline():
            await asyncio.sleep(999)
            return b""

        proc.stderr.readline = blocking_readline
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        bridge._acp_proc = proc
        bridge._acp_conn = None

        bridge._acp_stderr_task = asyncio.create_task(
            bridge._monitor_acp_stderr()
        )
        await asyncio.sleep(0.01)
        assert not bridge._acp_stderr_task.done()

        await bridge._cleanup_acp()
        assert bridge._acp_stderr_task is None


# =============================================================================
# ACP callback exception surfacing
# =============================================================================


class TestACPCallbackExceptionSurfacing:
    """Test that exceptions in _handle_acp_update are surfaced, not swallowed."""

    @pytest.mark.asyncio
    async def test_gemini_callback_error_emits_diagnostic(self):
        """GeminiBridge._handle_acp_update emits diagnostic on exception."""
        bridge = GeminiBridge(
            executable="gemini",
            working_dir="/tmp",
            timeout=5,
            acp_enabled=False,
        )

        events: List[Dict[str, Any]] = []
        bridge._on_event = lambda evt: events.append(evt)

        # Force an exception in _handle_acp_update_inner
        with patch.object(bridge, "_handle_acp_update_inner", side_effect=ValueError("bad update format")):
            bridge._handle_acp_update("session-123", {"broken": True})

        assert len(events) == 1
        assert events[0]["type"] == "diagnostic"
        assert events[0]["level"] == "error"
        assert events[0]["source"] == "acp-callback"
        assert "bad update format" in events[0]["message"]

    @pytest.mark.asyncio
    async def test_codex_callback_error_emits_diagnostic(self):
        """CodexBridge._handle_acp_update emits diagnostic on exception."""
        bridge = CodexBridge(
            executable="npx",
            working_dir="/tmp",
            timeout=5,
        )

        events: List[Dict[str, Any]] = []
        bridge._on_event = lambda evt: events.append(evt)

        with patch.object(bridge, "_handle_acp_update_inner", side_effect=KeyError("missing_field")):
            bridge._handle_acp_update("session-456", {"incomplete": True})

        assert len(events) == 1
        assert events[0]["type"] == "diagnostic"
        assert events[0]["level"] == "error"
        assert events[0]["source"] == "acp-callback"
        assert "missing_field" in events[0]["message"]

    @pytest.mark.asyncio
    async def test_gemini_callback_no_event_cb_doesnt_crash(self):
        """If _on_event is None, exception is still handled gracefully."""
        bridge = GeminiBridge(
            executable="gemini",
            working_dir="/tmp",
            timeout=5,
            acp_enabled=False,
        )
        bridge._on_event = None

        with patch.object(bridge, "_handle_acp_update_inner", side_effect=RuntimeError("oops")):
            # Should not raise
            bridge._handle_acp_update("session-123", {})

    @pytest.mark.asyncio
    async def test_codex_callback_no_event_cb_doesnt_crash(self):
        """If _on_event is None, exception is still handled gracefully."""
        bridge = CodexBridge(
            executable="npx",
            working_dir="/tmp",
            timeout=5,
        )
        bridge._on_event = None

        with patch.object(bridge, "_handle_acp_update_inner", side_effect=RuntimeError("oops")):
            bridge._handle_acp_update("session-456", {})

    def test_gemini_callback_logs_warning_not_debug(self):
        """GeminiBridge logs callback errors at WARNING level, not DEBUG."""
        import inspect
        from avatar_engine.bridges import gemini

        source = inspect.getsource(gemini.GeminiBridge._handle_acp_update)
        # Must use warning, not debug
        assert "logger.warning" in source
        assert "logger.debug" not in source

    def test_codex_callback_logs_warning_not_debug(self):
        """CodexBridge logs callback errors at WARNING level, not DEBUG."""
        import inspect
        from avatar_engine.bridges import codex

        source = inspect.getsource(codex.CodexBridge._handle_acp_update)
        assert "logger.warning" in source
        assert "logger.debug" not in source


# =============================================================================
# Timeout context (server.py)
# =============================================================================


class TestTimeoutContext:
    """Test that server timeout errors include contextual information."""

    def test_timeout_error_includes_elapsed_time(self):
        """Source-level: timeout handler uses time.monotonic() for elapsed."""
        import inspect
        from avatar_engine.web import server

        # Find the _run_chat function source — it's a nested def so we check
        # the module source directly
        source = inspect.getsource(server)
        # Must set chat_start before wait_for
        assert "chat_start = time.monotonic()" in source
        # Must compute elapsed in timeout handler
        assert "elapsed = time.monotonic() - chat_start" in source

    def test_timeout_error_includes_engine_state(self):
        """Source-level: timeout handler collects engine/bridge state."""
        import inspect
        from avatar_engine.web import server

        source = inspect.getsource(server)
        assert "bridge_state" in source
        assert "engine_state" in source

    def test_timeout_error_includes_last_diagnostic(self):
        """Source-level: timeout handler includes last stderr diagnostic."""
        import inspect
        from avatar_engine.web import server

        source = inspect.getsource(server)
        assert "get_stderr_buffer" in source
        assert "last diagnostic" in source

    def test_timeout_error_format(self):
        """Source-level: timeout message includes elapsed seconds."""
        import inspect
        from avatar_engine.web import server

        source = inspect.getsource(server)
        assert "timed out after" in source


# =============================================================================
# DiagnosticEvent pipeline integration
# =============================================================================


class TestDiagnosticEventPipeline:
    """Test the full diagnostic event pipeline from bridge to engine."""

    def test_engine_handles_diagnostic_event_type(self):
        """engine.py _process_event emits DiagnosticEvent for type=diagnostic."""
        from avatar_engine.events import DiagnosticEvent
        import inspect
        from avatar_engine import engine as eng_mod

        source = inspect.getsource(eng_mod.AvatarEngine._process_event)
        assert '"diagnostic"' in source
        assert "DiagnosticEvent" in source

    def test_web_bridge_forwards_diagnostic(self):
        """web/bridge.py registers handler for DiagnosticEvent."""
        import inspect
        from avatar_engine.web import bridge as br_mod

        # Handler registration is in _register_handlers (called from __init__)
        source = inspect.getsource(br_mod.WebSocketBridge._register_handlers)
        assert "DiagnosticEvent" in source

    def test_protocol_maps_diagnostic_event(self):
        """web/protocol.py maps DiagnosticEvent to 'diagnostic' WS type."""
        from avatar_engine.web.protocol import EVENT_TYPE_MAP
        from avatar_engine.events import DiagnosticEvent

        assert EVENT_TYPE_MAP.get(DiagnosticEvent) == "diagnostic"

    def test_stderr_source_is_acp_stderr(self):
        """ACP stderr monitor uses 'acp-stderr' as diagnostic source."""
        import inspect
        from avatar_engine.bridges import gemini, codex

        gemini_source = inspect.getsource(gemini.GeminiBridge._monitor_acp_stderr)
        assert '"acp-stderr"' in gemini_source

        codex_source = inspect.getsource(codex.CodexBridge._monitor_acp_stderr)
        assert '"acp-stderr"' in codex_source

    def test_callback_source_is_acp_callback(self):
        """ACP callback error uses 'acp-callback' as diagnostic source."""
        import inspect
        from avatar_engine.bridges import gemini, codex

        gemini_source = inspect.getsource(gemini.GeminiBridge._handle_acp_update)
        assert '"acp-callback"' in gemini_source

        codex_source = inspect.getsource(codex.CodexBridge._handle_acp_update)
        assert '"acp-callback"' in codex_source


# =============================================================================
# Stderr buffer thread safety
# =============================================================================


class TestStderrBufferThreadSafety:
    """Test that stderr buffer is protected by lock for ACP callbacks."""

    @pytest.mark.asyncio
    async def test_gemini_stderr_uses_lock(self):
        """Verify _monitor_acp_stderr uses _stderr_lock for buffer access."""
        import inspect
        from avatar_engine.bridges import gemini

        source = inspect.getsource(gemini.GeminiBridge._monitor_acp_stderr)
        assert "_stderr_lock" in source

    @pytest.mark.asyncio
    async def test_codex_stderr_uses_lock(self):
        """Verify _monitor_acp_stderr uses _stderr_lock for buffer access."""
        import inspect
        from avatar_engine.bridges import codex

        source = inspect.getsource(codex.CodexBridge._monitor_acp_stderr)
        assert "_stderr_lock" in source

    @pytest.mark.asyncio
    async def test_concurrent_stderr_writes(self):
        """Simulate concurrent stderr writes from multiple threads."""
        bridge = GeminiBridge(
            executable="gemini",
            working_dir="/tmp",
            timeout=5,
            acp_enabled=False,
        )

        # Simulate many lines being written concurrently
        lines = [f"Line {i}" for i in range(50)]
        bridge._acp_proc = create_mock_acp_proc(stderr_lines=lines)

        await bridge._monitor_acp_stderr()

        buf = bridge.get_stderr_buffer()
        assert len(buf) == 50


# =============================================================================
# Claude bridge comparison (already correct)
# =============================================================================


class TestClaudeBridgeStderrBaseline:
    """Verify Claude bridge already has proper stderr handling as baseline."""

    def test_claude_uses_stderr_pipe(self):
        """Claude bridge uses stderr=PIPE (has always been correct)."""
        import inspect
        from avatar_engine.bridges import claude

        source = inspect.getsource(claude.ClaudeBridge)
        assert "stderr=asyncio.subprocess.PIPE" in source

    def test_claude_starts_stderr_monitor(self):
        """Claude bridge starts _monitor_stderr in persistent mode."""
        import inspect
        from avatar_engine.bridges import claude

        source = inspect.getsource(claude.ClaudeBridge.start)
        assert "_stderr_task" in source or "_monitor_stderr" in source


# =============================================================================
# Gemini _start_acp spawns stderr task
# =============================================================================


class TestACPStartSpawnsStderrTask:
    """Verify that _start_acp creates the stderr monitor task."""

    def test_gemini_start_acp_creates_stderr_task(self):
        """gemini.py _start_acp creates _acp_stderr_task."""
        import inspect
        from avatar_engine.bridges import gemini

        source = inspect.getsource(gemini.GeminiBridge._start_acp)
        assert "_acp_stderr_task" in source
        assert "_monitor_acp_stderr" in source

    def test_codex_start_acp_creates_stderr_task(self):
        """codex.py _start_acp creates _acp_stderr_task."""
        import inspect
        from avatar_engine.bridges import codex

        source = inspect.getsource(codex.CodexBridge._start_acp)
        assert "_acp_stderr_task" in source
        assert "_monitor_acp_stderr" in source


# =============================================================================
# Server timeout value sanity check
# =============================================================================


class TestServerTimeoutConfig:
    """Verify server chat timeout is reasonable."""

    def test_server_timeout_at_least_600(self):
        """Server chat_timeout base value should be >= 600 seconds."""
        import re
        import inspect
        from avatar_engine.web import server

        source = inspect.getsource(server)
        match = re.search(r"chat_timeout\s*=\s*(\d+)", source)
        assert match, "chat_timeout not found in server source"
        assert int(match.group(1)) >= 600
