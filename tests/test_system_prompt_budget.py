"""Tests for GAP-5 (system prompt consistency) and GAP-6 (budget control)."""

import threading
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from avatar_engine.bridges.base import BaseBridge
from avatar_engine.events import ErrorEvent
from avatar_engine.types import BridgeResponse, BridgeState


# =============================================================================
# BaseBridge._prepend_system_prompt()
# =============================================================================


class TestPrependSystemPrompt:
    """Tests for system prompt injection into first ACP message."""

    def _make_bridge(self, system_prompt=""):
        """Create a minimal BaseBridge-like object for testing."""
        bridge = MagicMock(spec=BaseBridge)
        bridge.system_prompt = system_prompt
        bridge._stats_lock = threading.Lock()
        bridge._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration_ms": 0,
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
        # Bind the real method
        bridge._prepend_system_prompt = BaseBridge._prepend_system_prompt.__get__(bridge)
        return bridge

    def test_no_system_prompt(self):
        """Without system_prompt, message should pass through unchanged."""
        bridge = self._make_bridge(system_prompt="")
        result = bridge._prepend_system_prompt("Hello")
        assert result == "Hello"

    def test_first_message_gets_prepend(self):
        """First message should include system prompt."""
        bridge = self._make_bridge(system_prompt="You are Aria. Speak Czech.")
        result = bridge._prepend_system_prompt("Hello")
        assert "[SYSTEM INSTRUCTIONS]" in result
        assert "You are Aria. Speak Czech." in result
        assert "[END INSTRUCTIONS]" in result
        assert "Hello" in result

    def test_second_message_no_prepend(self):
        """Second message should NOT include system prompt."""
        bridge = self._make_bridge(system_prompt="You are Aria.")
        # Simulate first request already happened
        bridge._stats["total_requests"] = 1
        result = bridge._prepend_system_prompt("Second message")
        assert result == "Second message"
        assert "[SYSTEM INSTRUCTIONS]" not in result

    def test_prepend_preserves_original_message(self):
        """Original message should be intact after system prompt."""
        bridge = self._make_bridge(system_prompt="Be helpful.")
        result = bridge._prepend_system_prompt("What is 2+2?")
        # Message should end with the original prompt
        assert result.endswith("What is 2+2?")

    def test_multiline_system_prompt(self):
        """Multi-line system prompt should work."""
        prompt = "Line 1\nLine 2\nLine 3"
        bridge = self._make_bridge(system_prompt=prompt)
        result = bridge._prepend_system_prompt("Hello")
        assert "Line 1\nLine 2\nLine 3" in result

    def test_thread_safety(self):
        """Concurrent calls should not corrupt state."""
        bridge = self._make_bridge(system_prompt="Test")
        errors = []

        def worker(i):
            try:
                result = bridge._prepend_system_prompt(f"msg-{i}")
                assert f"msg-{i}" in result
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# =============================================================================
# BaseBridge.is_over_budget()
# =============================================================================


class TestIsOverBudget:
    """Tests for budget control in BaseBridge."""

    def _make_bridge(self, max_budget=None, spent=0.0):
        bridge = MagicMock(spec=BaseBridge)
        bridge._stats_lock = threading.Lock()
        bridge._stats = {
            "total_requests": 5,
            "successful_requests": 5,
            "failed_requests": 0,
            "total_duration_ms": 1000,
            "total_cost_usd": spent,
            "total_input_tokens": 100,
            "total_output_tokens": 200,
        }
        if max_budget is not None:
            bridge._max_budget_usd = max_budget
        else:
            # Ensure attribute doesn't exist for the test
            del bridge._max_budget_usd
        bridge.is_over_budget = BaseBridge.is_over_budget.__get__(bridge)
        return bridge

    def test_no_budget_set(self):
        """Without max_budget_usd, should always return False."""
        bridge = self._make_bridge(max_budget=None)
        assert bridge.is_over_budget() is False

    def test_under_budget(self):
        """Should return False when under budget."""
        bridge = self._make_bridge(max_budget=5.0, spent=2.50)
        assert bridge.is_over_budget() is False

    def test_at_budget(self):
        """Should return True when exactly at budget."""
        bridge = self._make_bridge(max_budget=5.0, spent=5.0)
        assert bridge.is_over_budget() is True

    def test_over_budget(self):
        """Should return True when over budget."""
        bridge = self._make_bridge(max_budget=1.0, spent=1.50)
        assert bridge.is_over_budget() is True

    def test_zero_budget(self):
        """Zero budget should not trigger (treated as 'no budget')."""
        bridge = self._make_bridge(max_budget=0, spent=0)
        assert bridge.is_over_budget() is False

    def test_zero_spent(self):
        """With budget set but nothing spent, should be under budget."""
        bridge = self._make_bridge(max_budget=10.0, spent=0.0)
        assert bridge.is_over_budget() is False


