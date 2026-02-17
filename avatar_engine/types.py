"""
Avatar Engine type definitions.

This module contains all public types used by the Avatar Engine library.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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
class Attachment:
    """File attachment metadata (image, PDF, audio, etc.)."""
    path: Path          # Local file path on disk
    mime_type: str       # MIME type (image/png, application/pdf, ...)
    filename: str        # Original filename
    size: int           # File size in bytes


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class BridgeResponse:
    """Response from AI bridge."""
    content: str
    success: bool = True
    error: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_events: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    session_id: str | None = None
    cost_usd: float | None = None
    token_usage: dict[str, Any] | None = None
    generated_images: list[Path] = field(default_factory=list)

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
    title: str | None = None
    updated_at: str | None = None  # ISO 8601


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
class ToolPolicy:
    """Per-tool allow/deny rules applied at engine level.

    If allow is set, only listed tools can execute.
    If deny is set, listed tools are blocked.
    deny takes precedence over allow.
    """
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed by this policy."""
        if self.deny and tool_name in self.deny:
            return False
        if self.allow:
            return tool_name in self.allow
        return True


@dataclass
class ProviderCapabilities:
    """Full provider capability declaration for GUI adaptation.

    Each bridge sets its own capabilities during construction.
    GUI uses this to decide which panels/widgets to display.
    """
    # Session
    can_list_sessions: bool = False
    can_load_session: bool = False
    can_continue_last: bool = False

    # Thinking
    thinking_supported: bool = False
    thinking_structured: bool = False

    # Cost
    cost_tracking: bool = False
    budget_enforcement: bool = False

    # System prompt
    system_prompt_method: str = "unsupported"  # "native" | "injected" | "unsupported"

    # Streaming
    streaming: bool = True
    parallel_tools: bool = False

    # Control
    cancellable: bool = False

    # MCP
    mcp_supported: bool = False


@dataclass
class HealthStatus:
    """Health check result."""
    healthy: bool
    state: str
    provider: str
    session_id: str | None = None
    history_length: int = 0
    pid: int | None = None
    returncode: int | None = None
    total_cost_usd: float = 0.0
    uptime_seconds: float = 0.0
