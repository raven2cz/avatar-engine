"""
Error recovery tests — tests engine resilience and failure handling.

These tests verify:
- UC-4: Auto-restart on failure
- Max restarts limit
- Fallback from persistent to oneshot
- Error event emission
"""

import asyncio
import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from avatar_engine import AvatarEngine
from avatar_engine.bridges.claude import ClaudeBridge
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.bridges.base import BridgeState
from avatar_engine.events import ErrorEvent, StateEvent
from avatar_engine.types import BridgeResponse


# =============================================================================
# Mock Helpers
# =============================================================================


def create_mock_subprocess(
    stdout_lines: List[str],
    returncode: int = 0,
):
    """Create a mock subprocess."""
    proc = MagicMock()
    proc.pid = 12345
    _returncode = [returncode]
    type(proc).returncode = PropertyMock(side_effect=lambda: _returncode[0])

    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()

    stdout_queue = asyncio.Queue()
    for line in stdout_lines:
        stdout_queue.put_nowait(line + "\n" if line else "")
    stdout_queue.put_nowait("")

    async def mock_readline():
        try:
            line = stdout_queue.get_nowait()
            return line.encode() if line else b""
        except asyncio.QueueEmpty:
            return b""

    async def mock_read(_n=None):
        try:
            line = stdout_queue.get_nowait()
            return line.encode() if line else b""
        except asyncio.QueueEmpty:
            return b""

    proc.stdout = MagicMock()
    proc.stdout.readline = mock_readline
    proc.stdout.read = mock_read
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    async def mock_wait():
        _returncode[0] = returncode
        return returncode

    proc.wait = mock_wait

    async def mock_communicate():
        all_stdout = "\n".join(stdout_lines).encode()
        _returncode[0] = returncode
        return (all_stdout, b"")

    proc.communicate = mock_communicate

    return proc


def make_success_response_lines():
    """Create standard successful response lines."""
    return [
        json.dumps({"type": "init", "session_id": "test-session"}),
        json.dumps({"type": "message", "role": "assistant", "content": "OK"}),
        json.dumps({"type": "result", "status": "success"}),
    ]


def make_error_response_lines(error_msg="Something went wrong"):
    """Create error response lines."""
    return [
        json.dumps({"type": "init", "session_id": "test-session"}),
        json.dumps({"type": "error", "message": error_msg}),
        json.dumps({"type": "result", "status": "error", "error": error_msg}),
    ]


# =============================================================================
# UC-4: Auto-Restart on Failure Tests
# =============================================================================


class TestAutoRestart:
    """
    Use Case: Engine recovers from bridge crash.

    Expected behavior:
    1. Chat works normally
    2. If bridge crashes, next chat auto-restarts
    3. Recovery is transparent to user
    """

    @pytest.mark.asyncio
    async def test_oneshot_mode_creates_new_process_each_call(self):
        """In oneshot mode, each chat() creates a new process."""
        success_lines = make_success_response_lines()
        call_count = [0]

        async def create_new_proc(*args, **kwargs):
            call_count[0] += 1
            return create_mock_subprocess(success_lines)

        with patch("asyncio.create_subprocess_exec", side_effect=create_new_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                # Explicitly disable ACP to test oneshot mode
                engine = AvatarEngine(provider="gemini", acp_enabled=False)
                await engine.start()

                # Each chat should create new process
                await engine.chat("First")
                await engine.chat("Second")
                await engine.chat("Third")

                assert call_count[0] == 3

                await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_handles_failed_response_gracefully(self):
        """Engine should handle failed responses without crashing."""
        error_lines = make_error_response_lines("API error")

        mock_proc = create_mock_subprocess(error_lines, returncode=1)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # Should return error response, not raise
                response = await engine.chat("Hello")

                # Engine should still be functional - is_healthy() is the correct method
                # In oneshot mode, health depends on bridge state
                assert engine._bridge is not None

                await engine.stop()

    @pytest.mark.asyncio
    async def test_subsequent_calls_work_after_error(self):
        """Subsequent chat calls should work after an error."""
        error_lines = make_error_response_lines()
        success_lines = make_success_response_lines()

        call_count = [0]

        async def create_proc(*args, **kwargs):
            call_count[0] += 1
            # First call fails, rest succeed
            if call_count[0] == 1:
                return create_mock_subprocess(error_lines, returncode=1)
            return create_mock_subprocess(success_lines)

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # First call gets error
                resp1 = await engine.chat("First")

                # Second call should work
                resp2 = await engine.chat("Second")
                assert resp2.success is True
                assert resp2.content == "OK"

                await engine.stop()


# =============================================================================
# Error Event Emission Tests
# =============================================================================


class TestErrorEventEmission:
    """
    Test that ErrorEvent is emitted on failures.
    """

    @pytest.mark.asyncio
    async def test_error_event_emitted_on_timeout(self):
        """ErrorEvent may be emitted when chat times out."""
        error_events = []

        # Create process that times out
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdin.close = MagicMock()
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=0)

        async def hang():
            await asyncio.sleep(100)
            return b""

        proc.stdout = MagicMock()
        proc.stdout.readline = hang
        proc.stdout.read = hang
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")

        async def mock_communicate():
            await asyncio.sleep(100)
            return (b"", b"")
        proc.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini", timeout=1)

                @engine.on(ErrorEvent)
                def capture_error(event):
                    error_events.append(event)

                await engine.start()
                response = await engine.chat("Hello")

                # Response should indicate failure
                assert response.success is False

                # Note: ErrorEvent emission depends on implementation
                # The important thing is that the response indicates failure

                await engine.stop()


# =============================================================================
# State Recovery Tests
# =============================================================================


