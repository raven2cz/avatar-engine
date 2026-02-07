"""
Avatar Engine type definitions.

This module contains all public types used by the Avatar Engine library.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class ProviderType(Enum):
    """Supported AI provider types."""
    GEMINI = "gemini"
    CLAUDE = "claude"
    CODEX = "codex"


class BridgeState(Enum):
    """Bridge connection state."""
    DISCONNECTED = "disconnected"
    WARMING_UP = "warming_up"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BridgeResponse:
    """Response from AI bridge."""
    content: str
    success: bool = True
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_events: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    token_usage: Optional[Dict[str, Any]] = None

    def __bool__(self) -> bool:
        """Allow `if response:` checks."""
        return self.success


@dataclass
class SessionInfo:
    """Session metadata for listing and resuming sessions.

    Mirrors ACP SessionInfo — only fields that providers actually return.
    """
    session_id: str
    provider: str  # "gemini" | "claude" | "codex"
    cwd: str = ""
    title: Optional[str] = None
    updated_at: Optional[str] = None  # ISO 8601


@dataclass
class SessionCapabilitiesInfo:
    """What session operations the current bridge supports.

    Detected at runtime from ACP InitializeResponse or set
    statically for Claude (which uses CLI flags instead of ACP).
    """
    can_list: bool = False           # ACP list_sessions
    can_load: bool = False           # ACP load_session / Claude --resume
    can_continue_last: bool = False  # ACP list+load combo / Claude --continue


@dataclass
class HealthStatus:
    """Health check result."""
    healthy: bool
    state: str
    provider: str
    session_id: Optional[str] = None
    history_length: int = 0
    pid: Optional[int] = None
    returncode: Optional[int] = None
    total_cost_usd: float = 0.0
    uptime_seconds: float = 0.0
