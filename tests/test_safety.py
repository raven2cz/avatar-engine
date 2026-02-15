"""Tests for safety instructions feature."""

import asyncio
import textwrap
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from avatar_engine import AvatarEngine, AvatarConfig
from avatar_engine.safety import (
    DEFAULT_SAFETY_INSTRUCTIONS,
    ASK_MODE_SAFETY_INSTRUCTIONS,
    SafetyMode,
    normalize_safety_mode,
)
from avatar_engine.types import ProviderType


class TestSafetyInstructions:
    """Tests for safety instructions prepended to system prompt."""

    def test_safety_mode_default_safe(self):
        """AvatarEngine has safety_mode='safe' by default."""
        engine = AvatarEngine()
        assert engine._safety_mode == "safe"

    def test_safety_instructions_prepended(self):
        """Bridge receives safety instructions + user prompt when enabled."""
        engine = AvatarEngine(
            provider="gemini",
            system_prompt="Be helpful.",
        )
        bridge = engine._create_bridge()
        assert bridge.system_prompt.startswith(DEFAULT_SAFETY_INSTRUCTIONS)
        assert bridge.system_prompt.endswith("Be helpful.")
        assert "\n\n" in bridge.system_prompt

    def test_safety_instructions_disabled(self):
        """safety_instructions=False → bridge gets only user prompt."""
        engine = AvatarEngine(
            provider="gemini",
            system_prompt="Be helpful.",
            safety_instructions=False,
        )
        bridge = engine._create_bridge()
        assert bridge.system_prompt == "Be helpful."
        assert DEFAULT_SAFETY_INSTRUCTIONS not in bridge.system_prompt

    def test_safety_instructions_without_user_prompt(self):
        """With no user prompt, bridge gets only safety instructions."""
        engine = AvatarEngine(provider="gemini")
        bridge = engine._create_bridge()
        assert bridge.system_prompt == DEFAULT_SAFETY_INSTRUCTIONS

    def test_safety_instructions_from_config(self):
        """Config with safety_instructions: false disables safety."""
        config = AvatarConfig(
            provider=ProviderType.GEMINI,
            system_prompt="Custom prompt.",
            safety_instructions=False,
        )
        engine = AvatarEngine(config=config)
        assert engine._safety_mode == "unrestricted"
        bridge = engine._create_bridge()
        assert bridge.system_prompt == "Custom prompt."
        assert DEFAULT_SAFETY_INSTRUCTIONS not in bridge.system_prompt


class TestSafetyModes:
    """Tests for three-mode safety system (safe/ask/unrestricted)."""

    def test_normalize_bool_true(self):
        assert normalize_safety_mode(True) == "safe"

    def test_normalize_bool_false(self):
        assert normalize_safety_mode(False) == "unrestricted"

    def test_normalize_string_safe(self):
        assert normalize_safety_mode("safe") == "safe"

    def test_normalize_string_ask(self):
        assert normalize_safety_mode("ask") == "ask"

    def test_normalize_string_unrestricted(self):
        assert normalize_safety_mode("unrestricted") == "unrestricted"

    def test_normalize_invalid_defaults_safe(self):
        assert normalize_safety_mode("bogus") == "safe"

    def test_ask_mode_system_prompt(self):
        """Ask mode prepends ASK_MODE_SAFETY_INSTRUCTIONS."""
        engine = AvatarEngine(
            provider="gemini",
            system_prompt="Be helpful.",
            safety_mode="ask",
        )
        bridge = engine._create_bridge()
        assert bridge.system_prompt.startswith(ASK_MODE_SAFETY_INSTRUCTIONS)
        assert bridge.system_prompt.endswith("Be helpful.")
        assert DEFAULT_SAFETY_INSTRUCTIONS not in bridge.system_prompt

    def test_ask_mode_without_user_prompt(self):
        """Ask mode with no user prompt → only ASK instructions."""
        engine = AvatarEngine(provider="gemini", safety_mode="ask")
        bridge = engine._create_bridge()
        assert bridge.system_prompt == ASK_MODE_SAFETY_INSTRUCTIONS

    def test_unrestricted_mode(self):
        """Unrestricted mode → no safety prefix."""
        engine = AvatarEngine(
            provider="gemini",
            system_prompt="Be helpful.",
            safety_mode="unrestricted",
        )
        bridge = engine._create_bridge()
        assert bridge.system_prompt == "Be helpful."

    def test_safety_mode_property(self):
        """Engine exposes safety_mode property."""
        engine = AvatarEngine(safety_mode="ask")
        assert engine.safety_mode == "ask"

    def test_legacy_safety_instructions_kwarg(self):
        """Legacy safety_instructions=False maps to unrestricted."""
        engine = AvatarEngine(safety_instructions=False)
        assert engine._safety_mode == "unrestricted"

    def test_safety_mode_kwarg_takes_precedence(self):
        """safety_mode kwarg is accepted."""
        engine = AvatarEngine(safety_mode="ask")
        assert engine._safety_mode == "ask"

    def test_config_with_string_safety_instructions(self):
        """Config with safety_instructions: 'ask' creates ask mode engine."""
        config = AvatarConfig(
            provider=ProviderType.GEMINI,
            safety_instructions="ask",
        )
        engine = AvatarEngine(config=config)
        assert engine._safety_mode == "ask"

    def test_config_with_string_unrestricted(self):
        """Config with safety_instructions: 'unrestricted' works."""
        config = AvatarConfig(
            provider=ProviderType.GEMINI,
            safety_instructions="unrestricted",
        )
        engine = AvatarEngine(config=config)
        assert engine._safety_mode == "unrestricted"


