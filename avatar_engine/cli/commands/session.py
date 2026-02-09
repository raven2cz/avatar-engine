"""Session management commands."""

import asyncio
import click
from rich.console import Console
from rich.table import Table

from ...config import AvatarConfig
from ...engine import AvatarEngine
from ...types import ProviderType

console = Console()


@click.group()
@click.option(
    "--provider", "-p",
    type=click.Choice(["gemini", "claude", "codex"]),
    default=None,
    help="AI provider (default: from config or gemini)",
)
@click.pass_context
def session(ctx: click.Context, provider: str) -> None:
    """Manage provider sessions.

    List and inspect sessions stored by the provider (Gemini, Claude, Codex).
    Sessions are auto-saved by each provider — no manual save needed.

    Examples:

        avatar session list

        avatar session -p codex list

        avatar session info abc123
    """
    ctx.ensure_object(dict)
    provider_explicit = provider is not None
    if not provider:
        provider = "gemini"
    ctx.obj["session_provider"] = provider
    ctx.obj["session_provider_explicit"] = provider_explicit


@session.command("list")
@click.option("--limit", "-n", type=int, default=20, help="Max sessions to show")
@click.pass_context
def session_list(ctx: click.Context, limit: int) -> None:
    """List available sessions for the current provider."""
    provider = ctx.obj["session_provider"]
    config_path = ctx.obj.get("config")
    provider_explicit = ctx.obj.get("session_provider_explicit", False)

    asyncio.run(_session_list_async(provider, config_path, provider_explicit, limit))


async def _session_list_async(
    provider: str, config_path: str, provider_explicit: bool, limit: int
) -> None:
    """List sessions async."""
    engine = _build_engine(provider, config_path, provider_explicit)

    try:
        await engine.start()

        caps = engine.session_capabilities
        if not caps.can_list:
            console.print(f"[yellow]{provider} does not support session listing[/yellow]")
            return

        sessions = await engine.list_sessions()

        if not sessions:
            console.print("[dim]No sessions found[/dim]")
            return

        table = Table(title=f"Sessions ({provider})")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title")
        table.add_column("Directory")
        table.add_column("Updated", style="dim")

        for s in sessions[:limit]:
            title = s.title or "-"
            if len(title) > 40:
                title = title[:37] + "..."
            cwd = s.cwd or "-"
            if len(cwd) > 30:
                cwd = "..." + cwd[-27:]
            table.add_row(
                s.session_id[:12],
                title,
                cwd,
                s.updated_at or "-",
            )

        console.print(table)
        console.print(f"[dim]{len(sessions)} session(s) total[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    finally:
        await engine.stop()


@session.command("info")
@click.argument("session_id")
@click.pass_context
def session_info(ctx: click.Context, session_id: str) -> None:
    """Show details for a specific session."""
    provider = ctx.obj["session_provider"]
    config_path = ctx.obj.get("config")
    provider_explicit = ctx.obj.get("session_provider_explicit", False)

    asyncio.run(_session_info_async(provider, config_path, provider_explicit, session_id))


async def _session_info_async(
    provider: str, config_path: str, provider_explicit: bool, session_id: str
) -> None:
    """Show session info async."""
    engine = _build_engine(provider, config_path, provider_explicit)

    try:
        await engine.start()

        caps = engine.session_capabilities
        if not caps.can_list:
            console.print(f"[yellow]{provider} does not support session listing[/yellow]")
            return

        sessions = await engine.list_sessions()
        match = [s for s in sessions if s.session_id.startswith(session_id)]

        if not match:
            console.print(f"[red]No session found matching: {session_id}[/red]")
            raise SystemExit(1)

        if len(match) > 1:
            console.print(f"[yellow]Ambiguous ID — {len(match)} matches:[/yellow]")
            for s in match:
                console.print(f"  {s.session_id}")
            raise SystemExit(1)

        s = match[0]
        console.print(f"[bold]Session:[/bold] {s.session_id}")
        console.print(f"[bold]Provider:[/bold] {s.provider}")
        if s.title:
            console.print(f"[bold]Title:[/bold] {s.title}")
        if s.cwd:
            console.print(f"[bold]Directory:[/bold] {s.cwd}")
        if s.updated_at:
            console.print(f"[bold]Updated:[/bold] {s.updated_at}")

    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    finally:
        await engine.stop()


def _build_engine(
    provider: str, config_path: str, provider_explicit: bool
) -> AvatarEngine:
    """Build engine from CLI context."""
    if config_path:
        config = AvatarConfig.load(config_path)
        if provider_explicit:
            config.provider = ProviderType(provider)
        return AvatarEngine(config=config)
    return AvatarEngine(provider=provider)
