"""
Claude Code bridge — PERSISTENT mode (true warm session).

Architecture:
    start() spawns:
        claude -p --input-format stream-json --output-format stream-json
    The process stays alive. Each send() writes a JSONL user message to stdin
    and reads JSONL response events from stdout until the result event.

    ┌─────────────┐     stdin: JSONL user messages      ┌─────────────┐
    │ Python App  │ ──────────────────────────────────→  │ claude -p   │
    │             │ ←──────────────────────────────────  │ (running)   │
    └─────────────┘     stdout: JSONL response events    └─────────────┘
                                                          ↕ MCP servers

No cold start after start(). Session and conversation context are maintained
by the single running process.

Stream-JSON event types:
    {"type":"system","subtype":"init","session_id":"...","tools":[...]}
    {"type":"user","message":{"role":"user","content":[...]}}
    {"type":"assistant","message":{"role":"assistant","content":[...]}}
    {"type":"result","subtype":"success","session_id":"...","result":"..."}
"""

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from ..config_sandbox import ConfigSandbox
from ..types import Attachment, SessionInfo
from .base import BaseBridge, BridgeState

logger = logging.getLogger(__name__)


class ClaudeBridge(BaseBridge):
    """
    Claude Code bridge using persistent --input-format stream-json.

    True warm session: process starts once, stays alive for all messages.
    Falls back to oneshot mode if persistent fails.
    """

    def __init__(
        self,
        executable: str = "claude",
        model: str = "claude-sonnet-4-5",
        working_dir: str = "",
        timeout: int = 600,
        system_prompt: str = "",
        allowed_tools: list[str] | None = None,
        permission_mode: str = "acceptEdits",
        strict_mcp_config: bool = False,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
        json_schema: dict[str, Any] | None = None,
        continue_session: bool = False,
        resume_session_id: str | None = None,
        fallback_model: str | None = None,
        debug: bool = False,
        env: dict[str, str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ):
        super().__init__(
            executable=executable, model=model, working_dir=working_dir,
            timeout=timeout, system_prompt=system_prompt, env=env,
            mcp_servers=mcp_servers, debug=debug,
        )
        self.allowed_tools = allowed_tools or []
        self.permission_mode = permission_mode
        self.strict_mcp_config = strict_mcp_config
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.json_schema = json_schema
        self.continue_session = continue_session
        self.resume_session_id = resume_session_id
        self.fallback_model = fallback_model

        # Track whether we're in persistent mode (can fall back to oneshot)
        self._persistent_mode = True

        # Session capabilities — Claude supports resume and continue via CLI flags
        self._session_capabilities.can_list = True  # filesystem fallback
        self._session_capabilities.can_load = True
        self._session_capabilities.can_continue_last = True

        # Budget tracking
        self._max_budget_usd = max_budget_usd

        # Provider capabilities
        self._provider_capabilities.thinking_supported = False  # Claude CLI doesn't export thinking
        self._provider_capabilities.thinking_structured = False
        self._provider_capabilities.cost_tracking = True
        self._provider_capabilities.budget_enforcement = True
        self._provider_capabilities.system_prompt_method = "native"  # --append-system-prompt
        self._provider_capabilities.streaming = True
        self._provider_capabilities.parallel_tools = True
        self._provider_capabilities.cancellable = False
        self._provider_capabilities.mcp_supported = True
        self._provider_capabilities.can_list_sessions = True  # filesystem fallback
        self._provider_capabilities.can_load_session = True
        self._provider_capabilities.can_continue_last = True
        self._total_cost_usd = 0.0

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def is_persistent(self) -> bool:
        return self._persistent_mode

    # === Session management ===============================================

    async def resume_session(self, session_id: str) -> bool:
        """Resume a Claude session by restarting with --resume <id>."""
        await self.stop()
        self.resume_session_id = session_id
        self.continue_session = False
        await self.start()
        return True

    async def list_sessions(self) -> list[SessionInfo]:
        """List sessions from Claude Code's filesystem store."""
        from ..sessions import get_session_store

        store = get_session_store("claude")
        if store:
            return await store.list_sessions(self.working_dir)
        return []

    # === Start override (no warm-up wait for Claude stream-json) =========

    async def start(self) -> None:
        """
        Start Claude bridge.

        Attempts persistent mode first. Unlike Gemini ACP, Claude with
        --input-format stream-json doesn't send init events until the first
        user message. So we just spawn the process and mark it ready immediately.

        Falls back to oneshot mode if persistent fails.
        """
        logger.info(f"Starting {self.provider_name} bridge (persistent mode)")
        self._setup_config_files()
        self._persistent_mode = True

        try:
            self._set_state(BridgeState.WARMING_UP, "Spawning Claude CLI...")
            cmd = self._build_persistent_command()
            env = {**os.environ, **self.env}

            logger.info(f"Spawning: {' '.join(cmd[:15])}…")
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env=env,
            )

            # Quick check: did the process die immediately?
            self._set_state(BridgeState.WARMING_UP, "Checking process health...")
            await asyncio.sleep(0.1)
            if self._proc.returncode is not None:
                stderr = await self._proc.stderr.read()
                raise RuntimeError(
                    f"Claude process exited immediately (code {self._proc.returncode}): "
                    f"{stderr.decode(errors='replace')[:500]}"
                )

            # Start stderr monitoring (prevents stderr buffer from filling up
            # and blocking the subprocess — same as base._start_persistent)
            self._stderr_task = asyncio.create_task(self._monitor_stderr())

            # Claude stream-json: no init event until first message
            self._set_state(BridgeState.READY)
            logger.info(f"Claude bridge ready (persistent). PID: {self._proc.pid}")

        except Exception as exc:
            logger.warning(f"Persistent mode failed ({exc}), falling back to oneshot")
            self._persistent_mode = False
            self._proc = None
            self._set_state(BridgeState.READY)
            logger.info("Claude bridge ready (oneshot mode)")

    # === Config =========================================================

    def _setup_config_files(self) -> None:
        """Write config to sandbox (temp dir), NOT to working_dir.

        Zero Footprint: uses CLI flags to point Claude Code to temp config.
        Host application's .claude/settings.json and CLAUDE.md are untouched.
        """
        self._sandbox = ConfigSandbox()

        # Settings → temp file for --settings flag
        settings: dict[str, Any] = {}
        if self.allowed_tools:
            settings["permissions"] = {"allow": self.allowed_tools}
        self._claude_settings_path = self._sandbox.write_claude_settings(settings)

        # MCP servers → temp file for --mcp-config flag
        if self.mcp_servers:
            self._mcp_config_path = self._sandbox.write_mcp_config(self.mcp_servers)
        else:
            self._mcp_config_path = None

        # JSON schema → temp file for --json-schema flag
        if self.json_schema:
            self._schema_path = self._sandbox.write_json_schema(self.json_schema)
        else:
            self._schema_path = None

    # === Persistent command ==============================================

    def _build_persistent_command(self) -> list[str]:
        """
        Build the persistent subprocess command.

        Zero Footprint: all config via CLI flags pointing to sandbox temp files.
        No files written to working_dir.

        Key flags:
            -p                          Non-interactive (print) mode
            --input-format stream-json  Accept JSONL user messages on stdin
            --output-format stream-json Emit JSONL events on stdout
            --verbose                   Include all event types
            --include-partial-messages  Enable streaming text deltas (REQUIRED!)
            --settings <file>           Settings from sandbox (NOT .claude/settings.json)
            --mcp-config <file>         MCP config from sandbox (NOT working_dir)
        """
        cmd = [self.executable, "-p"]

        if self.model:
            cmd.extend(["--model", self.model])

        # Bidirectional JSONL streaming
        cmd.extend(["--input-format", "stream-json"])
        cmd.extend(["--output-format", "stream-json"])

        # Include partial messages for streaming deltas
        # CRITICAL: Without --include-partial-messages, stream_event with
        # text_delta won't be emitted, breaking real-time streaming!
        cmd.append("--verbose")
        cmd.append("--include-partial-messages")

        # Settings via --settings flag (NOT .claude/settings.json!)
        if hasattr(self, "_claude_settings_path") and self._claude_settings_path:
            cmd.extend(["--settings", str(self._claude_settings_path)])

        # Permission mode
        if self.permission_mode:
            cmd.extend(["--permission-mode", self.permission_mode])

        # System prompt via CLI flag (NOT CLAUDE.md!)
        if self.system_prompt:
            cmd.extend(["--append-system-prompt", self.system_prompt])

        # MCP config from sandbox temp file
        if hasattr(self, "_mcp_config_path") and self._mcp_config_path:
            cmd.extend(["--mcp-config", str(self._mcp_config_path)])
            if self.strict_mcp_config:
                cmd.append("--strict-mcp-config")

        # Cost control
        if self.max_turns:
            cmd.extend(["--max-turns", str(self.max_turns)])

        # Session management
        if self.continue_session:
            cmd.append("--continue")
        elif self.resume_session_id:
            cmd.extend(["--resume", self.resume_session_id])

        # Structured output (JSON schema from sandbox)
        if hasattr(self, "_schema_path") and self._schema_path:
            cmd.extend(["--json-schema", str(self._schema_path)])

        # Fallback model (when primary model is overloaded)
        if self.fallback_model:
            cmd.extend(["--fallback-model", self.fallback_model])

        # Debug flag
        if self.debug:
            cmd.append("--debug")

        return cmd

    def _format_user_message(self, prompt: str, attachments: list[Attachment] | None = None) -> str:
        """
        Format a user prompt as JSONL for Claude's --input-format stream-json.

        Format documented at:
        https://code.claude.com/docs/en/headless#streaming-json-input
        """
        content: list[dict[str, Any]] = []

        # Attachments before text (Claude docs recommend documents first)
        if attachments:
            for att in attachments:
                b64 = base64.b64encode(att.path.read_bytes()).decode("ascii")
                if att.mime_type.startswith("image/"):
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": att.mime_type, "data": b64},
                    })
                elif att.mime_type == "application/pdf":
                    content.append({
                        "type": "document",
                        "source": {"type": "base64", "media_type": att.mime_type, "data": b64},
                        "title": att.filename,
                    })

        content.append({"type": "text", "text": prompt})

        msg: dict[str, Any] = {
            "type": "user",
            "message": {
                "role": "user",
                "content": content,
            },
        }
        # Include session_id if we have one
        if self.session_id:
            msg["session_id"] = self.session_id

        return json.dumps(msg, ensure_ascii=False)

    # === Oneshot fallback ==============================================

    def _build_oneshot_command(self, prompt: str) -> list[str]:
        """Build oneshot command (fallback when persistent fails)."""
        cmd = [self.executable, "-p", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.extend(["--output-format", "stream-json"])

        # Tool permissions
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.permission_mode:
            cmd.extend(["--permission-mode", self.permission_mode])

        # Resume session for context continuity
        if self.session_id:
            cmd.extend(["--resume", self.session_id])

        # MCP config
        mcp_path = Path(self.working_dir) / "mcp_servers.json"
        if mcp_path.exists():
            cmd.extend(["--mcp-config", str(mcp_path)])
            if self.strict_mcp_config:
                cmd.append("--strict-mcp-config")

        # Cost control
        if self.max_turns:
            cmd.extend(["--max-turns", str(self.max_turns)])

        # Session management (for oneshot, --resume takes priority over --continue)
        if not self.session_id:
            if self.continue_session:
                cmd.append("--continue")
            elif self.resume_session_id:
                cmd.extend(["--resume", self.resume_session_id])

        # Structured output (JSON schema)
        if self.json_schema:
            schema_path = Path(self.working_dir) / ".claude_schema.json"
            schema_path.write_text(json.dumps(self.json_schema, indent=2))
            cmd.extend(["--json-schema", str(schema_path)])

        # Fallback model (when primary model is overloaded)
        if self.fallback_model:
            cmd.extend(["--fallback-model", self.fallback_model])

        # Debug flag
        if self.debug:
            cmd.append("--debug")

        return cmd

    # === Event parsing ==================================================

    def _is_turn_complete(self, event: dict[str, Any]) -> bool:
        """Result event marks end of assistant turn."""
        # Only result event marks turn complete
        # (system/init is received with first response, not separately)
        return event.get("type") == "result"

    def _parse_session_id(self, events: list[dict[str, Any]]) -> str | None:
        for ev in events:
            if ev.get("type") in ("system", "init") and "session_id" in ev:
                return ev["session_id"]
        for ev in events:
            if ev.get("type") == "result" and "session_id" in ev:
                return ev["session_id"]
        return None

    def _parse_content(self, events: list[dict[str, Any]]) -> str:
        parts: list[str] = []

        for ev in events:
            # Assistant message events
            if ev.get("type") == "assistant":
                msg = ev.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))

            # Also check "message" type with assistant role
            elif ev.get("type") == "message" and ev.get("role") == "assistant":
                content = ev.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))

        # Fallback: result.result
        if not parts:
            for ev in events:
                if ev.get("type") == "result" and "result" in ev:
                    return ev["result"]

        return "".join(parts)

    def _parse_tool_calls(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        calls = []
        for ev in events:
            if ev.get("type") == "tool_use":
                calls.append({
                    "tool": ev.get("tool_name", ev.get("name", "")),
                    "parameters": ev.get("parameters", ev.get("input", {})),
                    "tool_id": ev.get("tool_id", ev.get("id", "")),
                })
        return calls

    def _parse_usage(self, events: list[dict[str, Any]]) -> dict[str, Any] | None:
        for ev in events:
            if ev.get("type") == "result":
                u = {}
                for key in ("total_cost_usd", "duration_ms", "num_turns",
                            "duration_api_ms"):
                    if key in ev:
                        u[key] = ev[key]
                return u or None
        return None

    def _extract_text_delta(self, event: dict[str, Any]) -> str | None:
        # stream_event with text_delta (--verbose --include-partial-messages)
        if event.get("type") == "stream_event":
            delta = event.get("event", {}).get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text")

        # Full assistant message
        if event.get("type") in ("assistant", "message"):
            if event.get("type") == "message" and event.get("role") != "assistant":
                return None
            msg = event.get("message", event)
            content = msg.get("content", "")
            if isinstance(content, str):
                return content or None
            if isinstance(content, list):
                texts = [b["text"] for b in content
                         if isinstance(b, dict) and b.get("type") == "text"]
                return "".join(texts) or None

        return None

    # === Cost tracking ==================================================

    def _track_cost(self, events: list[dict[str, Any]]) -> float | None:
        """Extract and accumulate cost from response events."""
        for ev in events:
            if ev.get("type") == "result":
                cost = ev.get("total_cost_usd")
                if cost is not None:
                    self._total_cost_usd += cost
                    return cost
        return None

    def get_usage(self) -> dict[str, Any]:
        """Extended usage with cost and budget info."""
        usage = super().get_usage()
        usage["total_cost_usd"] = self._total_cost_usd
        if self.max_budget_usd is not None:
            usage["budget_usd"] = self.max_budget_usd
            usage["budget_remaining_usd"] = max(0, self.max_budget_usd - self._total_cost_usd)
        return usage

    def get_total_cost(self) -> float:
        """Get total accumulated cost for this session."""
        return self._total_cost_usd

    def is_over_budget(self) -> bool:
        """Check if max_budget_usd has been exceeded."""
        if self.max_budget_usd is None:
            return False
        return self._total_cost_usd >= self.max_budget_usd

    def check_health(self) -> dict[str, Any]:
        """Extended health check with cost information."""
        health = super().check_health()
        health["total_cost_usd"] = self._total_cost_usd
        health["over_budget"] = self.is_over_budget()
        if self.max_budget_usd:
            health["budget_remaining_usd"] = max(0, self.max_budget_usd - self._total_cost_usd)
        return health