class TestPermissionHandling:
    """Tests for permission request/resolve flow."""

    def test_resolve_permission(self):
        """resolve_permission resolves a pending future."""
        import asyncio
        engine = AvatarEngine()

        loop = asyncio.new_event_loop()
        try:
            future = loop.create_future()
            engine._pending_permissions["test-123"] = future
            engine.resolve_permission("test-123", option_id="allow_once")

            assert future.done()
            result = future.result()
            assert result["option_id"] == "allow_once"
            assert result["cancelled"] is False
        finally:
            loop.close()

    def test_resolve_unknown_request(self):
        """resolve_permission with unknown ID is a no-op."""
        engine = AvatarEngine()
        engine.resolve_permission("nonexistent")  # should not raise

    def test_cancel_all_permissions(self):
        """cancel_all_permissions cancels all pending futures."""
        import asyncio
        engine = AvatarEngine()

        loop = asyncio.new_event_loop()
        try:
            f1 = loop.create_future()
            f2 = loop.create_future()
            engine._pending_permissions["a"] = f1
            engine._pending_permissions["b"] = f2

            engine.cancel_all_permissions()

            assert f1.done()
            assert f2.done()
            assert f1.result()["cancelled"] is True
            assert f2.result()["cancelled"] is True
            assert len(engine._pending_permissions) == 0
        finally:
            loop.close()

    @pytest.mark.asyncio
    async def test_handle_permission_request_emits_event(self):
        """handle_permission_request emits PermissionRequestEvent and awaits future."""
        from avatar_engine.events import PermissionRequestEvent

        engine = AvatarEngine()
        emitted = []
        engine.add_handler(PermissionRequestEvent, lambda e: emitted.append(e))

        # Run handle_permission_request in a task so we can resolve the future
        task = asyncio.create_task(
            engine.handle_permission_request(
                "req-1", "bash", "rm file", [{"option_id": "a1", "kind": "allow_once"}]
            )
        )
        # Yield control so the task starts and emits the event
        await asyncio.sleep(0)

        assert len(emitted) == 1
        assert emitted[0].request_id == "req-1"
        assert emitted[0].tool_name == "bash"

        # Resolve the pending permission
        engine.resolve_permission("req-1", option_id="a1")
        result = await task

        assert result["option_id"] == "a1"
        assert result["cancelled"] is False

    @pytest.mark.asyncio
    async def test_handle_permission_request_cancelled(self):
        """handle_permission_request returns cancelled when resolve_permission sets cancelled."""
        engine = AvatarEngine()

        task = asyncio.create_task(
            engine.handle_permission_request("req-2", "exec", "sudo reboot", [])
        )
        await asyncio.sleep(0)

        engine.resolve_permission("req-2", cancelled=True)
        result = await task

        assert result["cancelled"] is True

    @pytest.mark.asyncio
    async def test_stop_cancels_pending_permissions(self):
        """engine.stop() should cancel all pending permission requests."""
        engine = AvatarEngine()

        loop = asyncio.get_running_loop()
        f1 = loop.create_future()
        engine._pending_permissions["stop-test"] = f1

        await engine.stop()

        assert f1.done()
        assert f1.result()["cancelled"] is True
        assert len(engine._pending_permissions) == 0

    @pytest.mark.asyncio
    async def test_handle_permission_request_timeout(self):
        """handle_permission_request auto-denies after timeout."""
        engine = AvatarEngine()

        # Patch timeout to 0.1s for fast test
        import avatar_engine.engine as eng_mod
        original = eng_mod.asyncio.wait_for

        async def fast_wait_for(fut, timeout):
            return await original(fut, timeout=0.05)

        eng_mod.asyncio.wait_for = fast_wait_for
        try:
            result = await engine.handle_permission_request(
                "timeout-test", "bash", "rm file", []
            )
            assert result["cancelled"] is True
            assert "timeout-test" not in engine._pending_permissions
        finally:
            eng_mod.asyncio.wait_for = original

    def test_resolve_already_done_future(self):
        """resolve_permission on already-done future is a no-op."""
        engine = AvatarEngine()

        loop = asyncio.new_event_loop()
        try:
            future = loop.create_future()
            future.set_result({"option_id": "first", "cancelled": False})
            engine._pending_permissions["done-test"] = future

            # Should not raise
            engine.resolve_permission("done-test", option_id="second")

            # Original result preserved
            assert future.result()["option_id"] == "first"
        finally:
            loop.close()


