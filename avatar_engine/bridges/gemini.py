"""
Gemini CLI bridge — ACP warm session with OAuth + oneshot fallback.

Primary mode: ACP (Agent Client Protocol) via ``agent-client-protocol`` SDK.
    gemini --experimental-acp --yolo
    → initialize → authenticate(oauth-personal) → new_session → prompt → prompt …
    = ONE process, multiple prompts = TRUE warm session

Fallback mode: Oneshot headless JSON (if ACP fails or is unavailable).
    gemini -p "..." --output-format stream-json --yolo
    = NEW process per prompt = cold start every call

OAuth authentication:
    ACP uses ``authenticate(methodId="oauth-personal")`` which re-uses cached
    Google credentials from ``~/.gemini/google_accounts.json``.
    User must have run ``gemini`` interactively at least once to cache creds.
    Bug #7549 (cached creds not used in ACP) was fixed in PR #9410 (Dec 2025).

Requirements:
    pip install agent-client-protocol>=0.6.0
"""

import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
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
        "agent-client-protocol not installed — ACP warm session unavailable, "
        "falling back to oneshot mode. Install with: "
        "pip install agent-client-protocol"
    )


class GeminiBridge(BaseBridge):
    """
    Gemini CLI bridge with hybrid ACP warm session / oneshot fallback.

    Lifecycle::

        bridge = GeminiBridge(...)
        await bridge.start()     # Tries ACP warm session first
                                 # Falls back to oneshot if ACP fails
        resp = await bridge.send("Ahoj!")   # Instant in ACP mode
        resp = await bridge.send("Dál?")    # Still instant (same process)
        await bridge.stop()
    """

    def __init__(
        self,
        executable: str = "gemini",
        model: str = "gemini-2.5-pro",
        working_dir: str = "",
        timeout: int = 120,
        system_prompt: str = "",
        approval_mode: str = "yolo",
        auth_method: str = "oauth-personal",
        context_messages: int = 20,
        context_max_chars: int = 500,
        acp_enabled: bool = True,
        generation_config: Optional[Dict[str, Any]] = None,
        env: Optional[Dict[str, str]] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            approval_mode: "yolo" auto-approves all tool calls.
            auth_method: ACP auth method ("oauth-personal", "gemini-api-key", "vertex-ai").
            context_messages: Max history messages for oneshot context injection.
            context_max_chars: Max chars per message in oneshot context.
            acp_enabled: Whether to attempt ACP warm session. If False, oneshot only.
            generation_config: Model generation parameters (temperature, thinking_level, etc.).
                Supported keys:
                - temperature: float (0.0-1.0, default 1.0 for Gemini 3)
                - thinking_level: str ("minimal", "low", "medium", "high")
                - include_thoughts: bool (show thinking in output)
                - max_output_tokens: int (max response length)
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
        self.approval_mode = approval_mode
        self.auth_method = auth_method
        self.context_messages = context_messages
        self.context_max_chars = context_max_chars
        self.acp_enabled = acp_enabled and _ACP_AVAILABLE
        self.generation_config = generation_config or {}

        # ACP state
        self._acp_conn = None
        self._acp_proc = None
        self._acp_ctx = None
        self._acp_session_id: Optional[str] = None
        self._acp_mode = False  # True = running in ACP warm session

        # Collected events from ACP session_update notifications
        self._acp_events: List[Dict[str, Any]] = []
        self._acp_text_buffer: str = ""

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def is_persistent(self) -> bool:
        return self._acp_mode

    # ======================================================================
    # Lifecycle — ACP with fallback to oneshot
    # ======================================================================

    async def start(self) -> None:
        """
        Initialize bridge. Attempts ACP warm session first, falls back to oneshot.
        """
        logger.info(f"Starting Gemini bridge (ACP enabled: {self.acp_enabled})")
        self._setup_config_files()

        if self.acp_enabled:
            try:
                await self._start_acp()
                self._acp_mode = True
                logger.info(
                    f"ACP warm session active. Session: {self._acp_session_id}, "
                    f"Auth: {self.auth_method}"
                )
                return
            except Exception as exc:
                logger.warning(
                    f"ACP warm session failed ({exc}), falling back to oneshot mode"
                )
                self._acp_mode = False
                await self._cleanup_acp()

        # Fallback: oneshot mode
        self._acp_mode = False
        self._set_state(BridgeState.READY)
        logger.info("Gemini bridge ready (oneshot mode)")

    async def stop(self) -> None:
        """Shutdown bridge — clean up ACP or oneshot state."""
        if self._acp_mode:
            await self._cleanup_acp()
            self._acp_mode = False
        await super().stop()

    # ======================================================================
    # ACP warm session management
    # ======================================================================

    async def _start_acp(self) -> None:
        """Spawn Gemini CLI in ACP mode, authenticate with OAuth, create session."""
        self._set_state(BridgeState.WARMING_UP)

        # Verify Gemini CLI is available
        gemini_bin = shutil.which(self.executable)
        if not gemini_bin:
            raise FileNotFoundError(
                f"Gemini CLI not found: '{self.executable}'. "
                "Install with: npm install -g @google/gemini-cli"
            )

        # Build ACP client that handles permission requests
        client = _AvatarACPClient(
            auto_approve=(self.approval_mode == "yolo"),
            on_update=self._handle_acp_update,
        )

        # Build command args
        cmd_args = [gemini_bin, "--experimental-acp"]
        if self.approval_mode == "yolo":
            cmd_args.append("--yolo")
        if self.model:
            cmd_args.extend(["--model", self.model])

        env = {**os.environ, **self.env}

        logger.info(f"Spawning ACP: {' '.join(cmd_args[:6])}…")

        # spawn_agent_process is an async context manager — we enter it
        # manually and store the context so we can exit it later in stop()
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

        # Step 2: Authenticate with OAuth (Google Pro account)
        # Note: Some Gemini CLI versions auto-detect cached credentials without
        # explicit authenticate() call. PR #9410 fixed credential caching.
        auth_success = False
        try:
            auth_resp = await asyncio.wait_for(
                self._acp_conn.authenticate(method_id=self.auth_method),
                timeout=self.timeout,
            )
            auth_success = True
            logger.info(f"ACP authenticated via: {self.auth_method}")
        except asyncio.TimeoutError:
            # Timeout is a real problem - don't silently continue
            logger.error(f"ACP authentication timed out after {self.timeout}s")
            raise RuntimeError(
                f"ACP authentication timed out. Ensure you have valid credentials "
                f"cached (run 'gemini' interactively first) or check your network."
            )
        except Exception as exc:
            # Other errors might be OK (e.g., method not supported, auto-detect)
            exc_str = str(exc).lower()
            if "not supported" in exc_str or "not implemented" in exc_str:
                logger.info(f"ACP authenticate not required (auto-detect mode)")
            else:
                logger.warning(
                    f"ACP authenticate issue: {exc} — continuing with cached creds. "
                    f"If session fails, run 'gemini' interactively to refresh OAuth."
                )

        # Step 3: Create a new session
        mcp_servers_acp = []
        if self.mcp_servers:
            for name, srv in self.mcp_servers.items():
                # Convert env dict to ACP's EnvVariable list format
                env_dict = srv.get("env", {})
                env_list = [{"name": k, "value": v} for k, v in env_dict.items()]
                entry = {
                    "name": name,
                    "command": srv["command"],
                    "args": srv.get("args", []),
                    "env": env_list,  # List[EnvVariable] - required by ACP SDK
                }
                mcp_servers_acp.append(entry)

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
        """Callback for ACP session/update notifications (streaming text)."""
        event = {"type": "acp_update", "session_id": session_id, "raw": str(update)}

        # Extract text content from update
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
    # send() / send_stream() — dispatches to ACP or oneshot
    # ======================================================================

    async def send(self, prompt: str) -> BridgeResponse:
        """Send prompt. Uses ACP warm session if active, otherwise oneshot."""
        if self.state == BridgeState.DISCONNECTED:
            await self.start()

        if self._acp_mode:
            return await self._send_acp(prompt)
        else:
            return await super().send(prompt)

    async def send_stream(self, prompt: str) -> AsyncIterator[str]:
        """Send prompt with streaming. ACP or oneshot."""
        if self.state == BridgeState.DISCONNECTED:
            await self.start()

        if self._acp_mode:
            async for chunk in self._stream_acp(prompt):
                yield chunk
        else:
            async for chunk in super().send_stream(prompt):
                yield chunk

    # ======================================================================
    # ACP send/stream implementation
    # ======================================================================

    async def _send_acp(self, prompt: str) -> BridgeResponse:
        """Send a prompt through the ACP warm session."""
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

            # Parse response content — prefer accumulated streaming buffer,
            # fallback to extracting from the final result object
            content = self._acp_text_buffer or _extract_text_from_result(result)

            self.history.append(Message(role="user", content=prompt))
            self.history.append(Message(role="assistant", content=content))
            self._set_state(BridgeState.READY)

            return BridgeResponse(
                content=content,
                raw_events=self._acp_events.copy(),
                duration_ms=elapsed,
                session_id=self._acp_session_id,
                success=True,
            )

        except asyncio.TimeoutError:
            self._set_state(BridgeState.ERROR)
            return BridgeResponse(
                content="",
                duration_ms=int((time.time() - t0) * 1000),
                success=False,
                error=f"ACP timeout ({self.timeout}s)",
            )
        except Exception as exc:
            logger.error(f"ACP send failed: {exc}", exc_info=True)
            self._set_state(BridgeState.ERROR)

            # Attempt fallback to oneshot for this single request
            if self.acp_enabled:
                logger.warning("ACP error — falling back to oneshot for this request")
                self._acp_mode = False
                return await super().send(prompt)

            return BridgeResponse(
                content="",
                duration_ms=int((time.time() - t0) * 1000),
                success=False,
                error=str(exc),
            )

    async def _stream_acp(self, prompt: str) -> AsyncIterator[str]:
        """Stream response from ACP warm session."""
        self._set_state(BridgeState.BUSY)
        self._acp_events.clear()
        self._acp_text_buffer = ""

        # ACP SDK streams via the session_update callback set on the client.
        # The prompt() call blocks until the model finishes its turn, but text
        # chunks arrive asynchronously through _handle_acp_update.
        # We use an asyncio.Queue to bridge callback → async iterator.
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
    # Config files (shared between ACP and oneshot)
    # ======================================================================

    def _setup_config_files(self) -> None:
        """Write .gemini/settings.json and GEMINI.md."""
        gemini_dir = Path(self.working_dir) / ".gemini"
        gemini_dir.mkdir(parents=True, exist_ok=True)

        settings: Dict[str, Any] = {}

        # Model name (required for proper model selection)
        if self.model:
            settings["model"] = {"name": self.model}

        # Enable preview features (required for Gemini 3 models)
        settings["previewFeatures"] = True

        # MCP servers
        if self.mcp_servers:
            mcp = {}
            for name, srv in self.mcp_servers.items():
                mcp[name] = {"command": srv["command"], "args": srv.get("args", [])}
                if "env" in srv:
                    mcp[name]["env"] = srv["env"]
            settings["mcpServers"] = mcp

        # Model configuration with thinking and generation parameters
        if self.model or self.generation_config:
            # Build generateContentConfig from generation_config
            gen_cfg: Dict[str, Any] = {}

            # Temperature: default 1.0 for Gemini 3 (docs recommend not lowering)
            gen_cfg["temperature"] = self.generation_config.get("temperature", 1.0)

            # Sampling parameters
            if "top_p" in self.generation_config:
                gen_cfg["topP"] = self.generation_config["top_p"]
            if "top_k" in self.generation_config:
                gen_cfg["topK"] = self.generation_config["top_k"]

            if "max_output_tokens" in self.generation_config:
                gen_cfg["maxOutputTokens"] = self.generation_config["max_output_tokens"]

            # Build thinkingConfig for Gemini 3 models
            thinking_cfg: Dict[str, Any] = {}
            if "thinking_level" in self.generation_config:
                # Map config values to API values (uppercase)
                level = self.generation_config["thinking_level"].upper()
                thinking_cfg["thinkingLevel"] = level
            if "include_thoughts" in self.generation_config:
                thinking_cfg["includeThoughts"] = self.generation_config["include_thoughts"]

            if thinking_cfg:
                gen_cfg["thinkingConfig"] = thinking_cfg

            # Add modelConfigs with customAliases
            if gen_cfg:
                settings["modelConfigs"] = {
                    "customAliases": {
                        self.model: {
                            "modelConfig": {
                                "generateContentConfig": gen_cfg
                            }
                        }
                    }
                }

        (gemini_dir / "settings.json").write_text(
            json.dumps(settings, indent=2, ensure_ascii=False)
        )

        if self.system_prompt:
            (Path(self.working_dir) / "GEMINI.md").write_text(
                self.system_prompt, encoding="utf-8"
            )

    # ======================================================================
    # Oneshot fallback (BaseBridge abstract implementations)
    # ======================================================================

    def _build_oneshot_command(self, prompt: str) -> List[str]:
        """Build CLI command for oneshot headless JSON mode."""
        cmd = [self.executable]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.approval_mode == "yolo":
            cmd.append("--yolo")
        cmd.extend(["--output-format", "stream-json"])
        effective = self._build_effective_prompt(prompt)
        cmd.extend(["-p", effective])
        return cmd

    def _build_effective_prompt(self, prompt: str) -> str:
        """Prepend conversation history to the prompt for context continuity."""
        if not self.history:
            return prompt

        lines = ["[Previous conversation:]"]
        recent = self.history[-self.context_messages :]
        for msg in recent:
            role = "User" if msg.role == "user" else "Assistant"
            text = msg.content
            if len(text) > self.context_max_chars:
                text = text[: self.context_max_chars] + "…"
            lines.append(f"{role}: {text}")
        lines.append("[Continue:]")
        lines.append(f"User: {prompt}")
        return "\n".join(lines)

    # Persistent mode stubs — ACP handles this differently
    def _build_persistent_command(self) -> List[str]:
        raise NotImplementedError("Use ACP mode for persistent Gemini sessions")

    def _format_user_message(self, prompt: str) -> str:
        raise NotImplementedError("Use ACP mode for persistent Gemini sessions")

    # ======================================================================
    # Event parsing (used by oneshot fallback)
    # ======================================================================

    def _is_turn_complete(self, event: Dict[str, Any]) -> bool:
        return event.get("type") == "result"

    def _parse_session_id(self, events: List[Dict[str, Any]]) -> Optional[str]:
        for ev in events:
            if ev.get("type") == "init" and "session_id" in ev:
                return ev["session_id"]
        return None

    def _parse_content(self, events: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for ev in events:
            if ev.get("type") == "message" and ev.get("role") == "assistant":
                text = ev.get("content", "")
                if text:
                    parts.append(text)
        if not parts:
            for ev in events:
                if ev.get("type") == "result" and "response" in ev:
                    return ev["response"]
        return "".join(parts)

    def _parse_tool_calls(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        calls = []
        for ev in events:
            if ev.get("type") == "tool_use":
                calls.append(
                    {
                        "tool": ev.get("tool_name", ""),
                        "parameters": ev.get("parameters", {}),
                        "tool_id": ev.get("tool_id", ""),
                    }
                )
        return calls

    def _parse_usage(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for ev in events:
            if ev.get("type") == "result" and "stats" in ev:
                return ev["stats"]
        return None

    def _extract_text_delta(self, event: Dict[str, Any]) -> Optional[str]:
        if event.get("type") == "message" and event.get("role") == "assistant":
            return event.get("content", "") or None
        return None


# ==========================================================================
# ACP Client implementation (handles permission requests from Gemini)
# ==========================================================================

if _ACP_AVAILABLE:

    class _AvatarACPClient(ACPClient):
        """
        ACP client that handles Gemini CLI's permission requests and
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
            """Handle tool permission requests from Gemini CLI."""
            if self._auto_approve:
                logger.debug(
                    f"Auto-approving tool call in session {session_id}"
                )
                # Return the first available option (typically "approve")
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
            """Handle streaming session updates from Gemini CLI."""
            if self._on_update:
                self._on_update(session_id, update)

else:

    class _AvatarACPClient:  # type: ignore[no-redef]
        """Placeholder when ACP SDK is not installed."""

        pass


# ==========================================================================
# Helpers for extracting text from ACP response objects
# ==========================================================================


def _extract_text_from_update(update: Any) -> Optional[str]:
    """Extract text content from an ACP session/update notification."""
    try:
        # Direct content block (e.g., update.content = TextContentBlock)
        if hasattr(update, "content"):
            content = update.content
            # Single TextContentBlock
            if hasattr(content, "text"):
                return content.text
            # List of content blocks
            if isinstance(content, list):
                parts = []
                for block in content:
                    if hasattr(block, "text"):
                        parts.append(block.text)
                return "".join(parts) if parts else None

        # ACP update can contain agent_message with content blocks
        if hasattr(update, "agent_message"):
            msg = update.agent_message
            if hasattr(msg, "content") and msg.content:
                parts = []
                for block in msg.content:
                    if hasattr(block, "text"):
                        parts.append(block.text)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                return "".join(parts) if parts else None

        # Fallback: try dict-style access
        if isinstance(update, dict):
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


def _extract_text_from_result(result: Any) -> str:
    """Extract text content from an ACP prompt result (PromptResponse)."""
    try:
        # PromptResponse may have content blocks
        if hasattr(result, "content"):
            content = result.content
            # Single TextContentBlock
            if hasattr(content, "text"):
                return content.text
            # List of content blocks
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
