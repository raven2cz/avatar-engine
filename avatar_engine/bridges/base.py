"""
Abstract base bridge for CLI communication.

Two modes:
1. PERSISTENT — one subprocess stays alive, multi-turn via stdin/stdout JSONL
   → True warm session: start() warms up, then send() is instant
   → Claude Code: --input-format stream-json --output-format stream-json

2. ONESHOT — new subprocess per prompt, --resume for context continuity
   → Cold start every call, but model remembers conversation
   → Gemini CLI: gemini -p "..." --output-format stream-json
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from ..types import Attachment, SessionInfo, SessionCapabilitiesInfo, ProviderCapabilities

logger = logging.getLogger(__name__)


class BridgeState(Enum):
    DISCONNECTED = "disconnected"
    WARMING_UP = "warming_up"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class Message:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Attachment] = field(default_factory=list)


@dataclass
class BridgeResponse:
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_events: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    token_usage: Optional[Dict[str, Any]] = None
    success: bool = True
    error: Optional[str] = None
    generated_images: List[Path] = field(default_factory=list)


def _classify_stderr_level(text: str) -> str:
    """Classify stderr line into diagnostic level."""
    lower = text.lower()
    if any(w in lower for w in ["error", "fatal", "critical", "failed", "exception"]):
        return "error"
    if any(w in lower for w in ["warn", "deprecated", "expir"]):
        return "warning"
    if any(w in lower for w in ["debug", "trace"]):
        return "debug"
    return "info"


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    return _ANSI_RE.sub('', text)


class BaseBridge(ABC):
    """Abstract base class supporting persistent and oneshot modes."""

    def __init__(
        self,
        executable: str,
        model: str,
        working_dir: str = "",
        timeout: int = 600,
        system_prompt: str = "",
        env: Optional[Dict[str, str]] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
    ):
        self.executable = executable
        self.model = model
        self.working_dir = working_dir or os.getcwd()
        self.timeout = timeout
        self.system_prompt = system_prompt
        self.env = env or {}
        self.mcp_servers = mcp_servers or {}
        self.tool_policy: Optional[ToolPolicy] = None  # GAP-8: Engine-level tool policy

        self.state = BridgeState.DISCONNECTED
        self.history: List[Message] = []
        self.session_id: Optional[str] = None

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._read_lock = asyncio.Lock()
        self._stdin_lock = asyncio.Lock()  # RC-7: protect concurrent stdin writes
        self._stderr_task: Optional[asyncio.Task] = None
        self._stderr_buffer: List[str] = []
        self._stderr_lock = threading.Lock()  # RC-8: protect stderr buffer

        self._on_output: Optional[Callable[[str], None]] = None
        self._on_state_change: Optional[Callable[[BridgeState, str], None]] = None
        self._state_detail: str = ""
        self._on_event: Optional[Callable[[Dict[str, Any]], None]] = None
        self._on_stderr: Optional[Callable[[str], None]] = None

        # Session capabilities (populated during start by subclasses)
        self._session_capabilities = SessionCapabilitiesInfo()

        # Provider capabilities (set by subclass constructors)
        self._provider_capabilities = ProviderCapabilities()

        # RC-9/10: Locks for history and stats
        self._history_lock = threading.Lock()
        self._stats_lock = threading.Lock()

        # Usage statistics
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration_ms": 0,
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

    # === Abstract interface =============================================

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def is_persistent(self) -> bool:
        """True = warm session (one process). False = cold start per call."""
        ...

    @abstractmethod
    def _setup_config_files(self) -> None: ...

    @abstractmethod
    def _parse_session_id(self, events: List[Dict[str, Any]]) -> Optional[str]: ...

    @abstractmethod
    def _parse_content(self, events: List[Dict[str, Any]]) -> str: ...

    @abstractmethod
    def _parse_tool_calls(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def _parse_usage(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def _extract_text_delta(self, event: Dict[str, Any]) -> Optional[str]: ...

    @abstractmethod
    def _is_turn_complete(self, event: Dict[str, Any]) -> bool:
        """Return True when event signals the model finished its response."""
        ...

    # Persistent mode
    @abstractmethod
    def _build_persistent_command(self) -> List[str]: ...

    @abstractmethod
    def _format_user_message(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> str:
        """Encode user prompt as a single JSONL line for stdin."""
        ...

    # Oneshot mode
    @abstractmethod
    def _build_oneshot_command(self, prompt: str) -> List[str]: ...

    def _build_subprocess_env(self) -> Dict[str, str]:
        """Build environment for subprocesses. Override to add sandbox env vars."""
        return {**os.environ, **self.env}

    # === Unbounded line reader ==========================================
    # asyncio's readline() raises LimitOverrunError when a single line
    # exceeds the stream buffer limit (default 64 KB).  Large JSON events
    # (e.g. code-block responses) easily surpass this.  read() has *no*
    # limit, so we accumulate raw chunks and split on newlines ourselves.

    _read_buf: bytes = b""

    async def _read_line(self, stream: asyncio.StreamReader) -> bytes:
        """Read one \\n-terminated line with no size limit.

        Returns b'' on EOF (same contract as readline).
        """
        while b"\n" not in self._read_buf:
            chunk = await stream.read(256 * 1024)  # 256 KB chunks
            if not chunk:
                # EOF — return whatever is left
                remaining = self._read_buf
                self._read_buf = b""
                return remaining
            self._read_buf += chunk
        line, self._read_buf = self._read_buf.split(b"\n", 1)
        return line + b"\n"

    # === Callbacks ======================================================

    def on_output(self, cb: Callable[[str], None]) -> None:
        self._on_output = cb

    def on_state_change(self, cb: Callable[[BridgeState, str], None]) -> None:
        self._on_state_change = cb

    def on_event(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._on_event = cb

    def on_stderr(self, cb: Callable[[str], None]) -> None:
        """Register callback for stderr output."""
        self._on_stderr = cb

    def get_stderr_buffer(self) -> List[str]:
        """Get accumulated stderr output."""
        with self._stderr_lock:  # RC-8: safe concurrent access
            return list(self._stderr_buffer)

    def clear_stderr_buffer(self) -> None:
        """Clear accumulated stderr output."""
        with self._stderr_lock:  # RC-8: safe concurrent access
            self._stderr_buffer.clear()

    # === Session management ===============================================

    @property
    def session_capabilities(self) -> SessionCapabilitiesInfo:
        """What session operations this bridge supports."""
        return self._session_capabilities

    @property
    def provider_capabilities(self) -> ProviderCapabilities:
        """Full provider capability declaration for GUI adaptation."""
        return self._provider_capabilities

    async def list_sessions(self) -> List[SessionInfo]:
        """List available sessions. Override in subclass if supported."""
        return []

    async def resume_session(self, session_id: str) -> bool:
        """Resume a specific session. Override in subclass if supported."""
        raise NotImplementedError(
            f"{self.provider_name} does not support session resume"
        )

    # === State ===========================================================

    def _set_state(self, state: BridgeState, detail: str = "") -> None:
        old = self.state
        old_detail = self._state_detail
        self.state = state
        self._state_detail = detail
        if self._on_state_change and (old != state or old_detail != detail):
            self._on_state_change(state, detail)

    # === Lifecycle ======================================================

    async def start(self) -> None:
        """
        Initialize bridge.

        For persistent mode: spawns subprocess, waits for init event (warm-up).
        For oneshot mode: just writes config files, marks READY.
        """
        logger.info(f"Starting {self.provider_name} bridge "
                     f"({'persistent' if self.is_persistent else 'oneshot'})")
        self._setup_config_files()

        if self.is_persistent:
            await self._start_persistent()
        else:
            self._set_state(BridgeState.READY)

    async def stop(self) -> None:
        """Shutdown bridge."""
        # Stop stderr monitoring task
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

        if self._proc and self._proc.returncode is None:
            logger.info("Terminating persistent process")
            try:
                self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._proc.kill()
            self._proc = None
        self.session_id = None
        self._set_state(BridgeState.DISCONNECTED)
        # Cleanup sandbox temp files (Zero Footprint)
        if hasattr(self, "_sandbox") and self._sandbox:
            self._sandbox.cleanup()
            self._sandbox = None

    async def _start_persistent(self) -> None:
        """Spawn long-running process and wait for warm-up (init event)."""
        self._set_state(BridgeState.WARMING_UP)
        cmd = self._build_persistent_command()
        env = self._build_subprocess_env()

        logger.info(f"Spawning: {' '.join(cmd[:10])}…")
        self._read_buf = b""  # reset line buffer for new process
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env=env,
        )

        # Start stderr monitoring task
        self._stderr_task = asyncio.create_task(self._monitor_stderr())

        # Read init/system events until the process is ready
        try:
            init_events = await self._read_until_turn_complete()
            sid = self._parse_session_id(init_events)
            if sid:
                self.session_id = sid
            self._set_state(BridgeState.READY)
            logger.info(f"Warm-up done. Session: {self.session_id}, "
                        f"PID: {self._proc.pid}")
        except Exception as exc:
            logger.error(f"Warm-up failed: {exc}")
            self._set_state(BridgeState.ERROR)
            raise

    async def _monitor_stderr(self) -> None:
        """Background task to monitor stderr output."""
        try:
            while self._proc and self._proc.returncode is None:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                text = _strip_ansi(line.decode(errors="replace").strip())
                if text:
                    with self._stderr_lock:  # RC-8: safe concurrent access
                        self._stderr_buffer.append(text)
                    logger.debug(f"stderr: {text}")
                    if self._on_stderr:
                        self._on_stderr(text)
                    # GAP-7: Surface stderr as diagnostic event
                    if self._on_event:
                        self._on_event({
                            "type": "diagnostic",
                            "message": text,
                            "level": _classify_stderr_level(text),
                            "source": "stderr",
                        })
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug(f"stderr monitor: {exc}")

    # === Core API =======================================================

    async def send(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> BridgeResponse:
        """Send prompt with optional file attachments, get complete response."""
        if self.state == BridgeState.DISCONNECTED:
            await self.start()

        self._set_state(BridgeState.BUSY)
        t0 = time.time()

        try:
            if self.is_persistent:
                events = await self._send_persistent(prompt, attachments=attachments)
            else:
                if attachments:
                    logger.warning(
                        f"Attachments not supported in oneshot mode — "
                        f"{len(attachments)} file(s) will be ignored"
                    )
                events = await self._send_oneshot(prompt)

            elapsed = int((time.time() - t0) * 1000)
            content = self._parse_content(events)
            sid = self._parse_session_id(events)
            tools = self._parse_tool_calls(events)
            usage = self._parse_usage(events)

            if sid:
                self.session_id = sid
            with self._history_lock:  # RC-9
                self.history.append(Message(role="user", content=prompt, attachments=attachments or []))
                self.history.append(Message(role="assistant", content=content, tool_calls=tools))

            self._set_state(BridgeState.READY)
            response = BridgeResponse(
                content=content, tool_calls=tools, raw_events=events,
                duration_ms=elapsed, session_id=self.session_id,
                token_usage=usage, success=True,
            )
            self._update_stats(response)
            return response

        except asyncio.TimeoutError:
            self._set_state(BridgeState.ERROR)
            response = BridgeResponse(content="", duration_ms=int((time.time() - t0) * 1000),
                                      success=False, error=f"Timeout ({self.timeout}s)")
            self._update_stats(response)
            return response
        except Exception as exc:
            logger.error(f"send: {exc}", exc_info=True)
            self._set_state(BridgeState.ERROR)
            response = BridgeResponse(content="", duration_ms=int((time.time() - t0) * 1000),
                                      success=False, error=str(exc))
            self._update_stats(response)
            return response

    async def send_stream(self, prompt: str) -> AsyncIterator[str]:
        """Send prompt, yield text chunks in real-time."""
        if self.state == BridgeState.DISCONNECTED:
            await self.start()

        self._set_state(BridgeState.BUSY)
        full = ""
        all_events: List[Dict[str, Any]] = []

        try:
            if self.is_persistent:
                gen = self._stream_persistent(prompt)
            else:
                gen = self._stream_oneshot(prompt)

            async for event in gen:
                all_events.append(event)
                if self._on_event:
                    self._on_event(event)
                delta = self._extract_text_delta(event)
                if delta:
                    full += delta
                    if self._on_output:
                        self._on_output(delta)
                    yield delta

            sid = self._parse_session_id(all_events)
            if sid:
                self.session_id = sid
            with self._history_lock:  # RC-9
                self.history.append(Message(role="user", content=prompt))
                self.history.append(Message(role="assistant", content=full))
            self._set_state(BridgeState.READY)
        except Exception:
            self._set_state(BridgeState.ERROR)
            raise

    # === PERSISTENT internals ===========================================

    async def _send_persistent(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> List[Dict[str, Any]]:
        if not self._proc or self._proc.returncode is not None:
            raise RuntimeError("Persistent process not running")
        line = self._format_user_message(prompt, attachments=attachments)
        logger.debug(f"stdin> {line.strip()}")
        async with self._stdin_lock:  # RC-7: prevent garbled input
            self._proc.stdin.write((line + "\n").encode())
            await self._proc.stdin.drain()
        return await self._read_until_turn_complete()

    async def _stream_persistent(self, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        if not self._proc or self._proc.returncode is not None:
            raise RuntimeError("Persistent process not running")
        line = self._format_user_message(prompt)
        async with self._stdin_lock:  # RC-7: prevent garbled input
            self._proc.stdin.write((line + "\n").encode())
            await self._proc.stdin.drain()
        async for event in self._read_events():
            yield event
            if self._is_turn_complete(event):
                break

    async def _read_until_turn_complete(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        async with self._read_lock:
            while True:
                raw = await asyncio.wait_for(
                    self._read_line(self._proc.stdout), timeout=self.timeout,
                )
                if not raw:
                    raise RuntimeError("Process exited unexpectedly")
                text = raw.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    logger.debug(f"non-json: {text[:200]}")
                    continue
                events.append(event)
                if self._on_event:
                    self._on_event(event)
                if self._is_turn_complete(event):
                    break
        return events

    async def _read_events(self) -> AsyncIterator[Dict[str, Any]]:
        async with self._read_lock:
            while True:
                raw = await asyncio.wait_for(
                    self._read_line(self._proc.stdout), timeout=self.timeout,
                )
                if not raw:
                    raise RuntimeError("Process exited unexpectedly")
                text = raw.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    yield json.loads(text)
                except json.JSONDecodeError:
                    logger.debug(f"non-json: {text[:200]}")

    # === ONESHOT internals ==============================================

    async def _send_oneshot(self, prompt: str) -> List[Dict[str, Any]]:
        cmd = self._build_oneshot_command(prompt)
        env = self._build_subprocess_env()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir, env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise

        if stderr:
            logger.debug(f"stderr: {stderr.decode(errors='replace')[:500]}")

        events: List[Dict[str, Any]] = []
        for line in stdout.decode(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
                # Emit raw events (GAP-3: ensures thinking events
                # are emitted in oneshot mode for GUI ThinkingEvent)
                if self._on_event:
                    self._on_event(event)
            except json.JSONDecodeError:
                logger.debug(f"non-json: {line[:200]}")

        if proc.returncode != 0 and not events:
            raise RuntimeError(f"CLI exit {proc.returncode}: "
                               f"{stderr.decode(errors='replace')[:500]}")
        return events

    async def _stream_oneshot(self, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        cmd = self._build_oneshot_command(prompt)
        env = self._build_subprocess_env()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir, env=env,
        )
        event_count = 0
        oneshot_buf = b""
        async def _read_line_local(stream: asyncio.StreamReader) -> bytes:
            nonlocal oneshot_buf
            while b"\n" not in oneshot_buf:
                chunk = await stream.read(256 * 1024)
                if not chunk:
                    remaining = oneshot_buf
                    oneshot_buf = b""
                    return remaining
                oneshot_buf += chunk
            line, oneshot_buf = oneshot_buf.split(b"\n", 1)
            return line + b"\n"
        try:
            while True:
                raw = await asyncio.wait_for(_read_line_local(proc.stdout), timeout=self.timeout)
                if not raw:
                    break
                text = raw.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    event_count += 1
                    yield json.loads(text)
                except json.JSONDecodeError:
                    logger.debug(f"non-json: {text[:200]}")
        except asyncio.TimeoutError:
            proc.kill()
            raise
        finally:
            await proc.wait()
            # Check for silent failure: process exited with error and no events
            if proc.returncode != 0 and event_count == 0:
                stderr = ""
                if proc.stderr:
                    stderr_raw = await proc.stderr.read()
                    stderr = stderr_raw.decode(errors="replace").strip()
                raise RuntimeError(
                    f"CLI exited with code {proc.returncode}"
                    + (f": {stderr[:500]}" if stderr else "")
                )

    # === History ========================================================

    def get_history(self) -> List[Message]:
        with self._history_lock:  # RC-9
            return list(self.history)

    def clear_history(self) -> None:
        with self._history_lock:  # RC-9
            self.history.clear()
        self.session_id = None

    # === Health =========================================================

    def is_healthy(self) -> bool:
        """Quick health check — is bridge operational?"""
        if self.state == BridgeState.DISCONNECTED:
            return False
        if self.state == BridgeState.ERROR:
            return False
        if self.is_persistent and self._proc:
            if self._proc.returncode is not None:
                return False  # Process died
        return True

    def check_health(self) -> Dict[str, Any]:
        """Detailed health check with diagnostics."""
        with self._history_lock:  # RC-9
            history_len = len(self.history)
        health: Dict[str, Any] = {
            "healthy": self.is_healthy(),
            "state": self.state.value,
            "provider": self.provider_name,
            "session_id": self.session_id,
            "history_length": history_len,
        }
        if self._proc:
            health["pid"] = self._proc.pid
            health["returncode"] = self._proc.returncode
        # Include usage stats
        with self._stats_lock:  # RC-10
            health.update(self._stats)
        return health

    # === System Prompt Injection =========================================

    def _prepend_system_prompt(self, prompt: str) -> str:
        """Prepend system prompt to the first user message.

        For ACP bridges where the protocol has no native system prompt
        parameter. Only prepends on the very first request (total_requests == 0).
        Claude bridge doesn't need this (uses --append-system-prompt flag).
        Gemini oneshot doesn't need this (uses GEMINI_SYSTEM_MD env var).
        """
        with self._stats_lock:
            is_first = self._stats["total_requests"] == 0
        if is_first and self.system_prompt:
            return (
                f"[SYSTEM INSTRUCTIONS]\n{self.system_prompt}\n"
                f"[END INSTRUCTIONS]\n\n{prompt}"
            )
        return prompt

    # === Budget Control ==================================================

    def is_over_budget(self) -> bool:
        """Check if accumulated cost exceeds the configured budget.

        Subclasses that support budget limits (e.g. ClaudeBridge) should
        set self._max_budget_usd. Returns False if no budget is set.
        """
        max_budget = getattr(self, "_max_budget_usd", None)
        if not max_budget:
            return False
        with self._stats_lock:
            return self._stats["total_cost_usd"] >= max_budget

    # === Usage Stats ====================================================

    def get_usage(self) -> Dict[str, Any]:
        """Get usage summary for display (e.g. /usage REPL command)."""
        with self._stats_lock:  # RC-10
            stats = dict(self._stats)
        stats["provider"] = self.provider_name
        stats["session_id"] = self.session_id
        return stats

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        with self._stats_lock:  # RC-10
            return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        with self._stats_lock:  # RC-10
            self._stats = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_duration_ms": 0,
                "total_cost_usd": 0.0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
            }

    def _update_stats(self, response: BridgeResponse) -> None:
        """Update stats from a response."""
        with self._stats_lock:  # RC-10
            self._stats["total_requests"] += 1
            if response.success:
                self._stats["successful_requests"] += 1
            else:
                self._stats["failed_requests"] += 1
            self._stats["total_duration_ms"] += response.duration_ms
            if response.cost_usd:
                self._stats["total_cost_usd"] += response.cost_usd
            if response.token_usage:
                self._stats["total_input_tokens"] += response.token_usage.get("input", 0)
                self._stats["total_output_tokens"] += response.token_usage.get("output", 0)
