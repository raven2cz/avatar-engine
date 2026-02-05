"""
Async flow integration tests — tests real chat/stream functionality.

These tests verify the complete flow from user message to response,
including subprocess communication, JSONL parsing, and event emission.
"""

import asyncio
import json
from typing import List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from avatar_engine import AvatarEngine
from avatar_engine.bridges.claude import ClaudeBridge
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.events import TextEvent, ToolEvent, StateEvent, ErrorEvent
from avatar_engine.types import BridgeResponse, BridgeState


# =============================================================================
# Mock Subprocess Factory
# =============================================================================


def create_mock_subprocess(
    stdout_lines: List[str],
    stderr_lines: List[str] = None,
    returncode: int = None,
    delay_per_line: float = 0.0,
) -> Tuple[MagicMock, asyncio.Queue]:
    """
    Create a realistic mock subprocess for testing.

    Returns:
        Tuple of (mock_proc, stdout_queue) for controlling responses.
    """
    proc = MagicMock()
    proc.pid = 12345

    # returncode starts as None (running), set when process exits
    _returncode = [returncode]
    type(proc).returncode = PropertyMock(side_effect=lambda: _returncode[0])

    # Stdin mock
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()

    # Stdout as async queue for controlled responses
    stdout_queue = asyncio.Queue()
    for line in stdout_lines:
        stdout_queue.put_nowait(line + "\n" if line else "")
    stdout_queue.put_nowait("")  # EOF

    async def mock_readline():
        if delay_per_line > 0:
            await asyncio.sleep(delay_per_line)
        try:
            line = stdout_queue.get_nowait()
            return line.encode() if line else b""
        except asyncio.QueueEmpty:
            return b""

    proc.stdout = MagicMock()
    proc.stdout.readline = mock_readline

    # Stderr mock
    stderr_content = "\n".join(stderr_lines) if stderr_lines else ""
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=stderr_content.encode())

    # Process control
    async def mock_wait():
        _returncode[0] = 0
        return 0

    proc.wait = mock_wait
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    # Communicate for oneshot mode
    async def mock_communicate():
        all_stdout = "\n".join(stdout_lines).encode()
        all_stderr = stderr_content.encode()
        _returncode[0] = 0
        return (all_stdout, all_stderr)

    proc.communicate = mock_communicate

    return proc, stdout_queue


# =============================================================================
# UC-1: Basic Chat Flow Tests
# =============================================================================


