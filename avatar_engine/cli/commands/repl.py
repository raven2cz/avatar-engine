"""REPL command — interactive chat session."""

import asyncio
import json
import logging
import time
from contextlib import contextmanager, nullcontext
import click
from rich.console import Console
from rich.table import Table

from ...config import AvatarConfig
from ...engine import AvatarEngine
from ...types import ProviderType
from ..display import DisplayManager

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    PromptSession = None  # type: ignore[assignment]

    def patch_stdout():
        return nullcontext()

console = Console()


async def _animate_spinner(display: DisplayManager) -> None:
    """Animate thinking spinner while waiting for response text."""
    try:
        while True:
            display.advance_spinner()
            await asyncio.sleep(0.125)
    except asyncio.CancelledError:
        display.clear_status()
        raise


@contextmanager
def _quiet_repl_logs(enabled: bool):
    """Temporarily suppress noisy INFO logs in interactive REPL."""
    if not enabled:
        yield
        return

    logger_names = [
        "avatar_engine.engine",
        "avatar_engine.bridges.gemini",
        "avatar_engine.bridges.claude",
        "avatar_engine.bridges.codex",
    ]
    original_levels = {}
    try:
        for name in logger_names:
            lg = logging.getLogger(name)
            original_levels[name] = lg.level
            lg.setLevel(logging.WARNING)
        yield
    finally:
        for name in logger_names:
            logging.getLogger(name).setLevel(original_levels.get(name, logging.NOTSET))


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
@click.option("--plain/--color", default=False, help="Plain output or Rich color output (default)")
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
    plain: bool,
) -> None:
    """Start an interactive chat session.

    Special commands:

        /exit, /quit  - Exit the session

        /clear        - Clear conversation history

        /health       - Show health status

        /stats        - Show session statistics

        /usage        - Show usage (tokens, cost, requests)

        /tools        - List available MCP tools

        /tool NAME    - Show MCP tool detail

        /mcp          - Show MCP server status

        /sessions     - List available sessions

        /session      - Show current session ID

        /resume ID    - Resume a session by ID
    """
    provider = ctx.obj["provider"]
    config_path = ctx.obj.get("config")
    provider_explicit = ctx.obj.get("provider_explicit", False)
    verbose = ctx.obj.get("verbose", False)
    working_dir = ctx.obj.get("working_dir")

    # Parse inline MCP servers
    mcp_servers = _parse_mcp_servers(mcp, mcp_server)

    asyncio.run(_repl_async(
        provider=provider,
        model=model,
        config_path=config_path,
        provider_explicit=provider_explicit,
        verbose=verbose,
        working_dir=working_dir,
        mcp_servers=mcp_servers,
        thinking_level=thinking_level,
        yolo=yolo,
        timeout=timeout,
        resume_id=resume_id,
        continue_last=continue_last,
        plain=plain,
    ))


