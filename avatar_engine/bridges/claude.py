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
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseBridge, BridgeState
from ..config_sandbox import ConfigSandbox

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
        timeout: int = 120,
        system_prompt: str = "",
        allowed_tools: Optional[List[str]] = None,
        permission_mode: str = "acceptEdits",
        strict_mcp_config: bool = False,
        max_turns: Optional[int] = None,
        max_budget_usd: Optional[float] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        continue_session: bool = False,
        resume_session_id: Optional[str] = None,
        fallback_model: Optional[str] = None,
        debug: bool = False,
        env: Optional[Dict[str, str]] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            executable=executable, model=model, working_dir=working_dir,
            timeout=timeout, system_prompt=system_prompt, env=env,
            mcp_servers=mcp_servers,
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
        self.debug = debug

        # Track whether we're in persistent mode (can fall back to oneshot)
        self._persistent_mode = True

        # Session capabilities — Claude supports resume and continue via CLI flags
        self._session_capabilities.can_load = True
        self._session_capabilities.can_continue_last = True
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
            self._set_state(BridgeState.WARMING_UP)
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
            await asyncio.sleep(0.1)
            if self._proc.returncode is not None:
                stderr = await self._proc.stderr.read()
                raise RuntimeError(
                    f"Claude process exited immediately (code {self._proc.returncode}): "
                    f"{stderr.decode(errors='replace')[:500]}"
                )

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
        settings: Dict[str, Any] = {}
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

    def _build_persistent_command(self) -> List[str]:
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

    def _format_user_message(self, prompt: str) -> str:
        """
        Format a user prompt as JSONL for Claude's --input-format stream-json.

        Format documented at:
        https://code.claude.com/docs/en/headless#streaming-json-input
        """
        msg = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            },
        }
        # Include session_id if we have one
        if self.session_id:
            msg["session_id"] = self.session_id

        return json.dumps(msg, ensure_ascii=False)

    # === Oneshot fallback ==============================================

    def _build_oneshot_command(self, prompt: str) -> List[str]:
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

    def _is_turn_complete(self, event: Dict[str, Any]) -> bool:
        """Result event marks end of assistant turn."""
        # Only result event marks turn complete
        # (system/init is received with first response, not separately)
        return event.get("type") == "result"

    def _parse_session_id(self, events: List[Dict[str, Any]]) -> Optional[str]:
        for ev in events:
            if ev.get("type") in ("system", "init") and "session_id" in ev:
                return ev["session_id"]
        for ev in events:
            if ev.get("type") == "result" and "session_id" in ev:
                return ev["session_id"]
        return None

    def _parse_content(self, events: List[Dict[str, Any]]) -> str:
        parts: List[str] = []

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

    def _parse_tool_calls(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        calls = []
        for ev in events:
            if ev.get("type") == "tool_use":
                calls.append({
                    "tool": ev.get("tool_name", ev.get("name", "")),
                    "parameters": ev.get("parameters", ev.get("input", {})),
                    "tool_id": ev.get("tool_id", ev.get("id", "")),
                })
        return calls

    def _parse_usage(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for ev in events:
            if ev.get("type") == "result":
                u = {}
                for key in ("total_cost_usd", "duration_ms", "num_turns",
                            "duration_api_ms"):
                    if key in ev:
                        u[key] = ev[key]
                return u or None
        return None

    def _extract_text_delta(self, event: Dict[str, Any]) -> Optional[str]:
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

    def _track_cost(self, events: List[Dict[str, Any]]) -> Optional[float]:
        """Extract and accumulate cost from response events."""
        for ev in events:
            if ev.get("type") == "result":
                cost = ev.get("total_cost_usd")
                if cost is not None:
                    self._total_cost_usd += cost
                    return cost
        return None

    def get_usage(self) -> Dict[str, Any]:
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

    def check_health(self) -> Dict[str, Any]:
        """Extended health check with cost information."""
        health = super().check_health()
        health["total_cost_usd"] = self._total_cost_usd
        health["over_budget"] = self.is_over_budget()
        if self.max_budget_usd:
            health["budget_remaining_usd"] = max(0, self.max_budget_usd - self._total_cost_usd)
        return health
