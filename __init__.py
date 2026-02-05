"""Avatar Engine — headless JSON bridges for Gemini CLI and Claude Code."""

from .avatar_engine import AvatarEngine
from .bridges import BridgeResponse, BridgeState, ClaudeBridge, GeminiBridge, Message

__all__ = [
    "AvatarEngine",
    "BridgeResponse",
    "BridgeState",
    "ClaudeBridge",
    "GeminiBridge",
    "Message",
]
