"""Persistent key-value store for custom session titles.

Stores user-defined session titles in a JSON file, independent of
provider session files. This allows renaming sessions without
modifying provider-specific conversation histories.

Default location: ~/.avatar-engine/session-titles.json
"""

import json
from pathlib import Path


class SessionTitleRegistry:
    """Persistent key-value store mapping session_id -> custom title."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path.home() / ".avatar-engine" / "session-titles.json"
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                if isinstance(data, dict):
                    self._cache = data
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._cache, indent=2, ensure_ascii=False))

    def get(self, session_id: str) -> str | None:
        return self._cache.get(session_id)

    def set(self, session_id: str, title: str) -> None:
        self._cache[session_id] = title
        self._save()

    def delete(self, session_id: str) -> None:
        self._cache.pop(session_id, None)
        self._save()
