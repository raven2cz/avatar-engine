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

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_bridge import BaseBridge, BridgeState

logger = logging.getLogger(__name__)


class ClaudeBridge(BaseBridge):
    """
    Claude Code bridge using persistent --input-format stream-json.

    True warm session: process starts once, stays alive for all messages.
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

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def is_persistent(self) -> bool:
        return True  # TRUE warm session!

    # === Start override (no warm-up wait for Claude stream-json) =========

    async def start(self) -> None:
        """
        Start Claude bridge.

        Unlike Gemini ACP, Claude with --input-format stream-json doesn't send
        init events until the first user message. So we just spawn the process
        and mark it ready immediately.
        """
        import asyncio

        logger.info(f"Starting {self.provider_name} bridge (persistent, no warm-up wait)")
        self._setup_config_files()

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

        # Claude stream-json: no init event until first message, so we're ready now
        self._set_state(BridgeState.READY)
        logger.info(f"Claude bridge ready. PID: {self._proc.pid}")

    # === Config =========================================================

    def _setup_config_files(self) -> None:
        claude_dir = Path(self.working_dir) / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

        # .claude/settings.json
        settings: Dict[str, Any] = {}
        if self.allowed_tools:
            settings["permissions"] = {"allow": self.allowed_tools}
        if self.mcp_servers:
            mcp = {}
            for name, srv in self.mcp_servers.items():
                mcp[name] = {"command": srv["command"], "args": srv.get("args", [])}
                if "env" in srv:
                    mcp[name]["env"] = srv["env"]
            settings["mcpServers"] = mcp
        (claude_dir / "settings.json").write_text(
            json.dumps(settings, indent=2, ensure_ascii=False))

        # mcp_servers.json for --mcp-config
        if self.mcp_servers:
            mcp_file = {"mcpServers": {}}
            for name, srv in self.mcp_servers.items():
                mcp_file["mcpServers"][name] = {
                    "command": srv["command"], "args": srv.get("args", []),
                }
                if "env" in srv:
                    mcp_file["mcpServers"][name]["env"] = srv["env"]
            (Path(self.working_dir) / "mcp_servers.json").write_text(
                json.dumps(mcp_file, indent=2, ensure_ascii=False))

        # CLAUDE.md
        if self.system_prompt:
            (Path(self.working_dir) / "CLAUDE.md").write_text(
                self.system_prompt, encoding="utf-8")

    # === Persistent command ==============================================

    def _build_persistent_command(self) -> List[str]:
        """
        Build the persistent subprocess command.

        Key flags:
            -p                          Non-interactive (print) mode
            --input-format stream-json  Accept JSONL user messages on stdin
            --output-format stream-json Emit JSONL events on stdout
            --verbose                   Include all event types
            --include-partial-messages  Enable streaming text deltas (REQUIRED!)
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

        # Tool permissions
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.permission_mode:
            cmd.extend(["--permission-mode", self.permission_mode])

        # System prompt
        if self.system_prompt:
            cmd.extend(["--append-system-prompt", self.system_prompt])

        # MCP config
        mcp_path = Path(self.working_dir) / "mcp_servers.json"
        if mcp_path.exists():
            cmd.extend(["--mcp-config", str(mcp_path)])

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

    # === Oneshot (not used, but required by ABC) ========================

    def _build_oneshot_command(self, prompt: str) -> List[str]:
        # Fallback if persistent fails
        cmd = [self.executable, "-p", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.extend(["--output-format", "stream-json"])
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
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
