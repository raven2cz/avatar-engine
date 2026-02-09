"""Claude Code filesystem session store.

Claude Code stores sessions at:
    ~/.claude/projects/<encoded-cwd>/*.jsonl

Path encoding: slashes replaced with dashes.
    /home/box/git/project -> -home-box-git-project

Each JSONL file contains events with types: user, assistant, system, etc.
Session ID = filename stem (UUID).
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from ..types import Message, SessionInfo
from ._base import SessionStore

logger = logging.getLogger(__name__)

# Max lines to read from each JSONL file (avoids reading multi-MB files)
_MAX_LINES = 50


class ClaudeFileSessionStore(SessionStore):
    """Reads Claude Code session files from ~/.claude/projects/."""

    def __init__(self, claude_home: Optional[Path] = None):
        self._claude_home = claude_home or Path.home() / ".claude" / "projects"

    @staticmethod
    def _encode_path(working_dir: str) -> str:
        """Encode working directory path the way Claude Code does.

        /home/box/git/project -> -home-box-git-project
        """
        return working_dir.replace("/", "-")

    def _parse_session_file(self, path: Path) -> Optional[SessionInfo]:
        """Parse a Claude JSONL session file into SessionInfo.

        Reads only the first _MAX_LINES to extract a title from the
        first user message. Uses file mtime for updated_at.
        """
        session_id = path.stem

        title = None
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= _MAX_LINES:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if event.get("type") != "user":
                        continue

                    # Extract text from content blocks
                    msg = event.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                # Skip interrupted request markers
                                if text and not text.startswith("[Request interrupted"):
                                    title = text[:80]
                                    break
                    if title:
                        break
        except OSError as exc:
            logger.debug(f"Failed to read {path}: {exc}")
            return None

        # Use file modification time for updated_at
        try:
            mtime = path.stat().st_mtime
            from datetime import datetime, timezone
            updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            updated_at = None

        return SessionInfo(
            session_id=session_id,
            provider="claude",
            title=title,
            updated_at=updated_at,
        )

    async def list_sessions(self, working_dir: str) -> List[SessionInfo]:
        """List Claude sessions for the given working directory."""
        encoded = self._encode_path(working_dir)
        project_dir = self._claude_home / encoded

        if not project_dir.is_dir():
            return []

        sessions: List[SessionInfo] = []
        for path in project_dir.glob("*.jsonl"):
            info = self._parse_session_file(path)
            if info:
                info.cwd = working_dir
                sessions.append(info)

        # Sort by updated_at descending (newest first), None last
        sessions.sort(key=lambda s: s.updated_at or "", reverse=True)
        return sessions

    def load_session_messages(self, session_id: str, working_dir: str) -> List[Message]:
        """Load messages from a Claude Code JSONL session file.

        Parses user and assistant events into Message objects.
        Returns empty list if session not found or unparseable.
        """
        encoded = self._encode_path(working_dir)
        session_file = self._claude_home / encoded / f"{session_id}.jsonl"

        if not session_file.is_file():
            logger.debug(f"Session file not found: {session_file}")
            return []

        messages: List[Message] = []
        try:
            with session_file.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type")
                    if event_type not in ("user", "assistant"):
                        continue

                    # Extract text from content blocks
                    msg = event.get("message", {})
                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        parts = []
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                parts.append(block.get("text", ""))
                        text = "".join(parts)

                    if not text.strip():
                        continue

                    role = "user" if event_type == "user" else "assistant"
                    messages.append(Message(role=role, content=text))
        except OSError as exc:
            logger.debug(f"Failed to read {session_file}: {exc}")
            return []

        return messages
