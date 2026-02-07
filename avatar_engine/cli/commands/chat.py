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
        mcp_servers=mcp_servers,
        thinking_level=thinking_level,
        yolo=yolo,
        permission_mode=permission_mode,
        max_turns=max_turns,
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
    mcp_servers: dict,
    thinking_level: str,
    yolo: bool,
    permission_mode: str,
    max_turns: int,
    timeout: int,
    resume_id: str = None,
    continue_last: bool = False,
) -> None:
    """Async chat implementation."""
    # Build engine kwargs
    kwargs = {"timeout": timeout}

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
        if model:
            config.model = model
        engine = AvatarEngine(config=config)
    else:
        engine = AvatarEngine(provider=provider, model=model, **kwargs)

    # Verbose/debug event handlers
    if verbose or debug:
        @engine.on(TextEvent)
        def on_text(event: TextEvent) -> None:
            if debug:
                console.print(f"[dim]TEXT:[/dim] {event.text[:80]}...")

        @engine.on(ToolEvent)
        def on_tool(event: ToolEvent) -> None:
            status_color = "green" if event.status == "completed" else "yellow"
            console.print(f"[{status_color}]TOOL: {event.tool_name} ({event.status})[/{status_color}]")

        @engine.on(ThinkingEvent)
        def on_thinking(event: ThinkingEvent) -> None:
            console.print(f"[dim italic]THINKING: {event.thought[:100]}...[/dim italic]")

    try:
        await engine.start()

        if verbose:
            console.print(f"[dim]Provider: {provider}, Session: {engine.session_id}[/dim]")

        if stream and not json_output:
            # Streaming output
            full_response = ""
            async for chunk in engine.chat_stream(message):
                console.print(chunk, end="")
                full_response += chunk
            console.print()  # Final newline
        else:
            # Complete response
            response = await engine.chat(message)

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
        await engine.stop()


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
