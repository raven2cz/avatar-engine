"""
Avatar Engine bridge implementations.

Bridges provide communication with AI CLI tools:
- ClaudeBridge: Claude Code via stream-json
- GeminiBridge: Gemini CLI via ACP (with oneshot fallback)
"""

from .base import BaseBridge, BridgeResponse, BridgeState, Message
from .claude import ClaudeBridge
from .gemini import GeminiBridge

__all__ = [
    "BaseBridge",
    "BridgeResponse",
    "BridgeState",
    "Message",
    "ClaudeBridge",
    "GeminiBridge",
]
