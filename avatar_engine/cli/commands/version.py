"""Version command."""

import asyncio
import click
from rich.console import Console
from rich.table import Table

from ... import __version__
from ...utils.version import check_cli_version

console = Console()


@click.command()
@click.option("--check-cli", is_flag=True, help="Also check CLI tool versions")
def version(check_cli: bool) -> None:
    """Show Avatar Engine version.

    Examples:

        avatar version

        avatar version --check-cli
    """
    console.print(f"[bold]Avatar Engine[/bold] v{__version__}")

    if check_cli:
        console.print()
        asyncio.run(_check_cli_versions())


async def _check_cli_versions() -> None:
    """Check versions of CLI tools."""
    table = Table(title="CLI Tools")
    table.add_column("Tool", style="cyan")
    table.add_column("Available")
    table.add_column("Version")

    # Check Claude CLI
    claude_info = await check_cli_version("claude")
    claude_avail = "[green]✓[/green]" if claude_info.available else "[red]✗[/red]"
    table.add_row("claude", claude_avail, claude_info.version or "-")

    # Check Gemini CLI
    gemini_info = await check_cli_version("gemini")
    gemini_avail = "[green]✓[/green]" if gemini_info.available else "[red]✗[/red]"
    table.add_row("gemini", gemini_avail, gemini_info.version or "-")

    console.print(table)