async def _repl_async(
    provider: str,
    model: str,
    config_path: str,
    provider_explicit: bool,
    verbose: bool,
    working_dir: str,
    mcp_servers: dict,
    thinking_level: str,
    yolo: bool,
    timeout: int,
    resume_id: str = None,
    continue_last: bool = False,
    plain: bool = True,
) -> None:
    """Async REPL implementation."""
    # Build engine kwargs
    kwargs = {"timeout": timeout}
    if working_dir:
        kwargs["working_dir"] = working_dir

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

    out_console = (
        Console(file=console.file, no_color=True, force_terminal=False, highlight=False)
        if plain
        else console
    )

    # DisplayManager handles all event visualization
    display = DisplayManager(engine, console=out_console, verbose=verbose)

    out_console.print(f"[bold]Avatar Engine REPL[/bold] ({provider})")
    out_console.print("Type '/exit' to quit, '/help' for commands\n")

    if PromptSession is None:
        raise RuntimeError("prompt_toolkit is required for REPL mode. Install avatar-engine[cli].")

    session = PromptSession()

    try:
        with _quiet_repl_logs(enabled=not verbose):
            await engine.start()

        if verbose:
            out_console.print(f"[dim]Session: {engine.session_id}[/dim]\n")

        with patch_stdout():
            while True:
                try:
                    user_input = await session.prompt_async("You: ")

                    # Handle commands
                    if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                        break

                    if user_input.lower() in ("/clear", "/reset"):
                        engine.clear_history()
                        out_console.print("[dim]History cleared[/dim]")
                        continue

                    if user_input.lower() == "/health":
                        health = engine.get_health()
                        out_console.print_json(data=health.__dict__)
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
                        out_console.print_json(data=stats)
                        continue

                    if user_input.lower() == "/usage":
                        _show_usage(engine, out_console)
                        continue

                    if user_input.lower() == "/tools":
                        _show_tools(engine, out_console)
                        continue

                    if user_input.lower().startswith("/tool "):
                        tool_name = user_input[6:].strip()
                        _show_tool_detail(engine, tool_name, out_console)
                        continue

                    if user_input.lower() == "/mcp":
                        _show_mcp_status(engine, out_console)
                        continue

                    if user_input.lower() == "/help":
                        out_console.print("[bold]Commands:[/bold]")
                        out_console.print("  /exit, /quit  - Exit the session")
                        out_console.print("  /clear        - Clear conversation history")
                        out_console.print("  /health       - Show health status")
                        out_console.print("  /stats        - Show session statistics")
                        out_console.print("  /usage        - Show usage (tokens, cost, requests)")
                        out_console.print("  /tools        - List available MCP tools")
                        out_console.print("  /tool NAME    - Show MCP tool detail")
                        out_console.print("  /mcp          - Show MCP server status")
                        out_console.print("  /sessions     - List available sessions")
                        out_console.print("  /session      - Show current session ID")
                        out_console.print("  /resume ID    - Resume a session by ID")
                        out_console.print("  /help         - Show this help")
                        continue

                    if user_input.lower() == "/session":
                        out_console.print(f"[dim]Session: {engine.session_id or 'N/A'}[/dim]")
                        continue

                    if user_input.lower() == "/sessions":
                        caps = engine.session_capabilities
                        if not caps.can_list:
                            out_console.print(f"[yellow]{engine.current_provider} does not support session listing[/yellow]")
                            continue
                        sessions = await engine.list_sessions()
                        if not sessions:
                            out_console.print("[dim]No sessions found[/dim]")
                        else:
                            for s in sessions[:20]:
                                title = f" — {s.title}" if s.title else ""
                                out_console.print(f"  [cyan]{s.session_id[:12]}[/cyan]{title}")
                            out_console.print(f"[dim]{len(sessions)} session(s)[/dim]")
                        continue

                    if user_input.lower().startswith("/resume"):
                        parts = user_input.split(maxsplit=1)
                        if len(parts) < 2:
                            out_console.print("[yellow]Usage: /resume <session-id>[/yellow]")
                            continue
                        sid = parts[1].strip()
                        caps = engine.session_capabilities
                        if not caps.can_load:
                            out_console.print(f"[yellow]{engine.current_provider} does not support session resume[/yellow]")
                            continue
                        try:
                            ok = await engine.resume_session(sid)
                            if ok:
                                out_console.print(f"[green]Resumed session: {sid}[/green]")
                            else:
                                out_console.print(f"[red]Failed to resume: {sid}[/red]")
                        except Exception as e:
                            out_console.print(f"[red]Error: {e}[/red]")
                        continue

                    if not user_input.strip():
                        continue

                    # Send message and stream response
                    display.on_response_start()
                    spinner_task = asyncio.create_task(_animate_spinner(display))
                    printed_header = False

                    try:
                        async for chunk in engine.chat_stream(user_input):
                            if not printed_header:
                                spinner_task.cancel()
                                try:
                                    await spinner_task
                                except asyncio.CancelledError:
                                    pass
                                display.clear_status()
                                out_console.print("Assistant:")
                                printed_header = True
                            out_console.print(chunk, end="")
                    finally:
                        if not spinner_task.done():
                            spinner_task.cancel()
                            try:
                                await spinner_task
                            except asyncio.CancelledError:
                                pass

                    if printed_header:
                        out_console.print("\n")
                    display.on_response_end()

                except KeyboardInterrupt:
                    display.on_response_end()
                    out_console.print("\n[dim]Use '/exit' to quit[/dim]")
                    continue
                except EOFError:
                    break

    except KeyboardInterrupt:
        pass

    except Exception as e:
        out_console.print(f"[red]Error: {e}[/red]")

    finally:
        display.unregister()
        await engine.stop()
        out_console.print("[dim]Session ended[/dim]")


