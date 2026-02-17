"""Codex CLI filesystem session store.

Codex CLI stores sessions at:
    ~/.codex/sessions/YYYY/MM/DD/rollout-{timestamp}-{sessionId}.jsonl

Each JSONL file has events:
    - session_meta: payload.id, payload.cwd, payload.timestamp
    - response_item: payload.role, payload.type, payload.content[]
        role "user" + content[].type "input_text" → user message
        role "assistant" + content[].type "output_text" → assistant message
    - event_msg, turn_context, exec_command — skipped
"""

import json
import logging
from pathlib import Path

from ..types import Message, SessionInfo
from ._base import SessionStore

logger = logging.getLogger(__name__)


class CodexFileSessionStore(SessionStore):
    """Reads Codex CLI session files from ~/.codex/sessions/."""

    def __init__(self, codex_home: Path | None = None):
        self._codex_home = codex_home or Path.home() / ".codex" / "sessions"

    def _find_session_file(self, session_id: str) -> Path | None:
        """Find a Codex session file by session ID.

        Filenames use ``rollout-{timestamp}-{sessionId}.jsonl``
        where sessionId is the full UUID.  Glob by suffix for speed.
        """
        if not self._codex_home.is_dir():
            return None

        # Fast path: glob by session ID suffix across all date dirs
        for path in self._codex_home.glob(f"**/*-{session_id}.jsonl"):
            return path

        return None

    def _parse_session_meta(self, path: Path) -> dict | None:
        """Read the first line (session_meta) from a Codex session file."""
        try:
            with open(path, encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line.strip():
                    return None
                event = json.loads(first_line)
                if event.get("type") == "session_meta":
                    return event.get("payload", {})
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(f"Failed to parse {path}: {exc}")
        return None

    async def list_sessions(self, working_dir: str) -> list[SessionInfo]:
        """List Codex sessions for the given working directory.

        Note: Codex ACP list_sessions works natively, so this is a fallback.
        Scans all date directories under ~/.codex/sessions/.
        """
        if not self._codex_home.is_dir():
            return []

        sessions: list[SessionInfo] = []
        for path in self._codex_home.glob("**/*.jsonl"):
            meta = self._parse_session_meta(path)
            if not meta:
                continue

            # Filter by working directory
            if meta.get("cwd") != working_dir:
                continue

            session_id = meta.get("id")
            if not session_id:
                continue

            # Title: first user message
            title = self._get_first_user_message(path)

            sessions.append(SessionInfo(
                session_id=session_id,
                provider="codex",
                cwd=working_dir,
                title=title[:80] if title and len(title) > 80 else title,
                updated_at=meta.get("timestamp"),
            ))

        sessions.sort(key=lambda s: s.updated_at or "", reverse=True)
        return sessions

    def _get_first_user_message(self, path: Path) -> str | None:
        """Extract first real user message text from a session file."""
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("type") != "response_item":
                        continue
                    payload = event.get("payload", {})
                    if payload.get("role") != "user" or payload.get("type") != "message":
                        continue
                    text = self._extract_text(payload, "input_text")
                    if text:
                        return text
        except (json.JSONDecodeError, OSError):
            pass
        return None

    @staticmethod
    def _extract_text(payload: dict, content_type: str) -> str | None:
        """Extract text from a response_item payload with given content type."""
        content = payload.get("content", [])
        if not isinstance(content, list):
            return None
        texts = []
        for block in content:
            if block.get("type") == content_type:
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    # Skip system/developer content (permissions, environment, etc.)
                    stripped = text.strip()
                    if stripped.startswith("<") and ("instructions" in stripped[:100].lower()
                                                     or "environment" in stripped[:100].lower()):
                        continue
                    if stripped.startswith("#") and "AGENTS.md" in stripped[:50]:
                        continue
                    texts.append(stripped)
        return "\n".join(texts) if texts else None

    def load_session_messages(self, session_id: str, working_dir: str) -> list[Message]:
        """Load messages from a Codex session file.

        Finds the file by session ID in the filename, then parses
        response_item events for user/assistant messages.
        """
        session_file = self._find_session_file(session_id)
        if not session_file:
            logger.debug(f"Codex session not found: {session_id}")
            return []

        messages: list[Message] = []
        try:
            with open(session_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("type") != "response_item":
                        continue

                    payload = event.get("payload", {})
                    ptype = payload.get("type")
                    role = payload.get("role")

                    if ptype != "message":
                        continue

                    if role == "user":
                        text = self._extract_text(payload, "input_text")
                        if text:
                            messages.append(Message(role="user", content=text))
                    elif role == "assistant":
                        text = self._extract_text(payload, "output_text")
                        if text:
                            messages.append(Message(role="assistant", content=text))
                    # Skip developer, reasoning, etc.

        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(f"Failed to parse Codex session {session_id}: {exc}")
            return []

        return messages
