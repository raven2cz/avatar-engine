"""
Event → JSON serialization for the WebSocket protocol.

Converts all AvatarEvent subclasses to JSON-safe dicts:
    {"type": "<event_type>", "data": {...}}

Enums are converted to their string values. Timestamps are floats (epoch).
"""

import dataclasses
from enum import Enum
from typing import Any, Dict, Optional, Type

from ..events import (
    ActivityEvent,
    AvatarEvent,
    CostEvent,
    DiagnosticEvent,
    ErrorEvent,
    PermissionRequestEvent,
    StateEvent,
    TextEvent,
    ThinkingEvent,
    ToolEvent,
)
from ..types import BridgeResponse, HealthStatus, ProviderCapabilities

# Maps event classes to WebSocket message type strings
EVENT_TYPE_MAP: Dict[Type[AvatarEvent], str] = {
    TextEvent: "text",
    ThinkingEvent: "thinking",
    ToolEvent: "tool",
    StateEvent: "state",
    CostEvent: "cost",
    ErrorEvent: "error",
    DiagnosticEvent: "diagnostic",
    ActivityEvent: "activity",
    PermissionRequestEvent: "permission_request",
}


def _serialize_value(val: Any) -> Any:
    """Recursively convert enums and non-JSON types to JSON-safe values."""
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, dict):
        return {k: _serialize_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_serialize_value(item) for item in val]
    return val


def event_to_dict(event: AvatarEvent) -> Optional[Dict[str, Any]]:
    """Convert an AvatarEvent to a WebSocket message dict.

    Returns:
        {"type": "text", "data": {...}} or None if unknown event type.
    """
    event_type = EVENT_TYPE_MAP.get(type(event))
    if event_type is None:
        return None

    data = {}
    for f in dataclasses.fields(event):
        data[f.name] = _serialize_value(getattr(event, f.name))

    return {"type": event_type, "data": data}


def response_to_dict(response: BridgeResponse) -> Dict[str, Any]:
    """Convert BridgeResponse to a chat_response WebSocket message."""
    data: Dict[str, Any] = {
        "content": response.content,
        "success": response.success,
        "error": response.error,
        "duration_ms": response.duration_ms,
        "session_id": response.session_id,
        "cost_usd": response.cost_usd,
        "tool_calls": response.tool_calls,
    }
    if response.generated_images:
        data["images"] = [
            {"url": f"/api/avatar/files/{p.name}", "filename": p.name}
            for p in response.generated_images
        ]
    return {"type": "chat_response", "data": data}


def health_to_dict(health: HealthStatus) -> Dict[str, Any]:
    """Convert HealthStatus to JSON-safe dict."""
    data = {}
    for f in dataclasses.fields(health):
        data[f.name] = _serialize_value(getattr(health, f.name))
    return data


def capabilities_to_dict(caps: ProviderCapabilities) -> Dict[str, Any]:
    """Convert ProviderCapabilities to JSON-safe dict."""
    data = {}
    for f in dataclasses.fields(caps):
        data[f.name] = _serialize_value(getattr(caps, f.name))
    return data


def parse_client_message(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse and validate a client→server WebSocket message.

    Expected format: {"type": "chat|stop|ping|clear_history|switch|resume_session|new_session", "data": {...}}

    Returns:
        Validated dict with "type" and "data" keys, or None if invalid.
    """
    msg_type = raw.get("type")
    if msg_type not in ("chat", "stop", "ping", "clear_history", "switch", "resume_session", "new_session", "permission_response"):
        return None
    return {
        "type": msg_type,
        "data": raw.get("data", {}),
    }
