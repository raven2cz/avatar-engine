"""
Avatar Engine bridge implementations.

Bridges provide communication with AI CLI tools:
- ClaudeBridge: Claude Code via stream-json
- GeminiBridge: Gemini CLI via ACP (with oneshot fallback)
- CodexBridge: Codex CLI via ACP codex-acp adapter
"""

from .base import BaseBridge, BridgeResponse, BridgeState, Message
from .claude import ClaudeBridge
from .codex import CodexBridge
from .gemini import GeminiBridge

__all__ = [
    "BaseBridge",
    "BridgeResponse",
    "BridgeState",
    "Message",
    "ClaudeBridge",
    "CodexBridge",
    "GeminiBridge",
]
