"""
Codex CLI bridge — ACP warm session via codex-acp adapter.

Architecture:
    start() spawns codex-acp via ACP Python SDK:
        npx @zed-industries/codex-acp
    → initialize → authenticate → new_session → prompt → prompt …
    = ONE process, multiple prompts = TRUE warm session

    ┌─────────────┐     ACP JSON-RPC (stdin/stdout)     ┌─────────────┐
    │ Python App  │ ──────────────────────────────────→  │ codex-acp   │
    │ (ACP SDK)   │ ←──────────────────────────────────  │ (Rust bin)  │
    └─────────────┘                                      └─────────────┘
                                                           ↕ codex-core
                                                         OpenAI API

Unlike GeminiBridge, there is NO oneshot fallback — codex-acp is the only
integration path. The Codex CLI does not have a headless stream-json mode.

Authentication:
    ACP uses ``authenticate(methodId="chatgpt")`` for browser OAuth,
    or ``codex-api-key`` / ``openai-api-key`` for API key auth.

Requirements:
    pip install agent-client-protocol>=0.6.0
    npm install -g @zed-industries/codex-acp  (or use npx)
"""

import asyncio
from collections import deque
import logging
import shutil
import threading
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .base import BaseBridge, BridgeResponse, BridgeState, Message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional ACP SDK import
# ---------------------------------------------------------------------------
_ACP_AVAILABLE = False
try:
    from acp import PROTOCOL_VERSION, connect_to_agent, text_block
    from acp.interfaces import Client as ACPClient
    from acp.schema import (
        AgentMessageChunk,
        AgentThoughtChunk,
        AllowedOutcome,
        ClientCapabilities,
        DeniedOutcome,
        FileSystemCapability,
        PermissionOption,
        RequestPermissionResponse,
        TextContentBlock,
        ToolCall,
        ToolCallStart,
        ToolCallProgress,
    )

    _ACP_AVAILABLE = True
except ImportError:
    logger.info(
        "agent-client-protocol not installed — Codex ACP unavailable. "
        "Install with: uv add agent-client-protocol"
    )


from ._acp_session import ACPSessionMixin


