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
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .bridges import BaseBridge, ClaudeBridge, GeminiBridge
from .config import AvatarConfig
from .events import (
    EventEmitter,
    AvatarEvent,
    TextEvent,
    ToolEvent,
    StateEvent,
    ErrorEvent,
    CostEvent,
)
from .types import BridgeResponse, BridgeState, HealthStatus, Message, ProviderType

logger = logging.getLogger(__name__)


class AvatarEngine(EventEmitter):
    """
    Avatar Engine — AI assistant integration library.

    Provides a unified interface to Claude Code and Gemini CLI
    with event-driven architecture for GUI integration.

    Usage (async):
        engine = AvatarEngine(provider="gemini")
        await engine.start()
        response = await engine.chat("Hello!")
        await engine.stop()

    Usage (sync):
        engine = AvatarEngine.from_config("config.yaml")
        engine.start_sync()
        response = engine.chat_sync("Hello!")
        engine.stop_sync()

    Usage (event-driven):
        engine = AvatarEngine()

        @engine.on(TextEvent)
        def on_text(event):
            print(event.text, end="", flush=True)

        engine.start_sync()
        engine.chat_sync("Tell me a story")
    """

    def __init__(
        self,
        provider: Union[str, ProviderType] = ProviderType.GEMINI,
        model: Optional[str] = None,
        working_dir: Optional[str] = None,
        timeout: int = 120,
        system_prompt: str = "",
        config: Optional[AvatarConfig] = None,
        **kwargs: Any,
    ):
        """
        Initialize Avatar Engine.

        Args:
            provider: AI provider ("gemini" or "claude")
            model: Model name (e.g., "gemini-3-pro-preview", "claude-sonnet-4-5")
            working_dir: Working directory for the AI session
            timeout: Request timeout in seconds
            system_prompt: System prompt for the AI
            config: Optional AvatarConfig object (overrides other params)
            **kwargs: Additional provider-specific parameters
        """
        super().__init__()  # Initialize EventEmitter

        if config:
            self._config = config
            self._provider = config.provider
            self._model = config.model
            self._working_dir = config.get_working_dir()
            self._timeout = config.timeout
            self._system_prompt = config.system_prompt
            self._kwargs = config.provider_kwargs
        else:
            self._config = None
            self._provider = ProviderType(provider) if isinstance(provider, str) else provider
            self._model = model
            self._working_dir = working_dir or str(Path.cwd())
            self._timeout = timeout
            self._system_prompt = system_prompt
            self._kwargs = kwargs

        self._bridge: Optional[BaseBridge] = None
        self._started = False
        self._start_time: Optional[float] = None
        self._restart_count = 0

        # Setup logging
        if config:
            level = getattr(logging, config.log_level.upper(), logging.INFO)
            logging.basicConfig(
                level=level,
                format="%(asctime)s %(name)s %(levelname)s %(message)s"
            )
            if config.log_file:
                logging.getLogger().addHandler(logging.FileHandler(config.log_file))

    @classmethod
    def from_config(cls, config_path: str) -> "AvatarEngine":
        """
        Create engine from YAML config file.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            AvatarEngine instance
        """
        config = AvatarConfig.load(config_path)
        return cls(config=config)

    # === Lifecycle (async) ===

    async def start(self) -> None:
        """Start the engine (async)."""
        if self._started:
            return

        self._bridge = self._create_bridge()
        self._setup_bridge_callbacks()

        try:
            await self._bridge.start()
            self._started = True
            self._start_time = time.time()
            logger.info(
                f"Engine ready: {self._provider.value} "
                f"({'persistent' if self._bridge.is_persistent else 'oneshot'}) "
                f"session_id={self._bridge.session_id}"
            )
        except Exception as e:
            self.emit(ErrorEvent(
                provider=self._provider.value,
                error=str(e),
                recoverable=False,
            ))
            raise

    async def stop(self) -> None:
        """Stop the engine (async)."""
        if self._bridge:
            await self._bridge.stop()
        self._started = False
        self._bridge = None
        self._start_time = None

    # === Lifecycle (sync wrappers) ===

    def start_sync(self) -> None:
        """Start the engine (sync wrapper)."""
        asyncio.run(self.start())

    def stop_sync(self) -> None:
        """Stop the engine (sync wrapper)."""
        asyncio.run(self.stop())

    # === Chat API (async) ===

    async def chat(self, message: str) -> BridgeResponse:
        """
        Send a message and get response (async).

        Args:
            message: User message to send

        Returns:
            BridgeResponse with content and metadata
        """
        if not self._started:
            await self.start()

        response = await self._bridge.send(message)

        # Auto-restart on failure
        if not response.success and self._should_restart():
            logger.warning(f"Restarting due to error: {response.error}")
            await self._restart()
            response = await self._bridge.send(message)

        # Emit cost event
        if response.cost_usd:
            self.emit(CostEvent(
                provider=self._provider.value,
                cost_usd=response.cost_usd,
                input_tokens=response.token_usage.get("input", 0) if response.token_usage else 0,
                output_tokens=response.token_usage.get("output", 0) if response.token_usage else 0,
            ))

        return response

    async def chat_stream(self, message: str) -> AsyncIterator[str]:
        """
        Stream response chunks (async generator).

        Args:
            message: User message to send

        Yields:
            Text chunks as they arrive
        """
        if not self._started:
            await self.start()

        async for chunk in self._bridge.send_stream(message):
            yield chunk

    # === Chat API (sync wrappers) ===

    def chat_sync(self, message: str) -> BridgeResponse:
        """Send a message (sync wrapper)."""
        return asyncio.run(self.chat(message))

    def chat_async(
        self,
        message: str,
        callback: Callable[[BridgeResponse], None],
    ) -> asyncio.Task:
        """
        Send message asynchronously with callback (for GUI).

        Args:
            message: User message to send
            callback: Function to call with the response

        Returns:
            Task that can be cancelled if needed
        """
        async def _run():
            response = await self.chat(message)
            callback(response)

        return asyncio.create_task(_run())

    # === Provider switching ===

    async def switch_provider(self, provider: Union[str, ProviderType]) -> None:
        """
        Switch to a different provider.

        Args:
            provider: New provider to use
        """
        await self.stop()
        self._provider = ProviderType(provider) if isinstance(provider, str) else provider
        self._restart_count = 0
        await self.start()

    # === Health ===

    def is_healthy(self) -> bool:
        """Quick health check."""
        return self._bridge is not None and self._bridge.is_healthy()

    def get_health(self) -> HealthStatus:
        """Detailed health status."""
        if not self._bridge:
            return HealthStatus(
                healthy=False,
                state="not_started",
                provider=self._provider.value,
            )

        health_dict = self._bridge.check_health()
        health_dict["uptime_seconds"] = time.time() - self._start_time if self._start_time else 0
        return HealthStatus(**health_dict)

    # === History ===

    def get_history(self) -> List[Message]:
        """Get conversation history."""
        if self._bridge:
            return self._bridge.get_history()
        return []

    def clear_history(self) -> None:
        """Clear conversation history."""
        if self._bridge:
            self._bridge.clear_history()

    # === Properties ===

    @property
    def current_provider(self) -> str:
        """Get current provider name."""
        return self._provider.value

    @property
    def session_id(self) -> Optional[str]:
        """Get current session ID."""
        return self._bridge.session_id if self._bridge else None

    @property
    def is_warm(self) -> bool:
        """True if the bridge is persistent (warm session)."""
        return self._bridge.is_persistent if self._bridge else False

    # === Internal ===

    def _create_bridge(self) -> BaseBridge:
        """Create the appropriate bridge for the provider."""
        common = dict(
            working_dir=self._working_dir,
            timeout=self._timeout,
            system_prompt=self._system_prompt,
        )

        if self._config:
            # Use full config from file
            pcfg = self._config.get_provider_config()
            common["mcp_servers"] = pcfg.get("mcp_servers", {})
            common["env"] = pcfg.get("env", {})

        if self._provider == ProviderType.CLAUDE:
            pcfg = self._config.claude_config if self._config else self._kwargs
            # Extract cost_control settings if present
            cost_cfg = pcfg.get("cost_control", {})
            return ClaudeBridge(
                executable=pcfg.get("executable", "claude"),
                model=self._model or pcfg.get("model", "claude-sonnet-4-5"),
                allowed_tools=pcfg.get("allowed_tools", []),
                permission_mode=pcfg.get("permission_mode", "acceptEdits"),
                strict_mcp_config=pcfg.get("strict_mcp_config", False),
                max_turns=cost_cfg.get("max_turns"),
                max_budget_usd=cost_cfg.get("max_budget_usd"),
                **common,
            )
        else:
            pcfg = self._config.gemini_config if self._config else self._kwargs
            return GeminiBridge(
                executable=pcfg.get("executable", "gemini"),
                model=self._model or pcfg.get("model", "gemini-3-pro-preview"),
                approval_mode=pcfg.get("approval_mode", "yolo"),
                auth_method=pcfg.get("auth_method", "oauth-personal"),
                acp_enabled=pcfg.get("acp_enabled", True),
                context_messages=pcfg.get("context_messages", 20),
                context_max_chars=pcfg.get("context_max_chars", 500),
                generation_config=pcfg.get("generation_config", {}),
                **common,
            )

    def _setup_bridge_callbacks(self) -> None:
        """Connect bridge callbacks to event emitter."""
        # Text output callback
        self._bridge.on_output(lambda text: self.emit(TextEvent(
            provider=self._provider.value,
            text=text,
        )))

        # State change callback
        def on_state_change(state: BridgeState) -> None:
            self.emit(StateEvent(
                provider=self._provider.value,
                new_state=state,
            ))
        self._bridge.on_state_change(on_state_change)

        # Raw event callback
        self._bridge.on_event(self._handle_raw_event)

    def _handle_raw_event(self, event: Dict[str, Any]) -> None:
        """Process raw events from bridge and emit typed events."""
        event_type = event.get("type", "")

        # Tool events
        if event_type == "tool_use":
            self.emit(ToolEvent(
                provider=self._provider.value,
                tool_name=event.get("tool_name", event.get("name", "")),
                tool_id=event.get("tool_id", event.get("id", "")),
                parameters=event.get("parameters", event.get("input", {})),
                status="started",
            ))
        elif event_type == "tool_result":
            self.emit(ToolEvent(
                provider=self._provider.value,
                tool_name=event.get("tool_name", ""),
                tool_id=event.get("tool_id", ""),
                status="completed" if event.get("success", True) else "failed",
                result=event.get("result"),
                error=event.get("error"),
            ))

    def _should_restart(self) -> bool:
        """Check if auto-restart is allowed."""
        if self._config:
            if not self._config.auto_restart:
                return False
            return self._restart_count < self._config.max_restarts
        return self._restart_count < 3

    async def _restart(self) -> None:
        """Restart the engine."""
        self._restart_count += 1
        await self.stop()
        await self.start()