# =============================================================================
# Engine budget check integration (unit level)
# =============================================================================


class TestEngineBudgetCheck:
    """Tests for pre-request budget check in AvatarEngine.chat()."""

    @pytest.mark.asyncio
    async def test_chat_blocked_when_over_budget(self):
        """chat() should return error when budget is exceeded."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")

        # Mock bridge
        mock_bridge = MagicMock()
        mock_bridge.is_over_budget.return_value = True
        mock_bridge.get_usage.return_value = {"total_cost_usd": 5.50}
        mock_bridge._max_budget_usd = 5.0
        engine._bridge = mock_bridge
        engine._started = True

        # Capture error events
        errors = []
        engine.add_handler(ErrorEvent, lambda e: errors.append(e))

        response = await engine.chat("Hello")

        assert response.success is False
        assert "Budget exceeded" in response.error
        assert len(errors) == 1
        assert errors[0].recoverable is False
        # Bridge.send() should NOT have been called
        mock_bridge.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_proceeds_when_under_budget(self):
        """chat() should proceed normally when under budget."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")

        mock_bridge = MagicMock()
        mock_bridge.is_over_budget.return_value = False
        mock_bridge.send = AsyncMock(return_value=BridgeResponse(
            content="Hello!", success=True, duration_ms=100,
        ))
        engine._bridge = mock_bridge
        engine._started = True
        engine._rate_limiter = MagicMock()
        engine._rate_limiter.acquire = AsyncMock(return_value=0)

        response = await engine.chat("Hello")

        assert response.success is True
        assert response.content == "Hello!"
        mock_bridge.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_stream_blocked_when_over_budget(self):
        """chat_stream() should yield nothing when budget is exceeded."""
        from avatar_engine import AvatarEngine

        engine = AvatarEngine(provider="gemini")

        mock_bridge = MagicMock()
        mock_bridge.is_over_budget.return_value = True
        mock_bridge.get_usage.return_value = {"total_cost_usd": 10.0}
        mock_bridge._max_budget_usd = 5.0
        engine._bridge = mock_bridge
        engine._started = True

        errors = []
        engine.add_handler(ErrorEvent, lambda e: errors.append(e))

        chunks = []
        async for chunk in engine.chat_stream("Hello"):
            chunks.append(chunk)

        assert chunks == []
        assert len(errors) == 1


# =============================================================================
# Codex system prompt prepend (unit test with mock)
# =============================================================================


class TestCodexSystemPromptPrepend:
    """Verify Codex bridge uses _prepend_system_prompt in send paths."""

    def test_codex_send_calls_prepend(self):
        """Codex.send() should call _prepend_system_prompt."""
        # Verify the code path exists by checking the source
        import inspect
        from avatar_engine.bridges.codex import CodexBridge
        source = inspect.getsource(CodexBridge.send)
        assert "_prepend_system_prompt" in source

    def test_codex_send_stream_calls_prepend(self):
        """Codex.send_stream() should call _prepend_system_prompt."""
        import inspect
        from avatar_engine.bridges.codex import CodexBridge
        source = inspect.getsource(CodexBridge.send_stream)
        assert "_prepend_system_prompt" in source


# =============================================================================
# Gemini system prompt prepend (unit test with mock)
# =============================================================================


class TestGeminiSystemPromptPrepend:
    """Verify Gemini bridge uses _prepend_system_prompt in ACP paths."""

    def test_gemini_send_acp_calls_prepend(self):
        """Gemini._send_acp() should call _prepend_system_prompt."""
        import inspect
        from avatar_engine.bridges.gemini import GeminiBridge
        source = inspect.getsource(GeminiBridge._send_acp)
        assert "_prepend_system_prompt" in source

    def test_gemini_stream_acp_calls_prepend(self):
        """Gemini._stream_acp() should call _prepend_system_prompt."""
        import inspect
        from avatar_engine.bridges.gemini import GeminiBridge
        source = inspect.getsource(GeminiBridge._stream_acp)
        assert "_prepend_system_prompt" in source