class CodexBridge(ACPSessionMixin, BaseBridge):
    """
    Codex CLI bridge via ACP adapter (codex-acp).

    Uses the same ACP Python SDK as GeminiBridge but communicates
    with the codex-acp Rust binary instead of Gemini CLI.

    ACP-only: no oneshot fallback (Codex CLI has no headless stream-json mode).

    Lifecycle::

        bridge = CodexBridge(...)
        await bridge.start()     # Spawns codex-acp, authenticates, creates session
        resp = await bridge.send("Hello!")   # Instant (warm session)
        resp = await bridge.send("More?")    # Same session
        await bridge.stop()
    """

    def __init__(
        self,
        executable: str = "npx",
        executable_args: Optional[List[str]] = None,
        model: str = "",  # Empty = Codex default (gpt-5.3-codex)
        working_dir: str = "",
        timeout: int = 120,
        system_prompt: str = "",
        auth_method: str = "chatgpt",  # chatgpt | codex-api-key | openai-api-key
        approval_mode: str = "auto",   # auto-approve tool calls
        sandbox_mode: str = "workspace-write",  # read-only | workspace-write | danger-full-access
        env: Optional[Dict[str, str]] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
        resume_session_id: Optional[str] = None,
        continue_last: bool = False,
    ):
        """
        Args:
            executable: Path to codex-acp binary or npx.
            executable_args: Arguments after executable (default: ["@zed-industries/codex-acp"]).
            model: Model name (empty = Codex default).
            working_dir: Working directory for the Codex session.
            timeout: Request timeout in seconds.
            system_prompt: System prompt for the AI.
            auth_method: ACP authentication method:
                - "chatgpt" — Browser OAuth flow via codex-login
                - "codex-api-key" — CODEX_API_KEY env var
                - "openai-api-key" — OPENAI_API_KEY env var
            approval_mode: Tool approval mode:
                - "auto" — Auto-approve all tool calls (non-interactive)
                - "manual" — Require explicit approval (interactive only)
            sandbox_mode: Filesystem sandbox mode:
                - "read-only" — Can read files, no writes
                - "workspace-write" — Can modify workspace files
                - "danger-full-access" — Full filesystem access
            env: Extra environment variables for the subprocess.
            mcp_servers: MCP server configurations (passed per-session).
            resume_session_id: Resume a specific session by ID (via ACP load_session).
            continue_last: Continue the most recent session (via ACP list+load).
        """
        super().__init__(
            executable=executable,
            model=model,
            working_dir=working_dir,
            timeout=timeout,
            system_prompt=system_prompt,
            env=env,
            mcp_servers=mcp_servers,
        )
        self.executable_args = executable_args if executable_args is not None else ["@zed-industries/codex-acp"]
        self.auth_method = auth_method
        self.approval_mode = approval_mode
        self.sandbox_mode = sandbox_mode
        self.resume_session_id = resume_session_id
        self.continue_last = continue_last

        # ACP state
        self._acp_conn = None
        self._acp_proc = None
        self._acp_session_id: Optional[str] = None

        # Collected events from ACP session_update notifications
        self._acp_events: List[Dict[str, Any]] = []
        self._acp_text_buffer: str = ""
        self._recent_thinking_norm = deque(maxlen=8)
        self._was_thinking = False  # Track thinking→text transition for is_complete
        self._acp_buffer_lock = threading.Lock()  # RC-3/4: sync callback vs main thread

        # Provider capabilities
        self._provider_capabilities.thinking_supported = True   # Codex reasoning
        self._provider_capabilities.thinking_structured = True
        self._provider_capabilities.cost_tracking = False
        self._provider_capabilities.budget_enforcement = False
        self._provider_capabilities.system_prompt_method = "injected"  # ACP prepend
        self._provider_capabilities.streaming = True
        self._provider_capabilities.parallel_tools = False
        self._provider_capabilities.cancellable = False
        self._provider_capabilities.mcp_supported = True

    @property
    def provider_name(self) -> str:
        return "codex"

    @property
    def is_persistent(self) -> bool:
        return True  # Always ACP warm session

    # ======================================================================
    # Lifecycle — ACP only (no oneshot fallback)
    # ======================================================================

    async def start(self) -> None:
        """
        Start the Codex bridge via ACP.

        Spawns codex-acp, authenticates, and creates a session.
        Raises RuntimeError if ACP SDK is not installed.
        """
        if not _ACP_AVAILABLE:
            raise RuntimeError(
                "agent-client-protocol SDK not installed. "
                "Install with: pip install agent-client-protocol"
            )

        logger.info(f"Starting Codex bridge (auth: {self.auth_method})")

        try:
            await self._start_acp()
            logger.info(
                f"Codex ACP warm session active. Session: {self._acp_session_id}, "
                f"Auth: {self.auth_method}"
            )
        except Exception as exc:
            logger.error(f"Codex ACP start failed: {exc}")
            self._set_state(BridgeState.ERROR)
            await self._cleanup_acp()
            raise

    async def stop(self) -> None:
        """Shutdown bridge — clean up ACP context."""
        await self._cleanup_acp()
        await super().stop()

    # ======================================================================
    # ACP warm session management
    # ======================================================================

    async def _start_acp(self) -> None:
        """Spawn codex-acp via connect_to_agent (official SDK API)."""
        self._set_state(BridgeState.WARMING_UP)

        # Verify executable is available
        exe_bin = shutil.which(self.executable)
        if not exe_bin:
            raise FileNotFoundError(
                f"Executable not found: '{self.executable}'. "
                "Install npx (Node.js) or codex-acp binary."
            )

        # Build command: executable + executable_args
        cmd_args = [exe_bin] + self.executable_args
        env = self._build_subprocess_env()

        logger.info(f"Spawning ACP: {' '.join(cmd_args[:6])}")

        # Spawn process with stdio pipes
        self._acp_proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
            cwd=self.working_dir,
            env=env,
        )

        # Build ACP client that handles permission requests
        client = _CodexACPClient(
            auto_approve=(self.approval_mode == "auto"),
            on_update=self._handle_acp_update,
        )

        # Connect via official SDK API
        self._acp_conn = connect_to_agent(
            client, self._acp_proc.stdin, self._acp_proc.stdout
        )

        # Step 1: Initialize protocol with client capabilities
        init_resp = await asyncio.wait_for(
            self._acp_conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(
                    fs=FileSystemCapability(
                        read_text_file=True,
                        write_text_file=True,
                    ),
                    terminal=True,
                ),
            ),
            timeout=self.timeout,
        )
        logger.debug(f"ACP initialized: protocol v{init_resp.protocol_version}")
        self._store_acp_capabilities(init_resp)

        # Step 2: Authenticate
        try:
            await asyncio.wait_for(
                self._acp_conn.authenticate(method_id=self.auth_method),
                timeout=self.timeout,
            )
            logger.info(f"ACP authenticated via: {self.auth_method}")
        except asyncio.TimeoutError:
            logger.error(f"ACP authentication timed out after {self.timeout}s")
            raise RuntimeError(
                f"Codex authentication timed out. "
                f"For '{self.auth_method}' auth, ensure credentials are available. "
                f"Run 'codex login' for ChatGPT auth, or set CODEX_API_KEY/OPENAI_API_KEY."
            )
        except Exception as exc:
            exc_str = str(exc).lower()
            if "not supported" in exc_str or "not implemented" in exc_str:
                logger.info("ACP authenticate not required (auto-detect mode)")
            else:
                logger.warning(
                    f"ACP authenticate issue: {exc} — continuing. "
                    f"If session fails, check your Codex credentials."
                )

        # Step 3: Create or resume session
        mcp_servers_acp = self._build_mcp_servers_acp()
        await self._create_or_resume_acp_session(mcp_servers_acp)

    def _build_mcp_servers_acp(self) -> list:
        """Convert MCP servers dict to ACP format."""
        mcp_servers_acp = []
        if self.mcp_servers:
            for name, srv in self.mcp_servers.items():
                env_dict = srv.get("env", {})
                env_list = [{"name": k, "value": v} for k, v in env_dict.items()]
                entry = {
                    "name": name,
                    "command": srv["command"],
                    "args": srv.get("args", []),
                    "env": env_list,
                }
                mcp_servers_acp.append(entry)
        return mcp_servers_acp

    async def _cleanup_acp(self) -> None:
        """Clean up ACP connection and terminate process.

        Closes subprocess pipes and transport explicitly to prevent
        'Event loop is closed' errors from BaseSubprocessTransport.__del__.
        """
        if self._acp_conn:
            try:
                await self._acp_conn.close()
            except Exception as exc:
                logger.debug(f"ACP conn close: {exc}")
            self._acp_conn = None
        if self._acp_proc:
            # Close stdin to signal EOF to child process
            if self._acp_proc.stdin:
                try:
                    self._acp_proc.stdin.close()
                except Exception:
                    pass
            if self._acp_proc.returncode is None:
                try:
                    self._acp_proc.terminate()
                    await asyncio.wait_for(self._acp_proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._acp_proc.kill()
                    await self._acp_proc.wait()
                except Exception as exc:
                    logger.debug(f"ACP process cleanup: {exc}")
            # Close the subprocess transport so pipe transports are cleaned up
            # while the event loop is still running
            try:
                transport = getattr(self._acp_proc, "_transport", None)
                if transport and hasattr(transport, "close"):
                    transport.close()
                # Give event loop a chance to process pipe close callbacks
                await asyncio.sleep(0)
            except Exception:
                pass
        self._acp_proc = None
        self._acp_session_id = None

    def _handle_acp_update(self, session_id: str, update: Any) -> None:
        """Callback for ACP session/update notifications (streaming text + thinking).

        Called from ACP SDK thread — all buffer writes protected by lock (RC-3/4).
        Wrapped in try-except so exceptions don't propagate into ACP SDK internals.
        """
        try:
            self._handle_acp_update_inner(session_id, update)
        except Exception as exc:
            logger.debug(f"Error in ACP update handler: {exc}", exc_info=True)

    def _handle_acp_update_inner(self, session_id: str, update: Any) -> None:
        """Inner handler for ACP updates — uses typed SDK objects.

        The ACP SDK delivers typed updates:
        - AgentThoughtChunk → thinking event (spinner, NOT printed)
        - AgentMessageChunk → response text (printed to output)
        - ToolCallStart/ToolCallProgress → tool events
        - Fallback: legacy attribute-based extraction
        """
        # --- Typed dispatch (ACP SDK 0.8+) ---
        if _ACP_AVAILABLE and isinstance(update, AgentThoughtChunk):
            thinking = _text_from_content(update.content)
            if thinking:
                self._was_thinking = True
                norm = _normalize_reasoning_text(thinking)
                if norm:
                    with self._acp_buffer_lock:
                        self._recent_thinking_norm.append(norm)
                thinking_event = {
                    "type": "thinking",
                    "session_id": session_id,
                    "thought": thinking,
                }
                with self._acp_buffer_lock:
                    self._acp_events.append(thinking_event)
                if self._on_event:
                    self._on_event(thinking_event)
            return

        if _ACP_AVAILABLE and isinstance(update, AgentMessageChunk):
            text = _text_from_content(update.content)
            if text and not self._should_suppress_text_output(text):
                # Thinking→text transition: emit is_complete so display stops spinner
                if self._was_thinking:
                    self._was_thinking = False
                    complete_event = {
                        "type": "thinking",
                        "session_id": session_id,
                        "thought": "",
                        "is_complete": True,
                    }
                    if self._on_event:
                        self._on_event(complete_event)

                event = {"type": "acp_update", "session_id": session_id, "text": text}
                with self._acp_buffer_lock:
                    self._acp_text_buffer += text
                    self._acp_events.append(event)
                if self._on_output:
                    self._on_output(text)
                if self._on_event:
                    self._on_event(event)
            return

        if _ACP_AVAILABLE and isinstance(update, (ToolCallStart, ToolCallProgress)):
            tool_event = _extract_tool_event_from_update(update)
            if tool_event:
                tool_event["session_id"] = session_id
                with self._acp_buffer_lock:
                    self._acp_events.append(tool_event)
                if self._on_event:
                    self._on_event(tool_event)
            return

        # --- Fallback: legacy attribute-based extraction ---
        event = {"type": "acp_update", "session_id": session_id, "raw": str(update)}

        thinking = _extract_thinking_from_update(update)
        if thinking:
            self._was_thinking = True
            norm = _normalize_reasoning_text(thinking)
            if norm:
                with self._acp_buffer_lock:
                    self._recent_thinking_norm.append(norm)
            thinking_event = {
                "type": "thinking",
                "session_id": session_id,
                "thought": thinking,
            }
            with self._acp_buffer_lock:
                self._acp_events.append(thinking_event)
            if self._on_event:
                self._on_event(thinking_event)

        tool_event = _extract_tool_event_from_update(update)
        if tool_event:
            tool_event["session_id"] = session_id
            with self._acp_buffer_lock:
                self._acp_events.append(tool_event)
            if self._on_event:
                self._on_event(tool_event)

        text = None if thinking else _extract_text_from_update(update)
        if text and not self._should_suppress_text_output(text):
            if self._was_thinking:
                self._was_thinking = False
                complete_event = {
                    "type": "thinking",
                    "session_id": session_id,
                    "thought": "",
                    "is_complete": True,
                }
                if self._on_event:
                    self._on_event(complete_event)

            event["text"] = text
            with self._acp_buffer_lock:
                self._acp_text_buffer += text
            if self._on_output:
                self._on_output(text)

        with self._acp_buffer_lock:
            self._acp_events.append(event)
        if self._on_event:
            self._on_event(event)

    # ======================================================================
    # send() / send_stream() — ACP only
    # ======================================================================

    async def send(self, prompt: str) -> BridgeResponse:
        """Send prompt through the ACP warm session."""
        if self.state == BridgeState.DISCONNECTED:
            await self.start()

        if not self._acp_conn or not self._acp_session_id:
            raise RuntimeError("Codex ACP session not active. Call start() first.")

        # GAP-5: Inject system prompt into first ACP message
        effective_prompt = self._prepend_system_prompt(prompt)

        self._set_state(BridgeState.BUSY)
        t0 = time.time()
        with self._acp_buffer_lock:  # RC-3/4
            self._acp_events.clear()
            self._acp_text_buffer = ""
            self._recent_thinking_norm.clear()

        try:
            result = await asyncio.wait_for(
                self._acp_conn.prompt(
                    session_id=self._acp_session_id,
                    prompt=[text_block(effective_prompt)],
                ),
                timeout=self.timeout,
            )

            elapsed = int((time.time() - t0) * 1000)

            # Prefer accumulated streaming buffer, fallback to result, then thinking
            with self._acp_buffer_lock:  # RC-3/4
                content = self._acp_text_buffer or _extract_text_from_result(result)
                # Codex sends responses as thinking chunks — if text buffer is
                # empty, reconstruct content from thinking events
                if not content:
                    thinking_parts = [
                        e["thought"] for e in self._acp_events
                        if e.get("type") == "thinking" and e.get("thought")
                    ]
                    if thinking_parts:
                        content = "".join(thinking_parts).strip()
                events_copy = self._acp_events.copy()

            with self._history_lock:  # RC-9
                self.history.append(Message(role="user", content=prompt))
                self.history.append(Message(role="assistant", content=content))
            self._set_state(BridgeState.READY)

            response = BridgeResponse(
                content=content,
                raw_events=events_copy,
                duration_ms=elapsed,
                session_id=self._acp_session_id,
                success=True,
            )
            self._update_stats(response)
            return response

        except asyncio.TimeoutError:
            self._set_state(BridgeState.ERROR)
            response = BridgeResponse(
                content="",
                duration_ms=int((time.time() - t0) * 1000),
                success=False,
                error=f"Codex ACP timeout ({self.timeout}s)",
            )
            self._update_stats(response)
            return response
        except Exception as exc:
            logger.error(f"Codex ACP send failed: {exc}", exc_info=True)
            self._set_state(BridgeState.ERROR)
            response = BridgeResponse(
                content="",
                duration_ms=int((time.time() - t0) * 1000),
                success=False,
                error=str(exc),
            )
            self._update_stats(response)
            return response

    async def send_stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream response from ACP warm session."""
        if self.state == BridgeState.DISCONNECTED:
            await self.start()

        if not self._acp_conn or not self._acp_session_id:
            raise RuntimeError("Codex ACP session not active. Call start() first.")

        # GAP-5: Inject system prompt into first ACP message
        effective_prompt = self._prepend_system_prompt(prompt)

        self._set_state(BridgeState.BUSY)
        with self._acp_buffer_lock:  # RC-3/4
            self._acp_events.clear()
            self._acp_text_buffer = ""
            self._recent_thinking_norm.clear()

        # Bridge callback → async iterator via Queue
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        original_callback = self._on_output

        def _stream_callback(text: str) -> None:
            queue.put_nowait(text)
            if original_callback:
                original_callback(text)

        self._on_output = _stream_callback

        async def _run_prompt():
            try:
                await self._acp_conn.prompt(
                    session_id=self._acp_session_id,
                    prompt=[text_block(effective_prompt)],
                )
            finally:
                await queue.put(None)  # Signal completion

        task = asyncio.create_task(_run_prompt())

        try:
            full_text = ""
            while True:
                chunk = await asyncio.wait_for(queue.get(), timeout=self.timeout)
                if chunk is None:
                    break
                full_text += chunk
                yield chunk

            with self._history_lock:  # RC-9
                self.history.append(Message(role="user", content=prompt))
                self.history.append(Message(role="assistant", content=full_text))
            self._set_state(BridgeState.READY)
        except asyncio.TimeoutError:
            task.cancel()
            self._set_state(BridgeState.ERROR)
            raise
        finally:
            self._on_output = original_callback
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    # ======================================================================
    # Config — Zero Footprint (no files needed for Codex)
    # ======================================================================

    def _setup_config_files(self) -> None:
        """No config files needed for Codex ACP.

        Codex ACP receives all configuration through the ACP protocol:
        - MCP servers via new_session()
        - Auth via authenticate()
        - No settings.json or config files needed in project directory
        """
        pass  # Zero Footprint naturally satisfied

    # ======================================================================
    # BaseBridge abstract method stubs
    # (Not used — ACP handles everything, but required by ABC)
    # ======================================================================

    def _build_persistent_command(self) -> List[str]:
        raise NotImplementedError("Codex uses ACP, not raw subprocess")

    def _format_user_message(self, prompt: str) -> str:
        raise NotImplementedError("Codex uses ACP, not raw subprocess")

    def _build_oneshot_command(self, prompt: str) -> List[str]:
        raise NotImplementedError("Codex is ACP-only, no oneshot mode")

    def _is_turn_complete(self, event: Dict[str, Any]) -> bool:
        return event.get("type") == "result"

    def _parse_session_id(self, events: List[Dict[str, Any]]) -> Optional[str]:
        # Session ID comes from new_session(), not from events
        return self._acp_session_id

    def _parse_content(self, events: List[Dict[str, Any]]) -> str:
        parts = []
        for ev in events:
            if ev.get("type") == "acp_update" and "text" in ev:
                parts.append(ev["text"])
        return "".join(parts)

    def _parse_tool_calls(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        calls = []
        for ev in events:
            if ev.get("type") == "tool_call":
                calls.append({
                    "tool": ev.get("tool_name", ""),
                    "parameters": ev.get("parameters", {}),
                    "tool_id": ev.get("tool_id", ""),
                    "kind": ev.get("kind", ""),
                })
        return calls

    def _parse_usage(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        # Token usage may come from ACP notifications
        for ev in events:
            if ev.get("type") == "token_usage":
                return ev.get("usage", {})
        return None

    def _extract_text_delta(self, event: Dict[str, Any]) -> Optional[str]:
        if event.get("type") == "acp_update":
            return event.get("text")
        return None

    def _should_suppress_text_output(self, text: str) -> bool:
        """Suppress text chunks that duplicate recent thinking/reasoning content."""
        norm_text = _normalize_reasoning_text(text)
        if not norm_text:
            return False
        with self._acp_buffer_lock:
            recent = list(self._recent_thinking_norm)
        for thought in recent:
            if not thought:
                continue
            if norm_text == thought:
                return True
            if norm_text.startswith(thought) or thought.startswith(norm_text):
                return True
        return False


# ==========================================================================
# ACP Client implementation (handles permission requests from Codex)
# ==========================================================================

if _ACP_AVAILABLE:

    class _CodexACPClient(ACPClient):
        """
        ACP client that handles codex-acp's permission requests and
        session update notifications for the Avatar Engine.
        """

        def __init__(
            self,
            auto_approve: bool = True,
            on_update: Optional[Callable] = None,
        ):
            self._auto_approve = auto_approve
            self._on_update = on_update

        async def request_permission(
            self, options, session_id, tool_call, **kwargs
        ):
            """Handle tool permission requests from codex-acp.

            Codex ACP sends RequestPermission for exec, patch, MCP calls.
            Returns typed RequestPermissionResponse (SDK 0.8+).
            """
            if self._auto_approve:
                logger.debug(
                    f"Auto-approving tool call in session {session_id}"
                )
                if hasattr(options, "options") and options.options:
                    opt = options.options[0]
                    return RequestPermissionResponse(
                        outcome=AllowedOutcome(
                            option_id=opt.option_id, outcome="selected"
                        )
                    )
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(
                        option_id="approved", outcome="selected"
                    )
                )
            else:
                logger.warning(
                    f"Tool call denied (auto_approve=False): {tool_call}"
                )
                return RequestPermissionResponse(
                    outcome=DeniedOutcome(outcome="cancelled")
                )

        async def session_update(self, session_id, update, **kwargs):
            """Handle streaming session updates from codex-acp."""
            if self._on_update:
                self._on_update(session_id, update)

else:

    class _CodexACPClient:  # type: ignore[no-redef]
        """Placeholder when ACP SDK is not installed."""

        pass


# ==========================================================================
# Helpers for extracting content from ACP response objects
# ==========================================================================


def _extract_thinking_from_update(update: Any) -> Optional[str]:
    """Extract thinking content from a codex-acp AgentThoughtChunk."""
    try:
        # AgentThoughtChunk with content.text
        if hasattr(update, "thought") and update.thought:
            if hasattr(update.thought, "text"):
                return update.thought.text
            if isinstance(update.thought, str):
                return update.thought

        # Content block with type "thinking"
        if hasattr(update, "content"):
            content = update.content
            if hasattr(content, "type") and getattr(content, "type", "") == "thinking":
                if hasattr(content, "text"):
                    return content.text
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "type") and block.type == "thinking":
                        if hasattr(block, "text"):
                            return block.text

        # AgentThoughtChunk pattern
        type_name = type(update).__name__
        if "Thought" in type_name:
            if hasattr(update, "content"):
                content = update.content
                if hasattr(content, "text"):
                    return content.text
                if isinstance(content, str):
                    return content

        # Dict-style access
        if isinstance(update, dict):
            if "thought" in update:
                return update["thought"]
            if update.get("type") == "AgentThoughtChunk":
                return update.get("content", {}).get("text", "")

    except Exception as exc:
        logger.debug(f"Could not extract thinking from update: {exc}")
    return None


def _extract_text_from_update(update: Any) -> Optional[str]:
    """Extract text from a codex-acp AgentMessageChunk."""
    try:
        def _is_reasoning_block(block_type: Any) -> bool:
            if not block_type:
                return False
            bt = str(block_type).lower()
            return bt in {"thinking", "thought", "reasoning", "analysis"}

        # AgentMessageChunk.content.text
        if hasattr(update, "content"):
            content = update.content
            if hasattr(content, "text"):
                # Skip thinking blocks
                if hasattr(content, "type") and _is_reasoning_block(getattr(content, "type", "")):
                    return None
                return content.text
            if isinstance(content, list):
                parts = []
                for block in content:
                    if hasattr(block, "type") and _is_reasoning_block(getattr(block, "type", "")):
                        continue  # Skip thinking blocks
                    if isinstance(block, dict) and _is_reasoning_block(block.get("type")):
                        continue
                    if hasattr(block, "text"):
                        parts.append(block.text)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(str(block["text"]))
                return "".join(parts) if parts else None

        # Check for message chunk pattern by type name
        type_name = type(update).__name__
        if "Message" in type_name and "Thought" not in type_name:
            if hasattr(update, "content"):
                content = update.content
                if hasattr(content, "text"):
                    if hasattr(content, "type") and _is_reasoning_block(getattr(content, "type", "")):
                        return None
                    return content.text

        # Dict-style access
        if isinstance(update, dict):
            if update.get("type") == "AgentMessageChunk":
                content = update.get("content", {})
                if isinstance(content, dict):
                    if _is_reasoning_block(content.get("type")):
                        return None
                    if "text" in content:
                        return str(content.get("text") or "")
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if _is_reasoning_block(block.get("type")):
                                continue
                            if "text" in block:
                                parts.append(str(block["text"]))
                    return "".join(parts) if parts else None
            msg = update.get("agentMessage", {})
            content = msg.get("content", [])
            parts = []
            for block in content:
                if isinstance(block, dict) and _is_reasoning_block(block.get("type")):
                    continue
                if isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
            return "".join(parts) if parts else None

    except Exception as exc:
        logger.debug(f"Could not extract text from update: {exc}")
    return None


def _extract_tool_event_from_update(update: Any) -> Optional[Dict[str, Any]]:
    """Extract tool call events from codex-acp ToolCall/ToolCallUpdate."""
    try:
        type_name = type(update).__name__

        # ToolCall — tool invocation started
        if type_name == "ToolCall" or (isinstance(update, dict) and update.get("type") == "ToolCall"):
            tool_name = ""
            tool_id = ""
            kind = ""
            parameters = {}

            if hasattr(update, "name"):
                tool_name = update.name
            if hasattr(update, "id"):
                tool_id = update.id
            if hasattr(update, "kind"):
                kind = str(update.kind)
            if hasattr(update, "parameters"):
                parameters = update.parameters if isinstance(update.parameters, dict) else {}

            if isinstance(update, dict):
                tool_name = update.get("name", tool_name)
                tool_id = update.get("id", tool_id)
                kind = update.get("kind", kind)
                parameters = update.get("parameters", parameters)

            return {
                "type": "tool_call",
                "tool_name": tool_name,
                "tool_id": tool_id,
                "kind": kind,
                "parameters": parameters,
                "status": "started",
            }

        # ToolCallUpdate — tool result/progress
        if type_name == "ToolCallUpdate" or (isinstance(update, dict) and update.get("type") == "ToolCallUpdate"):
            tool_id = ""
            status = "completed"
            result = None
            error = None

            if hasattr(update, "id"):
                tool_id = update.id
            if hasattr(update, "status"):
                status = str(update.status)
            if hasattr(update, "output"):
                result = str(update.output) if update.output else None
            if hasattr(update, "error"):
                error = str(update.error) if update.error else None

            if isinstance(update, dict):
                tool_id = update.get("id", tool_id)
                status = update.get("status", status)
                result = update.get("output", result)
                error = update.get("error", error)

            # Map status
            if error or "fail" in status.lower():
                mapped_status = "failed"
            elif "complet" in status.lower():
                mapped_status = "completed"
            else:
                mapped_status = status

            return {
                "type": "tool_result",
                "tool_id": tool_id,
                "status": mapped_status,
                "result": result,
                "error": error,
            }

    except Exception as exc:
        logger.debug(f"Could not extract tool event from update: {exc}")
    return None


def _extract_text_from_result(result: Any) -> str:
    """Extract text content from an ACP PromptResponse."""
    try:
        if hasattr(result, "content"):
            content = result.content
            if hasattr(content, "text"):
                return content.text
            if isinstance(content, list):
                parts = []
                for block in content:
                    if hasattr(block, "text"):
                        parts.append(block.text)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                if parts:
                    return "".join(parts)
    except Exception as exc:
        logger.debug(f"Could not extract text from result: {exc}")
    return ""


def _text_from_content(content: Any) -> Optional[str]:
    """Extract text from a typed ACP content block (SDK 0.8+).

    Handles TextContentBlock and plain strings.
    """
    if content is None:
        return None
    if _ACP_AVAILABLE and isinstance(content, TextContentBlock):
        return content.text or None
    if isinstance(content, str):
        return content or None
    if hasattr(content, "text"):
        return content.text or None
    return None


def _normalize_reasoning_text(text: Any) -> str:
    """Normalize text for lightweight reasoning/output dedupe."""
    if text is None:
        return ""
    normalized = str(text).strip().lower()
    if not normalized:
        return ""
    normalized = normalized.replace("**", "")
    normalized = " ".join(normalized.split())
    return normalized
