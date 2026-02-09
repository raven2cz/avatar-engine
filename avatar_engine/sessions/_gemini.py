"""Gemini CLI filesystem session store.

Gemini CLI stores sessions at:
    ~/.gemini/tmp/<sha256(cwd)>/chats/session-*.json

Each JSON file contains:
    sessionId, lastUpdated, startTime, messages[]

Message format:
    type: "user" | "gemini" | "error"
    content: str (plain text)
    id, timestamp, thoughts[], tokens{}, model
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Optional

from ..types import Message, SessionInfo
from ._base import SessionStore

logger = logging.getLogger(__name__)


class GeminiFileSessionStore(SessionStore):
    """Reads Gemini CLI session files from ~/.gemini/tmp/."""

    def __init__(self, gemini_home: Optional[Path] = None):
        self._gemini_home = gemini_home or Path.home() / ".gemini" / "tmp"

    @staticmethod
    def _compute_project_hash(working_dir: str) -> str:
        """SHA-256 hash of the working directory path (matches Gemini CLI)."""
        return hashlib.sha256(working_dir.encode()).hexdigest()

    def _parse_session_file(self, path: Path) -> Optional[SessionInfo]:
        """Parse a single Gemini session JSON file into SessionInfo."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(f"Failed to parse {path}: {exc}")
            return None

        session_id = data.get("sessionId")
        if not session_id:
            return None

        # Title: first user message content (summary field doesn't exist)
        title = None
        for msg in data.get("messages", []):
            if msg.get("type") == "user":
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    title = content.strip()[:80]
                    break

        # Timestamp: prefer lastUpdated, fall back to startTime
        updated_at = data.get("lastUpdated") or data.get("startTime")

        return SessionInfo(
            session_id=session_id,
            provider="gemini",
            title=title,
            updated_at=updated_at,
        )

    async def list_sessions(self, working_dir: str) -> List[SessionInfo]:
        """List Gemini sessions for the given working directory."""
        project_hash = self._compute_project_hash(working_dir)
        chats_dir = self._gemini_home / project_hash / "chats"

        if not chats_dir.is_dir():
            return []

        sessions: List[SessionInfo] = []
        for path in chats_dir.glob("session-*.json"):
            info = self._parse_session_file(path)
            if info:
                info.cwd = working_dir
                sessions.append(info)

        # Sort by updated_at descending (newest first), None last
        sessions.sort(key=lambda s: s.updated_at or "", reverse=True)
        return sessions

    def _find_session_file(self, session_id: str, working_dir: str) -> Optional[Path]:
        """Find a Gemini session file by sessionId.

        Gemini CLI filenames use ``session-{timestamp}-{shortId}.json``
        (e.g. ``session-2026-02-09T05-53-fa4de119.json``), where shortId
        is the first 8 chars of the UUID.  The full UUID is only stored
        inside the JSON as ``sessionId``.

        Strategy: glob by short-ID suffix first (fast), then verify the
        ``sessionId`` field inside the matching file.
        """
        project_hash = self._compute_project_hash(working_dir)
        chats_dir = self._gemini_home / project_hash / "chats"
        if not chats_dir.is_dir():
            return None

        # Short ID = first 8 hex chars of UUID (before first hyphen)
        short_id = session_id.split("-")[0] if "-" in session_id else session_id[:8]

        # Fast path: glob for files ending with the short ID
        for path in chats_dir.glob(f"session-*{short_id}.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("sessionId") == session_id:
                    return path
            except (json.JSONDecodeError, OSError):
                continue

        # Slow fallback: scan all files (in case naming scheme changed)
        for path in chats_dir.glob("session-*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("sessionId") == session_id:
                    return path
            except (json.JSONDecodeError, OSError):
                continue

        return None

    def load_session_messages(self, session_id: str, working_dir: str) -> List[Message]:
        """Load messages from a Gemini session file.

        Finds the session file by matching the ``sessionId`` field inside
        the JSON (filenames use a timestamp-based scheme, not the raw UUID).
        Returns empty list if session not found or unparseable.
        """
        session_file = self._find_session_file(session_id, working_dir)
        if not session_file:
            logger.debug(f"Gemini session not found: {session_id}")
            return []

        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(f"Failed to parse session {session_id}: {exc}")
            return []

        messages: List[Message] = []
        for msg in data.get("messages", []):
            msg_type = msg.get("type", "")
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue

            if msg_type == "user":
                messages.append(Message(role="user", content=content))
            elif msg_type == "gemini":
                messages.append(Message(role="assistant", content=content))
            # Skip "error" and other types

        return messages
