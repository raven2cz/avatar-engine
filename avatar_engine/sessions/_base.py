"""Abstract base class for filesystem session stores."""

from abc import ABC, abstractmethod

from ..types import Message, SessionInfo


class SessionStore(ABC):
    """Read-only session store that lists sessions from provider-specific files.

    Each provider stores sessions differently on disk. Implementations
    parse those files and return unified SessionInfo objects.
    """

    @abstractmethod
    async def list_sessions(self, working_dir: str) -> list[SessionInfo]:
        """List sessions scoped to working directory, sorted by updated_at desc."""
        ...

    def load_session_messages(self, session_id: str, working_dir: str) -> list[Message]:
        """Load messages from a session file. Default: empty list."""
        return []
