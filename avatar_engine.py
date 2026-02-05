"""
Avatar Engine — unified interface for AI CLI bridges.

Provides a single API for both:
- Claude Code (persistent warm session via --input-format stream-json)
- Gemini CLI (persistent warm session via ACP --experimental-acp with OAuth,
              oneshot fallback with context injection)

The engine hides the difference — you always just call chat()/chat_stream().
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import yaml

from bridges import (
    BaseBridge,
    BridgeResponse,
    BridgeState,
    ClaudeBridge,
    GeminiBridge,
    Message,
)

logger = logging.getLogger(__name__)


class AvatarEngine:
    """
    High-level engine wrapping CLI bridges.

    Lifecycle::

        engine = AvatarEngine("config.yaml")
        await engine.start()       # Warms up (persistent) or prepares (oneshot)
        resp = await engine.chat("Ahoj!")   # Instant for persistent, cold for oneshot
        resp = await engine.chat("Dál?")    # Still instant (persistent) or cold (oneshot)
        await engine.stop()
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.bridge: Optional[BaseBridge] = None
        self._restart_count = 0

        self._on_message: Optional[Callable[[str], None]] = None
        self._on_state_change: Optional[Callable[[str], None]] = None
        self._on_event: Optional[Callable[[Dict[str, Any]], None]] = None

        log_cfg = self.config.get("logging", {})
        level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
        logging.basicConfig(level=level,
                            format="%(asctime)s %(name)s %(levelname)s %(message)s")
        log_file = log_cfg.get("file", "")
        if log_file:
            logging.getLogger().addHandler(logging.FileHandler(log_file))

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # === Lifecycle ======================================================

    async def start(self) -> None:
        """Create and start bridge. For Claude: warms up the process."""
        self.bridge = self._create_bridge()
        await self.bridge.start()
        logger.info(f"Engine ready: {self.current_provider} "
                     f"({'persistent' if self.bridge.is_persistent else 'oneshot'})"
                     f" session_id={self.bridge.session_id}")

    async def stop(self) -> None:
        if self.bridge:
            await self.bridge.stop()
            self.bridge = None

    async def switch_provider(self, provider: str) -> None:
        await self.stop()
        self.config["provider"] = provider
        self._restart_count = 0
        await self.start()

    @property
    def current_provider(self) -> str:
        return self.config.get("provider", "gemini")

    @property
    def session_id(self) -> Optional[str]:
        return self.bridge.session_id if self.bridge else None

    @property
    def is_warm(self) -> bool:
        """True if the bridge is persistent (warm session)."""
        return self.bridge.is_persistent if self.bridge else False

    # === Callbacks ======================================================

    def on_message(self, cb: Callable[[str], None]) -> None:
        self._on_message = cb
        if self.bridge:
            self.bridge.on_output(cb)

    def on_state_change(self, cb: Callable[[str], None]) -> None:
        self._on_state_change = cb
        if self.bridge:
            self.bridge.on_state_change(lambda s: cb(s.value))

    def on_event(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._on_event = cb
        if self.bridge:
            self.bridge.on_event(cb)

    # === Chat API =======================================================

    async def chat(self, prompt: str) -> BridgeResponse:
        if not self.bridge:
            await self.start()
        resp = await self.bridge.send(prompt)
        if not resp.success and self._should_restart():
            logger.warning(f"Restarting: {resp.error}")
            await self._restart()
            resp = await self.bridge.send(prompt)
        return resp

    async def chat_stream(self, prompt: str) -> AsyncIterator[str]:
        if not self.bridge:
            await self.start()
        async for chunk in self.bridge.send_stream(prompt):
            yield chunk

    # === History ========================================================

    def get_history(self) -> List[Message]:
        return self.bridge.get_history() if self.bridge else []

    def clear_history(self) -> None:
        if self.bridge:
            self.bridge.clear_history()

    # === Internal =======================================================

    def _create_bridge(self) -> BaseBridge:
        provider = self.current_provider.lower()
        pcfg = self.config.get(provider, {})
        acfg = self.config.get("avatar", {})

        wd = acfg.get("working_dir", "") or os.getcwd()
        wd = str(Path(wd).expanduser().resolve())

        common = dict(
            working_dir=wd,
            timeout=pcfg.get("timeout", 120),
            system_prompt=pcfg.get("system_prompt", ""),
            mcp_servers=pcfg.get("mcp_servers", {}),
            env=pcfg.get("env", {}),
        )

        if provider == "gemini":
            bridge = GeminiBridge(
                executable=pcfg.get("executable", "gemini"),
                model=pcfg.get("model", "gemini-2.5-pro"),
                approval_mode=pcfg.get("approval_mode", "yolo"),
                auth_method=pcfg.get("auth_method", "oauth-personal"),
                acp_enabled=pcfg.get("acp_enabled", True),
                context_messages=pcfg.get("context_messages", 20),
                context_max_chars=pcfg.get("context_max_chars", 500),
                generation_config=pcfg.get("generation_config", {}),
                **common,
            )
        elif provider == "claude":
            bridge = ClaudeBridge(
                executable=pcfg.get("executable", "claude"),
                model=pcfg.get("model", "claude-sonnet-4-5"),
                allowed_tools=pcfg.get("allowed_tools", []),
                permission_mode=pcfg.get("permission_mode", "acceptEdits"),
                **common,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

        if self._on_message:
            bridge.on_output(self._on_message)
        if self._on_state_change:
            bridge.on_state_change(lambda s: self._on_state_change(s.value))
        if self._on_event:
            bridge.on_event(self._on_event)

        return bridge

    def _should_restart(self) -> bool:
        acfg = self.config.get("avatar", {})
        if not acfg.get("auto_restart", True):
            return False
        return self._restart_count < acfg.get("max_restarts", 3)

    async def _restart(self) -> None:
        self._restart_count += 1
        await self.stop()
        await self.start()
