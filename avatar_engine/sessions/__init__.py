"""Filesystem session stores — fallback when ACP session methods are unavailable.

Usage:
    from avatar_engine.sessions import get_session_store

    store = get_session_store("gemini")
    if store:
        sessions = await store.list_sessions("/home/user/project")
"""

from typing import Optional

from ._base import SessionStore
from ._claude import ClaudeFileSessionStore
from ._codex import CodexFileSessionStore
from ._gemini import GeminiFileSessionStore

__all__ = [
    "SessionStore",
    "GeminiFileSessionStore",
    "ClaudeFileSessionStore",
    "CodexFileSessionStore",
    "get_session_store",
]


def get_session_store(provider: str) -> Optional[SessionStore]:
    """Get a filesystem session store for the given provider.

    All providers now have filesystem stores for loading session messages.
    Returns None only for unknown providers.
    """
    if provider == "gemini":
        return GeminiFileSessionStore()
    if provider == "claude":
        return ClaudeFileSessionStore()
    if provider == "codex":
        return CodexFileSessionStore()
    return None
