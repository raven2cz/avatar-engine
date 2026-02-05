"""
Avatar Engine — unified interface for AI CLI bridges.

Provides a single API for both:
- Claude Code (persistent warm session via --input-format stream-json)
- Gemini CLI (persistent warm session via ACP --experimental-acp with OAuth,
              oneshot fallback with context injection)

The engine hides the difference — you always just call chat()/chat_stream().
"""

import asyncio
import dataclasses
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .bridges import BaseBridge, ClaudeBridge, GeminiBridge
from .config import AvatarConfig
from .utils.logging import setup_logging
from .utils.rate_limit import RateLimiter
from .events import (
    EventEmitter,
    AvatarEvent,
    TextEvent,
    ToolEvent,
    StateEvent,
    ErrorEvent,
    CostEvent,
    ThinkingEvent,
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
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutting_down = False
        self._signal_handlers_installed = False
        self._original_sigterm = None
        self._original_sigint = None
        self._sync_loop: Optional[asyncio.AbstractEventLoop] = None  # For sync wrappers

        # Rate limiter
        if config:
            self._rate_limiter = RateLimiter(
                requests_per_minute=config.rate_limit_rpm,
                burst=config.rate_limit_burst,
                enabled=config.rate_limit_enabled,
            )
        else:
            self._rate_limiter = RateLimiter(enabled=False)

        # Setup logging from config (with file rotation support)
        if config:
            setup_logging(config)

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

        self._shutting_down = False
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

            # Start background health check if configured
            interval = self._get_health_check_interval()
            if interval > 0:
                self._health_check_task = asyncio.create_task(
                    self._health_check_loop(interval)
                )
                logger.debug(f"Started health check task (interval: {interval}s)")

        except Exception as e:
            self.emit(ErrorEvent(
                provider=self._provider.value,
                error=str(e),
                recoverable=False,
            ))
            raise

    async def stop(self) -> None:
        """Stop the engine (async)."""
        self._shutting_down = True

        # Cancel health check task
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        if self._bridge:
            await self._bridge.stop()
        self._started = False
        self._bridge = None
        self._start_time = None

    # === Lifecycle (sync wrappers) ===

    def _get_sync_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create the event loop for sync operations."""
        if self._sync_loop is None or self._sync_loop.is_closed():
            self._sync_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._sync_loop)
        return self._sync_loop

    def start_sync(self) -> None:
        """Start the engine (sync wrapper)."""
        loop = self._get_sync_loop()
        loop.run_until_complete(self.start())

    def stop_sync(self) -> None:
        """Stop the engine (sync wrapper)."""
        if self._sync_loop is None or self._sync_loop.is_closed():
            return  # Already stopped or never started
        try:
            self._sync_loop.run_until_complete(self.stop())
        finally:
            if self._sync_loop and not self._sync_loop.is_closed():
                self._sync_loop.close()
            self._sync_loop = None

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

        # Apply rate limiting
        wait_time = await self._rate_limiter.acquire()
        if wait_time > 0:
            logger.debug(f"Rate limited, waited {wait_time:.2f}s")

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

        # Apply rate limiting
        wait_time = await self._rate_limiter.acquire()
        if wait_time > 0:
            logger.debug(f"Rate limited, waited {wait_time:.2f}s")

        async for chunk in self._bridge.send_stream(message):
            yield chunk

    # === Chat API (sync wrappers) ===

    def chat_sync(self, message: str) -> BridgeResponse:
        """Send a message (sync wrapper)."""
        loop = self._get_sync_loop()
        return loop.run_until_complete(self.chat(message))

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
        # Filter to only valid HealthStatus fields
        valid_fields = {f.name for f in dataclasses.fields(HealthStatus)}
        filtered = {k: v for k, v in health_dict.items() if k in valid_fields}
        return HealthStatus(**filtered)

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

    @property
    def restart_count(self) -> int:
        """Get current restart count."""
        return self._restart_count

    @property
    def max_restarts(self) -> int:
        """Get maximum restart attempts."""
        if self._config:
            return self._config.max_restarts
        return 3

    @property
    def rate_limit_stats(self) -> dict:
        """Get rate limiter statistics."""
        return self._rate_limiter.get_stats()

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
            # Extract session settings if present
            session_cfg = pcfg.get("session", {})
            # Extract structured_output settings if present
            struct_cfg = pcfg.get("structured_output", {})
            return ClaudeBridge(
                executable=pcfg.get("executable", "claude"),
                model=self._model or pcfg.get("model", "claude-sonnet-4-5"),
                allowed_tools=pcfg.get("allowed_tools", []),
                permission_mode=pcfg.get("permission_mode", "acceptEdits"),
                strict_mcp_config=pcfg.get("strict_mcp_config", False),
                max_turns=cost_cfg.get("max_turns"),
                max_budget_usd=cost_cfg.get("max_budget_usd"),
                json_schema=struct_cfg.get("schema") if struct_cfg.get("enabled") else None,
                continue_session=session_cfg.get("continue_last", False),
                resume_session_id=session_cfg.get("resume_id"),
                fallback_model=pcfg.get("fallback_model"),
                debug=pcfg.get("debug", False),
                **common,
            )
        else:
            pcfg = self._config.gemini_config if self._config else self._kwargs
            return GeminiBridge(
                executable=pcfg.get("executable", "gemini"),
                model=self._model or pcfg.get("model", ""),  # Empty = Gemini CLI default
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

        # Thinking events (Gemini 3 with include_thoughts=True)
        if event_type == "thinking":
            self.emit(ThinkingEvent(
                provider=self._provider.value,
                thought=event.get("thought", ""),
            ))

        # Tool events
        elif event_type == "tool_use":
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
        if self._shutting_down:
            return

        self._restart_count += 1
        logger.info(f"Restarting engine (attempt {self._restart_count})")

        # Stop bridge but keep health check task management in stop()
        old_task = self._health_check_task
        self._health_check_task = None  # Prevent stop() from cancelling it

        if self._bridge:
            await self._bridge.stop()
        self._bridge = None
        self._started = False

        # Restore task reference for proper cleanup on next stop()
        self._health_check_task = old_task

        # Start fresh bridge
        self._bridge = self._create_bridge()
        self._setup_bridge_callbacks()

        try:
            await self._bridge.start()
            self._started = True
            logger.info(f"Engine restarted successfully (session: {self._bridge.session_id})")
            self.emit(StateEvent(
                provider=self._provider.value,
                new_state=BridgeState.READY,
            ))
        except Exception as e:
            logger.error(f"Restart failed: {e}")
            self.emit(ErrorEvent(
                provider=self._provider.value,
                error=f"Restart failed: {e}",
                recoverable=self._should_restart(),
            ))
            raise

    def _get_health_check_interval(self) -> int:
        """Get health check interval from config."""
        if self._config:
            return self._config.health_check_interval
        return 30  # Default 30 seconds

    async def _health_check_loop(self, interval: int) -> None:
        """Background task that periodically checks health and triggers restart."""
        while not self._shutting_down:
            try:
                await asyncio.sleep(interval)

                if self._shutting_down or not self._started:
                    break

                if not self.is_healthy():
                    logger.warning("Health check failed, bridge unhealthy")
                    self.emit(ErrorEvent(
                        provider=self._provider.value,
                        error="Bridge health check failed",
                        recoverable=self._should_restart(),
                    ))

                    if self._should_restart():
                        try:
                            await self._restart()
                        except Exception as e:
                            logger.error(f"Auto-restart failed: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    def reset_restart_count(self) -> None:
        """Reset the restart counter (e.g., after successful operation)."""
        self._restart_count = 0

    # === Signal Handling (Graceful Shutdown) ===

    def install_signal_handlers(self) -> None:
        """
        Install SIGTERM and SIGINT handlers for graceful shutdown.

        Call this to enable graceful shutdown when running in containers
        or as a daemon. The engine will cleanly stop when receiving
        SIGTERM (Kubernetes pod termination) or SIGINT (Ctrl+C).

        Example:
            engine = AvatarEngine()
            engine.install_signal_handlers()
            engine.start_sync()
            # ... engine runs until SIGTERM/SIGINT ...
        """
        if self._signal_handlers_installed:
            return

        # Store original handlers so we can restore them
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        self._original_sigint = signal.getsignal(signal.SIGINT)

        def handle_signal(signum: int, frame: Any) -> None:
            sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
            logger.info(f"Received {sig_name}, initiating graceful shutdown...")
            self._initiate_shutdown()

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
        self._signal_handlers_installed = True
        logger.debug("Signal handlers installed for graceful shutdown")

    def remove_signal_handlers(self) -> None:
        """
        Remove signal handlers and restore original behavior.
        """
        if not self._signal_handlers_installed:
            return

        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)

        self._signal_handlers_installed = False
        logger.debug("Signal handlers removed")

    def _initiate_shutdown(self) -> None:
        """Initiate graceful shutdown from signal handler."""
        self._shutting_down = True

        # Try to stop gracefully in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, schedule the stop
            asyncio.create_task(self._graceful_shutdown())
        except RuntimeError:
            # No running loop, use sync shutdown
            try:
                asyncio.run(self._graceful_shutdown())
            except Exception as e:
                logger.error(f"Shutdown error: {e}")
                # Force exit if graceful shutdown fails
                sys.exit(1)

    async def _graceful_shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Performing graceful shutdown...")

        try:
            await self.stop()
            logger.info("Graceful shutdown complete")
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            raise

    async def run_until_signal(self) -> None:
        """
        Run the engine until a termination signal is received.

        This is useful for daemon/server mode where the engine should
        run indefinitely until SIGTERM or SIGINT is received.

        Example:
            async def main():
                engine = AvatarEngine()
                await engine.start()
                await engine.run_until_signal()
                # Engine is now stopped

            asyncio.run(main())
        """
        if not self._started:
            await self.start()

        self.install_signal_handlers()

        # Wait until shutdown is initiated
        try:
            while not self._shutting_down:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

        # Clean up
        self.remove_signal_handlers()

    def run_until_signal_sync(self) -> None:
        """
        Sync version of run_until_signal.

        Example:
            engine = AvatarEngine()
            engine.run_until_signal_sync()
            # Engine runs until SIGTERM/SIGINT
        """
        asyncio.run(self.run_until_signal())
