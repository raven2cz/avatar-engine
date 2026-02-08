"""
Engine lifecycle manager for the web server.

Creates and manages a single AvatarEngine instance (one engine per server).
Exposes the engine and WebSocket bridge for use by FastAPI routes.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import AvatarConfig
from ..engine import AvatarEngine
from ..types import ProviderType
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
        model: Optional[str] = None,
        config_path: Optional[str] = None,
        working_dir: Optional[str] = None,
        system_prompt: str = "",
        **kwargs: Any,
    ) -> None:
        self._provider = provider
        self._model = model
        self._config_path = config_path
        self._working_dir = working_dir or str(Path.cwd())
        self._system_prompt = system_prompt
        self._kwargs = kwargs

        self._engine: Optional[AvatarEngine] = None
        self._ws_bridge: Optional[WebSocketBridge] = None

    @property
    def engine(self) -> Optional[AvatarEngine]:
        return self._engine

    @property
    def ws_bridge(self) -> Optional[WebSocketBridge]:
        return self._ws_bridge

    @property
    def is_started(self) -> bool:
        return self._engine is not None and self._engine._started

    async def start(self) -> None:
        """Create and start the engine + WebSocket bridge."""
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

        # Start engine
        await self._engine.start()

        logger.info(
            f"Web session started: provider={self._engine.current_provider} "
            f"session_id={self._engine.session_id}"
        )

    async def shutdown(self) -> None:
        """Stop the engine and clean up."""
        if self._ws_bridge:
            self._ws_bridge.unregister()
            self._ws_bridge = None

        if self._engine:
            await self._engine.stop()
            self._engine = None

        logger.info("Web session shut down")

    async def ensure_started(self) -> AvatarEngine:
        """Ensure engine is started and return it."""
        if not self.is_started:
            await self.start()
        assert self._engine is not None
        return self._engine