class TestACPClientAskMode:
    """Test ACP client permission routing in Ask mode (mock, no real CLI)."""

    @pytest.mark.asyncio
    async def test_gemini_acp_client_ask_mode_allow(self):
        """Gemini ACP client routes to permission_handler in Ask mode."""
        try:
            from acp.schema import AllowedOutcome, DeniedOutcome, RequestPermissionResponse
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.gemini import _AvatarACPClient

        # Mock permission handler that approves
        handler = AsyncMock(return_value={"option_id": "opt-allow", "cancelled": False})

        client = _AvatarACPClient(
            auto_approve=False,
            permission_handler=handler,
        )

        # Create mock options and tool_call
        mock_option = MagicMock()
        mock_option.option_id = "opt-allow"
        mock_option.kind = "allow_once"

        mock_tool = MagicMock()
        mock_tool.function_name = "bash"
        mock_tool.arguments = "rm test.txt"

        response = await client.request_permission(
            options=[mock_option],
            session_id="sess-1",
            tool_call=mock_tool,
        )

        handler.assert_called_once()
        assert isinstance(response.outcome, AllowedOutcome)
        assert response.outcome.option_id == "opt-allow"

    @pytest.mark.asyncio
    async def test_gemini_acp_client_ask_mode_deny(self):
        """Gemini ACP client returns DeniedOutcome when user cancels."""
        try:
            from acp.schema import DeniedOutcome
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.gemini import _AvatarACPClient

        handler = AsyncMock(return_value={"option_id": "", "cancelled": True})

        client = _AvatarACPClient(
            auto_approve=False,
            permission_handler=handler,
        )

        mock_tool = MagicMock()
        mock_tool.function_name = "exec"
        mock_tool.arguments = "sudo shutdown"

        response = await client.request_permission(
            options=[],
            session_id="sess-1",
            tool_call=mock_tool,
        )

        assert isinstance(response.outcome, DeniedOutcome)

    @pytest.mark.asyncio
    async def test_gemini_acp_client_no_handler_denies(self):
        """Gemini ACP client denies when auto_approve=False and no handler."""
        try:
            from acp.schema import DeniedOutcome
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.gemini import _AvatarACPClient

        client = _AvatarACPClient(auto_approve=False)

        mock_tool = MagicMock()
        mock_tool.function_name = "bash"

        response = await client.request_permission(
            options=[], session_id="s1", tool_call=mock_tool,
        )
        assert isinstance(response.outcome, DeniedOutcome)

    @pytest.mark.asyncio
    async def test_codex_acp_client_ask_mode_allow(self):
        """Codex ACP client routes to permission_handler in Ask mode."""
        try:
            from acp.schema import AllowedOutcome
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.codex import _CodexACPClient

        handler = AsyncMock(return_value={"option_id": "opt-ok", "cancelled": False})

        client = _CodexACPClient(
            auto_approve=False,
            permission_handler=handler,
        )

        mock_options = MagicMock()
        mock_opt = MagicMock()
        mock_opt.option_id = "opt-ok"
        mock_opt.kind = "allow_once"
        mock_options.options = [mock_opt]

        mock_tool = MagicMock()
        mock_tool.function_name = "patch"
        mock_tool.arguments = "file.py"

        response = await client.request_permission(
            options=mock_options,
            session_id="sess-2",
            tool_call=mock_tool,
        )

        handler.assert_called_once()
        assert isinstance(response.outcome, AllowedOutcome)

    @pytest.mark.asyncio
    async def test_codex_acp_client_ask_mode_cancel(self):
        """Codex ACP client returns DeniedOutcome on cancel."""
        try:
            from acp.schema import DeniedOutcome
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.codex import _CodexACPClient

        handler = AsyncMock(return_value={"option_id": "", "cancelled": True})

        client = _CodexACPClient(
            auto_approve=False,
            permission_handler=handler,
        )

        mock_options = MagicMock()
        mock_options.options = []

        mock_tool = MagicMock()
        mock_tool.function_name = "exec"
        mock_tool.arguments = "rm -rf /"

        response = await client.request_permission(
            options=mock_options,
            session_id="sess-2",
            tool_call=mock_tool,
        )

        assert isinstance(response.outcome, DeniedOutcome)

    @pytest.mark.asyncio
    async def test_codex_acp_client_handler_exception_denies(self):
        """Codex ACP client denies if permission_handler raises."""
        try:
            from acp.schema import DeniedOutcome
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.codex import _CodexACPClient

        handler = AsyncMock(side_effect=RuntimeError("GUI disconnected"))

        client = _CodexACPClient(
            auto_approve=False,
            permission_handler=handler,
        )

        mock_options = MagicMock()
        mock_options.options = []

        mock_tool = MagicMock()
        mock_tool.function_name = "bash"
        mock_tool.arguments = "test"

        response = await client.request_permission(
            options=mock_options,
            session_id="s",
            tool_call=mock_tool,
        )

        assert isinstance(response.outcome, DeniedOutcome)

    @pytest.mark.asyncio
    async def test_gemini_acp_client_handler_exception_denies(self):
        """Gemini ACP client denies if permission_handler raises."""
        try:
            from acp.schema import DeniedOutcome
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.gemini import _AvatarACPClient

        handler = AsyncMock(side_effect=RuntimeError("GUI disconnected"))

        client = _AvatarACPClient(
            auto_approve=False,
            permission_handler=handler,
        )

        mock_tool = MagicMock()
        mock_tool.function_name = "bash"
        mock_tool.arguments = "test"

        response = await client.request_permission(
            options=[], session_id="s", tool_call=mock_tool,
        )
        assert isinstance(response.outcome, DeniedOutcome)

    @pytest.mark.asyncio
    async def test_gemini_acp_client_auto_approve(self):
        """Gemini ACP client auto-approves when auto_approve=True."""
        try:
            from acp.schema import AllowedOutcome
        except ImportError:
            pytest.skip("ACP SDK not installed")

        from avatar_engine.bridges.gemini import _AvatarACPClient

        client = _AvatarACPClient(auto_approve=True)

        mock_option = MagicMock()
        mock_option.option_id = "opt-auto"
        mock_option.kind = "allow_once"

        mock_tool = MagicMock()
        mock_tool.function_name = "read"
        mock_tool.arguments = "file.py"

        response = await client.request_permission(
            options=[mock_option], session_id="s1", tool_call=mock_tool,
        )
        assert isinstance(response.outcome, AllowedOutcome)


