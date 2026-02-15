"""
Avatar Engine Web Bridge — FastAPI + WebSocket transport for GUI integration.

Exposes AvatarEngine events over HTTP/WebSocket so that any web frontend
(React, Vue, vanilla JS) can consume the real-time event stream.

Usage:
    from avatar_engine.web import create_app

    app = create_app(provider="gemini")
    # Run with: uvicorn avatar_engine.web:app
"""

from .server import create_app, create_api_app
from .bridge import WebSocketBridge
from .protocol import event_to_dict, EVENT_TYPE_MAP
from .session_manager import EngineSessionManager

__all__ = [
    "create_app",
    "create_api_app",
    "WebSocketBridge",
    "EngineSessionManager",
    "event_to_dict",
    "EVENT_TYPE_MAP",
]