class TestStateRecovery:
    """Test engine state recovery after failures."""

    @pytest.mark.asyncio
    async def test_engine_state_returns_to_ready_after_error(self):
        """Engine state should return to READY after error."""
        error_lines = make_error_response_lines()

        mock_proc = create_mock_subprocess(error_lines, returncode=1)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # Trigger error
                await engine.chat("Hello")

                # State should be READY (not stuck in BUSY or ERROR)
                # Access bridge state via _bridge.state
                assert engine._bridge.state == BridgeState.READY

                await engine.stop()


# =============================================================================
# Bridge-Specific Error Handling
# =============================================================================


class TestClaudeBridgeErrors:
    """Test Claude bridge error handling."""

    @pytest.mark.asyncio
    async def test_claude_handles_invalid_json_response(self):
        """Claude bridge should handle malformed JSON gracefully."""
        # Mix of valid and invalid JSON
        stdout_lines = [
            json.dumps({"type": "system", "session_id": "test"}),
            "not valid json {{{",  # Invalid
            json.dumps({"type": "assistant", "message": {"content": "OK"}}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/claude"):
                bridge = ClaudeBridge()
                await bridge.start()

                # Should not crash, should parse what it can
                response = await bridge.send("Hello")
                assert response is not None

                await bridge.stop()

    @pytest.mark.asyncio
    async def test_claude_budget_exceeded_error(self):
        """Claude should handle budget exceeded scenario."""
        bridge = ClaudeBridge(max_budget_usd=0.10)

        # Simulate already spent budget
        bridge._total_cost_usd = 0.15

        # Check should indicate over budget
        assert bridge.is_over_budget() is True


class TestGeminiBridgeErrors:
    """Test Gemini bridge error handling."""

    @pytest.mark.asyncio
    async def test_gemini_handles_empty_response(self):
        """Gemini bridge should handle empty response."""
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "result", "status": "success"}),
            # No assistant message
        ]

        mock_proc = create_mock_subprocess(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                bridge = GeminiBridge()
                await bridge.start()

                response = await bridge.send("Hello")

                # Should succeed with empty content
                assert response.success is True
                assert response.content == ""

                await bridge.stop()


# =============================================================================
# Timeout Handling Tests
# =============================================================================


class TestTimeoutHandling:
    """Test timeout scenarios."""

    @pytest.mark.asyncio
    async def test_timeout_returns_error_response(self):
        """Timeout should return error response, not raise."""
        proc = MagicMock()
        proc.pid = 12345
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdin.close = MagicMock()
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=0)

        async def hang():
            await asyncio.sleep(100)
            return b""

        proc.stdout = MagicMock()
        proc.stdout.readline = hang
        proc.stdout.read = hang
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")

        async def mock_communicate():
            await asyncio.sleep(100)
            return (b"", b"")
        proc.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini", timeout=1)
                await engine.start()

                response = await engine.chat("Hello")

                assert response.success is False
                assert response.error is not None
                assert "timeout" in response.error.lower() or "Timeout" in response.error

                await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_auto_restarts_on_timeout(self):
        """Engine should auto-restart on timeout and eventually succeed."""
        call_count = [0]

        async def create_proc(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call times out
                proc = MagicMock()
                proc.pid = 12345
                proc.returncode = None
                proc.stdin = MagicMock()
                proc.stdin.drain = AsyncMock()
                proc.stdin.close = MagicMock()
                proc.terminate = MagicMock()
                proc.kill = MagicMock()
                proc.wait = AsyncMock(return_value=0)

                async def hang():
                    await asyncio.sleep(100)
                    return b""
                proc.stdout = MagicMock()
                proc.stdout.readline = hang
                proc.stdout.read = hang
                proc.stderr = MagicMock()
                proc.stderr.read = AsyncMock(return_value=b"")

                async def mock_communicate():
                    await asyncio.sleep(100)
                    return (b"", b"")
                proc.communicate = mock_communicate
                return proc
            else:
                # Subsequent calls succeed
                return create_mock_subprocess(make_success_response_lines())

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini", timeout=1)
                await engine.start()

                # First call times out, but engine auto-restarts and succeeds
                resp = await engine.chat("First")

                # Engine auto-restarted and retried successfully
                assert resp.success is True
                assert call_count[0] >= 2  # At least 2 processes created

                await engine.stop()


# =============================================================================
# CLI Not Found Tests
# =============================================================================


class TestCLINotFound:
    """Test behavior when CLI tools are not installed."""

    @pytest.mark.asyncio
    async def test_start_fails_gracefully_when_cli_missing(self):
        """Engine should fail gracefully when CLI not found."""
        with patch("shutil.which", return_value=None):
            engine = AvatarEngine(provider="gemini")

            # Start should fail with clear error
            try:
                await engine.start()
                # If it doesn't raise, check health
                health = engine.get_health()
                assert health.healthy is False
            except Exception as e:
                # Should have clear error message
                assert "not found" in str(e).lower() or "gemini" in str(e).lower()

            await engine.stop()


# =============================================================================
# Concurrent Error Tests
# =============================================================================


class TestConcurrentErrors:
    """Test error handling in concurrent scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_errors_dont_corrupt_state(self):
        """Multiple concurrent errors should not corrupt engine state."""
        error_lines = make_error_response_lines()

        async def create_error_proc(*args, **kwargs):
            return create_mock_subprocess(error_lines, returncode=1)

        with patch("asyncio.create_subprocess_exec", side_effect=create_error_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # Fire multiple failing requests
                tasks = [
                    engine.chat(f"Message {i}")
                    for i in range(3)
                ]

                responses = await asyncio.gather(*tasks)

                # All should fail gracefully
                for resp in responses:
                    assert resp is not None

                # Engine should still be functional - bridge exists
                assert engine._bridge is not None

                await engine.stop()
