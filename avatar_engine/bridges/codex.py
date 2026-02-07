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
import logging
import shutil
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .base import BaseBridge, BridgeResponse, BridgeState, Message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional ACP SDK import
# ---------------------------------------------------------------------------
_ACP_AVAILABLE = False
try:
    from acp import spawn_agent_process, text_block
    from acp.interfaces import Client as ACPClient

    _ACP_AVAILABLE = True
except ImportError:
    logger.info(
        "agent-client-protocol not installed — Codex ACP unavailable. "
        "Install with: pip install agent-client-protocol"
    )


class CodexBridge(BaseBridge):
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

        # ACP state
        self._acp_conn = None
        self._acp_proc = None
        self._acp_ctx = None
        self._acp_session_id: Optional[str] = None

        # Collected events from ACP session_update notifications
        self._acp_events: List[Dict[str, Any]] = []
        self._acp_text_buffer: str = ""

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
        """Spawn codex-acp, authenticate, create session."""
        self._set_state(BridgeState.WARMING_UP)

        # Verify executable is available
        exe_bin = shutil.which(self.executable)
        if not exe_bin:
            raise FileNotFoundError(
                f"Executable not found: '{self.executable}'. "
                "Install npx (Node.js) or codex-acp binary."
            )

        # Build ACP client that handles permission requests
        client = _CodexACPClient(
            auto_approve=(self.approval_mode == "auto"),
            on_update=self._handle_acp_update,
        )

        # Build command: executable + executable_args
        cmd_args = [exe_bin] + self.executable_args
        env = self._build_subprocess_env()

        logger.info(f"Spawning ACP: {' '.join(cmd_args[:6])}")

        # spawn_agent_process is an async context manager
        self._acp_ctx = spawn_agent_process(
            client, *cmd_args, cwd=self.working_dir, env=env
        )
        self._acp_conn, self._acp_proc = await self._acp_ctx.__aenter__()

        # Step 1: Initialize protocol
        init_resp = await asyncio.wait_for(
            self._acp_conn.initialize(protocol_version=1),
            timeout=self.timeout,
        )
        logger.debug(f"ACP initialized: {init_resp}")

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

        # Step 3: Create a new session
        mcp_servers_acp = self._build_mcp_servers_acp()

        session_resp = await asyncio.wait_for(
            self._acp_conn.new_session(
                cwd=self.working_dir,
                mcp_servers=mcp_servers_acp,
            ),
            timeout=self.timeout,
        )
        self._acp_session_id = session_resp.session_id
        self.session_id = self._acp_session_id
        self._set_state(BridgeState.READY)

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
        """Clean up ACP context manager and process."""
        if self._acp_ctx:
            try:
                await self._acp_ctx.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug(f"ACP cleanup: {exc}")
            self._acp_ctx = None
        self._acp_conn = None
        self._acp_proc = None
        self._acp_session_id = None

    def _handle_acp_update(self, session_id: str, update: Any) -> None:
        """Callback for ACP session/update notifications (streaming text + thinking)."""
        event = {"type": "acp_update", "session_id": session_id, "raw": str(update)}

        # Extract thinking content
        thinking = _extract_thinking_from_update(update)
        if thinking:
            thinking_event = {
                "type": "thinking",
                "session_id": session_id,
                "thought": thinking,
            }
            self._acp_events.append(thinking_event)
            if self._on_event:
                self._on_event(thinking_event)

        # Extract tool call events
        tool_event = _extract_tool_event_from_update(update)
        if tool_event:
            tool_event["session_id"] = session_id
            self._acp_events.append(tool_event)
            if self._on_event:
                self._on_event(tool_event)

        # Extract text content
        text = _extract_text_from_update(update)
        if text:
            event["text"] = text
            self._acp_text_buffer += text
            if self._on_output:
                self._on_output(text)

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

        self._set_state(BridgeState.BUSY)
        t0 = time.time()
        self._acp_events.clear()
        self._acp_text_buffer = ""

        try:
            result = await asyncio.wait_for(
                self._acp_conn.prompt(
                    session_id=self._acp_session_id,
                    prompt=[text_block(prompt)],
                ),
                timeout=self.timeout,
            )

            elapsed = int((time.time() - t0) * 1000)

            # Prefer accumulated streaming buffer, fallback to result
            content = self._acp_text_buffer or _extract_text_from_result(result)

            self.history.append(Message(role="user", content=prompt))
            self.history.append(Message(role="assistant", content=content))
            self._set_state(BridgeState.READY)

            response = BridgeResponse(
                content=content,
                raw_events=self._acp_events.copy(),
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

        self._set_state(BridgeState.BUSY)
        self._acp_events.clear()
        self._acp_text_buffer = ""

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
                    prompt=[text_block(prompt)],
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
            Possible decisions: Approved, ApprovedForSession, Abort.
            """
            if self._auto_approve:
                logger.debug(
                    f"Auto-approving tool call in session {session_id}"
                )
                if hasattr(options, "options") and options.options:
                    first_option = options.options[0]
                    return {"outcome": first_option}
                return {"outcome": {"outcome": "approved"}}
            else:
                logger.warning(
                    f"Tool call denied (auto_approve=False): {tool_call}"
                )
                return {"outcome": {"outcome": "cancelled"}}

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
        # AgentMessageChunk.content.text
        if hasattr(update, "content"):
            content = update.content
            if hasattr(content, "text"):
                # Skip thinking blocks
                if hasattr(content, "type") and getattr(content, "type", "") == "thinking":
                    return None
                return content.text
            if isinstance(content, list):
                parts = []
                for block in content:
                    if hasattr(block, "type") and block.type == "thinking":
                        continue  # Skip thinking blocks
                    if hasattr(block, "text"):
                        parts.append(block.text)
                return "".join(parts) if parts else None

        # Check for message chunk pattern by type name
        type_name = type(update).__name__
        if "Message" in type_name and "Thought" not in type_name:
            if hasattr(update, "content"):
                content = update.content
                if hasattr(content, "text"):
                    return content.text

        # Dict-style access
        if isinstance(update, dict):
            if update.get("type") == "AgentMessageChunk":
                return update.get("content", {}).get("text", "")
            msg = update.get("agentMessage", {})
            content = msg.get("content", [])
            parts = []
            for block in content:
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
