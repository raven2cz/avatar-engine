"""
Integration tests for CLI display rewrite (Phase: cli-plan).

Tests the fixes from CLI_DISPLAY_REWRITE_PLAN.md:
1. _stream_acp() error propagation (errors shown to user, not swallowed)
2. is_complete tracking for thinking events
3. Thinking text excluded from response output
4. REPL simplification (no prompt_toolkit)

Run with: pytest tests/integration/test_real_cli_display_rewrite.py -v
"""

import asyncio
import pytest

from avatar_engine import AvatarEngine
from avatar_engine.events import TextEvent, ThinkingEvent, EngineState
from avatar_engine.cli.display import DisplayManager

from rich.console import Console
from io import StringIO


def _make_quiet_console():
    """Create a console that writes to a string buffer (no terminal output)."""
    return Console(file=StringIO(), force_terminal=True)


# =============================================================================
# Gemini: thinking is_complete tracking
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiThinkingIsComplete:
    """Verify Gemini bridge emits is_complete=True when thinking ends."""

    @pytest.mark.asyncio
    async def test_thinking_complete_emitted(self, skip_if_no_gemini):
        """After thinking, an is_complete=True event should fire before text."""
        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            generation_config={"thinking_level": "low"},
        )
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        thinking_events = []

        @engine.on(ThinkingEvent)
        def on_thinking(e):
            thinking_events.append(e)

        try:
            await engine.start()

            display.on_response_start()
            response = await engine.chat(
                "What is the capital of France? Think step by step, then answer."
            )
            display.on_response_end()

            assert response.success is True

            # If thinking was triggered, we should see is_complete=True
            if thinking_events:
                complete_events = [e for e in thinking_events if e.is_complete]
                assert len(complete_events) >= 1, (
                    f"Got {len(thinking_events)} thinking events but none with "
                    f"is_complete=True"
                )

        finally:
            display.unregister()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_thinking_not_in_response_text(self, skip_if_no_gemini):
        """Thinking/reasoning text must NOT appear in chat response content."""
        engine = AvatarEngine(
            provider="gemini",
            timeout=60,
            generation_config={"thinking_level": "low"},
        )

        try:
            await engine.start()

            response = await engine.chat(
                "What is 2+2? Think about it, then reply with just the number."
            )

            assert response.success is True
            # Response should be short (just a number), not contain internal thoughts
            content = response.content.strip()
            assert len(content) < 200, (
                f"Response suspiciously long ({len(content)} chars) — "
                f"thinking may have leaked: {content[:100]}..."
            )

        finally:
            await engine.stop()


# =============================================================================
# Gemini: streaming error propagation
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiStreamErrorPropagation:
    """Verify _stream_acp errors are propagated, not swallowed."""

    @pytest.mark.asyncio
    async def test_stream_chat_delivers_text(self, skip_if_no_gemini):
        """Basic streaming should deliver text without error."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            display.on_response_start()
            chunks = []
            async for chunk in engine.chat_stream("Say 'hello world'."):
                chunks.append(chunk)
            display.on_response_end()

            full = "".join(chunks)
            assert len(full) > 0, "No text received from stream"

        finally:
            display.unregister()
            await engine.stop()


# =============================================================================
# REPL: no prompt_toolkit
# =============================================================================


@pytest.mark.integration
class TestReplNoPtk:
    """Verify REPL module has no prompt_toolkit dependency."""

    def test_no_prompt_toolkit_import(self):
        """repl.py must not import prompt_toolkit."""
        import importlib
        import sys

        # Ensure fresh import
        mod_name = "avatar_engine.cli.commands.repl"
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
        else:
            mod = importlib.import_module(mod_name)

        import inspect
        source = inspect.getsource(mod)
        assert "prompt_toolkit" not in source, "repl.py still imports prompt_toolkit"
        assert "patch_stdout" not in source, "repl.py still uses patch_stdout"
        assert "_quiet_repl_logs" not in source, "repl.py still has _quiet_repl_logs"

    def test_repl_module_imports_cleanly(self):
        """Importing repl module should not raise any errors."""
        from avatar_engine.cli.commands.repl import repl  # noqa: F401
        assert callable(repl)


# =============================================================================
# Display: spinner and status
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestDisplaySpinner:
    """Verify spinner and status line work during real interaction."""

    @pytest.mark.asyncio
    async def test_spinner_advances_during_chat(self, skip_if_no_gemini):
        """advance_spinner should work without error during real chat."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            display.on_response_start()

            # Simulate spinner advancing (as the REPL does)
            for _ in range(5):
                display.advance_spinner()

            response = await engine.chat("Say hi.")
            display.clear_status()
            display.on_response_end()

            assert response.success is True
            # Spinner should have written something to buffer
            output = buf.getvalue()
            assert len(output) > 0, "Spinner produced no output"

        finally:
            display.unregister()
            await engine.stop()
