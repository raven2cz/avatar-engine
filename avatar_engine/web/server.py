"""
FastAPI web server with REST + WebSocket routes for Avatar Engine.

Provides:
- REST endpoints for health, capabilities, history, usage, chat
- WebSocket endpoint for real-time bidirectional streaming
- CORS middleware for React dev server
- Static file serving for the web-demo build (production)
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .protocol import (
    capabilities_to_dict,
    event_to_dict,
    health_to_dict,
    parse_client_message,
    response_to_dict,
)
from .session_manager import EngineSessionManager

logger = logging.getLogger(__name__)


def create_app(
    provider: str = "gemini",
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    working_dir: Optional[str] = None,
    system_prompt: str = "",
    cors_origins: Optional[List[str]] = None,
    serve_static: bool = True,
    **kwargs: Any,
) -> Any:
    """Create a FastAPI application for Avatar Engine web bridge.

    Args:
        provider: AI provider ("gemini", "claude", "codex")
        model: Model name override
        config_path: Path to YAML config file (overrides provider/model)
        working_dir: Working directory for AI session
        system_prompt: System prompt for the AI
        cors_origins: Allowed CORS origins (default: localhost dev servers)
        serve_static: Whether to serve the web-demo static build
        **kwargs: Additional engine parameters

    Returns:
        FastAPI application instance
    """
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the web bridge. "
            "Install with: uv sync --extra web"
        )

    # Session manager holds the engine + WS bridge
    manager = EngineSessionManager(
        provider=provider,
        model=model,
        config_path=config_path,
        working_dir=working_dir,
        system_prompt=system_prompt,
        **kwargs,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup/shutdown lifecycle."""
        logger.info("Starting Avatar Engine web server...")
        await manager.start()
        if manager.ws_bridge:
            manager.ws_bridge.set_loop(asyncio.get_running_loop())
        logger.info("Avatar Engine web server ready")
        app.state.manager = manager
        yield
        logger.info("Shutting down Avatar Engine web server...")
        await manager.shutdown()
        logger.info("Avatar Engine web server stopped")

    app = FastAPI(
        title="Avatar Engine",
        description="AI Avatar Engine — WebSocket + REST API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store manager on app state immediately (for tests that skip lifespan)
    app.state.manager = manager

    # CORS for React dev server
    origins = cors_origins or [
        "http://localhost:5173",   # Vite default
        "http://localhost:3000",   # CRA default
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # === REST Endpoints ===

    @app.get("/api/avatar/health")
    async def get_health() -> JSONResponse:
        """Health check."""
        engine = manager.engine
        if not engine:
            return JSONResponse(
                {"healthy": False, "state": "not_started", "provider": provider},
                status_code=503,
            )
        health = engine.get_health()
        return JSONResponse(health_to_dict(health))

    @app.get("/api/avatar/capabilities")
    async def get_capabilities() -> JSONResponse:
        """Provider capabilities for UI adaptation."""
        engine = manager.engine
        if not engine:
            return JSONResponse({"error": "Engine not started"}, status_code=503)
        caps = engine.capabilities
        return JSONResponse(capabilities_to_dict(caps))

    @app.get("/api/avatar/history")
    async def get_history() -> JSONResponse:
        """Conversation history."""
        engine = manager.engine
        if not engine:
            return JSONResponse([], status_code=200)
        messages = engine.get_history()
        return JSONResponse([
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in messages
        ])

    @app.get("/api/avatar/usage")
    async def get_usage() -> JSONResponse:
        """Usage and cost stats."""
        engine = manager.engine
        if not engine or not engine._bridge:
            return JSONResponse({})
        return JSONResponse(engine._bridge.get_usage())

    @app.get("/api/avatar/sessions")
    async def list_sessions() -> JSONResponse:
        """List available sessions."""
        engine = manager.engine
        if not engine:
            return JSONResponse([])
        sessions = await engine.list_sessions()
        return JSONResponse([
            {
                "session_id": s.session_id,
                "provider": s.provider,
                "cwd": s.cwd,
                "title": s.title,
                "updated_at": s.updated_at,
            }
            for s in sessions
        ])

    @app.post("/api/avatar/chat")
    async def post_chat(body: Dict[str, Any]) -> JSONResponse:
        """Non-streaming chat (for simple use cases)."""
        engine = await manager.ensure_started()
        message = body.get("message", "")
        if not message:
            return JSONResponse({"error": "Empty message"}, status_code=400)
        response = await engine.chat(message)
        return JSONResponse(response_to_dict(response)["data"])

    @app.post("/api/avatar/stop")
    async def post_stop() -> JSONResponse:
        """Stop the engine."""
        await manager.shutdown()
        return JSONResponse({"status": "stopped"})

    @app.post("/api/avatar/clear")
    async def post_clear() -> JSONResponse:
        """Clear conversation history."""
        engine = manager.engine
        if engine:
            engine.clear_history()
        return JSONResponse({"status": "cleared"})

    # === WebSocket ===

    @app.websocket("/api/avatar/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        """Bidirectional WebSocket for real-time streaming."""
        await ws.accept()

        bridge = manager.ws_bridge
        engine = manager.engine

        if not bridge or not engine:
            await ws.send_json({"type": "error", "data": {"error": "Engine not started"}})
            await ws.close()
            return

        # Add client to broadcast set
        await bridge.add_client(ws)

        # Send connected message with session info
        await ws.send_json({
            "type": "connected",
            "data": {
                "session_id": engine.session_id,
                "provider": engine.current_provider,
                "capabilities": capabilities_to_dict(engine.capabilities),
                "engine_state": bridge.engine_state.value,
            },
        })

        try:
            while True:
                raw = await ws.receive_json()
                parsed = parse_client_message(raw)
                if parsed is None:
                    await ws.send_json({
                        "type": "error",
                        "data": {"error": f"Unknown message type: {raw.get('type')}"},
                    })
                    continue

                msg_type = parsed["type"]
                msg_data = parsed["data"]

                if msg_type == "ping":
                    await ws.send_json({"type": "pong", "data": {"ts": time.time()}})

                elif msg_type == "chat":
                    message = msg_data.get("message", "")
                    if not message:
                        await ws.send_json({
                            "type": "error",
                            "data": {"error": "Empty message"},
                        })
                        continue

                    # Run chat in background — events auto-broadcast via bridge
                    async def _run_chat(msg: str) -> None:
                        try:
                            response = await engine.chat(msg)
                            bridge.broadcast_message(response_to_dict(response))
                        except Exception as e:
                            bridge.broadcast_message({
                                "type": "error",
                                "data": {"error": str(e), "recoverable": True},
                            })

                    asyncio.create_task(_run_chat(message))

                elif msg_type == "stop":
                    # TODO: implement chat cancellation
                    await ws.send_json({
                        "type": "error",
                        "data": {"error": "Stop not yet implemented"},
                    })

                elif msg_type == "clear_history":
                    engine.clear_history()
                    await ws.send_json({"type": "history_cleared", "data": {}})

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            await bridge.remove_client(ws)

    # === Optional: Serve static web-demo build ===

    if serve_static:
        static_dir = Path(__file__).parent.parent.parent / "examples" / "web-demo" / "dist"
        if static_dir.exists():
            try:
                from fastapi.staticfiles import StaticFiles
                app.mount("/", StaticFiles(directory=str(static_dir), html=True))
                logger.info(f"Serving static files from {static_dir}")
            except Exception:
                pass

    return app
