"""Subprocess + PTY integration tests for REPL terminal behavior."""

import os
import pty
import re
import select
import subprocess
import sys
import textwrap
import time

import pytest


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _run_repl_under_pty(user_input: str, timeout: float = 12.0) -> tuple[int, str]:
    """Run patched REPL process under PTY and return (exit_code, combined_output)."""
    child_script = textwrap.dedent(
        """
        import asyncio
        from types import SimpleNamespace
        from contextlib import contextmanager
        from avatar_engine.events import EventEmitter, ThinkingEvent, ToolEvent
        import avatar_engine.cli.commands.repl as repl_cmd
        from avatar_engine.cli import cli as cli_group

        class FakeEngine(EventEmitter):
            def __init__(self):
                super().__init__()
                self.session_id = "pty-session"
                self.current_provider = "gemini"
                self.is_warm = True
                self.restart_count = 0
                self.rate_limit_stats = {}
                self.session_capabilities = SimpleNamespace(can_list=False, can_load=False)

            async def start(self):
                return None

            async def stop(self):
                return None

            def clear_history(self):
                return None

            def get_history(self):
                return []

            async def list_sessions(self):
                return []

            async def resume_session(self, _sid):
                return False

            async def chat_stream(self, _message):
                self.emit(ThinkingEvent(subject="pty-thinking"))
                await asyncio.sleep(0)
                self.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
                self.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
                yield "mock-reply"
                self.emit(ThinkingEvent(is_complete=True))

        class _PTYPromptSession:
            async def prompt_async(self, _prompt):
                import sys
                line = sys.stdin.readline()
                if line == "":
                    raise EOFError()
                return line.rstrip("\\n")

        @contextmanager
        def _noop_patch_stdout():
            yield

        repl_cmd.AvatarEngine = lambda *a, **k: FakeEngine()
        repl_cmd.PromptSession = _PTYPromptSession
        repl_cmd.patch_stdout = _noop_patch_stdout
        cli_group.main(args=["-p", "gemini", "repl"], prog_name="avatar", standalone_mode=False)
        """
    )

    try:
        master_fd, slave_fd = os.openpty()
    except (AttributeError, OSError):
        try:
            master_fd, slave_fd = pty.openpty()
        except OSError as exc:
            pytest.skip(f"PTY not available in this environment: {exc}")
    env = dict(os.environ)
    env.setdefault("TERM", "xterm-256color")

    proc = subprocess.Popen(
        [sys.executable, "-c", child_script],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        env=env,
    )
    os.close(slave_fd)

    os.write(master_fd, user_input.encode("utf-8"))

    output_chunks = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if ready:
            try:
                data = os.read(master_fd, 8192)
            except OSError:
                break
            if not data:
                break
            output_chunks.append(data.decode("utf-8", errors="ignore"))
        if proc.poll() is not None:
            # drain once more
            try:
                data = os.read(master_fd, 8192)
                if data:
                    output_chunks.append(data.decode("utf-8", errors="ignore"))
            except OSError:
                pass
            break

    if proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=3)

    os.close(master_fd)
    return proc.returncode, "".join(output_chunks)


@pytest.mark.integration
@pytest.mark.pty
class TestRealReplPty:
    def test_help_and_exit_via_pty(self):
        code, out = _run_repl_under_pty("/help\n/exit\n")
        clean = _strip_ansi(out)
        assert code == 0, out
        assert "Avatar Engine" in clean
        assert "Commands:" in clean
        assert "/usage" in clean
        assert "Session ended" in clean

    def test_chat_turn_renders_assistant_and_tool_status(self):
        code, out = _run_repl_under_pty("Hello from PTY\n/exit\n")
        clean = _strip_ansi(out)
        assert code == 0, out
        assert "Assistant" in clean
        assert "mock-reply" in clean
        assert "Read" in clean
