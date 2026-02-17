"""Health check command."""

import asyncio

import click
from rich.console import Console
from rich.table import Table

from ...engine import AvatarEngine
from ...utils.version import check_cli_version
from ..app import provider_option

console = Console()


@click.command()
@provider_option
@click.option("--check-cli", is_flag=True, help="Check CLI tool versions")
@click.pass_context
def health(ctx: click.Context, provider: str, check_cli: bool) -> None:
    """Check system health and CLI availability.

    Examples:

        avatar health

        avatar health --check-cli

        avatar health -p claude
    """
    if not provider:
        provider = "gemini"
    if check_cli:
        asyncio.run(_check_cli_versions())
    else:
        asyncio.run(_check_bridge_health(provider, ctx.obj.get("config")))


async def _check_cli_versions() -> None:
    """Check versions of CLI tools."""
    table = Table(title="CLI Tools")
    table.add_column("Tool", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Version/Error")

    # Check Claude CLI
    claude_info = await check_cli_version("claude")
    claude_status = "[green]✓[/green]" if claude_info.available else "[red]✗[/red]"
    claude_detail = claude_info.version if claude_info.version else (claude_info.error or "not found")
    table.add_row("claude", claude_status, claude_detail)

    # Check Gemini CLI
    gemini_info = await check_cli_version("gemini")
    gemini_status = "[green]✓[/green]" if gemini_info.available else "[red]✗[/red]"
    gemini_detail = gemini_info.version if gemini_info.version else (gemini_info.error or "not found")
    table.add_row("gemini", gemini_status, gemini_detail)

    # Check Codex ACP (via npx)
    codex_info = await check_cli_version("npx")
    codex_status = "[green]✓[/green]" if codex_info.available else "[red]✗[/red]"
    codex_detail = "npx available (codex-acp)" if codex_info.available else "npx not found (install Node.js)"
    table.add_row("codex-acp", codex_status, codex_detail)

    console.print(table)


async def _check_bridge_health(provider: str, config_path: str) -> None:
    """Check bridge health status."""
    # Create engine
    if config_path:
        engine = AvatarEngine.from_config(config_path)
    else:
        engine = AvatarEngine(provider=provider)

    try:
        console.print(f"[dim]Starting {provider} bridge...[/dim]")
        await engine.start()

        health = engine.get_health()

        table = Table(title=f"Bridge Health ({provider})")
        table.add_column("Metric", style="cyan")
        table.add_column("Value")

        for key, value in health.__dict__.items():
            if key == "healthy":
                color = "green" if value else "red"
                table.add_row(key, f"[{color}]{value}[/{color}]")
            else:
                table.add_row(key, str(value))

        console.print(table)

        if health.healthy:
            console.print("[green]✓ Bridge is healthy[/green]")
        else:
            console.print("[red]✗ Bridge is unhealthy[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    finally:
        await engine.stop()
