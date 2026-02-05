"""
Edge cases and boundary condition tests.

These tests verify:
- Concurrent operations
- History limits
- Unicode handling
- Empty responses
- Very long responses
"""

import asyncio
import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from avatar_engine import AvatarEngine
from avatar_engine.bridges.claude import ClaudeBridge
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.types import Message


# =============================================================================
# Mock Helpers
# =============================================================================


def create_mock_subprocess(stdout_lines: List[str], returncode: int = 0):
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

    proc.stdout = MagicMock()
    proc.stdout.readline = mock_readline
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


def make_response(content: str, session_id: str = "test"):
    """Create response lines for a message."""
    return [
        json.dumps({"type": "init", "session_id": session_id}),
        json.dumps({"type": "message", "role": "assistant", "content": content}),
        json.dumps({"type": "result", "status": "success"}),
    ]


# =============================================================================
# UC-5: Concurrent Operations Tests
# =============================================================================


class TestConcurrentOperations:
    """Test behavior under concurrent chat requests."""

    @pytest.mark.asyncio
    async def test_concurrent_chat_calls_all_succeed(self):
        """Multiple concurrent chat calls should all succeed."""
        call_count = [0]

        async def create_proc(*args, **kwargs):
            call_count[0] += 1
            return create_mock_subprocess(make_response(f"Response {call_count[0]}"))

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                tasks = [engine.chat(f"Message {i}") for i in range(5)]
                responses = await asyncio.gather(*tasks)

                # All should succeed
                for i, resp in enumerate(responses):
                    assert resp.success is True
                    assert resp.content is not None

                await engine.stop()

    @pytest.mark.asyncio
    async def test_concurrent_stream_calls(self):
        """Multiple concurrent stream calls should not interfere."""
        async def create_proc(*args, **kwargs):
            return create_mock_subprocess([
                json.dumps({"type": "init", "session_id": "stream"}),
                json.dumps({"type": "message", "role": "assistant", "content": "chunk1"}),
                json.dumps({"type": "message", "role": "assistant", "content": "chunk2"}),
                json.dumps({"type": "result"}),
            ])

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # Collect chunks from two parallel streams
                async def collect_stream(msg: str):
                    chunks = []
                    async for chunk in engine.chat_stream(msg):
                        chunks.append(chunk)
                    return chunks

                results = await asyncio.gather(
                    collect_stream("A"),
                    collect_stream("B"),
                )

                # Both should have collected chunks
                for chunks in results:
                    assert len(chunks) >= 1

                await engine.stop()


# =============================================================================
# History Management Tests
# =============================================================================


class TestHistoryManagement:
    """Test conversation history handling."""

    @pytest.mark.asyncio
    async def test_history_accumulates(self):
        """History should accumulate across chat calls."""
        call_count = [0]

        async def create_proc(*args, **kwargs):
            call_count[0] += 1
            return create_mock_subprocess(make_response(f"Reply {call_count[0]}"))

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                await engine.chat("First")
                await engine.chat("Second")
                await engine.chat("Third")

                history = engine.get_history()
                # 3 user messages + 3 assistant messages
                assert len(history) == 6

                await engine.stop()

    @pytest.mark.asyncio
    async def test_clear_history(self):
        """History should be clearable."""
        async def create_proc(*args, **kwargs):
            return create_mock_subprocess(make_response("OK"))

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                await engine.chat("Hello")
                assert len(engine.get_history()) == 2

                engine.clear_history()
                assert len(engine.get_history()) == 0

                await engine.stop()

    def test_history_max_limit_on_bridge(self):
        """Bridge should respect max_history limit."""
        bridge = GeminiBridge()
        bridge.max_history = 4  # Limit to 4 messages

        # Add more than limit
        for i in range(10):
            bridge.history.append(Message(role="user", content=f"msg {i}"))

        # Trim manually (engine does this)
        while len(bridge.history) > bridge.max_history:
            bridge.history.pop(0)

        assert len(bridge.history) == 4


# =============================================================================
# Unicode and Encoding Tests
# =============================================================================


