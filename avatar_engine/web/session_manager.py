"""
Engine lifecycle manager for the web server.

Creates and manages a single AvatarEngine instance (one engine per server).
Exposes the engine and WebSocket bridge for use by FastAPI routes.
"""

import logging
from pathlib import Path
from typing import Any

from ..engine import AvatarEngine
from .bridge import WebSocketBridge

logger = logging.getLogger(__name__)


class EngineSessionManager:
    """Manages AvatarEngine lifecycle for the web server.

    One engine per server instance (matches Synapse's single-user pattern).

    Usage:
        manager = EngineSessionManager(provider="gemini")
        await manager.start()
        # ... use manager.engine and manager.ws_bridge ...
        await manager.shutdown()
    """

    def __init__(
        self,
        provider: str = "gemini",
        model: str | None = None,
        config_path: str | None = None,
        working_dir: str | None = None,
        system_prompt: str = "",
        **kwargs: Any,
    ) -> None:
        self._provider = provider
        self._model = model
        self._config_path = config_path
        self._working_dir = working_dir or str(Path.cwd())
        self._system_prompt = system_prompt
        self._kwargs = kwargs

        self._engine: AvatarEngine | None = None
        self._ws_bridge: WebSocketBridge | None = None
        self._ready: bool = False

    @property
    def engine(self) -> AvatarEngine | None:
        return self._engine

    @property
    def ws_bridge(self) -> WebSocketBridge | None:
        return self._ws_bridge

    @property
    def is_started(self) -> bool:
        return self._engine is not None and self._engine._started

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def prepare(self) -> None:
        """Create engine + WS bridge (fast, non-blocking).

        Does NOT start the engine — call start_engine() after WS clients
        can connect so they receive state events during initialization.
        """
        if self._engine is not None:
            return

        # Create engine from config file or parameters
        if self._config_path:
            self._engine = AvatarEngine.from_config(self._config_path)
        else:
            self._engine = AvatarEngine(
                provider=self._provider,
                model=self._model,
                working_dir=self._working_dir,
                system_prompt=self._system_prompt,
                **self._kwargs,
            )

        # Create WS bridge (registers event handlers on engine)
        self._ws_bridge = WebSocketBridge(self._engine)
        self._ready = False

    async def start_engine(self) -> None:
        """Start engine (slow — ACP spawn, auth, session). Call after prepare()."""
        if self._ready:
            return
        if not self._engine:
            raise RuntimeError("Call prepare() before start_engine()")
        await self._engine.start()
        self._ready = True
        logger.info(
            f"Web session started: provider={self._engine.current_provider} "
            f"session_id={self._engine.session_id}"
        )

    async def start(self) -> None:
        """Create and start the engine + WebSocket bridge.

        Convenience wrapper combining prepare() + start_engine().
        Used by switch/resume/new_session where WS is already connected.
        """
        await self.prepare()
        await self.start_engine()

    async def shutdown(self) -> None:
        """Stop the engine and clean up."""
        self._ready = False

        if self._ws_bridge:
            self._ws_bridge.unregister()
            self._ws_bridge = None

        if self._engine:
            await self._engine.stop()
            self._engine = None

        logger.info("Web session shut down")

    def _save_clients(self) -> set:
        """Save connected WebSocket clients before bridge teardown."""
        if self._ws_bridge:
            return set(self._ws_bridge._clients)
        return set()

    async def _restore_clients(self, saved_clients: set) -> None:
        """Restore saved WebSocket clients to the new bridge."""
        if self._ws_bridge and saved_clients:
            for ws in saved_clients:
                await self._ws_bridge.add_client(ws)

    async def switch(
        self,
        provider: str,
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Switch provider and/or model by restarting the engine.

        Preserves connected WebSocket clients across the restart.
        Options (if provided) are merged into engine kwargs — used for
        generation_config, max_turns, max_budget_usd, etc.
        Returns info dict with new provider/model/session_id.
        """
        old_provider = self._provider
        old_model = self._model
        old_kwargs = dict(self._kwargs)

        saved_clients = self._save_clients()

        self._provider = provider
        self._model = model
        if options:
            self._kwargs.update(options)

        try:
            await self.shutdown()
            await self.start()
            await self._restore_clients(saved_clients)
            logger.info(f"Switched to provider={provider} model={model}")
            return {
                "provider": self._provider,
                "model": self._model,
                "session_id": self._engine.session_id if self._engine else None,
            }
        except Exception as e:
            logger.error(f"Switch failed: {e}, reverting to {old_provider}/{old_model}")
            self._provider = old_provider
            self._model = old_model
            self._kwargs = old_kwargs
            try:
                await self.shutdown()
                await self.start()
                await self._restore_clients(saved_clients)
            except Exception:
                pass
            raise

    async def resume_session(self, session_id: str) -> dict[str, Any]:
        """Resume a previous session by restarting the engine with that session ID.

        Same pattern as switch(): save clients → set resume ID → restart → restore.
        """
        saved_clients = self._save_clients()
        self._kwargs["resume_session_id"] = session_id

        try:
            await self.shutdown()
            await self.start()
            await self._restore_clients(saved_clients)
            logger.info(f"Resumed session={session_id}")
            return {
                "provider": self._provider,
                "model": self._model,
                "session_id": self._engine.session_id if self._engine else None,
            }
        except Exception as e:
            logger.error(f"Resume session failed: {e}")
            self._kwargs.pop("resume_session_id", None)
            try:
                await self.shutdown()
                await self.start()
                await self._restore_clients(saved_clients)
            except Exception:
                pass
            raise

    async def new_session(self) -> dict[str, Any]:
        """Start a fresh session by restarting the engine without a resume ID.

        Same pattern as switch(): save clients → clear resume ID → restart → restore.
        """
        saved_clients = self._save_clients()
        self._kwargs.pop("resume_session_id", None)

        try:
            await self.shutdown()
            await self.start()
            await self._restore_clients(saved_clients)
            logger.info("Started new session")
            return {
                "provider": self._provider,
                "model": self._model,
                "session_id": self._engine.session_id if self._engine else None,
            }
        except Exception as e:
            logger.error(f"New session failed: {e}")
            try:
                await self.shutdown()
                await self.start()
                await self._restore_clients(saved_clients)
            except Exception:
                pass
            raise

    async def ensure_started(self) -> AvatarEngine:
        """Ensure engine is started and return it."""
        if not self.is_started:
            await self.start()
        assert self._engine is not None
        return self._engine
