"""Isolated temp directory for avatar engine config files.

Zero Footprint: no files are written to the host project directory.
All config files live in /tmp/avatar-<session>/ and are cleaned up on exit.
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4


class ConfigSandbox:
    """Manage temp config files for CLI subprocesses.

    Each bridge gets its own sandbox so concurrent avatar instances
    don't interfere with each other or the host application.
    """

    def __init__(self, session_id: str | None = None):
        self._session_id = session_id or uuid4().hex[:8]
        self._root = Path(tempfile.mkdtemp(prefix=f"avatar-{self._session_id}-"))

    @property
    def root(self) -> Path:
        return self._root

    # --- Gemini ---

    def write_gemini_settings(self, settings: dict[str, Any]) -> Path:
        """Write settings.json for GEMINI_CLI_SYSTEM_SETTINGS_PATH."""
        path = self._root / "gemini-settings.json"
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
        return path

    def write_system_prompt(self, prompt: str) -> Path:
        """Write system prompt for GEMINI_SYSTEM_MD."""
        path = self._root / "system.md"
        path.write_text(prompt, encoding="utf-8")
        return path

    # --- Claude ---

    def write_mcp_config(self, servers: dict[str, Any]) -> Path:
        """Write MCP config for Claude --mcp-config flag."""
        path = self._root / "mcp_servers.json"
        mcp_file: dict[str, Any] = {"mcpServers": {}}
        for name, srv in servers.items():
            entry: dict[str, Any] = {
                "command": srv["command"],
                "args": srv.get("args", []),
            }
            if "env" in srv:
                entry["env"] = srv["env"]
            mcp_file["mcpServers"][name] = entry
        path.write_text(json.dumps(mcp_file, indent=2, ensure_ascii=False))
        return path

    def write_claude_settings(self, settings: dict[str, Any]) -> Path:
        """Write settings JSON for Claude --settings flag."""
        path = self._root / "claude-settings.json"
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
        return path

    def write_json_schema(self, schema: dict[str, Any]) -> Path:
        """Write JSON schema for Claude --json-schema flag."""
        path = self._root / "schema.json"
        path.write_text(json.dumps(schema, indent=2))
        return path

    # --- Cleanup ---

    def cleanup(self) -> None:
        """Remove all temp files."""
        shutil.rmtree(self._root, ignore_errors=True)