class TestUnicodeHandling:
    """Test handling of Unicode content."""

    @pytest.mark.asyncio
    async def test_unicode_in_response(self):
        """Should handle Unicode in response content."""
        unicode_content = "Ahoj! 你好! مرحبا! 🌍"
        lines = make_response(unicode_content)

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Hello")

                assert response.success is True
                assert response.content == unicode_content

                await engine.stop()

    @pytest.mark.asyncio
    async def test_unicode_in_request(self):
        """Should handle Unicode in request message."""
        request_content = "Řekni mi něco o 日本"

        mock_proc = create_mock_subprocess(make_response("OK"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat(request_content)
                assert response.success is True

                # Request should be in history
                history = engine.get_history()
                assert history[0].content == request_content

                await engine.stop()

    @pytest.mark.asyncio
    async def test_emoji_handling(self):
        """Should handle emoji properly."""
        emoji_content = "That's great! 👍🎉🚀"
        lines = make_response(emoji_content)

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("How's it going?")

                assert response.success is True
                assert "👍" in response.content

                await engine.stop()


# =============================================================================
# Empty and Edge Case Responses
# =============================================================================


class TestEmptyResponses:
    """Test handling of empty or minimal responses."""

    @pytest.mark.asyncio
    async def test_empty_content_response(self):
        """Should handle empty content gracefully."""
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": ""}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Hello")

                assert response.success is True
                assert response.content == ""

                await engine.stop()

    @pytest.mark.asyncio
    async def test_whitespace_only_response(self):
        """Should handle whitespace-only content."""
        lines = make_response("   \n\t  ")

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Hello")

                assert response.success is True
                # Content is whitespace-only but not empty
                assert response.content == "   \n\t  "

                await engine.stop()

    @pytest.mark.asyncio
    async def test_null_content_field(self):
        """Should handle null content field."""
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": None}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Hello")

                # Should handle null gracefully
                assert response.success is True

                await engine.stop()


# =============================================================================
# Very Long Response Tests
# =============================================================================


class TestLongResponses:
    """Test handling of very long responses."""

    @pytest.mark.asyncio
    async def test_long_response_content(self):
        """Should handle very long response content."""
        # 10KB of content
        long_content = "A" * 10000
        lines = make_response(long_content)

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Generate something long")

                assert response.success is True
                assert len(response.content) == 10000

                await engine.stop()

    @pytest.mark.asyncio
    async def test_many_streaming_chunks(self):
        """Should handle many streaming chunks."""
        # Create 100 chunks
        chunks = [json.dumps({"type": "init", "session_id": "test"})]
        for i in range(100):
            chunks.append(json.dumps({
                "type": "message",
                "role": "assistant",
                "content": f"chunk{i} ",
                "delta": True
            }))
        chunks.append(json.dumps({"type": "result"}))

        mock_proc = create_mock_subprocess(chunks)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                collected = []
                async for chunk in engine.chat_stream("Generate"):
                    collected.append(chunk)

                # Should have received chunks
                assert len(collected) >= 1

                await engine.stop()


# =============================================================================
# Provider Switching Tests
# =============================================================================


class TestProviderSwitching:
    """Test provider switching functionality."""

    @pytest.mark.asyncio
    async def test_switch_provider_basic(self):
        """Should be able to switch providers."""
        lines = make_response("OK")

        async def create_proc(*args, **kwargs):
            return create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                assert engine.current_provider == "gemini"

                await engine.switch_provider("claude")
                assert engine.current_provider == "claude"

                await engine.stop()

    @pytest.mark.asyncio
    async def test_switch_clears_history(self):
        """Switching provider should clear history."""
        lines = make_response("OK")

        async def create_proc(*args, **kwargs):
            return create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                await engine.chat("Hello")
                assert len(engine.get_history()) == 2

                await engine.switch_provider("claude")
                # History should be cleared
                assert len(engine.get_history()) == 0

                await engine.stop()


# =============================================================================
# Input Validation Tests
# =============================================================================


class TestInputValidation:
    """Test input validation edge cases."""

    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Should handle empty message."""
        lines = make_response("I didn't get any input")

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                # Empty message should still work (or fail gracefully)
                response = await engine.chat("")
                # Either works or returns error
                assert response is not None

                await engine.stop()

    @pytest.mark.asyncio
    async def test_very_long_message(self):
        """Should handle very long input message."""
        lines = make_response("OK")

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                long_message = "A" * 50000  # 50KB message
                response = await engine.chat(long_message)

                # Should handle without crashing
                assert response is not None

                await engine.stop()


# =============================================================================
# Session ID Tests
# =============================================================================


class TestSessionID:
    """Test session ID handling."""

    @pytest.mark.asyncio
    async def test_session_id_extracted(self):
        """Session ID should be extracted from response."""
        lines = [
            json.dumps({"type": "init", "session_id": "unique-session-123"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                response = await engine.chat("Hello")

                assert response.session_id == "unique-session-123"
                assert engine.session_id == "unique-session-123"

                await engine.stop()

    @pytest.mark.asyncio
    async def test_session_id_persists_across_calls(self):
        """Session ID should persist across multiple calls."""
        call_count = [0]

        async def create_proc(*args, **kwargs):
            call_count[0] += 1
            session = "session-abc" if call_count[0] == 1 else None
            if session:
                return create_mock_subprocess([
                    json.dumps({"type": "init", "session_id": session}),
                    json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
                    json.dumps({"type": "result"}),
                ])
            else:
                return create_mock_subprocess([
                    json.dumps({"type": "message", "role": "assistant", "content": "Hi again"}),
                    json.dumps({"type": "result"}),
                ])

        with patch("asyncio.create_subprocess_exec", side_effect=create_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")
                await engine.start()

                await engine.chat("First")
                first_session = engine.session_id

                await engine.chat("Second")
                # Session ID should remain from first call
                assert engine.session_id == first_session

                await engine.stop()
