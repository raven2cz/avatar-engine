"""REPL command — interactive chat session."""

import asyncio
import json
import click
from rich.console import Console
from rich.prompt import Prompt

from ...config import AvatarConfig
from ...engine import AvatarEngine
from ...events import ToolEvent, ThinkingEvent
from ...types import ProviderType

console = Console()


@click.command()
@click.option("--model", "-m", help="Model name")
@click.option("--mcp", "-M", type=click.Path(exists=True), help="MCP config file")
@click.option(
    "--mcp-server",
    multiple=True,
    help="Inline MCP server: 'name:command arg1 arg2'",
)
@click.option("--thinking-level", type=click.Choice(["minimal", "low", "medium", "high"]))
@click.option("--yolo", is_flag=True, help="Auto-approve tool calls (Gemini/Codex)")
@click.option("--timeout", "-t", type=int, default=120, help="Request timeout")
@click.option("--resume", "resume_id", help="Resume session by ID")
@click.option("--continue", "continue_last", is_flag=True, help="Continue last session")
@click.pass_context
def repl(
    ctx: click.Context,
    model: str,
    mcp: str,
    mcp_server: tuple,
    thinking_level: str,
    yolo: bool,
    timeout: int,
    resume_id: str,
    continue_last: bool,
) -> None:
    """Start an interactive chat session.

    Special commands:

        /exit, /quit  - Exit the session

        /clear        - Clear conversation history

        /health       - Show health status

        /stats        - Show session statistics

        /sessions     - List available sessions

        /session      - Show current session ID

        /resume ID    - Resume a session by ID
    """
    provider = ctx.obj["provider"]
    config_path = ctx.obj.get("config")
    provider_explicit = ctx.obj.get("provider_explicit", False)
    verbose = ctx.obj.get("verbose", False)

    # Parse inline MCP servers
    mcp_servers = _parse_mcp_servers(mcp, mcp_server)

    asyncio.run(_repl_async(
        provider=provider,
        model=model,
        config_path=config_path,
        provider_explicit=provider_explicit,
        verbose=verbose,
        mcp_servers=mcp_servers,
        thinking_level=thinking_level,
        yolo=yolo,
        timeout=timeout,
        resume_id=resume_id,
        continue_last=continue_last,
    ))


async def _repl_async(
    provider: str,
    model: str,
    config_path: str,
    provider_explicit: bool,
    verbose: bool,
    mcp_servers: dict,
    thinking_level: str,
    yolo: bool,
    timeout: int,
    resume_id: str = None,
    continue_last: bool = False,
) -> None:
    """Async REPL implementation."""
    # Build engine kwargs
    kwargs = {"timeout": timeout}

    # Session params
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

    # Event handlers
    @engine.on(ToolEvent)
    def on_tool(event: ToolEvent) -> None:
        if event.status == "started":
            console.print(f"[yellow]  {event.tool_name}[/yellow]")
        elif event.status == "completed":
            console.print(f"[green]  {event.tool_name}[/green]")

    @engine.on(ThinkingEvent)
    def on_thinking(event: ThinkingEvent) -> None:
        if verbose:
            console.print(f"[dim italic]  {event.thought[:80]}...[/dim italic]")

    console.print(f"[bold]Avatar Engine REPL[/bold] ({provider})")
    console.print("Type '/exit' to quit, '/help' for commands\n")

    try:
        await engine.start()

        if verbose:
            console.print(f"[dim]Session: {engine.session_id}[/dim]\n")

        while True:
            try:
                user_input = Prompt.ask("[bold blue]You[/bold blue]")

                # Handle commands
                if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                    break

                if user_input.lower() in ("/clear", "/reset"):
                    engine.clear_history()
                    console.print("[dim]History cleared[/dim]")
                    continue

                if user_input.lower() == "/health":
                    health = engine.get_health()
                    console.print_json(data=health.__dict__)
                    continue

                if user_input.lower() == "/stats":
                    stats = {
                        "session_id": engine.session_id,
                        "provider": engine.current_provider,
                        "is_warm": engine.is_warm,
                        "history_length": len(engine.get_history()),
                        "restart_count": engine.restart_count,
                        "rate_limit": engine.rate_limit_stats,
                    }
                    console.print_json(data=stats)
                    continue

                if user_input.lower() == "/help":
                    console.print("[bold]Commands:[/bold]")
                    console.print("  /exit, /quit  - Exit the session")
                    console.print("  /clear        - Clear conversation history")
                    console.print("  /health       - Show health status")
                    console.print("  /stats        - Show session statistics")
                    console.print("  /sessions     - List available sessions")
                    console.print("  /session      - Show current session ID")
                    console.print("  /resume ID    - Resume a session by ID")
                    console.print("  /help         - Show this help")
                    continue

                if user_input.lower() == "/session":
                    console.print(f"[dim]Session: {engine.session_id or 'N/A'}[/dim]")
                    continue

                if user_input.lower() == "/sessions":
                    caps = engine.session_capabilities
                    if not caps.can_list:
                        console.print(f"[yellow]{engine.current_provider} does not support session listing[/yellow]")
                        continue
                    sessions = await engine.list_sessions()
                    if not sessions:
                        console.print("[dim]No sessions found[/dim]")
                    else:
                        for s in sessions[:20]:
                            title = f" — {s.title}" if s.title else ""
                            console.print(f"  [cyan]{s.session_id[:12]}[/cyan]{title}")
                        console.print(f"[dim]{len(sessions)} session(s)[/dim]")
                    continue

                if user_input.lower().startswith("/resume"):
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2:
                        console.print("[yellow]Usage: /resume <session-id>[/yellow]")
                        continue
                    sid = parts[1].strip()
                    caps = engine.session_capabilities
                    if not caps.can_load:
                        console.print(f"[yellow]{engine.current_provider} does not support session resume[/yellow]")
                        continue
                    try:
                        ok = await engine.resume_session(sid)
                        if ok:
                            console.print(f"[green]Resumed session: {sid}[/green]")
                        else:
                            console.print(f"[red]Failed to resume: {sid}[/red]")
                    except Exception as e:
                        console.print(f"[red]Error: {e}[/red]")
                    continue

                if not user_input.strip():
                    continue

                # Send message and stream response
                console.print("[bold green]Assistant[/bold green]:")
                async for chunk in engine.chat_stream(user_input):
                    console.print(chunk, end="")
                console.print("\n")

            except KeyboardInterrupt:
                console.print("\n[dim]Use '/exit' to quit[/dim]")
                continue

    except KeyboardInterrupt:
        pass

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

    finally:
        await engine.stop()
        console.print("[dim]Session ended[/dim]")


def _parse_mcp_servers(mcp_file: str, mcp_servers: tuple) -> dict:
    """Parse MCP servers from file and inline arguments."""
    servers = {}

    # Load from file
    if mcp_file:
        from pathlib import Path

        content = Path(mcp_file).read_text()
        data = json.loads(content)
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
