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
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import __version__
from .protocol import (
    capabilities_to_dict,
    event_to_dict,
    health_to_dict,
    parse_client_message,
    response_to_dict,
)
from .session_manager import EngineSessionManager
from .uploads import UploadStorage
from ..sessions._titles import SessionTitleRegistry
from ..types import Attachment

logger = logging.getLogger(__name__)

# Shared title registry (one per process, covers all providers)
title_registry = SessionTitleRegistry()


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
        from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
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

    # Track background startup task so it can be cancelled on early switch
    _startup_task: Optional[asyncio.Task] = None

    async def _run_startup(mgr: EngineSessionManager) -> None:
        """Background task: start engine and broadcast connected."""
        try:
            await mgr.start_engine()
            _broadcast_connected(mgr)
        except asyncio.CancelledError:
            logger.info("Engine startup cancelled (provider switch during init)")
        except Exception as exc:
            logger.error(f"Engine startup failed: {exc}")
            if mgr.ws_bridge:
                mgr.ws_bridge.broadcast_message({
                    "type": "error",
                    "data": {"error": f"Engine startup failed: {exc}", "recoverable": False},
                })

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup/shutdown lifecycle.

        Uses non-blocking startup: prepare() creates objects instantly,
        then start_engine() runs in background so WS clients can connect
        and see granular init status events in real time.
        """
        nonlocal _startup_task
        logger.info("Starting Avatar Engine web server...")
        await manager.prepare()
        if manager.ws_bridge:
            manager.ws_bridge.set_loop(asyncio.get_running_loop())
        app.state.manager = manager
        _startup_task = asyncio.create_task(_run_startup(manager))
        logger.info("Avatar Engine web server accepting connections")
        yield
        logger.info("Shutting down Avatar Engine web server...")
        _startup_task.cancel()
        try:
            await _startup_task
        except asyncio.CancelledError:
            pass
        await manager.shutdown()
        logger.info("Avatar Engine web server stopped")

    app = FastAPI(
        title="Avatar Engine",
        description="AI Avatar Engine — WebSocket + REST API",
        version=__version__,
        lifespan=lifespan,
    )

    # Store manager and upload storage on app state (for tests that skip lifespan)
    app.state.manager = manager
    app.state.upload_storage = None  # set after upload_storage is created below

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

    @app.get("/api/avatar/version")
    async def get_version() -> JSONResponse:
        """Engine version."""
        return JSONResponse({"version": __version__})

    # Provider → CLI executable mapping (used for availability detection)
    _PROVIDER_EXECUTABLES = {
        "gemini": "gemini",
        "claude": "claude",
        "codex": "npx",
    }

    @app.get("/api/avatar/providers")
    async def get_providers() -> JSONResponse:
        """List all known providers with CLI availability on this machine."""
        providers = []
        for provider_id, executable in _PROVIDER_EXECUTABLES.items():
            available = shutil.which(executable) is not None
            providers.append({
                "id": provider_id,
                "available": available,
                "executable": executable,
            })
        return JSONResponse(providers)

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
        # Normalize current session ID for reliable comparison
        current_sid = str(engine.session_id) if engine.session_id else None
        result = []
        for s in sessions:
            custom = title_registry.get(s.session_id)
            result.append({
                "session_id": s.session_id,
                "provider": s.provider,
                "cwd": s.cwd,
                "title": custom or s.title,
                "updated_at": s.updated_at,
                "is_current": current_sid is not None and str(s.session_id) == current_sid,
            })
        return JSONResponse(result)

    @app.put("/api/avatar/sessions/{session_id}/title")
    async def set_session_title(session_id: str, request: Request) -> JSONResponse:
        """Set or clear a custom session title."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
        new_title = body.get("title", "").strip() if isinstance(body, dict) else ""
        if not new_title:
            title_registry.delete(session_id)
        else:
            title_registry.set(session_id, new_title)

        # Broadcast title update to all WS clients
        # Include is_current_session so frontend doesn't need ID comparison
        engine = manager.engine
        current_sid = str(engine.session_id) if engine and engine.session_id else None
        is_current = current_sid is not None and str(session_id) == current_sid
        if manager.ws_bridge:
            manager.ws_bridge.broadcast_message({
                "type": "session_title_updated",
                "data": {
                    "session_id": session_id,
                    "title": new_title or None,
                    "is_current_session": is_current,
                },
            })

        return JSONResponse({"session_id": session_id, "title": new_title or None})

    @app.get("/api/avatar/sessions/{session_id}/messages")
    async def get_session_messages(session_id: str) -> JSONResponse:
        """Load messages from a specific session (for displaying history on resume)."""
        from ..sessions import get_session_store

        engine = manager.engine
        current_provider = engine.current_provider if engine else manager._provider

        store = get_session_store(current_provider)
        if not store:
            return JSONResponse([])

        wd = manager._working_dir
        messages = store.load_session_messages(session_id, wd)
        return JSONResponse([
            {"role": m.role, "content": m.content}
            for m in messages
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

    # === File uploads ===

    upload_storage = UploadStorage()
    app.state.upload_storage = upload_storage

    @app.post("/api/avatar/upload")
    async def upload_file(request: Request) -> JSONResponse:
        """Upload a file for attaching to a chat message (multipart/form-data)."""
        form = await request.form()
        uploaded = form.get("file")
        if not uploaded or not hasattr(uploaded, "read"):
            return JSONResponse({"error": "No file provided"}, status_code=400)

        data = await uploaded.read()
        filename = getattr(uploaded, "filename", "unnamed") or "unnamed"
        content_type = getattr(uploaded, "content_type", "application/octet-stream") or "application/octet-stream"

        try:
            attachment = upload_storage.save(filename=filename, data=data, mime_type=content_type)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=413)

        return JSONResponse({
            "file_id": attachment.path.stem,
            "filename": attachment.filename,
            "mime_type": attachment.mime_type,
            "size": attachment.size,
            "path": str(attachment.path),
        })

    # Serve uploaded files (for generated image display in frontend)
    try:
        from starlette.staticfiles import StaticFiles
        app.mount("/api/avatar/files", StaticFiles(directory=str(upload_storage.base_dir)), name="uploads")
    except Exception:
        logger.warning("Could not mount static file serving for uploads")

    # === WebSocket helpers ===

    def _get_model(mgr: EngineSessionManager) -> Optional[str]:
        """Extract current model from engine/bridge/config.

        Falls back to 'gemini-3-pro-preview' for Gemini provider when no
        explicit model is set — this is the actual default used by gemini-cli.
        """
        eng = mgr.engine
        if not eng:
            return None
        mdl = None
        if eng._bridge:
            for _attr in ('_actual_model', '_model', 'model'):
                _val = getattr(eng._bridge, _attr, None)
                if isinstance(_val, str) and _val:
                    mdl = _val
                    break
        if mdl is None and eng._config:
            mdl = eng._config.model
        if mdl is None:
            mdl = mgr._model
        # When no model is explicitly configured, report the actual default
        # so the frontend knows what model is running.
        if not mdl and mgr._provider == "gemini":
            mdl = "gemini-3-pro-preview"
        return mdl or None

    def _get_session_title(mgr: EngineSessionManager, session_id: Optional[str]) -> Optional[str]:
        """Look up the title for a session.

        Priority: custom title (from registry) > provider title (first user message).
        """
        if not session_id:
            return None

        # 1. Custom title (highest priority)
        custom = title_registry.get(session_id)
        if custom:
            return custom

        # 2. Provider title (from first user message)
        try:
            from ..sessions import get_session_store

            eng = mgr.engine
            provider = eng.current_provider if eng else mgr._provider
            store = get_session_store(provider)
            if not store:
                return None

            # Load first user message as title
            messages = store.load_session_messages(session_id, mgr._working_dir)
            for m in messages:
                if m.role == "user" and m.content.strip():
                    text = m.content.strip()
                    return text[:80] if len(text) > 80 else text
        except Exception:
            pass
        return None

    def _broadcast_connected(mgr: EngineSessionManager, provider_fallback: str = "") -> None:
        """Broadcast a 'connected' message to all WS clients after engine restart."""
        brg = mgr.ws_bridge
        eng = mgr.engine
        if not brg:
            return
        brg.set_loop(asyncio.get_running_loop())
        sid = eng.session_id if eng else None
        brg.broadcast_message({
            "type": "connected",
            "data": {
                "session_id": sid,
                "provider": eng.current_provider if eng else provider_fallback,
                "model": _get_model(mgr),
                "version": __version__,
                "capabilities": capabilities_to_dict(eng.capabilities) if eng else {},
                "engine_state": brg.engine_state.value,
                "cwd": mgr._working_dir,
                "session_title": _get_session_title(mgr, sid),
                "safety_mode": getattr(eng, '_safety_mode', 'safe') if eng else 'safe',
            },
        })

    def _broadcast_error_and_connected(
        mgr: EngineSessionManager, error_msg: str, provider_fallback: str = ""
    ) -> None:
        """Broadcast an error and then the current connected state."""
        brg = mgr.ws_bridge
        if not brg:
            return
        brg.set_loop(asyncio.get_running_loop())
        brg.broadcast_message({
            "type": "error",
            "data": {"error": error_msg, "recoverable": True},
        })
        _broadcast_connected(mgr, provider_fallback=provider_fallback)

    # === WebSocket ===

    @app.websocket("/api/avatar/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        """Bidirectional WebSocket for real-time streaming."""
        await ws.accept()

        bridge = manager.ws_bridge

        if not bridge:
            await ws.send_json({"type": "error", "data": {"error": "Engine not created"}})
            await ws.close()
            return

        # Add client to broadcast set — events will flow automatically
        await bridge.add_client(ws)

        engine = manager.engine

        if manager.is_ready and engine:
            # Engine already running — send connected immediately
            model = _get_model(manager)
            sid = engine.session_id
            await ws.send_json({
                "type": "connected",
                "data": {
                    "session_id": sid,
                    "provider": engine.current_provider,
                    "model": model,
                    "version": __version__,
                    "capabilities": capabilities_to_dict(engine.capabilities),
                    "engine_state": bridge.engine_state.value,
                    "cwd": manager._working_dir,
                    "session_title": _get_session_title(manager, sid),
                    "safety_mode": getattr(engine, '_safety_mode', 'safe'),
                },
            })
        else:
            # Engine still starting — send initializing message.
            # State events with detail will flow automatically via ws_bridge.
            detail = ""
            if engine and engine._bridge:
                detail = engine._bridge._state_detail
            await ws.send_json({
                "type": "initializing",
                "data": {
                    "provider": manager._provider or "",
                    "detail": detail,
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

                    # Parse file attachments from message data
                    raw_attachments = msg_data.get("attachments", [])
                    chat_attachments: Optional[List[Attachment]] = None
                    if raw_attachments:
                        valid = []
                        for a in raw_attachments:
                            p = Path(a.get("path", ""))
                            if p.exists() and upload_storage.is_valid_path(p):
                                valid.append(Attachment(
                                    path=p,
                                    mime_type=a.get("mime_type", "application/octet-stream"),
                                    filename=a.get("filename", p.name),
                                    size=p.stat().st_size,
                                ))
                        chat_attachments = valid or None

                    # Run chat in background — events auto-broadcast via bridge
                    # Use manager refs (not local vars) so chat works after switch
                    async def _run_chat(msg: str, atts: Optional[List[Attachment]] = chat_attachments, client_ws: WebSocket = ws) -> None:
                        try:
                            eng = manager.engine
                            brg = manager.ws_bridge
                            if not eng or not brg:
                                logger.error("Chat failed: engine or bridge not available")
                                try:
                                    await client_ws.send_json({
                                        "type": "error",
                                        "data": {"error": "Engine not available — try reconnecting", "recoverable": True},
                                    })
                                except Exception:
                                    pass
                                return

                            # Dynamic timeout: extend for large attachments.
                            # Base is 600s — ACP requests (tool chains, large
                            # analyses) routinely take 5–10 minutes.
                            chat_timeout = 600
                            total_att_mb = 0.0
                            if atts:
                                total_att_mb = sum(a.size for a in atts) / (1024 * 1024)
                                chat_timeout += int(total_att_mb * 3)  # +3s per MB

                            logger.debug(f"Chat request: {msg[:80]}... (attachments: {len(atts) if atts else 0}, {total_att_mb:.1f} MB, timeout: {chat_timeout}s)")
                            chat_start = time.monotonic()
                            response = await asyncio.wait_for(eng.chat(msg, attachments=atts), timeout=chat_timeout)
                            brg.broadcast_message(response_to_dict(response))
                        except asyncio.TimeoutError:
                            elapsed = time.monotonic() - chat_start
                            # Collect context to help user understand WHY
                            ctx_parts: list[str] = []
                            if atts:
                                total_mb = sum(a.size for a in atts) / (1024 * 1024)
                                ctx_parts.append(f"attachments: {total_mb:.1f} MB")
                            # Engine/bridge state
                            try:
                                bridge_state = eng._bridge.state.value if eng._bridge else "unknown"
                                engine_state = brg.engine_state.value if brg else "unknown"
                                ctx_parts.append(f"state: {engine_state}/{bridge_state}")
                            except Exception:
                                pass
                            # Last stderr diagnostic
                            try:
                                stderr_buf = eng._bridge.get_stderr_buffer() if eng._bridge else []
                                if stderr_buf:
                                    last_line = stderr_buf[-1][:120]
                                    ctx_parts.append(f"last diagnostic: {last_line}")
                            except Exception:
                                pass
                            ctx = f" ({', '.join(ctx_parts)})" if ctx_parts else ""
                            error_text = f"No response from engine — timed out after {int(elapsed)}s{ctx}"
                            logger.error(f"Chat timeout: {error_text}")
                            err_msg = {
                                "type": "error",
                                "data": {"error": error_text, "recoverable": True},
                            }
                            brg = manager.ws_bridge
                            if brg:
                                brg.broadcast_message(err_msg)
                            else:
                                try:
                                    await client_ws.send_json(err_msg)
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.error(f"Chat error: {e}")
                            err_msg = {
                                "type": "error",
                                "data": {"error": str(e), "recoverable": True},
                            }
                            brg = manager.ws_bridge
                            if brg:
                                brg.broadcast_message(err_msg)
                            else:
                                try:
                                    await client_ws.send_json(err_msg)
                                except Exception:
                                    pass

                    task = asyncio.create_task(_run_chat(message))

                    def _on_chat_done(t: asyncio.Task, client_ws: WebSocket = ws) -> None:
                        if t.cancelled():
                            return
                        exc = t.exception()
                        if exc:
                            logger.error(f"Unhandled chat task error: {exc}")
                            try:
                                asyncio.get_running_loop().create_task(
                                    client_ws.send_json({
                                        "type": "error",
                                        "data": {"error": f"Internal error: {exc}", "recoverable": True},
                                    })
                                )
                            except Exception:
                                pass

                    task.add_done_callback(_on_chat_done)

                elif msg_type == "stop":
                    # TODO: implement chat cancellation
                    await ws.send_json({
                        "type": "error",
                        "data": {"error": "Stop not yet implemented"},
                    })

                elif msg_type == "switch":
                    switch_provider = msg_data.get("provider", "")
                    switch_model = msg_data.get("model") or None
                    switch_options = msg_data.get("options") or None
                    if not switch_provider:
                        await ws.send_json({
                            "type": "error",
                            "data": {"error": "Missing provider for switch"},
                        })
                        continue

                    # Cancel pending startup task to avoid race condition
                    nonlocal _startup_task
                    if _startup_task and not _startup_task.done():
                        _startup_task.cancel()
                        try:
                            await _startup_task
                        except asyncio.CancelledError:
                            pass
                        _startup_task = None

                    # Cancel pending permission dialogs before switching
                    if manager.engine:
                        manager.engine.cancel_all_permissions()

                    try:
                        await manager.switch(switch_provider, switch_model, options=switch_options)
                        engine = manager.engine
                        bridge = manager.ws_bridge
                        _broadcast_connected(manager, provider_fallback=switch_provider)
                    except Exception as e:
                        logger.error(f"Switch failed: {e}")
                        engine = manager.engine
                        bridge = manager.ws_bridge
                        # Use manager._provider (reverted to old) — NOT the
                        # requested switch_provider which failed to start.
                        _broadcast_error_and_connected(
                            manager, f"Switch failed: {e}",
                            provider_fallback=manager._provider or provider,
                        )

                elif msg_type == "resume_session":
                    session_id = msg_data.get("session_id", "")
                    if not session_id:
                        await ws.send_json({
                            "type": "error",
                            "data": {"error": "Missing session_id for resume_session"},
                        })
                        continue

                    try:
                        await manager.resume_session(session_id)
                        engine = manager.engine
                        bridge = manager.ws_bridge
                        _broadcast_connected(manager, provider_fallback=provider)
                    except Exception as e:
                        logger.error(f"Resume session failed: {e}")
                        engine = manager.engine
                        bridge = manager.ws_bridge
                        _broadcast_error_and_connected(manager, f"Resume session failed: {e}", provider_fallback=provider)

                elif msg_type == "new_session":
                    try:
                        await manager.new_session()
                        engine = manager.engine
                        bridge = manager.ws_bridge
                        _broadcast_connected(manager, provider_fallback=provider)
                    except Exception as e:
                        logger.error(f"New session failed: {e}")
                        engine = manager.engine
                        bridge = manager.ws_bridge
                        _broadcast_error_and_connected(manager, f"New session failed: {e}", provider_fallback=provider)

                elif msg_type == "permission_response":
                    request_id = msg_data.get("request_id", "")
                    option_id = msg_data.get("option_id", "")
                    cancelled = msg_data.get("cancelled", False)
                    eng = manager.engine
                    if eng and request_id:
                        eng.resolve_permission(request_id, option_id=option_id, cancelled=cancelled)

                elif msg_type == "clear_history":
                    if manager.engine:
                        manager.engine.clear_history()
                    await ws.send_json({"type": "history_cleared", "data": {}})

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            # Use current bridge (may differ from initial after switch)
            current_bridge = manager.ws_bridge
            if current_bridge:
                await current_bridge.remove_client(ws)

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
