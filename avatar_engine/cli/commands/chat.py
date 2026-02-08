"""Chat command — single message interaction."""

import asyncio
import gc
import json
import sys
import click
from rich.console import Console
from rich.markdown import Markdown

from ...config import AvatarConfig
from ...engine import AvatarEngine
from ...events import TextEvent, ToolEvent, ThinkingEvent
from ...types import ProviderType
from ..display import DisplayManager

console = Console()


@click.command()
@click.argument("message")
@click.option("--model", "-m", help="Model name")
@click.option("--stream/--no-stream", default=True, help="Stream output")
@click.option("--json", "json_output", is_flag=True, help="JSON output format")
@click.option("--mcp", "-M", type=click.Path(exists=True), help="MCP config file")
@click.option(
    "--mcp-server",
    multiple=True,
    help="Inline MCP server: 'name:command arg1 arg2'",
)
@click.option("--thinking-level", type=click.Choice(["minimal", "low", "medium", "high"]))
@click.option("--yolo", is_flag=True, help="Auto-approve tool calls (Gemini/Codex)")
@click.option("--permission-mode", help="Permission mode (Claude)")
@click.option("--max-turns", type=int, help="Max turns (Claude)")
@click.option("--allowed-tools", help="Comma-separated allowed tools (Claude)")
@click.option("--timeout", "-t", type=int, default=120, help="Request timeout")
@click.option("--resume", "resume_id", help="Resume session by ID")
@click.option("--continue", "continue_last", is_flag=True, help="Continue last session")
@click.pass_context
def chat(
    ctx: click.Context,
    message: str,
    model: str,
    stream: bool,
    json_output: bool,
    mcp: str,
    mcp_server: tuple,
    thinking_level: str,
    yolo: bool,
    permission_mode: str,
    max_turns: int,
    allowed_tools: str,
    timeout: int,
    resume_id: str,
    continue_last: bool,
) -> None:
    """Send a message and get a response.

    Examples:

        avatar chat "What is 2+2?"

        avatar -p claude chat "Write a haiku"

        avatar chat --json "Hello" | jq .content
    """
    provider = ctx.obj["provider"]
    config_path = ctx.obj.get("config")
    provider_explicit = ctx.obj.get("provider_explicit", False)
    verbose = ctx.obj.get("verbose", False)
    debug = ctx.obj.get("debug", False)
    working_dir = ctx.obj.get("working_dir")

    # Parse inline MCP servers
    mcp_servers = _parse_mcp_servers(mcp, mcp_server)

    _run_async_clean(_chat_async(
        message=message,
        provider=provider,
        model=model,
        config_path=config_path,
        provider_explicit=provider_explicit,
        stream=stream,
        json_output=json_output,
        verbose=verbose,
        debug=debug,
        working_dir=working_dir,
        mcp_servers=mcp_servers,
        thinking_level=thinking_level,
        yolo=yolo,
        permission_mode=permission_mode,
        max_turns=max_turns,
        allowed_tools=allowed_tools,
        timeout=timeout,
        resume_id=resume_id,
        continue_last=continue_last,
    ))


