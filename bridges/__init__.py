"""Avatar Engine CLI bridges — headless JSON mode."""

from .base_bridge import BaseBridge, BridgeResponse, BridgeState, Message
from .claude_bridge import ClaudeBridge
from .gemini_bridge import GeminiBridge

__all__ = [
    "BaseBridge",
    "BridgeResponse",
    "BridgeState",
    "ClaudeBridge",
    "GeminiBridge",
    "Message",
]