class TestPermissionEdgeCases:
    """Edge case tests for permission handling."""

    @pytest.mark.asyncio
    async def test_duplicate_request_id_cancels_previous(self):
        """Duplicate request_id cancels the previous pending future."""
        engine = AvatarEngine()

        loop = asyncio.get_running_loop()
        f1 = loop.create_future()
        engine._pending_permissions["dup-id"] = f1

        # Emit second request with same ID via handle_permission_request
        task = asyncio.create_task(
            engine.handle_permission_request(
                "dup-id", "bash", "rm test", []
            )
        )
        await asyncio.sleep(0)

        # First future should be cancelled
        assert f1.done()
        assert f1.result()["cancelled"] is True

        # Resolve the new request
        engine.resolve_permission("dup-id", option_id="allow")
        result = await task
        assert result["option_id"] == "allow"
        assert result["cancelled"] is False

    def test_cancel_all_on_empty(self):
        """cancel_all_permissions on empty dict is a no-op."""
        engine = AvatarEngine()
        engine.cancel_all_permissions()  # should not raise
        assert len(engine._pending_permissions) == 0

    def test_normalize_safety_mode_none_defaults_safe(self):
        """normalize_safety_mode(None) falls back to 'safe'."""
        assert normalize_safety_mode(None) == "safe"

    def test_normalize_safety_mode_int_defaults_safe(self):
        """normalize_safety_mode(42) falls back to 'safe'."""
        assert normalize_safety_mode(42) == "safe"