async def _chat_async(
    message: str,
    provider: str,
    model: str,
    config_path: str,
    provider_explicit: bool,
    stream: bool,
    json_output: bool,
    verbose: bool,
    debug: bool,
    working_dir: str,
    mcp_servers: dict,
    thinking_level: str,
    yolo: bool,
    permission_mode: str,
    max_turns: int,
    allowed_tools: str,
    timeout: int,
    resume_id: str = None,
    continue_last: bool = False,
) -> None:
    """Async chat implementation."""
    # Build engine kwargs
    kwargs = {"timeout": timeout}
    if working_dir:
        kwargs["working_dir"] = working_dir

    # Session params (provider-agnostic — engine routes to correct bridge)
    if resume_id:
        kwargs["resume_session_id"] = resume_id
    if continue_last:
        kwargs["continue_last"] = True

    if provider == "gemini":
        if mcp_servers:
            kwargs["mcp_servers"] = mcp_servers
        gen_config = {}
        if thinking_level:
            gen_config["thinking_level"] = thinking_level
        if gen_config:
            kwargs["generation_config"] = gen_config
        if yolo:
            kwargs["approval_mode"] = "yolo"
    elif provider == "claude":
        if mcp_servers:
            kwargs["mcp_servers"] = mcp_servers
        if permission_mode:
            kwargs["permission_mode"] = permission_mode
        if max_turns:
            kwargs["max_turns"] = max_turns
        if allowed_tools:
            kwargs["allowed_tools"] = [t.strip() for t in allowed_tools.split(",")]
    elif provider == "codex":
        if mcp_servers:
            kwargs["mcp_servers"] = mcp_servers
        if yolo:
            kwargs["auto_approve"] = True

    # Create engine
    if config_path:
        config = AvatarConfig.load(config_path)
        # CLI flags override config file
        if provider_explicit:
            config.provider = ProviderType(provider)
            # Clear model when switching providers — each has its own default
            if not model:
                config.model = None
        if model:
            config.model = model
        engine = AvatarEngine(config=config)
    else:
        engine = AvatarEngine(provider=provider, model=model, **kwargs)

    # DisplayManager handles event visualization (always active for tool/thinking display)
    display = DisplayManager(engine, console=console, verbose=verbose or debug)

    # Debug-only raw text logging
    if debug:
        @engine.on(TextEvent)
        def on_text_debug(event: TextEvent) -> None:
            console.print(f"[dim]TEXT:[/dim] {event.text[:80]}...")

    try:
        await engine.start()

        if verbose:
            console.print(f"[dim]Provider: {provider}, Session: {engine.session_id}[/dim]")

        if stream and not json_output:
            # Streaming output
            display.on_response_start()
            spinner_task = asyncio.create_task(_animate_spinner(display))
            printed_header = False
            full_response = ""

            try:
                async for chunk in engine.chat_stream(message):
                    if not printed_header:
                        spinner_task.cancel()
                        try:
                            await spinner_task
                        except asyncio.CancelledError:
                            pass
                        display.clear_status()
                        printed_header = True
                    console.print(chunk, end="")
                    full_response += chunk
            finally:
                if not spinner_task.done():
                    spinner_task.cancel()
                    try:
                        await spinner_task
                    except asyncio.CancelledError:
                        pass

            console.print()  # Final newline
            display.on_response_end()
        else:
            # Complete response
            display.on_response_start()
            spinner_task = asyncio.create_task(_animate_spinner(display))
            try:
                response = await engine.chat(message)
            finally:
                spinner_task.cancel()
                try:
                    await spinner_task
                except asyncio.CancelledError:
                    pass
                display.clear_status()

            if json_output:
                result = {
                    "content": response.content,
                    "success": response.success,
                    "duration_ms": response.duration_ms,
                    "session_id": response.session_id,
                    "provider": provider,
                }
                if response.cost_usd:
                    result["cost_usd"] = response.cost_usd
                if response.tool_calls:
                    result["tool_calls"] = response.tool_calls
                console.print_json(json.dumps(result))
            else:
                console.print(Markdown(response.content))

    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    finally:
        display.unregister()
        await engine.stop()


async def _animate_spinner(display: DisplayManager) -> None:
    """Animate thinking spinner while waiting for response text."""
    try:
        while True:
            display.advance_spinner()
            await asyncio.sleep(0.125)
    except asyncio.CancelledError:
        display.clear_status()
        raise


def _run_async_clean(coro: object) -> None:
    """Run a coroutine with clean subprocess transport shutdown.

    Suppresses the harmless "Event loop is closed" RuntimeError that
    occurs when BaseSubprocessTransport.__del__ fires during interpreter
    shutdown after the loop has been closed.  This is a known CPython
    issue with asyncio subprocess transports — the process is already
    dead and the OS has reclaimed the pipes; the error is purely cosmetic.

    The hook stays installed until process exit because the transport
    __del__ fires during interpreter shutdown, after asyncio.run() returns.
    """
    _prev_hook = sys.unraisablehook

    def _suppress_transport_error(unraisable: object) -> None:
        if (
            isinstance(unraisable.exc_value, RuntimeError)
            and "Event loop is closed" in str(unraisable.exc_value)
        ):
            return  # suppress
        _prev_hook(unraisable)

    sys.unraisablehook = _suppress_transport_error
    asyncio.run(coro)


def _parse_mcp_servers(mcp_file: str, mcp_servers: tuple) -> dict:
    """Parse MCP servers from file and inline arguments."""
    servers = {}

    # Load from file
    if mcp_file:
        import json as json_module
        from pathlib import Path

        content = Path(mcp_file).read_text()
        data = json_module.loads(content)
        servers.update(data.get("mcpServers", {}))

    # Parse inline servers: "name:command arg1 arg2"
    for srv in mcp_servers:
        if ":" not in srv:
            continue
        name, rest = srv.split(":", 1)
        parts = rest.split()
        if parts:
            servers[name] = {
                "command": parts[0],
                "args": parts[1:] if len(parts) > 1 else [],
            }

    return servers