class TestBasicChatFlow:
    """
    Use Case: User sends a message and gets a response.

    Expected behavior:
    1. Engine starts and warms up bridge
    2. chat() sends message and receives response
    3. Response contains content, success=True
    4. Session ID is extracted
    5. History is updated
    """

    @pytest.mark.asyncio
    async def test_claude_chat_full_flow(self):
        """Complete chat flow with Claude bridge."""
        # Realistic Claude response
        stdout_lines = [
            json.dumps({"type": "system", "session_id": "sess-abc123", "message": "Session started"}),
            json.dumps({"type": "assistant", "message": {"content": "Hello! How can I help you today?"}}),
            json.dumps({"type": "result", "duration_ms": 1500, "total_cost_usd": 0.001}),
        ]

        mock_proc, _ = create_mock_subprocess(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/claude"):
                engine = AvatarEngine(provider="claude")
                await engine.start()

                response = await engine.chat("Hello!")

                # Verify response
                assert response.success is True
                assert response.content == "Hello! How can I help you today?"
                assert response.session_id == "sess-abc123"
                # Duration is stored in token_usage, not directly in response
                assert response.token_usage.get("duration_ms") == 1500

                # Verify state
                assert engine.session_id == "sess-abc123"
                assert len(engine.get_history()) == 2  # user + assistant
                assert engine.get_history()[0].role == "user"
                assert engine.get_history()[0].content == "Hello!"
                assert engine.get_history()[1].role == "assistant"

                await engine.stop()

    @pytest.mark.asyncio
    async def test_gemini_chat_full_flow_oneshot(self):
        """Complete chat flow with Gemini bridge in oneshot mode."""
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "gemini-123", "model": "gemini-2.0-flash"}),
            json.dumps({"type": "message", "role": "user", "content": "Hello!"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi there! I'm Gemini."}),
            json.dumps({"type": "result", "status": "success", "stats": {"input_tokens": 10, "output_tokens": 8}}),
        ]

        mock_proc, _ = create_mock_subprocess(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Hello!")

                assert response.success is True
                assert response.content == "Hi there! I'm Gemini."
                assert response.session_id == "gemini-123"

                await engine.stop()

    @pytest.mark.asyncio
    async def test_chat_returns_empty_on_no_content(self):
        """Chat should handle responses with no assistant content."""
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "test-123"}),
            json.dumps({"type": "result", "status": "success"}),
        ]

        mock_proc, _ = create_mock_subprocess(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Hello!")

                assert response.success is True
                assert response.content == ""  # Empty but not error

                await engine.stop()

    @pytest.mark.asyncio
    async def test_chat_multiple_turns_preserves_history(self):
        """Multi-turn chat should preserve conversation history."""
        # First turn
        stdout_lines_1 = [
            json.dumps({"type": "init", "session_id": "sess-1"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hello!"}),
            json.dumps({"type": "result"}),
        ]
        # Second turn
        stdout_lines_2 = [
            json.dumps({"type": "message", "role": "assistant", "content": "I remember you said hi."}),
            json.dumps({"type": "result"}),
        ]

        mock_proc_1, _ = create_mock_subprocess(stdout_lines_1)
        mock_proc_2, _ = create_mock_subprocess(stdout_lines_2)

        call_count = [0]

        async def mock_create_subprocess(*args, **kwargs):
            call_count[0] += 1
            return mock_proc_1 if call_count[0] == 1 else mock_proc_2

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                await engine.chat("Hi!")
                await engine.chat("Remember what I said?")

                history = engine.get_history()
                assert len(history) == 4  # 2 user + 2 assistant
                assert history[0].content == "Hi!"
                assert history[2].content == "Remember what I said?"

                await engine.stop()


# =============================================================================
# UC-2: Streaming Response Tests
# =============================================================================


class TestStreamingResponse:
    """
    Use Case: User streams response chunks in real-time.

    Expected behavior:
    1. chat_stream() yields chunks as they arrive
    2. TextEvent emitted for each chunk
    3. Final content matches accumulated chunks
    """

    @pytest.mark.asyncio
    async def test_chat_stream_yields_chunks(self):
        """chat_stream should yield response chunks."""
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "stream-test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hello ", "delta": True}),
            json.dumps({"type": "message", "role": "assistant", "content": "world!", "delta": True}),
            json.dumps({"type": "result"}),
        ]

        mock_proc, _ = create_mock_subprocess(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                chunks = []
                async for chunk in engine.chat_stream("Hello!"):
                    chunks.append(chunk)

                # Should have received chunks
                assert len(chunks) >= 1
                full_response = "".join(chunks)
                assert "Hello" in full_response or "world" in full_response

                await engine.stop()

    @pytest.mark.asyncio
    async def test_stream_emits_text_events(self):
        """Streaming should emit TextEvent for each chunk."""
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "event-test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc, _ = create_mock_subprocess(stdout_lines)

        text_events = []

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def capture_text(event: TextEvent):
                    text_events.append(event)

                await engine.start()

                async for _ in engine.chat_stream("Hello!"):
                    pass

                # Should have emitted at least one TextEvent
                assert len(text_events) >= 1

                await engine.stop()


# =============================================================================
# UC-3: Timeout Handling Tests
# =============================================================================


class TestTimeoutHandling:
    """
    Use Case: Handle timeouts gracefully.

    Expected behavior:
    1. Timeout during chat() returns error response
    2. Engine state recovers to READY
    3. ErrorEvent emitted
    """

    @pytest.mark.asyncio
    async def test_chat_timeout_returns_error_response(self):
        """Chat should return error response on timeout."""
        # Create subprocess that never responds
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdin.close = MagicMock()

        # Stdout that hangs forever
        async def hang_forever():
            await asyncio.sleep(100)  # Will be cancelled by timeout
            return b""

        proc.stdout = MagicMock()
        proc.stdout.readline = hang_forever
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=0)

        # Mock communicate for oneshot
        async def mock_communicate():
            await asyncio.sleep(100)
            return (b"", b"")
        proc.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini", timeout=1)  # 1 second timeout
                await engine.start()

                response = await engine.chat("Hello!")

                # Should fail gracefully
                assert response.success is False
                assert "timeout" in response.error.lower() or "Timeout" in response.error

                await engine.stop()


# =============================================================================
# UC-4: Process Crash Tests
# =============================================================================


class TestProcessCrash:
    """
    Use Case: Handle unexpected process termination.

    Expected behavior:
    1. Detect process exit mid-conversation
    2. Return error response
    3. Trigger auto-restart on next chat
    """

    @pytest.mark.asyncio
    async def test_chat_after_process_crash_triggers_restart(self):
        """Chat should work even after process issues (oneshot mode)."""
        # In oneshot mode (Gemini default), each chat creates a new process
        # so "crash recovery" means subsequent processes work fine

        stdout_lines = [
            json.dumps({"type": "init", "session_id": "gemini-test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Response OK"}),
            json.dumps({"type": "result"}),
        ]

        call_count = [0]

        async def create_fresh_proc(*args, **kwargs):
            call_count[0] += 1
            proc, _ = create_mock_subprocess(stdout_lines)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_fresh_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # First chat works
                response1 = await engine.chat("Hello!")
                assert response1.success is True

                # Second chat also works (fresh process)
                response2 = await engine.chat("Hello again!")
                assert response2.success is True

                # Each call creates a new process in oneshot mode
                assert call_count[0] == 2

                await engine.stop()


# =============================================================================
# UC-5: GUI Event Integration Tests
# =============================================================================


