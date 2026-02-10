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
    pip install agent-client-protocol>=0.8.0
"""

import asyncio
import base64
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .base import BaseBridge, BridgeResponse, BridgeState, Message
from ..config_sandbox import ConfigSandbox
from ..types import Attachment, SessionInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional ACP SDK import
# ---------------------------------------------------------------------------
_ACP_AVAILABLE = False
try:
    from acp import PROTOCOL_VERSION, connect_to_agent, text_block
    from acp.helpers import audio_block, embedded_blob_resource, image_block, resource_block, resource_link_block
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
        "agent-client-protocol not installed — ACP warm session unavailable, "
        "falling back to oneshot mode. Install with: "
        "pip install agent-client-protocol"
    )


from ._acp_session import ACPSessionMixin


INLINE_LIMIT_BYTES = 20 * 1024 * 1024  # ~20 MB — Gemini API rejects larger inline base64


def _build_prompt_blocks(text: str, attachments: Optional[List[Attachment]] = None) -> list:
    """Build ACP prompt content blocks from text + optional attachments.

    Returns [text_block(text)] when no attachments (zero overhead for 95% of calls).
    When attachments are present, prepends image/resource/audio blocks before the text.

    Files larger than INLINE_LIMIT_BYTES use resource_link_block with file:// URI
    so the CLI reads them from disk directly (no base64 overhead, no size limit).

    Requires ACP SDK — caller must only invoke this when _ACP_AVAILABLE is True.
    """
    if not _ACP_AVAILABLE:
        raise RuntimeError("ACP SDK required for multimodal prompt blocks")

    if not attachments:
        return [text_block(text)]

    blocks = []
    for att in attachments:
        if att.size and att.size > INLINE_LIMIT_BYTES:
            # Large file → file:// reference, CLI reads from disk
            blocks.append(resource_link_block(
                name=att.filename,
                uri=att.path.as_uri(),
                mime_type=att.mime_type,
                size=att.size,
            ))
        else:
            # Small file → inline base64
            b64 = base64.b64encode(att.path.read_bytes()).decode("ascii")
            if att.mime_type.startswith("image/"):
                blocks.append(image_block(b64, att.mime_type))
            elif att.mime_type.startswith("audio/"):
                blocks.append(audio_block(b64, att.mime_type))
            else:
                # PDF, video, and other binary formats → embedded blob resource
                blocks.append(resource_block(
                    embedded_blob_resource(f"file://{att.filename}", b64, mime_type=att.mime_type)
                ))
    blocks.append(text_block(text))
    return blocks


class GeminiBridge(ACPSessionMixin, BaseBridge):
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
        model: str = "",  # Empty = use Gemini CLI default
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
        resume_session_id: Optional[str] = None,
        continue_last: bool = False,
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
        self.approval_mode = approval_mode
        self.auth_method = auth_method
        self.context_messages = context_messages
        self.context_max_chars = context_max_chars
        self.acp_enabled = acp_enabled and _ACP_AVAILABLE
        self.generation_config = generation_config or {}
        self.resume_session_id = resume_session_id
        self.continue_last = continue_last

        # ACP state
        self._acp_conn = None
        self._acp_proc = None
        self._acp_session_id: Optional[str] = None
        self._acp_mode = False  # True = running in ACP warm session
        self._acp_restart_task: Optional[asyncio.Task] = None

        # Collected events from ACP session_update notifications
        self._acp_events: List[Dict[str, Any]] = []
        self._acp_text_buffer: str = ""
        self._acp_buffer_lock = threading.Lock()  # RC-3/4: sync callback vs main thread
        self._was_thinking = False  # Track thinking→text transition for is_complete

        # Provider capabilities
        self._provider_capabilities.thinking_supported = True
        self._provider_capabilities.thinking_structured = True
        self._provider_capabilities.cost_tracking = False
        self._provider_capabilities.budget_enforcement = False
        self._provider_capabilities.system_prompt_method = "injected"  # ACP: prepend; oneshot: env var
        self._provider_capabilities.streaming = True
        self._provider_capabilities.parallel_tools = True
        self._provider_capabilities.cancellable = False
        self._provider_capabilities.mcp_supported = True
        self._provider_capabilities.can_list_sessions = True  # filesystem fallback

        # Session capabilities — filesystem fallback always available
        self._session_capabilities.can_list = True

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def is_persistent(self) -> bool:
        return self._acp_mode

    # ======================================================================
    # Session management — ACP first, filesystem fallback
    # ======================================================================

    async def list_sessions(self) -> List[SessionInfo]:
        """List sessions — ACP first, filesystem fallback."""
        # Try ACP first (if connected and protocol supports it)
        if self._acp_conn and self._session_capabilities.can_list:
            result = await ACPSessionMixin.list_sessions(self)
            if result:
                return result

        # Filesystem fallback
        from ..sessions import get_session_store

        store = get_session_store("gemini")
        if store:
            return await store.list_sessions(self.working_dir)
        return []

    # ======================================================================
    # Filesystem resume — load history when ACP resume fails
    # ======================================================================

    async def _load_filesystem_history(self, session_id: str) -> None:
        """Load conversation history from filesystem after failed ACP resume."""
        from ..sessions._gemini import GeminiFileSessionStore

        store = GeminiFileSessionStore()
        messages = store.load_session_messages(session_id, self.working_dir)
        if messages:
            with self._history_lock:
                self.history.extend(messages)
            self._fs_resume_pending = True
            logger.info(
                f"Loaded {len(messages)} messages from filesystem for session {session_id}"
            )
        else:
            logger.warning(f"No messages found on filesystem for session {session_id}")

    def _prepend_system_prompt(self, prompt: str) -> str:
        """Prepend system prompt + resume context to the first ACP message."""
        result = super()._prepend_system_prompt(prompt)
        if getattr(self, '_fs_resume_pending', False):
            self._fs_resume_pending = False
            context = self._build_resume_context()
            if context:
                result = context + "\n\n" + result
        return result

    def _build_resume_context(self) -> str:
        """Build conversation history context for filesystem resume."""
        if not self.history:
            return ""
        lines = ["[Previous conversation:]"]
        recent = self.history[-self.context_messages:]
        for msg in recent:
            role = "User" if msg.role == "user" else "Assistant"
            text = msg.content
            if len(text) > self.context_max_chars:
                text = text[:self.context_max_chars] + "…"
            lines.append(f"{role}: {text}")
        lines.append("[Continue:]")
        return "\n".join(lines)

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
        await super().stop()  # BaseBridge.stop() handles sandbox cleanup

    # ======================================================================
    # ACP warm session management
    # ======================================================================

    async def _start_acp(self) -> None:
        """Spawn Gemini CLI in ACP mode via connect_to_agent (official SDK API).

        Uses asyncio.create_subprocess_exec + connect_to_agent instead of the
        deprecated spawn_agent_process. Passes ClientCapabilities so gemini-cli
        knows our client supports file I/O and terminal operations.
        """
        self._set_state(BridgeState.WARMING_UP, "Spawning Gemini CLI...")

        # Verify Gemini CLI is available
        gemini_bin = shutil.which(self.executable)
        if not gemini_bin:
            raise FileNotFoundError(
                f"Gemini CLI not found: '{self.executable}'. "
                "Install with: npm install -g @google/gemini-cli"
            )

        # Build command args
        cmd_args = [gemini_bin, "--experimental-acp"]
        if self.approval_mode == "yolo":
            cmd_args.append("--yolo")

        env = self._build_subprocess_env()

        logger.info(f"Spawning ACP: {' '.join(cmd_args[:6])}…")

        # Spawn gemini process with stdio pipes
        self._acp_proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
            cwd=self.working_dir,
            env=env,
        )

        # Build ACP client that handles permission requests and session updates
        client = _AvatarACPClient(
            auto_approve=(self.approval_mode == "yolo"),
            on_update=self._handle_acp_update,
        )

        # Connect to agent via official SDK API
        self._acp_conn = connect_to_agent(
            client, self._acp_proc.stdin, self._acp_proc.stdout
        )

        # Step 1: Initialize protocol with client capabilities
        self._set_state(BridgeState.WARMING_UP, "Initializing ACP protocol...")
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

        # Filesystem fallback always available — override ACP detection
        self._session_capabilities.can_list = True
        self._provider_capabilities.can_list_sessions = True

        # NOTE: Do NOT set can_load=True here — it would cause
        # _create_or_resume_acp_session to attempt ACP load_session,
        # which times out on Gemini CLI (-32601). Set it AFTER session creation.

        # Step 2: Create or resume session (auth handled by gemini-cli internally)
        self._set_state(BridgeState.WARMING_UP, "Creating session...")
        mcp_servers_acp = self._build_mcp_servers_acp()
        original_resume_id = self.resume_session_id
        await self._create_or_resume_acp_session(mcp_servers_acp)

        # Now enable filesystem fallback for resume (after session is created)
        self._session_capabilities.can_load = True
        self._provider_capabilities.can_load_session = True

        # If resume was requested but ACP created a new session instead,
        # load history from filesystem and inject as context
        if original_resume_id and self._acp_session_id != original_resume_id:
            await self._load_filesystem_history(original_resume_id)

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
                    "env": env_list,  # List[EnvVariable] - required by ACP SDK
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

    async def _restart_acp(self) -> None:
        """Restart ACP connection (cleanup + fresh start).

        Used after unrecoverable ACP errors (e.g. large file rejection)
        where the Gemini CLI session is left in a broken state.
        """
        try:
            await self._cleanup_acp()
            await self._start_acp()
            logger.info(f"ACP restarted successfully (session: {self._acp_session_id})")
        except Exception as exc:
            logger.error(f"ACP restart failed: {exc}")
            self._acp_mode = False  # Fall back to oneshot
            self._set_state(BridgeState.ERROR)

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
            if text:
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
            tool_event = {"type": "tool", "session_id": session_id, "raw": str(update)}
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
            thinking_event = {
                "type": "thinking",
                "session_id": session_id,
                "thought": thinking,
            }
            with self._acp_buffer_lock:
                self._acp_events.append(thinking_event)
            if self._on_event:
                self._on_event(thinking_event)

        text = None if thinking else _extract_text_from_update(update)
        if text:
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
    # send() / send_stream() — dispatches to ACP or oneshot
    # ======================================================================

    async def send(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> BridgeResponse:
        """Send prompt. Uses ACP warm session if active, otherwise oneshot."""
        if self.state == BridgeState.DISCONNECTED:
            await self.start()

        # Wait for background ACP restart (e.g. after large-file rejection)
        if self._acp_restart_task and not self._acp_restart_task.done():
            logger.debug("Waiting for ACP restart to complete before sending")
            await self._acp_restart_task

        if self._acp_mode:
            return await self._send_acp(prompt, attachments=attachments)
        else:
            return await super().send(prompt, attachments=attachments)

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

    async def _send_acp(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> BridgeResponse:
        """Send a prompt through the ACP warm session."""
        # GAP-5: Inject system prompt into first ACP message
        effective_prompt = self._prepend_system_prompt(prompt)

        self._set_state(BridgeState.BUSY)
        t0 = time.time()
        with self._acp_buffer_lock:  # RC-3/4
            self._acp_events.clear()
            self._acp_text_buffer = ""

        try:
            # Build content blocks: attachments (if any) + text
            prompt_blocks = _build_prompt_blocks(effective_prompt, attachments)

            # Dynamic timeout: add extra time for large attachments
            # (base64 encoding + transfer + API processing)
            effective_timeout = self.timeout
            if attachments:
                total_mb = sum(a.size for a in attachments) / (1024 * 1024)
                effective_timeout += int(total_mb * 3)  # +3s per MB
                if total_mb > 1:
                    logger.info(f"Large payload ({total_mb:.1f} MB), timeout extended to {effective_timeout}s")

            result = await asyncio.wait_for(
                self._acp_conn.prompt(
                    session_id=self._acp_session_id,
                    prompt=prompt_blocks,
                ),
                timeout=effective_timeout,
            )

            elapsed = int((time.time() - t0) * 1000)

            # Parse response content — prefer accumulated streaming buffer,
            # fallback to extracting from the final result object
            with self._acp_buffer_lock:  # RC-3/4
                content = self._acp_text_buffer or _extract_text_from_result(result)
                events_copy = self._acp_events.copy()

            # Extract generated images from response
            generated_images: List[Path] = []
            raw_images = _extract_images_from_result(result)
            if raw_images:
                import tempfile
                from uuid import uuid4
                upload_dir = os.environ.get("AVATAR_UPLOAD_DIR")
                img_dir = Path(upload_dir) if upload_dir else Path(tempfile.gettempdir()) / "avatar-engine" / "uploads"
                img_dir.mkdir(parents=True, exist_ok=True)
                for img_b64, img_mime in raw_images:
                    try:
                        ext = img_mime.split("/")[-1].split(";")[0] or "png"
                        fname = f"generated_{uuid4().hex[:8]}.{ext}"
                        fpath = img_dir / fname
                        fpath.write_bytes(base64.b64decode(img_b64))
                        generated_images.append(fpath)
                        logger.info(f"Saved generated image: {fname}")
                    except Exception as img_err:
                        logger.warning(f"Failed to save generated image: {img_err}")

            with self._history_lock:  # RC-9
                self.history.append(Message(role="user", content=prompt, attachments=attachments or []))
                self.history.append(Message(role="assistant", content=content))
            self._set_state(BridgeState.READY)

            response = BridgeResponse(
                content=content,
                raw_events=events_copy,
                duration_ms=elapsed,
                session_id=self._acp_session_id,
                success=True,
                generated_images=generated_images,
            )
            self._update_stats(response)
            return response

        except asyncio.TimeoutError:
            self._set_state(BridgeState.ERROR)
            response = BridgeResponse(
                content="",
                duration_ms=int((time.time() - t0) * 1000),
                success=False,
                error=f"ACP timeout ({self.timeout}s)",
            )
            self._update_stats(response)
            return response
        except Exception as exc:
            logger.error(f"ACP send failed: {exc}", exc_info=True)
            self._set_state(BridgeState.ERROR)

            # Large attachment + "Internal error" = API rejected the payload size
            if attachments and "internal error" in str(exc).lower():
                total_mb = sum(a.size for a in attachments) / (1024 * 1024)
                error_msg = (
                    f"File too large for inline upload ({total_mb:.0f} MB). "
                    f"Gemini supports up to ~20 MB inline. "
                    f"Try a smaller file or split the PDF."
                )
                logger.warning(error_msg)
                response = BridgeResponse(
                    content="",
                    duration_ms=int((time.time() - t0) * 1000),
                    success=False,
                    error=error_msg,
                )
                self._update_stats(response)
                # ACP session is corrupted after "Internal error" — restart
                # in background so next message works on a fresh session.
                logger.info("Restarting ACP after large-file rejection")
                self._acp_restart_task = asyncio.create_task(self._restart_acp())
                return response

            # Attempt fallback to oneshot for this single request
            if self.acp_enabled:
                logger.warning("ACP error — falling back to oneshot for this request")
                self._acp_mode = False
                return await super().send(prompt, attachments=attachments)

            response = BridgeResponse(
                content="",
                duration_ms=int((time.time() - t0) * 1000),
                success=False,
                error=str(exc),
            )
            self._update_stats(response)
            return response

    async def _stream_acp(self, prompt: str) -> AsyncIterator[str]:
        """Stream response from ACP warm session."""
        # GAP-5: Inject system prompt into first ACP message
        effective_prompt = self._prepend_system_prompt(prompt)

        self._set_state(BridgeState.BUSY)
        with self._acp_buffer_lock:  # RC-3/4
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

        prompt_error: Optional[Exception] = None

        async def _run_prompt():
            nonlocal prompt_error
            try:
                await self._acp_conn.prompt(
                    session_id=self._acp_session_id,
                    prompt=[text_block(effective_prompt)],
                )
            except Exception as exc:
                prompt_error = exc
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

            # Check if ACP prompt failed (error was swallowed by _run_prompt)
            if prompt_error is not None:
                logger.error(f"ACP stream failed: {prompt_error}", exc_info=prompt_error)
                self._set_state(BridgeState.ERROR)
                if self.acp_enabled and not full_text:
                    logger.warning("ACP error — falling back to oneshot for next request")
                    self._acp_mode = False
                raise prompt_error

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
    # Config files (shared between ACP and oneshot)
    # ======================================================================

    def _setup_config_files(self) -> None:
        """Write config to sandbox (temp dir), NOT to working_dir.

        Zero Footprint: uses env vars to point Gemini CLI to temp config.
        Host application's .gemini/settings.json and GEMINI.md are untouched.

        ACP mode uses two settings mechanisms:
          - ``customOverrides`` (array): generateContentConfig applied AFTER
            alias resolution — preserves the entire built-in alias chain.
          - ``customAliases``: model routing only (when non-default model).

        Runtime config methods (setSessionConfigOption, setSessionModel)
        are NOT implemented by gemini-cli.

        NEVER set ``model.name`` in ACP mode — it bypasses the entire alias
        chain and causes "Internal error" from the API.
        """
        self._sandbox = ConfigSandbox()

        settings: Dict[str, Any] = {}

        # model.name — only for oneshot mode.
        # ACP: NEVER set model.name (bypasses alias chain → "Internal error").
        if not self.acp_enabled and self.model:
            settings["model"] = {"name": self.model}

        # MCP servers in settings (oneshot only — ACP passes via protocol)
        if not self.acp_enabled and self.mcp_servers:
            mcp = {}
            for name, srv in self.mcp_servers.items():
                mcp[name] = {"command": srv["command"], "args": srv.get("args", [])}
                if "env" in srv:
                    mcp[name]["env"] = srv["env"]
            settings["mcpServers"] = mcp

        # Model configuration with thinking and generation parameters.
        #
        # ACP mode uses TWO mechanisms (runtime methods not implemented):
        #   - customAliases: model routing (only when non-default model)
        #   - customOverrides: generateContentConfig (applied AFTER alias
        #     resolution — does NOT replace built-in alias chain)
        #
        # Oneshot mode: model.name (above) handles model selection;
        #   customAliases provides generateContentConfig overrides.
        if self.model or self.generation_config:
            gen_cfg = self._build_generation_config()
            if gen_cfg:
                if self.acp_enabled:
                    model_configs: Dict[str, Any] = {}
                    actual_model = self.model or "gemini-3-pro-preview"

                    # Model routing: customAliases to override default terminal
                    # alias. Only needed for non-default models.
                    if self.model and self.model != "gemini-3-pro-preview":
                        extends_base = self._get_base_alias()
                        alias_entry: Dict[str, Any] = {
                            "modelConfig": {"model": actual_model}
                        }
                        if extends_base:
                            alias_entry["extends"] = extends_base
                        model_configs["customAliases"] = {
                            "gemini-3-pro-preview": alias_entry
                        }

                    # Config overrides: customOverrides applied AFTER alias
                    # resolution. This preserves the entire built-in alias chain
                    # (base → chat-base → chat-base-3 → gemini-3-pro-preview)
                    # and only overrides specific generateContentConfig fields.
                    model_configs["customOverrides"] = [
                        {
                            "match": {"model": actual_model},
                            "modelConfig": {
                                "generateContentConfig": gen_cfg,
                            },
                        }
                    ]

                    settings["modelConfigs"] = model_configs
                else:
                    # Oneshot: existing behavior (model.name handles selection)
                    settings["modelConfigs"] = {
                        "customAliases": {
                            self.model: {
                                "modelConfig": {
                                    "generateContentConfig": gen_cfg
                                }
                            }
                        }
                    }

        # Only write settings file if there's something to write
        if settings:
            self._gemini_settings_path = self._sandbox.write_gemini_settings(settings)
        else:
            self._gemini_settings_path = None

        # System prompt → temp file for GEMINI_SYSTEM_MD env var
        if self.system_prompt:
            self._system_prompt_path = self._sandbox.write_system_prompt(
                self.system_prompt
            )
        else:
            self._system_prompt_path = None

    def _get_base_alias(self) -> Optional[str]:
        """Determine the correct built-in base alias for the extends chain.

        Gemini CLI's built-in alias chain:
            base → chat-base → chat-base-3  (Gemini 3: thinkingLevel)
                              → chat-base-2.5 (Gemini 2.5: thinkingBudget)

        Image models have no built-in alias — they need explicit config.
        """
        model = self.model.lower() if self.model else ""
        if not model:
            return "chat-base-3"  # default gemini-cli model is gemini-3
        if "image" in model:
            return None  # image models need their own config, no extends
        if "gemini-3" in model or "gemini3" in model:
            return "chat-base-3"
        if "gemini-2.5" in model:
            return "chat-base-2.5"
        return "chat-base"  # generic fallback

    def _build_generation_config(self) -> Dict[str, Any]:
        """Build generateContentConfig dict from generation_config."""
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

        # Response modalities for image generation models
        if "response_modalities" in self.generation_config:
            val = self.generation_config["response_modalities"]
            if isinstance(val, str):
                val = [v.strip().upper() for v in val.split(",")]
            gen_cfg["responseModalities"] = val

        # Build thinkingConfig for Gemini 3 models (skip for image models —
        # they don't support thinking and the API returns "Internal error").
        is_image_model = self.model and "image" in self.model.lower()
        if not is_image_model:
            thinking_cfg: Dict[str, Any] = {}
            if "thinking_level" in self.generation_config:
                level = self.generation_config["thinking_level"].upper()
                thinking_cfg["thinkingLevel"] = level
            if "include_thoughts" in self.generation_config:
                thinking_cfg["includeThoughts"] = self.generation_config[
                    "include_thoughts"
                ]

            if thinking_cfg:
                gen_cfg["thinkingConfig"] = thinking_cfg

        return gen_cfg

    def _build_subprocess_env(self) -> Dict[str, str]:
        """Build subprocess environment with sandbox config paths.

        GEMINI_CLI_SYSTEM_SETTINGS_PATH has the highest priority in Gemini CLI's
        5-level settings hierarchy, ensuring avatar config overrides everything.
        These env vars are isolated to the subprocess — they don't affect the
        user's own Gemini CLI usage.
        """
        env = super()._build_subprocess_env()

        # System settings = highest priority (level 5 in Gemini CLI hierarchy)
        if hasattr(self, "_gemini_settings_path") and self._gemini_settings_path:
            env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(
                self._gemini_settings_path
            )

        # Custom system prompt (replaces Gemini CLI default)
        if hasattr(self, "_system_prompt_path") and self._system_prompt_path:
            env["GEMINI_SYSTEM_MD"] = str(self._system_prompt_path)

        return env

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

    def _format_user_message(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> str:
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
            self,
            options: list,
            session_id: str,
            tool_call: "ToolCall",
            **kwargs,
        ) -> "RequestPermissionResponse":
            """Handle tool permission requests from Gemini CLI."""
            if self._auto_approve:
                logger.debug(
                    f"Auto-approving tool call in session {session_id}"
                )
                # Pick allow_once/allow_always, fallback to first option
                for opt in options:
                    if getattr(opt, "kind", "") in {"allow_once", "allow_always"}:
                        return RequestPermissionResponse(
                            outcome=AllowedOutcome(
                                option_id=opt.option_id, outcome="selected"
                            )
                        )
                if options:
                    return RequestPermissionResponse(
                        outcome=AllowedOutcome(
                            option_id=options[0].option_id, outcome="selected"
                        )
                    )
                return RequestPermissionResponse(
                    outcome=DeniedOutcome(outcome="cancelled")
                )
            else:
                logger.warning(
                    f"Tool call denied (auto_approve=False): {tool_call}"
                )
                return RequestPermissionResponse(
                    outcome=DeniedOutcome(outcome="cancelled")
                )

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


def _extract_thinking_from_update(update: Any) -> Optional[str]:
    """Extract thinking content from an ACP session/update notification (Gemini 3)."""
    try:
        # Direct thinking attribute
        if hasattr(update, "thinking") and update.thinking:
            if hasattr(update.thinking, "text"):
                return update.thinking.text
            if isinstance(update.thinking, str):
                return update.thinking

        # Thinking in content blocks
        if hasattr(update, "content"):
            content = update.content
            if isinstance(content, list):
                for block in content:
                    # Check for thinking content block type
                    if hasattr(block, "type") and block.type == "thinking":
                        if hasattr(block, "text"):
                            return block.text
                    # Check for thinking attribute on block
                    if hasattr(block, "thinking"):
                        return block.thinking

        # ACP update with agent_message containing thinking
        if hasattr(update, "agent_message"):
            msg = update.agent_message
            if hasattr(msg, "thinking") and msg.thinking:
                return msg.thinking
            if hasattr(msg, "content") and msg.content:
                for block in msg.content:
                    if hasattr(block, "type") and getattr(block, "type", "") == "thinking":
                        if hasattr(block, "text"):
                            return block.text

        # Dict-style access
        if isinstance(update, dict):
            if "thinking" in update:
                return update["thinking"]
            msg = update.get("agentMessage", {})
            if "thinking" in msg:
                return msg["thinking"]
            for block in msg.get("content", []):
                if isinstance(block, dict) and block.get("type") == "thinking":
                    return block.get("text")

    except Exception as exc:
        logger.debug(f"Could not extract thinking from update: {exc}")
    return None


def _is_thinking_block(block: Any) -> bool:
    """Return True if block is a thinking/reasoning content block."""
    if hasattr(block, "type") and getattr(block, "type", None) == "thinking":
        return True
    if isinstance(block, dict) and block.get("type") == "thinking":
        return True
    # Only treat as thinking if .thinking has actual content (not None/False/"")
    if hasattr(block, "thinking") and block.thinking:
        return True
    return False


def _extract_text_from_update(update: Any) -> Optional[str]:
    """Extract text content from an ACP session/update notification.

    Skips thinking/reasoning blocks — those are handled by
    ``_extract_thinking_from_update`` and emitted as ThinkingEvents.
    """
    try:
        # Direct content block (e.g., update.content = TextContentBlock)
        if hasattr(update, "content"):
            content = update.content
            # Single TextContentBlock (not a list)
            if not isinstance(content, list) and hasattr(content, "text"):
                if not _is_thinking_block(content):
                    return content.text
                return None
            # List of content blocks — skip thinking blocks
            if isinstance(content, list):
                parts = []
                for block in content:
                    if _is_thinking_block(block):
                        continue
                    if hasattr(block, "text"):
                        parts.append(block.text)
                return "".join(parts) if parts else None

        # ACP update can contain agent_message with content blocks
        if hasattr(update, "agent_message"):
            msg = update.agent_message
            if hasattr(msg, "content") and msg.content:
                parts = []
                for block in msg.content:
                    if _is_thinking_block(block):
                        continue
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
                if isinstance(block, dict):
                    if block.get("type") == "thinking":
                        continue
                    if "text" in block:
                        parts.append(block["text"])
            return "".join(parts) if parts else None

    except Exception as exc:
        logger.debug(f"Could not extract text from update: {exc}")
    return None


def _extract_images_from_result(result: Any) -> List[tuple]:
    """Extract image content blocks from an ACP prompt result.

    Returns list of (base64_data, mime_type) tuples.
    """
    images = []
    try:
        if hasattr(result, "content") and isinstance(result.content, list):
            for block in result.content:
                # ImageContentBlock has .data (base64) and .mime_type
                if hasattr(block, "type") and getattr(block, "type", None) == "image":
                    data = getattr(block, "data", None)
                    mime = getattr(block, "mime_type", "image/png")
                    if data:
                        images.append((data, mime))
                # Also check for dict-based blocks
                elif isinstance(block, dict) and block.get("type") == "image":
                    data = block.get("data")
                    mime = block.get("mimeType", block.get("mime_type", "image/png"))
                    if data:
                        images.append((data, mime))
    except Exception as exc:
        logger.debug(f"Could not extract images from result: {exc}")
    return images


def _extract_text_from_result(result: Any) -> str:
    """Extract text content from an ACP prompt result (PromptResponse).

    Skips thinking/reasoning blocks.
    """
    try:
        # PromptResponse may have content blocks
        if hasattr(result, "content"):
            content = result.content
            # Single TextContentBlock
            if not isinstance(content, list) and hasattr(content, "text"):
                if not _is_thinking_block(content):
                    return content.text
                return ""
            # List of content blocks — skip thinking
            if isinstance(content, list):
                parts = []
                for block in content:
                    if _is_thinking_block(block):
                        continue
                    if hasattr(block, "text"):
                        parts.append(block.text)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                if parts:
                    return "".join(parts)

    except Exception as exc:
        logger.debug(f"Could not extract text from result: {exc}")
    return ""
