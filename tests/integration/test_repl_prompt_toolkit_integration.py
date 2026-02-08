"""Integration tests for REPL prompt_toolkit + display flow."""

import asyncio
from contextlib import contextmanager
from io import StringIO
import re
from types import SimpleNamespace

import pytest
from rich.console import Console

from avatar_engine.cli.commands import repl as repl_cmd
from avatar_engine.events import EventEmitter, ThinkingEvent, ToolEvent

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _FakeEngine(EventEmitter):
    """Minimal engine stub for _repl_async integration flow."""

    def __init__(self) -> None:
        super().__init__()
        self.session_id = "fake-session"
        self.current_provider = "gemini"
        self.is_warm = True
        self.restart_count = 0
        self.rate_limit_stats = {}
        self.session_capabilities = SimpleNamespace(can_list=False, can_load=False)
        self.started = False
        self.stopped = False
        self.stream_calls = 0

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def list_sessions(self):  # pragma: no cover - not used here
        return []

    async def resume_session(self, _sid: str):  # pragma: no cover - not used here
        return False

    def get_history(self):
        return []

    def clear_history(self) -> None:
        return None

    async def chat_stream(self, _message: str):
        self.stream_calls += 1
        self.emit(ThinkingEvent(subject="Analyzing request"))
        await asyncio.sleep(0)
        self.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        self.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        yield "Hello"
        yield " world"
        self.emit(ThinkingEvent(is_complete=True))


def _prompt_session_factory(inputs):
    class _FakePromptSession:
        def __init__(self):
            self._iter = iter(inputs)

        async def prompt_async(self, _prompt: str):
            try:
                return next(self._iter)
            except StopIteration:
                raise EOFError()

    return _FakePromptSession


@pytest.mark.integration
class TestReplPromptToolkitFlow:
    @pytest.mark.asyncio
    async def test_repl_stream_turn_with_spinner_and_patch_stdout(self, monkeypatch):
        fake_engine = _FakeEngine()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True)
        patch_events = {"entered": False, "exited": False}

        @contextmanager
        def _fake_patch_stdout():
            patch_events["entered"] = True
            try:
                yield
            finally:
                patch_events["exited"] = True

        monkeypatch.setattr(repl_cmd, "AvatarEngine", lambda *args, **kwargs: fake_engine)
        monkeypatch.setattr(repl_cmd, "PromptSession", _prompt_session_factory(["Say hi", "/exit"]))
        monkeypatch.setattr(repl_cmd, "patch_stdout", _fake_patch_stdout)
        monkeypatch.setattr(repl_cmd, "console", fake_console)

        await repl_cmd._repl_async(
            provider="gemini",
            model=None,
            config_path=None,
            provider_explicit=False,
            verbose=False,
            working_dir=None,
            mcp_servers={},
            thinking_level=None,
            yolo=False,
            timeout=30,
        )

        rendered = out.getvalue()
        assert fake_engine.started is True
        assert fake_engine.stopped is True
        assert fake_engine.stream_calls == 1
        assert patch_events["entered"] is True
        assert patch_events["exited"] is True
        assert "Assistant" in rendered
        assert "Hello world" in rendered
        assert "Read" in rendered
        assert "\r" in rendered  # transient spinner line rendering

    @pytest.mark.asyncio
    async def test_repl_help_command_works_with_prompt_session(self, monkeypatch):
        fake_engine = _FakeEngine()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True)

        monkeypatch.setattr(repl_cmd, "AvatarEngine", lambda *args, **kwargs: fake_engine)
        monkeypatch.setattr(repl_cmd, "PromptSession", _prompt_session_factory(["/help", "/exit"]))
        monkeypatch.setattr(repl_cmd, "console", fake_console)

        await repl_cmd._repl_async(
            provider="gemini",
            model=None,
            config_path=None,
            provider_explicit=False,
            verbose=False,
            working_dir=None,
            mcp_servers={},
            thinking_level=None,
            yolo=False,
            timeout=30,
        )

        rendered = out.getvalue()
        assert "Commands:" in rendered
        assert "/usage" in rendered
        assert "/tools" in rendered
        assert fake_engine.stream_calls == 0

    @pytest.mark.asyncio
    async def test_repl_plain_mode_disables_ansi_colors(self, monkeypatch):
        fake_engine = _FakeEngine()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True)

        monkeypatch.setattr(repl_cmd, "AvatarEngine", lambda *args, **kwargs: fake_engine)
        monkeypatch.setattr(repl_cmd, "PromptSession", _prompt_session_factory(["/help", "/exit"]))
        monkeypatch.setattr(repl_cmd, "console", fake_console)

        await repl_cmd._repl_async(
            provider="gemini",
            model=None,
            config_path=None,
            provider_explicit=False,
            verbose=False,
            working_dir=None,
            mcp_servers={},
            thinking_level=None,
            yolo=False,
            timeout=30,
            plain=True,
        )

        rendered = out.getvalue()
        assert "\x1b[" not in rendered
        assert "/usage" in rendered

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_during_stream_recovers_loop(self, monkeypatch):
        class _InterruptEngine(_FakeEngine):
            async def chat_stream(self, _message: str):
                self.stream_calls += 1
                self.emit(ThinkingEvent(subject="interrupting"))
                await asyncio.sleep(0)
                raise KeyboardInterrupt()
                yield  # pragma: no cover

        fake_engine = _InterruptEngine()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True)

        monkeypatch.setattr(repl_cmd, "AvatarEngine", lambda *args, **kwargs: fake_engine)
        monkeypatch.setattr(repl_cmd, "PromptSession", _prompt_session_factory(["cause interrupt", "/exit"]))
        monkeypatch.setattr(repl_cmd, "console", fake_console)

        await repl_cmd._repl_async(
            provider="gemini",
            model=None,
            config_path=None,
            provider_explicit=False,
            verbose=False,
            working_dir=None,
            mcp_servers={},
            thinking_level=None,
            yolo=False,
            timeout=30,
        )

        rendered = out.getvalue()
        cleaned = _ANSI_RE.sub("", rendered)
        assert "Use '/exit' to quit" in cleaned
        assert fake_engine.stream_calls == 1
        assert "Session ended" in cleaned

    @pytest.mark.asyncio
    async def test_spinner_stops_before_streamed_text_output(self, monkeypatch):
        class _SlowChunkEngine(_FakeEngine):
            async def chat_stream(self, _message: str):
                self.stream_calls += 1
                self.emit(ThinkingEvent(subject="thinking before text"))
                await asyncio.sleep(0.05)
                yield "first"
                await asyncio.sleep(0.05)
                yield " second"
                self.emit(ThinkingEvent(is_complete=True))

        fake_engine = _SlowChunkEngine()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True)

        monkeypatch.setattr(repl_cmd, "AvatarEngine", lambda *args, **kwargs: fake_engine)
        monkeypatch.setattr(repl_cmd, "PromptSession", _prompt_session_factory(["hello", "/exit"]))
        monkeypatch.setattr(repl_cmd, "console", fake_console)

        await repl_cmd._repl_async(
            provider="gemini",
            model=None,
            config_path=None,
            provider_explicit=False,
            verbose=False,
            working_dir=None,
            mcp_servers={},
            thinking_level=None,
            yolo=False,
            timeout=30,
        )

        rendered = out.getvalue()
        # Spinner uses carriage returns before first text chunk.
        assert "\r" in rendered
        idx = rendered.find("Assistant")
        assert idx >= 0
        tail = rendered[idx:]
        # After assistant header, no transient spinner line rewrites should happen.
        assert "\r" not in tail
        assert "first second" in tail