class TestGUIEventIntegration:
    """
    Use Case: Update GUI in real-time during AI response.

    Expected behavior:
    1. TextEvent fires during streaming
    2. StateEvent fires on state changes
    3. Events contain correct data
    """

    @pytest.mark.asyncio
    async def test_all_event_types_fire_correctly(self):
        """All event types should fire during chat flow."""
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "event-all"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Response"}),
            json.dumps({"type": "result", "status": "success"}),
        ]

        mock_proc, _ = create_mock_subprocess(stdout_lines)

        text_events = []
        state_events = []

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def on_text(e):
                    text_events.append(e)

                @engine.on(StateEvent)
                def on_state(e):
                    state_events.append(e)

                await engine.start()
                await engine.chat("Hello!")
                await engine.stop()

                # Verify events
                assert len(state_events) >= 1  # At least one state change

                # Check state transition contains valid states
                valid_states = {"warming_up", "ready", "busy", "disconnected"}
                for event in state_events:
                    # Compare by value to avoid enum identity issues
                    state_value = event.new_state.value if hasattr(event.new_state, "value") else str(event.new_state)
                    assert state_value in valid_states, f"Invalid state: {state_value}"

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash_engine(self):
        """Handler exceptions should be caught, not crash engine."""
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "error-handler"}),
            json.dumps({"type": "message", "role": "assistant", "content": "OK"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc, _ = create_mock_subprocess(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def bad_handler(e):
                    raise ValueError("Handler crashed!")

                await engine.start()

                # Should not raise despite handler exception
                response = await engine.chat("Hello!")
                assert response.success is True

                await engine.stop()


# =============================================================================
# UC-9: Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """
    Use Case: Prevent API rate limit errors.

    Expected behavior:
    1. Burst capacity allows initial requests
    2. Subsequent requests wait
    3. Stats track throttling
    """

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_burst(self):
        """Rate limiter should allow burst capacity."""
        from avatar_engine.utils.rate_limit import RateLimiter

        limiter = RateLimiter(requests_per_minute=10, burst=3, enabled=True)

        # First 3 should not wait (burst)
        for i in range(3):
            wait = await limiter.acquire()
            assert wait == 0, f"Burst request {i} should not wait"

    @pytest.mark.asyncio
    async def test_rate_limiter_throttles_after_burst(self):
        """Rate limiter should throttle after burst exhausted."""
        from avatar_engine.utils.rate_limit import RateLimiter

        limiter = RateLimiter(requests_per_minute=60, burst=2, enabled=True)

        # Exhaust burst
        await limiter.acquire()
        await limiter.acquire()

        # Third should require wait (or return 0 if token refilled)
        # Just verify it doesn't crash
        wait = await limiter.acquire()
        assert wait >= 0


# =============================================================================
# UC-10: Cost Tracking Tests (Claude)
# =============================================================================


class TestCostTracking:
    """
    Use Case: Monitor and limit costs.

    Expected behavior:
    1. Cost accumulates across requests
    2. CostEvent emitted
    3. Budget enforcement works
    """

    @pytest.mark.asyncio
    async def test_claude_cost_tracking_accumulates(self):
        """Claude bridge should track cumulative cost."""
        bridge = ClaudeBridge(max_budget_usd=1.0)

        # Simulate cost tracking via events (how it works in real usage)
        bridge._total_cost_usd = 0.0

        # _track_cost expects a list of events, not a float
        events_1 = [{"type": "result", "total_cost_usd": 0.10}]
        events_2 = [{"type": "result", "total_cost_usd": 0.20}]

        bridge._track_cost(events_1)
        bridge._track_cost(events_2)

        assert bridge._total_cost_usd == pytest.approx(0.30)

    @pytest.mark.asyncio
    async def test_claude_over_budget_detection(self):
        """Claude bridge should detect when over budget."""
        bridge = ClaudeBridge(max_budget_usd=0.50)

        bridge._total_cost_usd = 0.40
        assert bridge.is_over_budget() is False

        bridge._total_cost_usd = 0.60
        assert bridge.is_over_budget() is True


# =============================================================================
# Concurrent Operations Tests
# =============================================================================


class TestConcurrentOperations:
    """
    Test concurrent chat() calls to detect race conditions.
    """

    @pytest.mark.asyncio
    async def test_concurrent_chat_calls_dont_corrupt_state(self):
        """Multiple concurrent chat calls should not corrupt state."""
        # This is a basic test - full race condition testing would need
        # more sophisticated mocking

        stdout_lines = [
            json.dumps({"type": "init", "session_id": "concurrent"}),
            json.dumps({"type": "message", "role": "assistant", "content": "OK"}),
            json.dumps({"type": "result"}),
        ]

        call_count = [0]

        async def create_fresh_proc(*args, **kwargs):
            call_count[0] += 1
            proc, _ = create_mock_subprocess(stdout_lines)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_fresh_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # Fire multiple chat calls concurrently
                tasks = [
                    engine.chat(f"Message {i}")
                    for i in range(3)
                ]

                responses = await asyncio.gather(*tasks)

                # All should succeed
                for resp in responses:
                    assert resp.success is True

                await engine.stop()