def _show_usage(engine: AvatarEngine, out_console: Console = console) -> None:
    """Display usage statistics as a Rich table."""
    bridge = engine._bridge
    if not bridge:
        out_console.print("[yellow]No active bridge[/yellow]")
        return

    usage = bridge.get_usage()
    table = Table(title=f"Session Usage ({usage.get('provider', '?')})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Session ID", usage.get("session_id") or "—")

    total = usage.get("total_requests", 0)
    ok = usage.get("successful_requests", 0)
    table.add_row("Requests", f"{total} ({ok} ok)")

    inp = usage.get("total_input_tokens", 0)
    out = usage.get("total_output_tokens", 0)
    table.add_row("Input tokens", f"{inp:,}" if inp else "—")
    table.add_row("Output tokens", f"{out:,}" if out else "—")

    cost = usage.get("total_cost_usd", 0)
    if cost:
        table.add_row("Total cost", f"${cost:.4f}")
    else:
        table.add_row("Total cost", "—")

    if "budget_usd" in usage:
        remaining = usage.get("budget_remaining_usd", 0)
        budget = usage["budget_usd"]
        table.add_row("Budget remaining", f"${remaining:.2f} / ${budget:.2f}")

    dur = usage.get("total_duration_ms", 0)
    if total > 0:
        table.add_row("Avg latency", f"{dur // total:,} ms")

    if engine._start_time:
        uptime = int(time.time() - engine._start_time)
        mins, secs = divmod(uptime, 60)
        table.add_row("Uptime", f"{mins}m {secs}s")

    out_console.print(table)


def _show_tools(engine: AvatarEngine, out_console: Console = console) -> None:
    """List MCP tools from the engine's MCP server config."""
    bridge = engine._bridge
    if not bridge:
        out_console.print("[yellow]No active bridge[/yellow]")
        return

    servers = getattr(bridge, "mcp_servers", {})
    if not servers:
        out_console.print("[dim]No MCP servers configured[/dim]")
        return

    table = Table(title="MCP Servers & Tools")
    table.add_column("Server", style="cyan")
    table.add_column("Command")
    table.add_column("Args")

    for name, srv in servers.items():
        cmd = srv.get("command", "?")
        args = " ".join(srv.get("args", []))
        table.add_row(name, cmd, args)

    out_console.print(table)
    out_console.print(f"[dim]{len(servers)} server(s) configured[/dim]")


def _show_tool_detail(engine: AvatarEngine, tool_name: str, out_console: Console = console) -> None:
    """Show detail for a specific MCP server."""
    bridge = engine._bridge
    if not bridge:
        out_console.print("[yellow]No active bridge[/yellow]")
        return

    servers = getattr(bridge, "mcp_servers", {})
    if tool_name not in servers:
        # Try partial match
        matches = [n for n in servers if tool_name.lower() in n.lower()]
        if len(matches) == 1:
            tool_name = matches[0]
        elif matches:
            out_console.print(f"[yellow]Multiple matches: {', '.join(matches)}[/yellow]")
            return
        else:
            out_console.print(f"[red]MCP server not found: {tool_name}[/red]")
            return

    srv = servers[tool_name]
    out_console.print(f"[bold cyan]{tool_name}[/bold cyan]")
    out_console.print(f"  Command: {srv.get('command', '?')}")
    out_console.print(f"  Args:    {' '.join(srv.get('args', []))}")
    if srv.get("env"):
        out_console.print(f"  Env:     {', '.join(f'{k}={v}' for k, v in srv['env'].items())}")


def _show_mcp_status(engine: AvatarEngine, out_console: Console = console) -> None:
    """Show MCP server status."""
    bridge = engine._bridge
    if not bridge:
        out_console.print("[yellow]No active bridge[/yellow]")
        return

    servers = getattr(bridge, "mcp_servers", {})
    if not servers:
        out_console.print("[dim]No MCP servers configured[/dim]")
        return

    table = Table(title="MCP Server Status")
    table.add_column("Server", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Command")

    for name, srv in servers.items():
        cmd = srv.get("command", "?")
        # MCP servers are managed by the provider, we just show config
        table.add_row(name, "configured", cmd)

    out_console.print(table)


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
